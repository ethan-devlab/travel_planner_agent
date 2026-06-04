"""Owner A itinerary-management service for planner-agent tools."""

import json
import logging
import threading
import time as time_module
from datetime import datetime, time
from decimal import Decimal, InvalidOperation

from django.contrib.auth import get_user_model
from django.conf import settings
from django.db import transaction
from django.db.models import Q
from django.utils import timezone
from django.utils.dateparse import parse_date, parse_datetime
import requests

from ...budget_currency import BUDGET_CURRENCY_CODES, resolve_budget_currency
from ...models import Expense, Itinerary, Location, Status, Tag, TravelMethod

logger = logging.getLogger(__name__)

ITINERARY_FIELDS = {
    "title",
    "start_date",
    "end_date",
    "location",
    "budget",
    "budget_currency",
    "description",
    "is_public",
    "status",
}
REQUIRED_CREATE_FIELDS = {"title", "start_date", "end_date", "budget"}
VALID_STATUSES = {choice.value for choice in Status}
VALID_TRAVEL_METHODS = {choice.value for choice in TravelMethod}
VALID_EXPENSE_TYPES = {choice[0] for choice in Expense.EXPENSE_TYPE_CHOICES}
NOMINATIM_SEARCH_URL = "https://nominatim.openstreetmap.org/search"
NOMINATIM_USER_AGENT = "TravelPlannerAgent/1.0 (itinerary location geocoding)"
NOMINATIM_MIN_INTERVAL_SECONDS = 1.0
_nominatim_lock = threading.Lock()
_next_nominatim_request_at = 0.0


def list_user_itineraries_for_user(user, include_shared=True, limit=10):
    auth_error = _require_authenticated_user(user, "list_user_itineraries")
    if auth_error:
        return auth_error

    try:
        limit = max(1, min(int(limit), 25))
    except (TypeError, ValueError):
        limit = 10

    query = Q(owner=user)
    if include_shared:
        query |= Q(collaborators=user)

    itineraries = (
        Itinerary.objects.filter(query)
        .distinct()
        .prefetch_related("tags", "collaborators", "locations")
        .order_by("-updated_at")[:limit]
    )
    results = [_serialize_itinerary_summary(itinerary, user) for itinerary in itineraries]
    logger.info(
        "Owner A tool list_user_itineraries returned %s itineraries for user %s.",
        len(results),
        user.id,
    )
    return {
        "status": "ok",
        "tool": "list_user_itineraries",
        "itineraries": results,
        "count": len(results),
    }


def suggest_itinerary_changes_for_user(user, itinerary_id=None, travel_goal=""):
    auth_error = _require_authenticated_user(user, "suggest_itinerary_changes")
    if auth_error:
        return auth_error

    if not itinerary_id:
        logger.info("Owner A tool suggest_itinerary_changes generated generic suggestions.")
        return {
            "status": "ok",
            "tool": "suggest_itinerary_changes",
            "itinerary": None,
            "suggestions": _generic_suggestions(travel_goal),
        }

    itinerary, error = _get_editable_itinerary(user, itinerary_id, "suggest_itinerary_changes")
    if error:
        return error

    locations = list(itinerary.locations.prefetch_related("expenses"))
    suggestions = _itinerary_suggestions(itinerary, locations, travel_goal)
    logger.info(
        "Owner A tool suggest_itinerary_changes inspected itinerary %s with %s locations.",
        itinerary.id,
        len(locations),
    )
    return {
        "status": "ok",
        "tool": "suggest_itinerary_changes",
        "itinerary": _serialize_itinerary(itinerary, locations=locations),
        "suggestions": suggestions,
    }


