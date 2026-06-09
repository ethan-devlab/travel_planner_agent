"""Explicit itinerary review tools."""

import logging
from decimal import Decimal

from django.db.models import Q

from app.models import Itinerary
from app.views.itinerary.route_helpers import serialize_route_waypoints

from ..tool_context import get_current_planner_user
from .common import planner_tool

logger = logging.getLogger(__name__)


@planner_tool
def review_itinerary_on_request(itinerary_id=None, review_focus=""):
    """Review an itinerary only when the user requests review."""
    tool_name = "review_itinerary_on_request"
    user = get_current_planner_user()
    auth_error = _require_authenticated_user(user, tool_name)
    if auth_error:
        return auth_error

    itinerary_pk, id_error = _parse_itinerary_id(itinerary_id, tool_name)
    if id_error:
        return id_error

    itinerary = _reviewable_itinerary_for_user(user, itinerary_pk)
    if itinerary is None:
        logger.warning("review tool %s denied review for itinerary %s and user %s.", tool_name, itinerary_pk, user.id)
        return _error(tool_name, "itinerary_not_found", "No reviewable itinerary was found.")

    locations = list(itinerary.locations.prefetch_related("expenses").all())
    route_waypoints = serialize_route_waypoints(itinerary)
    risks = _review_risks(itinerary, locations, route_waypoints)
    suggested_next_actions = _suggested_next_actions(itinerary, locations, route_waypoints, risks)
    expense_total = _expense_total(locations)

    logger.info(
        "review tool %s reviewed itinerary %s for user %s with %s locations, %s waypoints, focus length %s.",
        tool_name,
        itinerary.id,
        user.id,
        len(locations),
        len(route_waypoints),
        len(str(review_focus or "")),
    )
    return {
        "status": "ok",
        "tool": tool_name,
        "itinerary_id": itinerary.id,
        "review_summary": {
            "title": itinerary.title,
            "destination": itinerary.location,
            "date_range": {
                "start_date": itinerary.start_date.isoformat(),
                "end_date": itinerary.end_date.isoformat(),
            },
            "status": itinerary.status,
            "budget": str(itinerary.budget),
            "budget_currency": itinerary.budget_currency,
            "location_count": len(locations),
            "route_waypoint_count": len(route_waypoints),
            "expense_total": str(expense_total),
            "expense_count": sum(location.expenses.count() for location in locations),
            "tag_names": list(itinerary.tags.values_list("name", flat=True)),
            "relationship": "owner" if itinerary.owner_id == user.id else (
                "collaborator" if itinerary.collaborators.filter(pk=user.pk).exists() else "public"
            ),
        },
        "risks": risks,
        "suggested_next_actions": suggested_next_actions,
    }


def _require_authenticated_user(user, tool_name):
    if user is None or not getattr(user, "is_authenticated", False):
        logger.warning("review tool %s rejected unauthenticated access.", tool_name)
        return _error(tool_name, "authentication_required", "Sign in before using review tools.")
    return None


def _parse_itinerary_id(itinerary_id, tool_name):
    try:
        itinerary_pk = int(itinerary_id)
    except (TypeError, ValueError):
        return None, {
            "status": "confirmation_required",
            "tool": tool_name,
            "error_code": "missing_itinerary_context",
            "message": "Please specify which itinerary to review before I run an itinerary review.",
        }
    if itinerary_pk <= 0:
        return None, _error(tool_name, "invalid_itinerary_id", "itinerary_id must be a positive integer.")
    return itinerary_pk, None


def _reviewable_itinerary_for_user(user, itinerary_pk):
    return (
        Itinerary.objects.filter(
            Q(owner=user) | Q(collaborators=user) | Q(is_public=True),
            pk=itinerary_pk,
        )
        .distinct()
        .prefetch_related("tags", "collaborators", "locations__expenses")
        .first()
    )


def _review_risks(itinerary, locations, route_waypoints):
    risks = []
    if not locations:
        risks.append(_risk("missing_stops", "Add stops before relying on this itinerary."))
    if len(locations) == 1:
        risks.append(_risk("single_stop", "Add at least one more stop for a useful route review."))
    if len(route_waypoints) < len(locations):
        risks.append(_risk("missing_route_coordinates", "Some stops do not have usable route coordinates."))
    if any(location.visit_date is None for location in locations):
        risks.append(_risk("missing_visit_times", "Some stops do not have visit dates and times."))
    if any(_visit_date_outside_itinerary(location, itinerary) for location in locations if location.visit_date):
        risks.append(_risk("visit_date_outside_trip", "Some stop visit dates fall outside the itinerary date range."))

    expense_total = _expense_total(locations)
    if expense_total > itinerary.budget:
        risks.append(_risk("expenses_over_budget", "Recorded stop expenses exceed the itinerary budget."))
    elif expense_total and itinerary.budget and expense_total >= itinerary.budget * Decimal("0.9"):
        risks.append(_risk("expenses_near_budget", "Recorded stop expenses are close to the itinerary budget."))

    if not risks:
        risks.append(_risk("no_major_risks_found", "No major structural risks were found from saved stops, route data, and expenses."))
    return risks


def _suggested_next_actions(itinerary, locations, route_waypoints, risks):
    actions = []
    risk_codes = {risk["code"] for risk in risks}
    if "missing_stops" in risk_codes or "single_stop" in risk_codes:
        actions.append("Add more dated stops before final review.")
    if "missing_route_coordinates" in risk_codes:
        actions.append("Fix stop coordinates so the route can be reviewed reliably.")
    if "missing_visit_times" in risk_codes or "visit_date_outside_trip" in risk_codes:
        actions.append("Review stop dates and times against the trip date range.")
    if "expenses_over_budget" in risk_codes or "expenses_near_budget" in risk_codes:
        actions.append("Adjust the budget or reduce planned stop expenses.")
    if not actions and locations and route_waypoints:
        actions.append("Review travel time between adjacent stops and confirm the route order.")
    if itinerary.status == "draft":
        actions.append("Keep the itinerary in draft until timing, route, and budget risks are resolved.")
    return actions


def _expense_total(locations):
    total = Decimal("0")
    for location in locations:
        for expense in location.expenses.all():
            total += expense.amount
    return total


def _visit_date_outside_itinerary(location, itinerary):
    visit_date = location.visit_date.date()
    return visit_date < itinerary.start_date or visit_date > itinerary.end_date


def _risk(code, message):
    return {
        "code": code,
        "message": message,
    }


def _error(tool_name, error_code, message):
    return {
        "status": "error",
        "tool": tool_name,
        "error_code": error_code,
        "message": message,
    }


TOOLS = (
    review_itinerary_on_request,
)
