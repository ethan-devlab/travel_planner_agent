"""Adjacent route leg timing and transport-status analysis."""

import math

from .route_risk_actions import risk

WALK_ROUTE_FACTOR = 1.25
WALK_SPEED_KMH = 4.8
LONG_WALK_DISTANCE_KM = 5.0
LONG_WALK_MINUTES = 90.0
SHORT_PLANE_DISTANCE_KM = 100.0
MAX_ROAD_SNAP_METERS = 500.0
TIGHT_MINIMUM_SECONDS = 15 * 60
TIGHT_DURATION_RATIO = 0.20


def build_leg(origin, destination, route_leg, snap_distance):
    # A location's travel_method represents the incoming leg from the previous stop.
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
                risks.append(risk(
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
            risks.append(risk(
                "long_walking_leg",
                "A planned walking leg is longer than 5 kilometres or 90 estimated minutes.",
            ))
    else:
        timing_status = "not_verified"
        status = "verification_required"
        risks.append(risk(
            "transport_verification_required",
            "Bus, rail, high-speed rail, plane, and boat legs require a timetable-capable provider.",
        ))
        if method == "plane" and direct_distance_km < SHORT_PLANE_DISTANCE_KM:
            risks.append(risk(
                "short_plane_leg",
                "A planned plane leg is under 100 kilometres and may be impractical.",
            ))

    if available_seconds <= 0:
        status = "chronological_conflict"
        timing_status = "chronological_conflict"
        risks.append(risk(
            "route_chronological_conflict",
            "A later route stop does not have a later scheduled start time.",
        ))
    elif timing_status == "insufficient":
        risks.append(risk(
            "route_interval_insufficient",
            "Estimated travel time exceeds the available interval between scheduled stop starts.",
        ))
    elif timing_status == "tight":
        risks.append(risk(
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


def has_coordinates(location):
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


def _minutes_or_none(seconds):
    return round(seconds / 60, 1) if seconds is not None else None