def create_or_update_itinerary_for_user(user, draft_payload=None):
    auth_error = _require_authenticated_user(user, "create_or_update_itinerary")
    if auth_error:
        return auth_error

    payload, payload_error = _coerce_payload(draft_payload, "create_or_update_itinerary")
    if payload_error:
        return payload_error

    itinerary_id = payload.get("itinerary_id") or payload.get("id")
    if itinerary_id:
        itinerary, error = _get_editable_itinerary(user, itinerary_id, "create_or_update_itinerary")
        if error:
            return error
        creating = False
    else:
        itinerary = None
        creating = True

    values, values_error = _validated_itinerary_values(payload, creating, itinerary)
    if values_error:
        return values_error

    tags, tag_error = _validated_tag_names(payload)
    if tag_error:
        return tag_error

    collaborators, collaborator_error = _validated_collaborators(payload, user)
    if collaborator_error:
        return collaborator_error

    geocoding_context = values.get("location") or getattr(itinerary, "location", "")
    replace_locations = _parse_bool(payload.get("replace_locations")) if "replace_locations" in payload else creating

    locations = None
    location_updates = None
    if creating or replace_locations:
        locations, location_error = _validated_locations(payload, geocoding_context)
        if location_error:
            return location_error
    elif _has_location_payload(payload):
        location_updates, location_error = _validated_location_updates(payload)
        if location_error:
            return location_error

    with transaction.atomic():
        if creating:
            itinerary = Itinerary.objects.create(owner=user, **values)
            action = "created"
        else:
            for field, value in values.items():
                setattr(itinerary, field, value)
            itinerary.save()
            action = "updated"

        if tags is not None:
            itinerary.tags.set(tags)
        if collaborators is not None:
            itinerary.collaborators.set(collaborators)
        if locations is not None:
            itinerary.locations.all().delete()
            _create_locations(itinerary, locations)
        elif location_updates is not None:
            update_result, update_error = _apply_location_updates(itinerary, location_updates, geocoding_context)
            if update_error:
                return update_error
            logger.info(
                "Owner A location patch updated %s locations and created %s locations for itinerary %s.",
                update_result["updated_count"],
                update_result["created_count"],
                itinerary.id,
            )

    location_count = itinerary.locations.count()
    logger.info(
        "Owner A tool create_or_update_itinerary %s itinerary %s with %s locations.",
        action,
        itinerary.id,
        location_count,
    )
    return {
        "status": "ok",
        "tool": "create_or_update_itinerary",
        "action": action,
        "itinerary": _serialize_itinerary(itinerary),
    }


def manage_itinerary_status_for_user(user, itinerary_id=None, status=""):
    auth_error = _require_authenticated_user(user, "manage_itinerary_status")
    if auth_error:
        return auth_error

    if not itinerary_id:
        return _error("manage_itinerary_status", "missing_itinerary_id", "An itinerary_id is required.")

    new_status = str(status or "").strip()
    if new_status not in VALID_STATUSES:
        logger.warning("Owner A status update rejected invalid status %s.", new_status or "<blank>")
        return _error("manage_itinerary_status", "invalid_status", "Status must be one of the documented choices.")

    itinerary, error = _get_editable_itinerary(user, itinerary_id, "manage_itinerary_status")
    if error:
        return error

    itinerary.status = new_status
    itinerary.save(update_fields=["status", "updated_at"])
    logger.info(
        "Owner A tool manage_itinerary_status set itinerary %s to status %s.",
        itinerary.id,
        new_status,
    )
    return {
        "status": "ok",
        "tool": "manage_itinerary_status",
        "itinerary": _serialize_itinerary(itinerary, include_locations=False),
    }


def delete_itinerary_for_user(user, itinerary_id=None):
    auth_error = _require_authenticated_user(user, "delete_itinerary")
    if auth_error:
        return auth_error

    if not itinerary_id:
        return _error("delete_itinerary", "missing_itinerary_id", "An itinerary_id is required.")

    itinerary, error = _get_owned_itinerary(user, itinerary_id, "delete_itinerary")
    if error:
        return error

    deleted_itinerary_id = itinerary.id
    itinerary.delete()
    logger.info("Owner A tool delete_itinerary removed itinerary %s for owner %s.", deleted_itinerary_id, user.id)
    return {
        "status": "ok",
        "tool": "delete_itinerary",
        "itinerary_id": deleted_itinerary_id,
        "action": "deleted",
    }


def _require_authenticated_user(user, tool_name):
    if user is None or not getattr(user, "is_authenticated", False):
        logger.warning("Owner A tool %s rejected unauthenticated access.", tool_name)
        return _error(tool_name, "authentication_required", "Sign in before using itinerary tools.")
    return None


