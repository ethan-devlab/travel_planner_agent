"""OSRM driving route and trip client helpers for route review evidence."""

import logging

import requests
from django.conf import settings

from app.views.itinerary.route_helpers import normalize_osrm_base_url

logger = logging.getLogger(__name__)


def fetch_route(locations):
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


def fetch_trip(locations):
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


def route_leg(route_snapshot, origin_index, destination_index):
    if route_snapshot is None or destination_index != origin_index + 1:
        return None
    legs = route_snapshot["legs"]
    return legs[origin_index] if origin_index < len(legs) else None


def leg_snap_distance(route_snapshot, origin_index, destination_index):
    if route_snapshot is None:
        return None
    waypoints = route_snapshot["waypoints"]
    if destination_index >= len(waypoints):
        return None
    return max(
        float(waypoints[origin_index].get("distance") or 0),
        float(waypoints[destination_index].get("distance") or 0),
    )


def _osrm_request(service, locations, params):
    base_url, _ = normalize_osrm_base_url(settings.ROUTING_SERVICE_URL)
    if not base_url:
        return None
    coordinates = ";".join(f"{location.longitude},{location.latitude}" for location in locations)
    try:
        # Route review treats OSRM as driving-only evidence, matching existing itinerary guidance.
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
