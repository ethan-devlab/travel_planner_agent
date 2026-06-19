"""Coordinate-derived geography evidence for saved itinerary stops."""

import logging
import math

from .nominatim import reverse_geocode_cached

logger = logging.getLogger(__name__)


def analyze_geography_evidence(itinerary, locations):
    del itinerary  # Geography is derived from saved stop coordinates only.
    geographies = []
    unavailable_count = 0
    missing_coordinate_count = 0
    country_codes = set()

    for location in locations:
        if not _has_coordinates(location):
            missing_coordinate_count += 1
            geographies.append(_unavailable_geography(location.name, "missing_coordinates"))
            continue

        geography = reverse_geocode_cached(location.latitude, location.longitude)
        geographies.append({"name": location.name, **geography})
        if geography["status"] != "ok":
            unavailable_count += 1
            continue
        if geography["country_code"]:
            country_codes.add(geography["country_code"])

    risks = []
    actions = []
    if missing_coordinate_count:
        risks.append(_risk(
            "geography_missing_coordinates",
            "Some stops have no usable coordinates, so their city and country could not be checked.",
        ))
        actions.append("Save coordinates for every stop before relying on the geography review.")
    if unavailable_count:
        risks.append(_risk(
            "geography_unavailable",
            "City and country evidence was unavailable for some stops.",
        ))
        actions.append("Retry the stop review when reverse geocoding is available.")
    if len(country_codes) > 1:
        risks.append(_risk(
            "multiple_countries",
            "Saved stop coordinates resolve to more than one country; confirm that the trip is intentionally cross-border.",
        ))
        actions.append("Confirm the cross-border order and transport for stops in different countries.")

    logger.info(
        "Geography review processed %s stops with %s missing coordinates, %s unavailable results, and %s countries.",
        len(locations),
        missing_coordinate_count,
        unavailable_count,
        len(country_codes),
    )
    return {
        "location_geographies": geographies,
        "risks": risks,
        "suggested_next_actions": actions,
    }


def _has_coordinates(location):
    latitude = location.latitude
    longitude = location.longitude
    return (
        math.isfinite(latitude)
        and math.isfinite(longitude)
        and -90 <= latitude <= 90
        and -180 <= longitude <= 180
        and not (latitude == 0 and longitude == 0)
    )


def _unavailable_geography(name, reason):
    return {
        "name": name,
        "status": "geography_unavailable",
        "reason": reason,
        "provider": "nominatim",
        "cache_status": "not_checked",
        "stale": False,
        "city": "",
        "state": "",
        "country": "",
        "country_code": "",
        "display_name": "",
    }


def _risk(code, message):
    return {"code": code, "message": message}
