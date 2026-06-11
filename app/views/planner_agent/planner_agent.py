import json
import logging

from django.contrib.auth.decorators import login_required
from django.http import HttpResponseBadRequest, JsonResponse, StreamingHttpResponse
from django.shortcuts import render
from django.views.decorators.http import require_http_methods, require_POST

from ...demo import consume_demo_ai_quota
from ...agents.planner_agent import (
    PlannerAgentConfigurationError,
    build_openai_chat_model,
    build_planner_agent,
)
from ...agents.tool_context import planner_tool_user

try:
    from langchain_core.messages import AIMessage, AIMessageChunk
except ImportError:
    AIMessage = None
    AIMessageChunk = None

logger = logging.getLogger(__name__)

PLANNER_CAPABILITIES = (
    {
        "icon": "ri-route-line",
        "title": "行程規劃",
        "description": "把目的地、日期、預算和停留地點整理成可執行的旅行安排。",
    },
    {
        "icon": "ri-search-eye-line",
        "title": "細節檢查",
        "description": "幫你看路線、時間和預算是否順得下來，提醒你需要補的資料。",
    },
    {
        "icon": "ri-cloud-windy-line",
        "title": "天氣與匯率",
        "description": "出發前快速確認天氣和匯率，方便你決定要帶什麼、怎麼花。",
    },
    {
        "icon": "ri-compass-3-line",
        "title": "行程靈感",
        "description": "看看公開行程的安排方式，快速找到適合自己的旅行方向。",
    },
    {
        "icon": "ri-calendar-2-line",
        "title": "行事曆整理",
        "description": "把行程事件整理到行事曆，方便你追蹤每天要做什麼。",
    },
)
CONFIGURATION_ERROR_RESPONSE = "規劃助手目前尚未完成設定，請稍後再試或聯絡管理員。"
EXECUTION_ERROR_RESPONSE = "規劃助手暫時無法安全完成這次需求，請稍後再試。"
PLANNER_HISTORY_SESSION_KEY = "planner_agent_history"
MAX_PLANNER_HISTORY_ROUNDS = 5
DEFAULT_STRUCTURED_SUMMARY = "我已幫你整理好了。"
DEFAULT_FALLBACK_SUMMARY = "我先幫你整理成可讀的重點。"


@login_required
@require_http_methods(["GET", "POST"])
def planner_agent_view(request):
    prompt = ""
    agent_response = ""
    chat_history = _planner_history(request)

    if request.method == "POST":
        prompt = request.POST.get("prompt", "").strip()
        if prompt:
            logger.info("Planner agent received prompt with %s characters.", len(prompt))
            quota_result = consume_demo_ai_quota(request.user)
            if quota_result.allowed:
                agent_response = _run_planner_agent(prompt, request.user, chat_history)
            else:
                agent_response = quota_result.message
                logger.warning("Planner agent rejected demo prompt due to %s.", quota_result.error_code)
            chat_history = _append_planner_history(request, prompt, agent_response)

    return render(request, "planner_agent/index.html", {
        "planner_capabilities": PLANNER_CAPABILITIES,
        "submitted_prompt": prompt,
        "agent_response": agent_response,
        "chat_history": chat_history,
    })


@login_required
@require_POST
def planner_agent_stream_view(request):
    prompt = request.POST.get("prompt", "").strip()
    if not prompt:
        return HttpResponseBadRequest("Prompt is required.")

    quota_result = consume_demo_ai_quota(request.user)
    if not quota_result.allowed:
        logger.warning("Planner agent stream rejected demo prompt due to %s.", quota_result.error_code)
        response = JsonResponse({
            "success": False,
            "error": quota_result.error_code,
            "message": quota_result.message,
        }, status=quota_result.status_code)
        if quota_result.retry_after:
            response["Retry-After"] = str(quota_result.retry_after)
        return response

    chat_history = _planner_history(request)
    logger.info("Planner agent stream received prompt with %s characters.", len(prompt))
    response = StreamingHttpResponse(
        _stream_planner_agent(prompt, request.user, chat_history, request),
        content_type="text/event-stream; charset=utf-8",
    )
    response["Cache-Control"] = "no-cache"
    response["X-Accel-Buffering"] = "no"
    return response


def _run_planner_agent(prompt, user, chat_history=None):
    try:
        model = build_openai_chat_model()
        agent = build_planner_agent(model)
        with planner_tool_user(user):
            result = agent.invoke({"messages": _agent_messages(prompt, chat_history)})
    except PlannerAgentConfigurationError:
        logger.warning("Planner agent configuration error for prompt length %s.", len(prompt))
        return CONFIGURATION_ERROR_RESPONSE
    except Exception as exc:
        logger.error(
            "Planner agent execution failed for prompt length %s with %s.",
            len(prompt),
            exc.__class__.__name__,
        )
        return EXECUTION_ERROR_RESPONSE

    return _history_text_from_card(_extract_response_card(result))


