"""Public itinerary lookup tools."""

import logging
from decimal import Decimal, InvalidOperation

from django.db import transaction
from django.db.models import Q
from pydantic import BaseModel, Field

from app.models import Expense, Itinerary, Location, Status

from ..tool_context import get_current_planner_user
from .common import planner_tool

logger = logging.getLogger(__name__)


class CopyPublicItineraryArgs(BaseModel):
    public_itinerary_id: int = Field(description="The id of the public itinerary to copy into the current user's items.")


@planner_tool
def search_public_itineraries(query="", location="", budget=None):
    """Search public itineraries after implementation."""
    tool_name = "search_public_itineraries"
    normalized_query = str(query or "").strip()
    normalized_location = str(location or "").strip()
    max_budget, budget_error = _parse_budget(budget)
    if budget_error:
        logger.warning("public-itinerary lookup tool %s rejected invalid budget filter.", tool_name)
        return _error(tool_name, "invalid_budget", "budget must be a non-negative number when provided.")

    itineraries = Itinerary.objects.filter(is_public=True)
    if normalized_query:
        itineraries = itineraries.filter(title__icontains=normalized_query)
    if normalized_location:
        itineraries = itineraries.filter(
            Q(location__icontains=normalized_location)
            | Q(title__icontains=normalized_location)
            | Q(locations__name__icontains=normalized_location)
        )
    if max_budget is not None:
        itineraries = itineraries.filter(budget__lte=max_budget)

    itineraries = (
        itineraries.distinct()
        .prefetch_related("tags", "locations")
        .order_by("-updated_at", "id")[:10]
    )
    results = [_public_itinerary_summary(itinerary) for itinerary in itineraries]
    logger.info(
        "public-itinerary lookup tool %s returned %s public itineraries for query length %s, location length %s, budget provided=%s.",
        tool_name,
        len(results),
        len(normalized_query),
        len(normalized_location),
        max_budget is not None,
    )
    return {
        "status": "ok",
        "tool": tool_name,
        "filters": {
            "query": normalized_query,
            "location": normalized_location,
            "max_budget": str(max_budget) if max_budget is not None else "",
        },
        "count": len(results),
        "itineraries": results,
    }


@planner_tool(args_schema=CopyPublicItineraryArgs)
def copy_public_itinerary_to_my_items(public_itinerary_id: int) -> dict:
    """Copy a public itinerary into the authenticated user's private items.

    Use this tool when the user asks to add a public itinerary to my items, apply
    it to my itinerary, copy a public itinerary, or add it to my itinerary. If the
    user only gives a name and multiple public itineraries match, or the intended
    itinerary is unclear, ask the user to confirm which public itinerary first.
    """
    tool_name = "copy_public_itinerary_to_my_items"
    user = get_current_planner_user()
    if user is None or not getattr(user, "is_authenticated", False):
        logger.warning("public-itinerary lookup tool %s rejected unauthenticated access.", tool_name)
        return _error(tool_name, "authentication_required", "Sign in before copying a public itinerary.")

    try:
        itinerary_pk = int(public_itinerary_id)
    except (TypeError, ValueError):
        return _error(tool_name, "invalid_public_itinerary_id", "public_itinerary_id must be an integer.")

    source = (
        Itinerary.objects.filter(pk=itinerary_pk, is_public=True)
        .prefetch_related("tags", "locations__expenses")
        .first()
    )
    if not source:
        logger.warning("public-itinerary lookup tool %s could not find public itinerary %s.", tool_name, itinerary_pk)
        return _error(tool_name, "public_itinerary_not_found", "No public itinerary was found.")

    with transaction.atomic():
        source_locations = list(source.locations.all())
        new_itinerary = Itinerary.objects.create(
            owner=user,
            title=source.title,
            start_date=source.start_date,
            end_date=source.end_date,
            location=source.location,
            budget=source.budget,
            budget_currency=source.budget_currency,
            description=source.description,
            status=Status.DRAFT,
            is_public=False,
        )
        new_itinerary.tags.set(source.tags.all())

        expense_count = 0
        for source_location in source_locations:
            new_location = Location.objects.create(
                itinerary=new_itinerary,
                name=source_location.name,
                visit_date=source_location.visit_date,
                travel_method=source_location.travel_method,
                latitude=source_location.latitude,
                longitude=source_location.longitude,
                route_order=source_location.route_order,
                note=source_location.note,
            )
            expenses = [
                Expense(
                    location=new_location,
                    expense_type=source_expense.expense_type,
                    amount=source_expense.amount,
                )
                for source_expense in source_location.expenses.all()
            ]
            Expense.objects.bulk_create(expenses)
            expense_count += len(expenses)

    logger.info(
        "public-itinerary lookup tool %s copied public itinerary %s to itinerary %s for user %s with %s locations and %s expenses.",
        tool_name,
        source.id,
        new_itinerary.id,
        user.id,
        len(source_locations),
        expense_count,
    )
    return {
        "status": "ok",
        "tool": tool_name,
        "source_itinerary_id": source.id,
        "new_itinerary_id": new_itinerary.id,
        "title": new_itinerary.title,
        "location_count": len(source_locations),
        "expense_count": expense_count,
        "message": "已將公共行程複製到你的項目。",
    }


def _parse_budget(value):
    if value in (None, ""):
        return None, None
    try:
        budget = Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError):
        return None, "invalid_budget"
    if budget < 0:
        return None, "invalid_budget"
    return budget, None


def _public_itinerary_summary(itinerary):
    return {
        "id": itinerary.id,
        "title": itinerary.title,
        "destination": itinerary.location,
        "start_date": itinerary.start_date.isoformat(),
        "end_date": itinerary.end_date.isoformat(),
        "budget": str(itinerary.budget),
        "budget_currency": itinerary.budget_currency,
        "status": itinerary.status,
        "tag_names": list(itinerary.tags.values_list("name", flat=True)),
        "public_stop_count": itinerary.locations.count(),
    }


def _error(tool_name, error_code, message):
    return {
        "status": "error",
        "tool": tool_name,
        "error_code": error_code,
        "message": message,
    }


TOOLS = (
    search_public_itineraries,
    copy_public_itinerary_to_my_items,
)