def _get_editable_itinerary(user, itinerary_id, tool_name):
    try:
        itinerary_pk = int(itinerary_id)
    except (TypeError, ValueError):
        return None, _error(tool_name, "invalid_itinerary_id", "itinerary_id must be an integer.")

    itinerary = (
        Itinerary.objects.filter(Q(owner=user) | Q(collaborators=user), pk=itinerary_pk)
        .distinct()
        .first()
    )
    if not itinerary:
        logger.warning("Owner A tool %s denied access to itinerary %s.", tool_name, itinerary_pk)
        return None, _error(tool_name, "itinerary_not_found", "No editable itinerary was found.")
    return itinerary, None


def _get_owned_itinerary(user, itinerary_id, tool_name):
    try:
        itinerary_pk = int(itinerary_id)
    except (TypeError, ValueError):
        return None, _error(tool_name, "invalid_itinerary_id", "itinerary_id must be an integer.")

    itinerary = Itinerary.objects.filter(owner=user, pk=itinerary_pk).first()
    if not itinerary:
        logger.warning("Owner A tool %s denied owner-only delete access to itinerary %s.", tool_name, itinerary_pk)
        return None, _error(tool_name, "itinerary_not_found", "No owned itinerary was found.")
    return itinerary, None


def _coerce_payload(raw_payload, tool_name):
    if raw_payload is None:
        return None, _error(tool_name, "missing_payload", "A draft_payload object is required.")
    if hasattr(raw_payload, "model_dump"):
        raw_payload = raw_payload.model_dump(exclude_none=True)
    if isinstance(raw_payload, str):
        try:
            raw_payload = json.loads(raw_payload)
        except json.JSONDecodeError:
            return None, _error(tool_name, "invalid_payload", "draft_payload must be a JSON object.")
    if not isinstance(raw_payload, dict):
        return None, _error(tool_name, "invalid_payload", "draft_payload must be an object.")
    return raw_payload, None


def _validated_itinerary_values(payload, creating, itinerary):
    missing = sorted(field for field in REQUIRED_CREATE_FIELDS if creating and field not in payload)
    if missing:
        return None, _error(
            "create_or_update_itinerary",
            "missing_required_fields",
            f"Missing required itinerary fields: {', '.join(missing)}.",
        )

    values = {}
    for field in ITINERARY_FIELDS:
        if field not in payload:
            continue
        value, error = _coerce_itinerary_field(field, payload[field])
        if error:
            return None, error
        values[field] = value

    start_date = values.get("start_date", getattr(itinerary, "start_date", None))
    end_date = values.get("end_date", getattr(itinerary, "end_date", None))
    if start_date and end_date and start_date > end_date:
        return None, _error(
            "create_or_update_itinerary",
            "invalid_date_range",
            "start_date must be on or before end_date.",
        )

    resolved_location = values.get("location", getattr(itinerary, "location", ""))
    submitted_currency = payload.get("budget_currency") if "budget_currency" in payload else ("AUTO" if creating else getattr(itinerary, "budget_currency", "TWD"))
    values["budget_currency"] = resolve_budget_currency(
        resolved_location,
        submitted_currency,
        fallback=getattr(itinerary, "budget_currency", "TWD") if itinerary else "TWD",
    )
    return values, None


