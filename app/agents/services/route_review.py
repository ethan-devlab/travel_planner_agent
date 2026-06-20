"""Deterministic route timing, transport, and order evidence."""

import logging
import math
from collections import defaultdict

import requests
from django.conf import settings
from django.utils import timezone

from app.views.itinerary.route_helpers import normalize_osrm_base_url

logger = logging.getLogger(__name__)

WALK_ROUTE_FACTOR = 1.25
WALK_SPEED_KMH = 4.8
LONG_WALK_DISTANCE_KM = 5.0
LONG_WALK_MINUTES = 90.0
SHORT_PLANE_DISTANCE_KM = 100.0
MAX_ROAD_SNAP_METERS = 500.0
TIGHT_MINIMUM_SECONDS = 15 * 60
TIGHT_DURATION_RATIO = 0.20
DETOUR_MINIMUM_SECONDS = 15 * 60
DETOUR_MINIMUM_RATIO = 0.20


def analyze_route_evidence(itinerary, locations):
    del itinerary  # Route analysis uses saved stop rows and configured OSRM only.
    route_legs = []
    day_order_results = []
    risks = []

    for visit_day, day_locations in _locations_by_day(locations).items():
        valid_locations = [location for location in day_locations if _has_coordinates(location)]
        route_snapshot = _fetch_route(valid_locations) if len(valid_locations) >= 2 else None
        if len(valid_locations) >= 2 and route_snapshot is None:
            risks.append(_risk(
                "route_service_unavailable",
                "The driving route service could not verify one or more same-day legs.",
            ))

        if len(day_locations) >= 2:
            valid_indices = {location.id: index for index, location in enumerate(valid_locations)}
            for origin, destination in zip(day_locations, day_locations[1:]):
                if not _has_coordinates(origin) or not _has_coordinates(destination):
                    continue
                origin_index = valid_indices[origin.id]
                destination_index = valid_indices[destination.id]
                route_leg = _route_leg(route_snapshot, origin_index, destination_index)
                snap_distance = _leg_snap_distance(route_snapshot, origin_index, destination_index)
                leg, leg_risks = _build_leg(origin, destination, route_leg, snap_distance)
                route_legs.append(leg)
                risks.extend(leg_risks)

        if len(day_locations) >= 3 and len(valid_locations) == len(day_locations):
            day_order_results.append(
                _analyze_day_order(visit_day, day_locations, route_snapshot, risks)
            )
        elif len(day_locations) >= 3:
            day_order_results.append(_not_applicable_day_order(
                visit_day,
                day_locations,
                valid_locations,
                "missing_coordinates",
                "Route-order analysis requires usable coordinates for every same-day stop.",
            ))
        else:
            day_order_results.append(_not_applicable_day_order(
                visit_day,
                day_locations,
                valid_locations,
                "fewer_than_three_same_day_stops",
                "Route-order analysis requires at least three stops on the same local date.",
            ))

    risks = _dedupe_risks(risks)
    actions = _route_actions(risks)
    logger.info(
        "Route review processed %s stops into %s legs and %s day-order analyses with %s risks.",
        len(locations),
        len(route_legs),
        len(day_order_results),
        len(risks),
    )
    return {
        "route_legs": route_legs,
        "route_order_analysis": _aggregate_order_results(day_order_results),
        "risks": risks,
        "suggested_next_actions": actions,
    }


def _build_leg(origin, destination, route_leg, snap_distance):
    method = destination.travel_method
    available_seconds = (destination.visit_date - origin.visit_date).total_seconds()
    direct_distance_km = _haversine_km(origin, destination)
    risks = []
    estimated_seconds = None
    distance_km = direct_distance_km
    evidence_source = "great_circle"
    transport_status = "unverified"

    if method == "car":
        if route_leg is None:
            status = "route_unavailable"
            timing_status = "not_verified"
            transport_status = "route_unavailable"
        else:
            estimated_seconds = float(route_leg.get("duration") or 0)
            distance_km = float(route_leg.get("distance") or 0) / 1000
            evidence_source = "osrm_driving"
            transport_status = "feasible"
            timing_status = _timing_status(available_seconds, estimated_seconds)
            status = timing_status
            if snap_distance is not None and snap_distance > MAX_ROAD_SNAP_METERS:
                status = "coordinate_far_from_road"
                transport_status = "coordinate_far_from_road"
                risks.append(_risk(
                    "route_coordinate_far_from_road",
                    "A stop is more than 500 metres from the road position used by the route service.",
                ))
    elif method == "walk":
        distance_km = direct_distance_km * WALK_ROUTE_FACTOR
        estimated_seconds = distance_km / WALK_SPEED_KMH * 3600
        evidence_source = "walking_estimate"
        transport_status = "estimated"
        timing_status = _timing_status(available_seconds, estimated_seconds)
        status = timing_status
        if distance_km > LONG_WALK_DISTANCE_KM or estimated_seconds / 60 > LONG_WALK_MINUTES:
            risks.append(_risk(
                "long_walking_leg",
                "A planned walking leg is longer than 5 kilometres or 90 estimated minutes.",
            ))
    else:
        timing_status = "not_verified"
        status = "verification_required"
        risks.append(_risk(
            "transport_verification_required",
            "Bus, rail, high-speed rail, plane, and boat legs require a timetable-capable provider.",
        ))
        if method == "plane" and direct_distance_km < SHORT_PLANE_DISTANCE_KM:
            risks.append(_risk(
                "short_plane_leg",
                "A planned plane leg is under 100 kilometres and may be impractical.",
            ))

    if available_seconds <= 0:
        status = "chronological_conflict"
        timing_status = "chronological_conflict"
        risks.append(_risk(
            "route_chronological_conflict",
            "A later route stop does not have a later scheduled start time.",
        ))
    elif timing_status == "insufficient":
        risks.append(_risk(
            "route_interval_insufficient",
            "Estimated travel time exceeds the available interval between scheduled stop starts.",
        ))
    elif timing_status == "tight":
        risks.append(_risk(
            "route_interval_tight",
            "A route leg leaves less than the configured minimum timing buffer.",
        ))

    return {
        "origin": origin.name,
        "destination": destination.name,
        "method": method,
        "distance_km": round(distance_km, 2),
        "estimated_minutes": _minutes_or_none(estimated_seconds),
        "available_minutes": round(available_seconds / 60, 1),
        "status": status,
        "timing_status": timing_status,
        "transport_status": transport_status,
        "evidence_source": evidence_source,
    }, risks


