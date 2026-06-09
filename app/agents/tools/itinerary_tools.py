"""Itinerary suggestion and management tools."""

from pydantic import BaseModel, Field

from ..services.itinerary_management import (
    create_or_update_itinerary_for_user,
    delete_itinerary_for_user,
    list_user_itineraries_for_user,
    manage_itinerary_status_for_user,
    suggest_itinerary_changes_for_user,
)
from ..tool_context import get_current_planner_user
from .common import planner_tool


class ExpenseDraft(BaseModel):
    expense_type: str = Field(description="One of meal, lodging, transport, ticket, shopping, or other.")
    amount: str | float = Field(description="Expense amount for this stop.")


class LocationDraft(BaseModel):
    location_id: int | None = Field(default=None, description="Existing location id when updating an itinerary.")
    name: str = Field(description="Place or activity name, such as Tokyo Tower or Senso-ji Temple.")
    travel_method: str = Field(default="walk", description="One of boat, plane, walk, car, hsr, train, or bus.")
    visit_date: str | None = Field(default=None, description="ISO datetime preferred (YYYY-MM-DDTHH:MM).")
    latitude: float | None = Field(default=None, description="Ignored by planner agent; coordinates are resolved via Nominatim.")
    longitude: float | None = Field(default=None, description="Ignored by planner agent; coordinates are resolved via Nominatim.")
    route_order: int | None = Field(default=None, description="Zero-based order in the route.")
    note: str = Field(default="", description="Short user-facing notes for this stop.")
    expenses: list[ExpenseDraft] = Field(default_factory=list, description="Optional expenses for this stop.")


class ItineraryDraftPayload(BaseModel):
    itinerary_id: int | None = Field(default=None, description="Existing itinerary id when updating.")
    title: str | None = Field(default=None, description="Itinerary title.")
    start_date: str | None = Field(default=None, description="Trip start date in YYYY-MM-DD format.")
    end_date: str | None = Field(default=None, description="Trip end date in YYYY-MM-DD format.")
    location: str | None = Field(default=None, description="Primary destination or country.")
    budget: str | float | None = Field(default=None, description="Total itinerary budget.")
    budget_currency: str | None = Field(default=None, description="Currency code such as TWD, USD, or JPY. Omit to infer from location.")
    description: str | None = Field(default=None, description="Short itinerary description.")
    is_public: bool | None = Field(default=None, description="Whether the itinerary is public.")
    status: str | None = Field(default=None, description="One of draft, ongoing, completed, or cancelled.")
    replace_locations: bool | None = Field(
        default=None,
        description="Set true only when you intentionally replace all existing locations.",
    )
    tags: list[str] = Field(default_factory=list, description="Tag names.")
    collaborators: list[str] = Field(default_factory=list, description="Collaborator usernames.")
    locations: list[LocationDraft] = Field(
        default_factory=list,
        description="Every planned place/activity to save as Location rows. Always include planned attractions here.",
    )


class CreateOrUpdateItineraryArgs(BaseModel):
    draft_payload: ItineraryDraftPayload = Field(
        description="Structured itinerary data. Put planned attractions in draft_payload.locations."
    )


@planner_tool
def list_user_itineraries(include_shared: bool = True, limit: int = 10) -> dict:
    """List the authenticated user's owned and shared itineraries for follow-up actions."""
    return list_user_itineraries_for_user(get_current_planner_user(), include_shared, limit)


@planner_tool
def suggest_itinerary_changes(itinerary_id: int | None = None, travel_goal: str = "") -> dict:
    """Suggest safe itinerary improvements without applying changes."""
    return suggest_itinerary_changes_for_user(get_current_planner_user(), itinerary_id, travel_goal)


@planner_tool(args_schema=CreateOrUpdateItineraryArgs)
def create_or_update_itinerary(draft_payload: dict | str | None = None) -> dict:
    """Create or update an itinerary; save each planned attraction in draft_payload.locations."""
    return create_or_update_itinerary_for_user(get_current_planner_user(), draft_payload)


@planner_tool
def manage_itinerary_status(itinerary_id: int | None = None, status: str = "") -> dict:
    """Update an editable itinerary to a valid status choice."""
    return manage_itinerary_status_for_user(get_current_planner_user(), itinerary_id, status)


@planner_tool
def delete_itinerary(itinerary_id: int | None = None) -> dict:
    """Delete an itinerary owned by the authenticated user."""
    return delete_itinerary_for_user(get_current_planner_user(), itinerary_id)


TOOLS = (
    list_user_itineraries,
    suggest_itinerary_changes,
    create_or_update_itinerary,
    manage_itinerary_status,
    delete_itinerary,
)