def _coerce_itinerary_field(field, raw_value):
    if field in {"title", "location"}:
        value = str(raw_value or "").strip()
        if field == "title" and not value:
            return None, _error("create_or_update_itinerary", "invalid_title", "title cannot be blank.")
        return value, None

    if field == "description":
        return str(raw_value or ""), None

    if field in {"start_date", "end_date"}:
        value = _parse_date_value(raw_value)
        if not value:
            return None, _error("create_or_update_itinerary", f"invalid_{field}", f"{field} must be YYYY-MM-DD.")
        return value, None

    if field == "budget":
        try:
            value = Decimal(str(raw_value))
        except (InvalidOperation, TypeError, ValueError):
            return None, _error("create_or_update_itinerary", "invalid_budget", "budget must be numeric.")
        if value < 0:
            return None, _error("create_or_update_itinerary", "invalid_budget", "budget cannot be negative.")
        return value, None

    if field == "budget_currency":
        value = str(raw_value or "").strip().upper()
        if not value or value == "AUTO":
            return value or "AUTO", None
        if value not in BUDGET_CURRENCY_CODES:
            return None, _error("create_or_update_itinerary", "invalid_budget_currency", "budget_currency must be a supported currency code.")
        return value, None

    if field == "is_public":
        return _parse_bool(raw_value), None

    if field == "status":
        value = str(raw_value or "").strip()
        if value not in VALID_STATUSES:
            return None, _error("create_or_update_itinerary", "invalid_status", "status is not valid.")
        return value, None

    return raw_value, None


def _validated_tag_names(payload):
    if "tags" not in payload:
        return None, None

    names = _string_list(payload.get("tags"))
    tags = []
    for name in _unique_in_order(names):
        tag, _ = Tag.objects.get_or_create(name=name)
        tags.append(tag)
    return tags, None


def _validated_collaborators(payload, owner):
    if "collaborators" not in payload:
        return None, None

    usernames = _unique_in_order(_string_list(payload.get("collaborators")))
    if not usernames:
        return [], None

    users_by_username = get_user_model().objects.in_bulk(usernames, field_name="username")
    missing = [username for username in usernames if username not in users_by_username]
    if missing:
        logger.warning("Owner A collaborator validation rejected %s missing users.", len(missing))
        return None, _error(
            "create_or_update_itinerary",
            "unknown_collaborator",
            "All collaborators must be existing usernames.",
        )

    return [users_by_username[username] for username in usernames if users_by_username[username] != owner], None


def _validated_locations(payload, geocoding_context=""):
    location_key = next(
        (key for key in ("locations", "activities", "stops", "places") if key in payload),
        None,
    )
    if location_key is None:
        return None, None

    raw_locations = payload.get(location_key) or []
    if not isinstance(raw_locations, list):
        return None, _error("create_or_update_itinerary", "invalid_locations", f"{location_key} must be a list.")

    locations = []
    for index, raw_location in enumerate(raw_locations):
        if not isinstance(raw_location, dict):
            return None, _error("create_or_update_itinerary", "invalid_location", "Each location must be an object.")
        location, error = _validated_location(raw_location, index, geocoding_context)
        if error:
            return None, error
        locations.append(location)
    return locations, None


def _has_location_payload(payload):
    return any(key in payload for key in ("locations", "activities", "stops", "places"))


def _validated_location_updates(payload):
    location_key = next(
        (key for key in ("locations", "activities", "stops", "places") if key in payload),
        None,
    )
    if location_key is None:
        return None, None

    raw_locations = payload.get(location_key) or []
    if not isinstance(raw_locations, list):
        return None, _error("create_or_update_itinerary", "invalid_locations", f"{location_key} must be a list.")

    updates = []
    for index, raw_location in enumerate(raw_locations):
        if not isinstance(raw_location, dict):
            return None, _error("create_or_update_itinerary", "invalid_location", "Each location must be an object.")

        route_order = _parse_int(raw_location.get("route_order"), None) if "route_order" in raw_location else None
        location_id = _parse_int(raw_location.get("location_id"), None) if "location_id" in raw_location else None
        name = str(raw_location.get("name") or "").strip() if "name" in raw_location else ""
        travel_method = str(raw_location.get("travel_method") or "").strip() if "travel_method" in raw_location else ""

        if travel_method and travel_method not in VALID_TRAVEL_METHODS:
            return None, _error("create_or_update_itinerary", "invalid_travel_method", "travel_method is not valid.")

        expenses = None
        if "expenses" in raw_location:
            expenses, expense_error = _validated_expenses(raw_location.get("expenses") or [])
            if expense_error:
                return None, expense_error

        updates.append({
            "index": index,
            "location_id": location_id,
            "route_order": route_order,
            "name": name,
            "travel_method": travel_method,
            "visit_date_raw": raw_location.get("visit_date"),
            "visit_date_provided": "visit_date" in raw_location and raw_location.get("visit_date") not in (None, ""),
            "note": str(raw_location.get("note") or "") if "note" in raw_location else "",
            "note_provided": "note" in raw_location,
            "route_order_provided": "route_order" in raw_location,
            "travel_method_provided": "travel_method" in raw_location and bool(travel_method),
            "name_provided": "name" in raw_location and bool(name),
            "expenses_provided": "expenses" in raw_location,
            "expenses": expenses or [],
            "has_coordinate_payload": "latitude" in raw_location or "longitude" in raw_location,
        })
    return updates, None