def _stream_planner_agent(prompt, user, chat_history, request):
    streamed_parts = []
    completed_response = ""
    structured_card = None
    try:
        model = build_openai_chat_model()
        agent = build_planner_agent(model)
        with planner_tool_user(user):
            for chunk in agent.stream(
                {"messages": _agent_messages(prompt, chat_history)},
                stream_mode=["messages", "updates"],
                version="v2",
            ):
                token_text = _stream_chunk_text(chunk)
                if token_text:
                    streamed_parts.append(token_text)
                    yield _sse_event("token", token_text)

                card_from_chunk = _structured_response_from_stream_chunk(chunk)
                if card_from_chunk:
                    structured_card = card_from_chunk

                completed_text = _completed_response_from_stream_chunk(chunk)
                if completed_text:
                    completed_response = completed_text
    except PlannerAgentConfigurationError:
        logger.warning("Planner agent stream configuration error for prompt length %s.", len(prompt))
        structured_card = _fallback_response_card(CONFIGURATION_ERROR_RESPONSE)
    except Exception as exc:
        logger.error(
            "Planner agent stream failed for prompt length %s with %s.",
            len(prompt),
            exc.__class__.__name__,
        )
        structured_card = _fallback_response_card(EXECUTION_ERROR_RESPONSE)

    if not structured_card:
        fallback_summary = _strip_leading_tool_json(
            completed_response or "".join(streamed_parts) or DEFAULT_FALLBACK_SUMMARY
        )
        structured_card = _fallback_response_card(fallback_summary)
        logger.info("Planner agent stream used fallback card for prompt length %s.", len(prompt))

    _append_planner_history(request, prompt, _history_text_from_card(structured_card), save=True)
    yield _sse_event("result", structured_card)
    yield _sse_event("done", None)


def _agent_messages(prompt, chat_history=None):
    messages = []
    for round_data in chat_history or []:
        user_message = str(round_data.get("user") or "").strip()
        assistant_message = str(round_data.get("assistant") or "").strip()
        if user_message:
            messages.append({"role": "user", "content": user_message})
        if assistant_message:
            messages.append({"role": "assistant", "content": assistant_message})
    messages.append({"role": "user", "content": prompt})
    return messages


def _planner_history(request):
    history = request.session.get(PLANNER_HISTORY_SESSION_KEY, [])
    if not isinstance(history, list):
        return []
    return [
        {
            "user": str(item.get("user") or ""),
            "assistant": _strip_leading_tool_json(str(item.get("assistant") or "")),
        }
        for item in history
        if isinstance(item, dict)
    ][-MAX_PLANNER_HISTORY_ROUNDS:]


def _append_planner_history(request, prompt, agent_response, save=False):
    history = _planner_history(request)
    history.append({"user": prompt, "assistant": agent_response})
    history = history[-MAX_PLANNER_HISTORY_ROUNDS:]
    request.session[PLANNER_HISTORY_SESSION_KEY] = history
    request.session.modified = True
    if save:
        request.session.save()
    return history


def _extract_response_card(result):
    if isinstance(result, dict):
        card_from_key = _structured_response_from_any(result.get("structured_response"))
        if card_from_key:
            return card_from_key

    direct_card = _structured_response_from_any(result)
    if direct_card:
        return direct_card

    if isinstance(result, str):
        return _fallback_response_card(result)

    if isinstance(result, dict):
        for key in ("output", "result", "response"):
            if not result.get(key):
                continue
            card = _structured_response_from_any(result[key])
            if card:
                return card
            return _fallback_response_card(_strip_leading_tool_json(_content_to_text(result[key])))

        messages = result.get("messages") or []
        final_message = _final_ai_message(messages)
        if final_message:
            return _fallback_response_card(_strip_leading_tool_json(_content_to_text(_message_content(final_message))))

    return _fallback_response_card(_strip_leading_tool_json(_content_to_text(result) or DEFAULT_FALLBACK_SUMMARY))


def _structured_response_from_stream_chunk(chunk):
    if not isinstance(chunk, dict) or chunk.get("type") != "updates":
        return None

    for source, update in (chunk.get("data") or {}).items():
        if source != "model" or not isinstance(update, dict):
            continue
        card = _structured_response_from_any(update.get("structured_response"))
        if card:
            return card
    return None


