# coding=utf-8

import json
import logging

from ...forms import ItineraryForm
from ...demo import consume_demo_ai_quota, is_demo_user
from ...utils.budget_currency import resolve_budget_currency
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
AI_ITINERARY_CHECK_EVIDENCE_INSTRUCTIONS = {
    "overall": "Use the computed routes, route-order analysis, and location geographies as evidence.",
    "stops": (
        "Use location geographies as evidence. Route and route-order analyses were intentionally not requested "
        "for this stop check. Do not describe route evidence as unavailable, failed, or missing, and do not make "
        "claims about route order or transport connections."
    ),
    "route": "Use the computed routes and route-order analysis as evidence.",
    "budget": (
        "Use saved budget and expense facts as evidence. Route, route-order, and geography analyses were "
        "intentionally not requested for this budget check."
    ),
}
AI_CHECK_DATA_SOURCES = {
    "route": [{
        "provider": "OSRM",
        "label": "路線資料：OSRM / © OpenStreetMap contributors",
        "url": "https://www.openstreetmap.org/copyright",
    }],
    "stops": [{
        "provider": "Nominatim",
        "label": "地理資料：Nominatim / © OpenStreetMap contributors",
        "url": "https://www.openstreetmap.org/copyright",
    }],
    "budget": [],
}
AI_CHECK_DATA_SOURCES["overall"] = AI_CHECK_DATA_SOURCES["route"] + AI_CHECK_DATA_SOURCES["stops"]


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
                if is_demo_user(request.user):
                    itinerary.is_public = False
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

    quota_result = consume_demo_ai_quota(request.user)
    if not quota_result.allowed:
        return JsonResponse({
            "success": False,
            "error": quota_result.error_code,
            "message": quota_result.message,
        }, status=quota_result.status_code)

    focus = AI_ITINERARY_CHECK_FOCUS[check_type]
    evidence_instructions = AI_ITINERARY_CHECK_EVIDENCE_INSTRUCTIONS[check_type]
    route_instructions = ""
    if check_type in {"overall", "route"}:
        route_instructions = (
            "Never use the term 路線腿; call each calculated connection 路線. "
            "When route-order analysis is not_applicable, explain its reason field in user-friendly Traditional Chinese. "
        )
    prompt = (
        f"Review itinerary_id={itinerary.id} using review_itinerary_on_request with check_type={check_type}. "
        f"Focus on {focus}. "
        "Do not ask for confirmation, do not modify the itinerary, and do not use unsaved form data. "
        f"{evidence_instructions} "
        f"{route_instructions}"
        "Include relevant distance/time or city/country facts in key_data and clearly label unavailable checks. "
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

    card = _extract_response_card(result)
    return JsonResponse({
        "success": True,
        "check_type": check_type,
        "summary": card["summary"],
        "actions": card["actions"],
        "key_data": card["key_data"],
        "next_steps": card["next_steps"],
        "data_sources": AI_CHECK_DATA_SOURCES[check_type],
    })