def _apply_location_updates(itinerary, updates, geocoding_context=""):
    existing_locations = list(itinerary.locations.prefetch_related("expenses").all())
    updated_count = 0
    created_count = 0

    for update in updates:
        target = _match_existing_location(existing_locations, update)
        if target is not None:
            patch_error = _apply_existing_location_patch(target, update)
            if patch_error:
                return None, patch_error
            updated_count += 1
            continue

        created_location, create_error = _create_location_from_update(itinerary, update, geocoding_context)
        if create_error:
            return None, create_error
        existing_locations.append(created_location)
        created_count += 1

    return {
        "updated_count": updated_count,
        "created_count": created_count,
    }, None


def _match_existing_location(existing_locations, update):
    location_id = update.get("location_id")
    if location_id is not None:
        for location in existing_locations:
            if location.id == location_id:
                return location

    route_order = update.get("route_order")
    if route_order is not None:
        matches = [location for location in existing_locations if location.route_order == route_order]
        if len(matches) == 1:
            return matches[0]

    name = update.get("name") or ""
    if name:
        normalized_name = name.casefold()
        for location in existing_locations:
            if location.name.casefold() == normalized_name:
                return location

    return None


def _apply_existing_location_patch(location, update):
    changed_fields = []

    if update.get("visit_date_provided"):
        visit_date, visit_error = _parse_visit_date(
            update.get("visit_date_raw"),
            reference_visit_date=location.visit_date,
            default_hour=_default_visit_hour_for_order(location.route_order),
        )
        if visit_error:
            return visit_error
        location.visit_date = visit_date
        changed_fields.append("visit_date")

    if update.get("note_provided"):
        location.note = update.get("note", "")
        changed_fields.append("note")

    if update.get("route_order_provided") and update.get("route_order") is not None:
        location.route_order = update["route_order"]
        changed_fields.append("route_order")

    if update.get("travel_method_provided"):
        location.travel_method = update["travel_method"]
        changed_fields.append("travel_method")

    if update.get("name_provided") and update.get("name") and update["name"] != location.name:
        logger.info("Owner A ignored location rename attempt for location %s.", location.id)

    if update.get("has_coordinate_payload"):
        logger.info("Owner A ignored model-provided coordinates for existing location %s.", location.id)

    if changed_fields:
        location.save(update_fields=changed_fields)

    if update.get("expenses_provided"):
        location.expenses.all().delete()
        for expense in update.get("expenses", []):
            Expense.objects.create(location=location, **expense)
    return None


def _create_location_from_update(itinerary, update, geocoding_context=""):
    name = update.get("name") or ""
    travel_method = update.get("travel_method") or ""
    if not name:
        return None, _error(
            "create_or_update_itinerary",
            "missing_location_name",
            "New location updates must include a location name.",
        )
    if not travel_method:
        return None, _error(
            "create_or_update_itinerary",
            "missing_travel_method",
            "New location updates must include travel_method.",
        )

    visit_date_raw = update.get("visit_date_raw")
    if visit_date_raw in (None, ""):
        return None, _error(
            "create_or_update_itinerary",
            "missing_visit_date",
            "New location updates must include visit_date with time.",
        )
    visit_date, visit_error = _parse_visit_date(
        visit_date_raw,
        reference_visit_date=None,
        default_hour=_default_visit_hour_for_order(update.get("route_order")),
    )
    if visit_error:
        return None, visit_error

    latitude, longitude = _geocode_location_coordinates(name, geocoding_context)
    route_order = update.get("route_order")
    if route_order is None:
        route_order = itinerary.locations.count()

    location = Location.objects.create(
        itinerary=itinerary,
        name=name,
        travel_method=travel_method,
        visit_date=visit_date,
        latitude=latitude,
        longitude=longitude,
        route_order=route_order,
        note=update.get("note", "") if update.get("note_provided") else "",
    )
    for expense in update.get("expenses", []):
        Expense.objects.create(location=location, **expense)
    return location, None