def _structured_response_from_any(raw):
    if raw is None:
        return None

    if hasattr(raw, "model_dump"):
        raw = raw.model_dump()
    elif hasattr(raw, "dict") and callable(raw.dict):
        raw = raw.dict()

    if not isinstance(raw, dict):
        return None

    summary = _safe_text(raw.get("summary"))
    actions = _safe_text_list(raw.get("actions"))
    key_data = _safe_key_data(raw.get("key_data"))
    next_steps = _safe_text_list(raw.get("next_steps"))

    if not summary and not actions and not key_data and not next_steps:
        return None

    return {
        "summary": summary or DEFAULT_STRUCTURED_SUMMARY,
        "actions": actions,
        "key_data": key_data,
        "next_steps": next_steps,
    }


def _safe_text(value):
    if value is None:
        return ""
    return str(value).strip()


def _safe_text_list(values):
    if not isinstance(values, (list, tuple)):
        return []

    cleaned = []
    for value in values:
        text = _safe_text(value)
        if text:
            cleaned.append(text)
    return cleaned


def _safe_key_data(values):
    if not isinstance(values, (list, tuple)):
        return []

    cleaned = []
    for item in values:
        if hasattr(item, "model_dump"):
            item = item.model_dump()
        elif hasattr(item, "dict") and callable(item.dict):
            item = item.dict()
        if not isinstance(item, dict):
            continue

        label = _safe_text(item.get("label"))
        value = _safe_text(item.get("value"))
        if not label or not value:
            continue
        cleaned.append({
            "label": label,
            "value": value,
        })
    return cleaned


def _fallback_response_card(summary):
    clean_summary = _safe_text(summary) or DEFAULT_STRUCTURED_SUMMARY
    return {
        "summary": clean_summary,
        "actions": [],
        "key_data": [],
        "next_steps": [],
    }


def _history_text_from_card(card):
    if not isinstance(card, dict):
        return DEFAULT_STRUCTURED_SUMMARY
    return _safe_text(card.get("summary")) or DEFAULT_STRUCTURED_SUMMARY


def _final_ai_message(messages):
    for message in reversed(messages):
        if AIMessage is not None and isinstance(message, AIMessage):
            if getattr(message, "tool_calls", None):
                continue
            if _content_to_text(_message_content(message)):
                return message
        elif isinstance(message, dict) and message.get("type") in {"ai", "AIMessage"}:
            if message.get("tool_calls"):
                continue
            if _content_to_text(message.get("content")):
                return message
        elif isinstance(message, dict) and message.get("content") and not message.get("tool_call_id"):
            if message.get("tool_calls"):
                continue
            return message
    return None


def _message_content(message):
    if isinstance(message, dict):
        return message.get("content", "")
    return getattr(message, "content", "")


def _stream_chunk_text(chunk):
    if isinstance(chunk, dict):
        if chunk.get("type") == "messages":
            data = chunk.get("data") or ()
            token = data[0] if data else None
            return _token_text(token)
        return ""

    if isinstance(chunk, tuple) and chunk:
        return _token_text(chunk[0])

    return _token_text(chunk)


def _completed_response_from_stream_chunk(chunk):
    if not isinstance(chunk, dict) or chunk.get("type") != "updates":
        return ""

    for source, update in (chunk.get("data") or {}).items():
        if source != "model":
            continue
        messages = update.get("messages") if isinstance(update, dict) else None
        if messages:
            final_message = _final_ai_message(messages)
            text = _content_to_text(_message_content(final_message)) if final_message else ""
            if text:
                return text
    return ""


def _token_text(token):
    if token is None:
        return ""
    if AIMessageChunk is not None and not isinstance(token, AIMessageChunk):
        return ""
    if getattr(token, "tool_call_chunks", None):
        return ""
    content = getattr(token, "content", "")
    if content:
        return _content_to_text(content)
    text = getattr(token, "text", None)
    if callable(text):
        return ""
    if text:
        return str(text)
    return _content_to_text(getattr(token, "content", token))


def _content_to_text(content):
    if content is None:
        return ""
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts = []
        for item in content:
            if isinstance(item, dict):
                parts.append(str(item.get("text") or item.get("content") or ""))
            else:
                parts.append(str(item))
        return "\n".join(part for part in parts if part)
    return str(content)


def _sse_event(event_name, payload):
    return f"event: {event_name}\ndata: {json.dumps(payload, ensure_ascii=False)}\n\n"


def _strip_leading_tool_json(text):
    value = str(text or "").strip()
    if not value or value[0] not in "[{":
        return value

    try:
        _, end_index = json.JSONDecoder().raw_decode(value)
    except json.JSONDecodeError:
        return value

    visible_text = value[end_index:].strip()
    if visible_text:
        return visible_text
    return "已完成工具操作。"
