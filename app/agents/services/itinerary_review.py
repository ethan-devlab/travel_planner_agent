"""Orchestrate focused evidence collection for itinerary review."""

import logging

from .geography_review import analyze_geography_evidence
from .route_review import analyze_route_evidence

logger = logging.getLogger(__name__)

CHECK_TYPES = {"overall", "stops", "route", "budget"}


def build_itinerary_review_evidence(itinerary, locations, check_type):
    if check_type not in CHECK_TYPES:
        raise ValueError("check_type must be one of: overall, stops, route, budget")

    result = {
        "location_geographies": [],
        "route_legs": [],
        "route_order_analysis": {
            "status": "not_requested",
            "reason_code": "route_check_not_requested",
            "reason": "Route and route-order analyses were not requested for this review.",
            "days": [],
        },
        "risks": [],
        "suggested_next_actions": [],
    }
    if check_type in {"overall", "route"}:
        _merge_evidence(result, analyze_route_evidence(itinerary, locations))
    if check_type in {"overall", "stops"}:
        _merge_evidence(result, analyze_geography_evidence(itinerary, locations))

    result["risks"] = _dedupe(result["risks"], lambda item: (item["code"], item["message"]))
    result["suggested_next_actions"] = _dedupe(result["suggested_next_actions"], lambda item: item)
    logger.info(
        "Built itinerary review evidence for check type %s with %s route legs, %s geographies, and %s risks.",
        check_type,
        len(result["route_legs"]),
        len(result["location_geographies"]),
        len(result["risks"]),
    )
    return result


def _merge_evidence(target, evidence):
    for key in ("location_geographies", "route_legs"):
        if key in evidence:
            target[key] = evidence[key]
    if "route_order_analysis" in evidence:
        target["route_order_analysis"] = evidence["route_order_analysis"]
    target["risks"].extend(evidence.get("risks", []))
    target["suggested_next_actions"].extend(evidence.get("suggested_next_actions", []))


def _dedupe(values, key):
    unique = []
    seen = set()
    for value in values:
        marker = key(value)
        if marker in seen:
            continue
        seen.add(marker)
        unique.append(value)
    return unique