def _validated_location(raw_location, index, geocoding_context=""):
    name = str(raw_location.get("name") or "").strip()
    travel_method = str(raw_location.get("travel_method") or "walk").strip()
    if not name:
        return None, _error("create_or_update_itinerary", "invalid_location_name", "Location name cannot be blank.")
    if travel_method not in VALID_TRAVEL_METHODS:
        return None, _error("create_or_update_itinerary", "invalid_travel_method", "travel_method is not valid.")

    route_order = _parse_int(raw_location.get("route_order"), index)
    visit_date, visit_error = _parse_visit_date(
        raw_location.get("visit_date"),
        reference_visit_date=None,
        default_hour=_default_visit_hour_for_order(route_order),
    )
    if visit_error:
        return None, visit_error

    expenses, expense_error = _validated_expenses(raw_location.get("expenses") or [])
    if expense_error:
        return None, expense_error

    # Planner-agent generated payload coordinates are never trusted.
    # To match user flows, every location coordinate is resolved via Nominatim.
    if raw_location.get("latitude") is not None or raw_location.get("longitude") is not None:
        logger.info("Owner A ignored model-provided coordinates for location name length %s.", len(name))
    latitude, longitude = _geocode_location_coordinates(name, geocoding_context)

    return {
        "name": name,
        "travel_method": travel_method,
        "visit_date": visit_date,
        "latitude": latitude,
        "longitude": longitude,
        "route_order": route_order,
        "note": str(raw_location.get("note") or ""),
        "expenses": expenses,
    }, None


def _coordinates_need_geocoding(latitude, longitude):
    return latitude == 0.0 and longitude == 0.0


def _geocode_location_coordinates(location_name, geocoding_context=""):
    coordinates = _nominatim_geocode_with_fallback(location_name, geocoding_context)
    if coordinates:
        return coordinates

    logger.warning("Owner A Nominatim geocoding found no coordinates for location length %s.", len(location_name))
    return 0.0, 0.0


def _geocoding_query(location_name, geocoding_context=""):
    context = str(geocoding_context or "").strip()
    if not context:
        return location_name
    if context.lower() in location_name.lower():
        return location_name
    return f"{location_name}, {context}"


def _nominatim_geocode_with_fallback(location_name, geocoding_context=""):
    queries = _unique_in_order([
        _geocoding_query(location_name, geocoding_context),
        location_name,
    ])
    for query in queries:
        coordinates = _nominatim_geocode(query)
        if coordinates:
            logger.info("Owner A geocoded location with Nominatim using query length %s.", len(query))
            return coordinates
    return None


def _nominatim_geocode(query):
    try:
        _throttle_nominatim_request()
        response = requests.get(
            NOMINATIM_SEARCH_URL,
            params={"q": query, "format": "json", "limit": 1},
            headers={"Accept": "application/json", "User-Agent": NOMINATIM_USER_AGENT},
            timeout=settings.REQUEST_TIMEOUT_SECONDS,
        )
        response.raise_for_status()
        results = response.json()
    except requests.RequestException as exc:
        logger.warning("Nominatim geocoding request failed with %s.", exc.__class__.__name__)
        return None

    if not isinstance(results, list):
        return None

    for result in results:
        latitude = _parse_float(result.get("lat"), 0.0)
        longitude = _parse_float(result.get("lon"), 0.0)
        if not _coordinates_need_geocoding(latitude, longitude):
            return latitude, longitude
    return None


def _throttle_nominatim_request():
    global _next_nominatim_request_at
    with _nominatim_lock:
        now = time_module.monotonic()
        delay = _next_nominatim_request_at - now
        if delay > 0:
            time_module.sleep(delay)
        _next_nominatim_request_at = time_module.monotonic() + NOMINATIM_MIN_INTERVAL_SECONDS


