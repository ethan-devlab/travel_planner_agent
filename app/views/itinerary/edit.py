# coding=utf-8

import json
import logging
import re

from ...forms import ItineraryForm
from ...budget_currency import resolve_budget_currency
from ...models import Itinerary
from ...agents.planner_agent import (
    PlannerAgentConfigurationError,
    build_openai_chat_model,
    build_planner_agent,
)
from ...agents.tool_context import planner_tool_user
from ..planner_agent.planner_agent import (
    CONFIGURATION_ERROR_RESPONSE,
    EXECUTION_ERROR_RESPONSE,
    _agent_messages,
    _extract_response_card,
)
from .location_form import save_locations_from_post
from .persistence import save_itinerary_relations_from_post
from .route_helpers import routing_context
from django.db import transaction
from django.shortcuts import render, get_object_or_404, redirect
from django.contrib.auth.decorators import login_required
from django.views.decorators.http import require_http_methods, require_POST
from django.http import HttpResponseForbidden, JsonResponse
from django.contrib import messages


logger = logging.getLogger(__name__)

AI_ITINERARY_CHECK_FOCUS = {
    "overall": "overall itinerary structure, timing, route, budget, and practical next actions",
    "stops": "saved stops, visit times, missing stop details, and whether the stop plan is practical",
    "route": "route order, route coordinates, travel methods, and route feasibility between saved stops",
    "budget": "budget, recorded expenses, expense coverage, and whether the trip is at risk of going over budget",
}
COUNTRY_CONSISTENCY_CHECK_TYPES = {"overall", "stops"}
COUNTRY_KEYWORD_MAPPING = (
    ("日本", ("日本", "東京", "大阪", "京都", "奈良", "神戶", "北海道", "沖繩", "名古屋", "福岡", "札幌", "淺草", "東京鐵塔")),
    ("韓國", ("韓國", "首爾", "釜山", "濟州", "明洞", "弘大", "首爾塔")),
    ("台灣", ("台灣", "臺灣", "台北", "臺北", "高雄", "台中", "臺中", "台南", "臺南", "花蓮", "宜蘭")),
    ("泰國", ("泰國", "曼谷", "清邁", "普吉")),
    ("美國", ("美國", "紐約", "洛杉磯", "舊金山", "拉斯維加斯", "西雅圖")),
    ("法國", ("法國", "巴黎", "艾菲爾鐵塔", "羅浮宮")),
    ("英國", ("英國", "倫敦", "大英博物館")),
    ("義大利", ("義大利", "羅馬", "米蘭", "威尼斯", "佛羅倫斯")),
)
AI_CHECK_TEXT_REPLACEMENTS = (
    ("country_mismatch", "國家不一致"),
    ("country_unknown", "主要國家無法判斷"),
    ("country_consistent", "國家一致"),
    ("risk_code", "風險類型"),
    ("error_code", "錯誤類型"),
    ("review_summary", "檢查摘要"),
    ("location_name", "停點名稱"),
    ("expected_country", "預期國家"),
    ("detected_country", "判斷國家"),
    ("visit_date", "造訪日期"),
    ("visit date", "造訪日期"),
    ("Itinerary", "行程"),
    ("draft", "草稿"),
)
AI_CHECK_INTERNAL_ID_PATTERNS = (
    re.compile(r"\bitinerary[_\s-]*id\s*(?:[:=]\s*)?\d+\b", re.IGNORECASE),
    re.compile(r"\bitinerary[_\s-]*id\b", re.IGNORECASE),
    re.compile(r"\bdatabase\s+id\s*(?:[:=]\s*)?\d+\b", re.IGNORECASE),
    re.compile(r"\binternal\s+id\s*(?:[:=]\s*)?\d+\b", re.IGNORECASE),
    re.compile(r"\bid\s*=\s*\d+\b", re.IGNORECASE),
    re.compile(r"資料庫\s*id\s*(?:[:=：]\s*)?\d+", re.IGNORECASE),
)


def _can_edit_itinerary(itinerary, user):
    return itinerary.owner_id == user.id or itinerary.collaborators.filter(pk=user.pk).exists()


@login_required
@require_http_methods(["GET", "POST"])
def edit_itinerary(request, id):
    itinerary = get_object_or_404(Itinerary, pk=id)
    if not _can_edit_itinerary(itinerary, request.user):
        return HttpResponseForbidden("You do not have permission to edit this itinerary.")

    locations = itinerary.locations.all()

    if request.method == 'POST':
        form = ItineraryForm(request.POST, instance=itinerary)
        if form.is_valid():
            with transaction.atomic():
                itinerary = form.save(commit=False)
                itinerary.budget_currency = resolve_budget_currency(
                    itinerary.location,
                    form.cleaned_data.get("budget_currency_choice"),
                    fallback=itinerary.budget_currency,
                )
                itinerary.save()
                save_itinerary_relations_from_post(itinerary, request.POST, request)
                save_locations_from_post(itinerary, request.POST, clear_existing=True)

            messages.success(request, f'行程 「{itinerary.title}」 已成功更新！')
            return redirect(request.path)
    else:
        initial = {
            'custom_tags': ', '.join([t.name for t in itinerary.tags.all()]),
            'collaborators': ', '.join([c.username for c in itinerary.collaborators.all()])
        }
        form = ItineraryForm(instance=itinerary, initial=initial)

    context = {
        'form': form,
        'locations': locations,
        'itinerary': itinerary,
    }
    context.update(routing_context())
    return render(request, 'itinerary/edit_itinerary.html', context)


