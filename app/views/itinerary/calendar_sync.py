# coding=utf-8
import logging

from ...models import Event, Status

logger = logging.getLogger(__name__)

SYNC_EVENT_COLOR = "green"


def sync_itinerary_to_calendar(itinerary, locations):
    if itinerary.status != Status.ONGOING:
        return {
            "status": "skipped",
            "reason": "status_not_ongoing",
            "created_count": 0,
        }

    events_to_sync = []
    for location in locations:
        if not location.visit_date:
            continue
        events_to_sync.append({
            "event_name": f"{itinerary.title}｜{location.name}",
            "date": location.visit_date.date(),
            "color": SYNC_EVENT_COLOR,
        })

    if not events_to_sync:
        events_to_sync.append({
            "event_name": itinerary.title,
            "date": itinerary.start_date,
            "color": SYNC_EVENT_COLOR,
        })

    created_count = 0
    for event_data in events_to_sync:
        _, created = Event.objects.get_or_create(
            owner=itinerary.owner,
            event_name=event_data["event_name"],
            date=event_data["date"],
            color=event_data["color"],
        )
        if created:
            created_count += 1

    logger.info(
        "Synced itinerary %s to calendar with %s new events out of %s candidates.",
        itinerary.id,
        created_count,
        len(events_to_sync),
    )
    return {
        "status": "ok",
        "created_count": created_count,
        "candidate_count": len(events_to_sync),
    }
