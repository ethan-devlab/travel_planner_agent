"""Calendar management tool stubs."""

from .common import not_implemented_response


def list_calendar_events(start_date="", end_date=""):
    """List user calendar events after implementation."""
    return not_implemented_response("list_calendar_events", "calendar listing")


def create_calendar_event(event_payload=None):
    """Create a user calendar event after implementation."""
    return not_implemented_response("create_calendar_event", "calendar creation")


def delete_calendar_event(event_id=None):
    """Delete a user calendar event after implementation."""
    return not_implemented_response("delete_calendar_event", "calendar deletion")


TOOLS = (
    list_calendar_events,
    create_calendar_event,
    delete_calendar_event,
)