@login_required
@require_POST
def ai_itinerary_check(request, id):
    itinerary = get_object_or_404(Itinerary, pk=id)
    if not _can_edit_itinerary(itinerary, request.user):
        logger.warning("AI itinerary check denied for itinerary %s and user %s.", itinerary.id, request.user.id)
        return JsonResponse({
            "success": False,
            "error": "permission_denied",
            "message": "You do not have permission to review this itinerary.",
        }, status=403)

    try:
        payload = json.loads(request.body.decode("utf-8") or "{}")
    except json.JSONDecodeError:
        return JsonResponse({
            "success": False,
            "error": "invalid_json",
            "message": "Request body must be valid JSON.",
        }, status=400)

    check_type = str(payload.get("check_type") or "").strip()
    if check_type not in AI_ITINERARY_CHECK_FOCUS:
        return JsonResponse({
            "success": False,
            "error": "invalid_check_type",
            "message": "check_type must be one of: overall, stops, route, budget.",
        }, status=400)

    locations = list(itinerary.locations.all())
    country_findings = []
    if check_type in COUNTRY_CONSISTENCY_CHECK_TYPES:
        country_findings = _country_consistency_findings(itinerary, locations)

    focus = AI_ITINERARY_CHECK_FOCUS[check_type]
    prompt = (
        f"Review itinerary_id={itinerary.id} using review_itinerary_on_request. "
        f"Focus on {focus}. "
        "Do not ask for confirmation, do not modify the itinerary, and do not use unsaved form data. "
        "itinerary_id 只供工具內部查詢使用，請不要在回覆中顯示 itinerary_id、資料庫 id、"
        "內部欄位名稱或技術細節。請使用行程標題、目的地、日期與停點名稱來描述。 "
        f"{_country_consistency_prompt_section(country_findings)} "
        "Return a concise structured review with summary, actions, key_data, and next_steps."
    )

    try:
        logger.info(
            "AI itinerary check requested for itinerary %s by user %s with check type %s.",
            itinerary.id,
            request.user.id,
            check_type,
        )
        model = build_openai_chat_model()
        agent = build_planner_agent(model)
        with planner_tool_user(request.user):
            result = agent.invoke({"messages": _agent_messages(prompt, [])})
    except PlannerAgentConfigurationError:
        logger.warning("AI itinerary check configuration error for itinerary %s.", itinerary.id)
        return JsonResponse({
            "success": False,
            "message": CONFIGURATION_ERROR_RESPONSE,
        })
    except Exception:
        logger.exception("AI itinerary check failed for itinerary %s.", itinerary.id)
        return JsonResponse({
            "success": False,
            "message": EXECUTION_ERROR_RESPONSE,
        })

    card = _clean_ai_check_card(_extract_response_card(result))
    return JsonResponse({
        "success": True,
        "check_type": check_type,
        "summary": card["summary"],
        "actions": card["actions"],
        "key_data": card["key_data"],
        "next_steps": card["next_steps"],
    })


def _country_consistency_findings(itinerary, locations):
    expected_country = _detect_country_from_text(itinerary.location) or _detect_country_from_text(itinerary.title)
    if not expected_country:
        return [{
            "type": "country_unknown",
            "message": "無法判斷主要國家，請確認行程地點或標題是否有清楚標示目的地國家。",
        }]

    findings = []
    for location in locations:
        detected_country = _detect_country_from_text(location.name)
        if not detected_country or detected_country == expected_country:
            continue
        findings.append({
            "type": "country_mismatch",
            "location_name": location.name,
            "expected_country": expected_country,
            "detected_country": detected_country,
            "message": f"「{location.name}」看起來位於{detected_country}，可能與行程國家「{expected_country}」不一致。",
        })
    if not findings:
        findings.append({
            "type": "country_consistent",
            "expected_country": expected_country,
            "message": "目前未發現標題、目的地與停點名稱有明顯國家不一致。",
        })
    return findings


def _detect_country_from_text(text):
    normalized_text = str(text or "").strip()
    if not normalized_text:
        return None

    for country, keywords in COUNTRY_KEYWORD_MAPPING:
        if any(keyword in normalized_text for keyword in keywords):
            return country
    return None


def _country_consistency_prompt_section(findings):
    if not findings:
        return ""

    findings_text = json.dumps(findings, ensure_ascii=False)
    return (
        "以下是系統先做的國家一致性檢查結果，請把它納入回覆："
        f"{findings_text} "
        "如果有 country_mismatch，請在 actions 或 next_steps 提醒使用者確認該停點是否真的屬於本次行程；"
        "如果是跨國行程，建議使用者在行程描述或標題中明確標示。"
    )


def _clean_ai_check_card(card):
    return {
        "summary": _clean_ai_check_text(card.get("summary")),
        "actions": [_clean_ai_check_text(action) for action in card.get("actions", [])],
        "key_data": [_clean_ai_check_key_data(item) for item in card.get("key_data", [])],
        "next_steps": [_clean_ai_check_text(step) for step in card.get("next_steps", [])],
    }


def _clean_ai_check_key_data(item):
    label = _clean_ai_check_text(item.get("label"))
    value = _clean_ai_check_text(item.get("value"))
    if _looks_like_internal_id_label(label) and re.fullmatch(r"\d+", value or ""):
        value = "目前行程"
    return {
        "label": label,
        "value": value,
    }


def _clean_ai_check_text(value):
    text = str(value or "").strip()
    if not text:
        return ""

    for pattern in AI_CHECK_INTERNAL_ID_PATTERNS:
        text = pattern.sub("目前行程", text)
    for source, replacement in AI_CHECK_TEXT_REPLACEMENTS:
        text = re.sub(re.escape(source), replacement, text, flags=re.IGNORECASE)
    return re.sub(r"\s{2,}", " ", text).strip()


def _looks_like_internal_id_label(label):
    normalized = str(label or "").lower()
    return (
        "id" in normalized
        or "itinerary" in normalized
        or "資料庫" in normalized
        or "內部" in normalized
    )
