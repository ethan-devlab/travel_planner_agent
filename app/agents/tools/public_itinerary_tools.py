"""Public itinerary lookup tools for Owner B."""

import logging
from decimal import Decimal, InvalidOperation

from django.db.models import Q

from app.models import Itinerary

from .common import planner_tool

logger = logging.getLogger(__name__)


@planner_tool
def search_public_itineraries(query="", location="", budget=None):
    """Search public itineraries after implementation."""
    tool_name = "search_public_itineraries"
    normalized_query = str(query or "").strip()
    normalized_location = str(location or "").strip()
    max_budget, budget_error = _parse_budget(budget)
    if budget_error:
        logger.warning("Owner B tool %s rejected invalid budget filter.", tool_name)
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
        "Owner B tool %s returned %s public itineraries for query length %s, location length %s, budget provided=%s.",
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
)