def _analyze_day_order(visit_day, locations, route_snapshot, risks):
    default = {
        "date": visit_day.isoformat(),
        "status": "optimization_unavailable",
        "reason_code": "driving_route_unavailable",
        "reason": "The driving route was unavailable, so stop-order optimization could not run.",
        "stop_count": len(locations),
        "valid_coordinate_count": len(locations),
        "advisory": not all(location.travel_method == "car" for location in locations[1:]),
        "current_minutes": None,
        "optimized_minutes": None,
        "extra_minutes": None,
        "extra_percent": None,
        "suggested_order": [location.name for location in locations],
        "evidence_source": "osrm_driving",
    }
    if route_snapshot is None:
        return default

    trip_snapshot = _fetch_trip(locations)
    if trip_snapshot is None:
        risks.append(_risk(
            "route_optimization_unavailable",
            "The route service could not calculate an optimized same-day stop order.",
        ))
        return {
            **default,
            "reason_code": "route_optimization_unavailable",
            "reason": "The route service could not calculate an optimized same-day stop order.",
        }

    current_seconds = route_snapshot["duration"]
    optimized_seconds = trip_snapshot["duration"]
    if optimized_seconds <= 0:
        return default

    extra_seconds = max(0.0, current_seconds - optimized_seconds)
    extra_ratio = extra_seconds / optimized_seconds
    is_detour = extra_seconds >= DETOUR_MINIMUM_SECONDS and extra_ratio >= DETOUR_MINIMUM_RATIO
    result = {
        **default,
        "status": "detour" if is_detour else "acceptable",
        "reason_code": "",
        "reason": "",
        "current_minutes": round(current_seconds / 60, 1),
        "optimized_minutes": round(optimized_seconds / 60, 1),
        "extra_minutes": round(extra_seconds / 60, 1),
        "extra_percent": round(extra_ratio * 100, 1),
        "suggested_order": _suggested_order(locations, trip_snapshot["waypoints"]),
    }
    if is_detour:
        qualifier = "driving-road advisory" if result["advisory"] else "driving route"
        risks.append(_risk(
            "route_detour",
            f"The current {qualifier} is at least 20% and 15 minutes longer than the optimized order.",
        ))
    return result


def _fetch_route(locations):
    payload = _osrm_request("route", locations, {"overview": "false", "steps": "false"})
    if not payload or payload.get("code") != "Ok" or not payload.get("routes"):
        return None
    route = payload["routes"][0]
    legs = route.get("legs") or []
    if len(legs) != len(locations) - 1:
        return None
    return {
        "duration": float(route.get("duration") or 0),
        "distance": float(route.get("distance") or 0),
        "legs": legs,
        "waypoints": payload.get("waypoints") or [],
    }


def _fetch_trip(locations):
    payload = _osrm_request("trip", locations, {
        "roundtrip": "false",
        "source": "first",
        "destination": "last",
        "overview": "false",
        "steps": "false",
    })
    if not payload or payload.get("code") != "Ok" or not payload.get("trips"):
        return None
    trip = payload["trips"][0]
    return {
        "duration": float(trip.get("duration") or 0),
        "distance": float(trip.get("distance") or 0),
        "waypoints": payload.get("waypoints") or [],
    }


def _osrm_request(service, locations, params):
    base_url, _ = normalize_osrm_base_url(settings.ROUTING_SERVICE_URL)
    if not base_url:
        return None
    coordinates = ";".join(f"{location.longitude},{location.latitude}" for location in locations)
    try:
        response = requests.get(
            f"{base_url}/{service}/v1/driving/{coordinates}",
            params=params,
            timeout=settings.REQUEST_TIMEOUT_SECONDS,
        )
        response.raise_for_status()
        return response.json()
    except (requests.RequestException, ValueError) as exc:
        logger.warning("OSRM %s request failed with %s for %s waypoints.", service, exc.__class__.__name__, len(locations))
        return None