def _validated_expenses(raw_expenses):
    if not isinstance(raw_expenses, list):
        return None, _error("create_or_update_itinerary", "invalid_expenses", "expenses must be a list.")

    expenses = []
    for raw_expense in raw_expenses:
        if not isinstance(raw_expense, dict):
            return None, _error("create_or_update_itinerary", "invalid_expense", "Each expense must be an object.")
        expense_type = str(raw_expense.get("expense_type") or "").strip()
        if expense_type not in VALID_EXPENSE_TYPES:
            return None, _error("create_or_update_itinerary", "invalid_expense_type", "expense_type is not valid.")
        try:
            amount = Decimal(str(raw_expense.get("amount")))
        except (InvalidOperation, TypeError, ValueError):
            return None, _error("create_or_update_itinerary", "invalid_expense_amount", "Expense amount must be numeric.")
        if amount < 0:
            return None, _error("create_or_update_itinerary", "invalid_expense_amount", "Expense amount cannot be negative.")
        expenses.append({"expense_type": expense_type, "amount": amount})
    return expenses, None


def _create_locations(itinerary, locations):
    for location_data in locations:
        expenses = location_data.pop("expenses")
        location = Location.objects.create(itinerary=itinerary, **location_data)
        for expense in expenses:
            Expense.objects.create(location=location, **expense)


def _serialize_itinerary(itinerary, include_locations=True, locations=None):
    data = {
        "id": itinerary.id,
        "title": itinerary.title,
        "start_date": itinerary.start_date.isoformat(),
        "end_date": itinerary.end_date.isoformat(),
        "location": itinerary.location,
        "budget": str(itinerary.budget),
        "budget_currency": itinerary.budget_currency,
        "budget_display": itinerary.budget_display,
        "is_public": itinerary.is_public,
        "status": itinerary.status,
        "tag_names": list(itinerary.tags.values_list("name", flat=True)),
        "collaborator_usernames": list(itinerary.collaborators.values_list("username", flat=True)),
        "description_length": len(itinerary.description or ""),
    }
    if include_locations:
        location_rows = locations if locations is not None else list(itinerary.locations.prefetch_related("expenses"))
        data["locations"] = [_serialize_location(location) for location in location_rows]
    return data


def _serialize_itinerary_summary(itinerary, user):
    return {
        "id": itinerary.id,
        "title": itinerary.title,
        "start_date": itinerary.start_date.isoformat(),
        "end_date": itinerary.end_date.isoformat(),
        "location": itinerary.location,
        "budget": str(itinerary.budget),
        "budget_currency": itinerary.budget_currency,
        "budget_display": itinerary.budget_display,
        "is_public": itinerary.is_public,
        "status": itinerary.status,
        "relationship": "owner" if itinerary.owner_id == user.id else "collaborator",
        "tag_names": list(itinerary.tags.values_list("name", flat=True)),
        "location_count": itinerary.locations.count(),
        "description_length": len(itinerary.description or ""),
    }


def _serialize_location(location):
    return {
        "id": location.id,
        "name": location.name,
        "visit_date": location.visit_date.isoformat() if location.visit_date else None,
        "travel_method": location.travel_method,
        "latitude": location.latitude,
        "longitude": location.longitude,
        "route_order": location.route_order,
        "note_length": len(location.note or ""),
        "expenses": [
            {
                "id": expense.id,
                "expense_type": expense.expense_type,
                "amount": str(expense.amount),
            }
            for expense in location.expenses.all()
        ],
    }


def _itinerary_suggestions(itinerary, locations, travel_goal):
    suggestions = []
    if travel_goal:
        suggestions.append("Align each stop with the stated travel goal before adding new stops.")
    if not locations:
        suggestions.append("Add dated location stops so the itinerary can be routed and reviewed.")
    if len(locations) == 1:
        suggestions.append("Add at least one more stop to create a useful route preview.")
    if any(location.latitude == 0 and location.longitude == 0 for location in locations):
        suggestions.append("Add precise coordinates for stops that still use default coordinates.")
    if itinerary.budget <= 0:
        suggestions.append("Add a realistic budget before moving the itinerary out of draft.")
    if not suggestions:
        suggestions.append("The itinerary has core details; review route order, travel times, and budget fit next.")
    return suggestions


