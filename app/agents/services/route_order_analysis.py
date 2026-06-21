"""Same-day stop order analysis for route review evidence."""

from .route_osrm_client import fetch_trip
from .route_risk_actions import risk

DETOUR_MINIMUM_SECONDS = 15 * 60
DETOUR_MINIMUM_RATIO = 0.20


def analyze_day_order(visit_day, locations, route_snapshot, risks):
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

    # OSRM trip optimization keeps the saved first and last stops fixed.
    trip_snapshot = fetch_trip(locations)
    if trip_snapshot is None:
        risks.append(risk(
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
        risks.append(risk(
            "route_detour",
            f"The current {qualifier} is at least 20% and 15 minutes longer than the optimized order.",
        ))
    return result


def aggregate_order_results(day_results):
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


def not_applicable_day_order(visit_day, locations, valid_locations, reason_code, reason):
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
