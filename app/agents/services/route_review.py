"""Deterministic route timing, transport, and order evidence."""

import logging
from collections import defaultdict

from django.utils import timezone

from .route_leg_timing import build_leg, has_coordinates
from .route_order_analysis import (
    aggregate_order_results,
    analyze_day_order,
    not_applicable_day_order,
)
from .route_osrm_client import fetch_route, leg_snap_distance, route_leg
from .route_risk_actions import dedupe_risks, risk, route_actions

logger = logging.getLogger(__name__)


def analyze_route_evidence(itinerary, locations):
    del itinerary  # Route analysis uses saved stop rows and configured OSRM only.
    route_legs = []
    day_order_results = []
    risks = []

    for visit_day, day_locations in _locations_by_day(locations).items():
        valid_locations = [location for location in day_locations if has_coordinates(location)]
        route_snapshot = fetch_route(valid_locations) if len(valid_locations) >= 2 else None
        if len(valid_locations) >= 2 and route_snapshot is None:
            risks.append(risk(
                "route_service_unavailable",
                "The driving route service could not verify one or more same-day legs.",
            ))

        if len(day_locations) >= 2:
            valid_indices = {location.id: index for index, location in enumerate(valid_locations)}
            for origin, destination in zip(day_locations, day_locations[1:]):
                if not has_coordinates(origin) or not has_coordinates(destination):
                    continue
                origin_index = valid_indices[origin.id]
                destination_index = valid_indices[destination.id]
                leg_snapshot = route_leg(route_snapshot, origin_index, destination_index)
                snap_distance = leg_snap_distance(route_snapshot, origin_index, destination_index)
                leg, leg_risks = build_leg(origin, destination, leg_snapshot, snap_distance)
                route_legs.append(leg)
                risks.extend(leg_risks)

        if len(day_locations) >= 3 and len(valid_locations) == len(day_locations):
            day_order_results.append(
                analyze_day_order(visit_day, day_locations, route_snapshot, risks)
            )
        elif len(day_locations) >= 3:
            day_order_results.append(not_applicable_day_order(
                visit_day,
                day_locations,
                valid_locations,
                "missing_coordinates",
                "Route-order analysis requires usable coordinates for every same-day stop.",
            ))
        else:
            day_order_results.append(not_applicable_day_order(
                visit_day,
                day_locations,
                valid_locations,
                "fewer_than_three_same_day_stops",
                "Route-order analysis requires at least three stops on the same local date.",
            ))

    risks = dedupe_risks(risks)
    actions = route_actions(risks)
    logger.info(
        "Route review processed %s stops into %s legs and %s day-order analyses with %s risks.",
        len(locations),
        len(route_legs),
        len(day_order_results),
        len(risks),
    )
    return {
        "route_legs": route_legs,
        "route_order_analysis": aggregate_order_results(day_order_results),
        "risks": risks,
        "suggested_next_actions": actions,
    }


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