def _generic_suggestions(travel_goal):
    suggestions = ["Create a draft with title, dates, budget, destination, and at least two dated stops."]
    if travel_goal:
        suggestions.append("Use the travel goal to prioritize stops before asking for route or review work.")
    return suggestions


def _parse_date_value(raw_value):
    if hasattr(raw_value, "isoformat") and not isinstance(raw_value, str):
        return raw_value
    return parse_date(str(raw_value or ""))


def _default_visit_hour_for_order(route_order):
    try:
        order = int(route_order)
    except (TypeError, ValueError):
        order = 0
    base_hour = 9
    scheduled_hour = base_hour + max(0, order)
    return min(scheduled_hour, 20)


def _parse_visit_date(raw_value, reference_visit_date=None, default_hour=9):
    if not raw_value:
        return None, None
    raw_text = str(raw_value).strip()
    parsed_date_only = parse_date(raw_text) if raw_text else None
    is_date_only_input = bool(parsed_date_only) and "T" not in raw_text and " " not in raw_text

    if is_date_only_input and parsed_date_only:
        if isinstance(reference_visit_date, datetime):
            reference_local = timezone.localtime(reference_visit_date, timezone.get_current_timezone())
            parsed = datetime.combine(
                parsed_date_only,
                time(
                    hour=reference_local.hour,
                    minute=reference_local.minute,
                    second=reference_local.second,
                    microsecond=reference_local.microsecond,
                ),
            )
        else:
            parsed = datetime.combine(parsed_date_only, time(hour=default_hour, minute=0))
        if timezone.is_naive(parsed):
            parsed = timezone.make_aware(parsed, timezone.get_current_timezone())
        return parsed, None

    if isinstance(raw_value, datetime):
        parsed = raw_value
    else:
        parsed = parse_datetime(raw_text)
        if parsed is None:
            date_value = parse_date(raw_text)
            if date_value:
                if isinstance(reference_visit_date, datetime):
                    reference_local = timezone.localtime(reference_visit_date, timezone.get_current_timezone())
                    parsed = datetime.combine(
                        date_value,
                        time(
                            hour=reference_local.hour,
                            minute=reference_local.minute,
                            second=reference_local.second,
                            microsecond=reference_local.microsecond,
                        ),
                    )
                else:
                    parsed = datetime.combine(date_value, time(hour=default_hour, minute=0))
    if parsed is None:
        return None, _error(
            "create_or_update_itinerary",
            "invalid_visit_date",
            "visit_date must be ISO formatted with date and optional time.",
        )
    if timezone.is_naive(parsed):
        parsed = timezone.make_aware(parsed, timezone.get_current_timezone())
    return parsed, None


def _parse_float(raw_value, default):
    try:
        return float(raw_value)
    except (TypeError, ValueError):
        return default


def _parse_int(raw_value, default):
    try:
        return int(raw_value)
    except (TypeError, ValueError):
        return default


def _parse_bool(raw_value):
    if isinstance(raw_value, bool):
        return raw_value
    if isinstance(raw_value, str):
        return raw_value.strip().lower() in {"1", "true", "yes", "on"}
    return bool(raw_value)


def _string_list(value):
    if value is None:
        return []
    if isinstance(value, str):
        return [item.strip() for item in value.split(",") if item.strip()]
    if isinstance(value, (list, tuple)):
        return [str(item).strip() for item in value if str(item).strip()]
    return [str(value).strip()] if str(value).strip() else []


def _unique_in_order(values):
    seen = set()
    unique_values = []
    for value in values:
        if value in seen:
            continue
        seen.add(value)
        unique_values.append(value)
    return unique_values


def _error(tool_name, error_code, message):
    return {
        "status": "error",
        "tool": tool_name,
        "error_code": error_code,
        "message": message,
    }