def _locations_by_day(locations):
    grouped = defaultdict(list)
    for location in sorted(locations, key=lambda item: (item.route_order, item.id)):
        if location.visit_date is None:
            continue
        visit_date = location.visit_date
        if timezone.is_aware(visit_date):
            visit_date = timezone.localtime(visit_date, timezone.get_current_timezone())
        grouped[visit_date.date()].append(location)
    return grouped


def _has_coordinates(location):
    return (
        math.isfinite(location.latitude)
        and math.isfinite(location.longitude)
        and -90 <= location.latitude <= 90
        and -180 <= location.longitude <= 180
        and not (location.latitude == 0 and location.longitude == 0)
    )


def _haversine_km(origin, destination):
    earth_radius_km = 6371.0088
    lat1 = math.radians(origin.latitude)
    lat2 = math.radians(destination.latitude)
    delta_lat = lat2 - lat1
    delta_lon = math.radians(destination.longitude - origin.longitude)
    value = math.sin(delta_lat / 2) ** 2 + math.cos(lat1) * math.cos(lat2) * math.sin(delta_lon / 2) ** 2
    return 2 * earth_radius_km * math.asin(math.sqrt(value))


def _timing_status(available_seconds, estimated_seconds):
    if available_seconds <= 0:
        return "chronological_conflict"
    if estimated_seconds > available_seconds:
        return "insufficient"
    remaining_seconds = available_seconds - estimated_seconds
    tight_threshold = max(TIGHT_MINIMUM_SECONDS, estimated_seconds * TIGHT_DURATION_RATIO)
    return "tight" if remaining_seconds < tight_threshold else "sufficient"


def _route_leg(route_snapshot, origin_index, destination_index):
    if route_snapshot is None or destination_index != origin_index + 1:
        return None
    legs = route_snapshot["legs"]
    return legs[origin_index] if origin_index < len(legs) else None


def _leg_snap_distance(route_snapshot, origin_index, destination_index):
    if route_snapshot is None:
        return None
    waypoints = route_snapshot["waypoints"]
    if destination_index >= len(waypoints):
        return None
    return max(
        float(waypoints[origin_index].get("distance") or 0),
        float(waypoints[destination_index].get("distance") or 0),
    )


def _suggested_order(locations, waypoints):
    if len(waypoints) != len(locations):
        return [location.name for location in locations]
    indexed_locations = zip(locations, waypoints)
    return [
        location.name
        for location, waypoint in sorted(
            indexed_locations,
            key=lambda item: int(item[1].get("waypoint_index", 0)),
        )
    ]


def _aggregate_order_results(day_results):
    if not day_results:
        return {
            "status": "not_applicable",
            "reason_code": "no_dated_stops",
            "reason": "Route-order analysis requires at least three stops on the same local date.",
            "required_same_day_stop_count": 3,
            "max_same_day_stop_count": 0,
            "days": [],
        }

    applicable_results = [item for item in day_results if item["status"] != "not_applicable"]
    if not applicable_results:
        selected = max(day_results, key=lambda item: item["stop_count"])
        return {
            **selected,
            "required_same_day_stop_count": 3,
            "max_same_day_stop_count": selected["stop_count"],
            "days": day_results,
        }

    selected = next(
        (item for item in applicable_results if item["status"] == "detour"),
        applicable_results[0],
    )
    return {**selected, "days": day_results}


def _not_applicable_day_order(visit_day, locations, valid_locations, reason_code, reason):
    return {
        "date": visit_day.isoformat(),
        "status": "not_applicable",
        "reason_code": reason_code,
        "reason": reason,
        "stop_count": len(locations),
        "valid_coordinate_count": len(valid_locations),
        "suggested_order": [location.name for location in locations],
        "evidence_source": "saved_itinerary",
    }


def _route_actions(risks):
    codes = {risk["code"] for risk in risks}
    actions = []
    if codes & {"route_interval_insufficient", "route_interval_tight", "route_chronological_conflict"}:
        actions.append("Adjust saved stop start times to leave enough time between adjacent stops.")
    if codes & {"route_service_unavailable", "route_coordinate_far_from_road"}:
        actions.append("Confirm stop coordinates and retry the driving route check.")
    if "route_detour" in codes:
        actions.append("Compare the current route order with the suggested same-day order.")
    if codes & {"transport_verification_required", "short_plane_leg", "long_walking_leg"}:
        actions.append("Confirm unverified transport legs with an appropriate timetable or operator.")
    return actions


def _dedupe_risks(risks):
    unique = []
    seen = set()
    for risk in risks:
        key = (risk["code"], risk["message"])
        if key in seen:
            continue
        seen.add(key)
        unique.append(risk)
    return unique


def _minutes_or_none(seconds):
    return round(seconds / 60, 1) if seconds is not None else None


def _risk(code, message):
    return {"code": code, "message": message}
