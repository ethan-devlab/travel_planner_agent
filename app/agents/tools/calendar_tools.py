"""Calendar management tools."""

import datetime as dt
import json
import logging
import uuid

from django.db import transaction
from pydantic import BaseModel, Field

from app.models import Event

from ..tool_context import get_current_planner_user
from .common import planner_tool

logger = logging.getLogger(__name__)

ALLOWED_EVENT_COLORS = {"orange", "blue", "yellow", "green"}


class CalendarEventPayload(BaseModel):
    eventName: str = Field(default="", description="Short event name.")
    date: str = Field(default="", description="Event date in YYYY-MM-DD format.")
    color: str = Field(default="", description="One of orange, blue, yellow, or green.")


class CreateCalendarEventArgs(BaseModel):
    event_payload: CalendarEventPayload | dict | str | None = Field(
        default=None,
        description="Calendar event payload with eventName, date, and color.",
    )


@planner_tool
def list_calendar_events(start_date="", end_date=""):
    """List calendar events for the authenticated user."""
    tool_name = "list_calendar_events"
    user = get_current_planner_user()
    auth_error = _require_authenticated_user(user, tool_name)
    if auth_error:
        return auth_error

    start_value, start_error = _parse_optional_date(start_date)
    end_value, end_error = _parse_optional_date(end_date)
    if start_error or end_error:
        logger.warning("calendar tool %s rejected invalid list range.", tool_name)
        return _error(tool_name, "invalid_date", "start_date and end_date must be YYYY-MM-DD when provided.")
    if start_value and end_value and start_value > end_value:
        return _error(tool_name, "invalid_date_range", "start_date must be on or before end_date.")

    queryset = Event.objects.filter(owner=user).order_by("date", "id")
    if start_value:
        queryset = queryset.filter(date__gte=start_value)
    if end_value:
        queryset = queryset.filter(date__lte=end_value)

    events = [
        {
            "id": str(event.id),
            "eventName": event.event_name,
            "date": event.date.isoformat(),
            "color": event.color,
            "calendar": event.color,
        }
        for event in queryset
    ]
    logger.info(
        "calendar tool %s returned %s events for user %s with range start=%s end=%s.",
        tool_name,
        len(events),
        user.id,
        bool(start_value),
        bool(end_value),
    )
    return {
        "status": "ok",
        "tool": tool_name,
        "requested_inputs": {
            "start_date": str(start_date or ""),
            "end_date": str(end_date or ""),
        },
        "normalized_values": {
            "start_date": start_value.isoformat() if start_value else "",
            "end_date": end_value.isoformat() if end_value else "",
        },
        "count": len(events),
        "events": events,
    }


@planner_tool(args_schema=CreateCalendarEventArgs)
def create_calendar_event(event_payload=None):
    """Create a calendar event for the authenticated user."""
    tool_name = "create_calendar_event"
    user = get_current_planner_user()
    auth_error = _require_authenticated_user(user, tool_name)
    if auth_error:
        return auth_error

    payload, error = _coerce_payload(event_payload, tool_name)
    if error:
        return error

    event_name = str(payload.get("eventName") or "").strip()
    event_date, date_error = _parse_required_date(payload.get("date"))
    color = str(payload.get("color") or "").strip().lower()

    if not event_name:
        return _error(tool_name, "invalid_event_name", "eventName cannot be blank.")
    if date_error:
        logger.warning("calendar tool %s rejected invalid create date for user %s.", tool_name, user.id)
        return _error(tool_name, "invalid_date", "date must be YYYY-MM-DD.")
    if color not in ALLOWED_EVENT_COLORS:
        logger.warning("calendar tool %s rejected invalid color for user %s.", tool_name, user.id)
        return _error(tool_name, "invalid_color", "color must be one of orange, blue, yellow, or green.")

    with transaction.atomic():
        event = Event.objects.create(owner=user, event_name=event_name, date=event_date, color=color)

    logger.info("calendar tool %s created event %s for user %s.", tool_name, event.id, user.id)
    return {
        "status": "ok",
        "tool": tool_name,
        "event": {
            "id": str(event.id),
            "eventName": event.event_name,
            "date": event.date.isoformat(),
            "color": event.color,
            "calendar": event.color,
        },
    }


@planner_tool
def delete_calendar_event(event_id=None):
    """Delete a calendar event owned by the authenticated user."""
    tool_name = "delete_calendar_event"
    user = get_current_planner_user()
    auth_error = _require_authenticated_user(user, tool_name)
    if auth_error:
        return auth_error

    event_pk, id_error = _parse_uuid(event_id)
    if id_error:
        return _error(tool_name, "invalid_event_id", "event_id must be a valid UUID.")

    event = Event.objects.filter(owner=user, pk=event_pk).first()
    if event is None:
        logger.warning("calendar tool %s denied delete for event %s and user %s.", tool_name, event_pk, user.id)
        return _error(tool_name, "event_not_found", "No owned event was found.")

    with transaction.atomic():
        event.delete()

    logger.info("calendar tool %s deleted event %s for user %s.", tool_name, event_pk, user.id)
    return {
        "status": "ok",
        "tool": tool_name,
        "event_id": str(event_pk),
        "action": "deleted",
    }


def _parse_uuid(value):
    try:
        return uuid.UUID(str(value)), None
    except (TypeError, ValueError, AttributeError):
        return None, "invalid_uuid"


def _require_authenticated_user(user, tool_name):
    if user is None or not getattr(user, "is_authenticated", False):
        logger.warning("calendar tool %s rejected unauthenticated access.", tool_name)
        return _error(tool_name, "authentication_required", "Sign in before using calendar tools.")
    return None


def _coerce_payload(raw_payload, tool_name):
    if raw_payload is None:
        return None, _error(tool_name, "missing_payload", "event_payload is required.")
    if hasattr(raw_payload, "model_dump"):
        raw_payload = raw_payload.model_dump(exclude_none=True)
    if isinstance(raw_payload, str):
        try:
            raw_payload = json.loads(raw_payload)
        except json.JSONDecodeError:
            return None, _error(tool_name, "invalid_payload", "event_payload must be a JSON object.")
    if not isinstance(raw_payload, dict):
        return None, _error(tool_name, "invalid_payload", "event_payload must be an object.")
    return raw_payload, None


def _parse_optional_date(value):
    value = str(value or "").strip()
    if not value:
        return None, None
    try:
        return dt.date.fromisoformat(value), None
    except ValueError:
        return None, "invalid_date"


def _parse_required_date(value):
    value = str(value or "").strip()
    if not value:
        return None, "invalid_date"
    try:
        return dt.date.fromisoformat(value), None
    except ValueError:
        return None, "invalid_date"


def _error(tool_name, error_code, message):
    return {
        "status": "error",
        "tool": tool_name,
        "error_code": error_code,
        "message": message,
    }


TOOLS = (
    list_calendar_events,
    create_calendar_event,
    delete_calendar_event,
)
