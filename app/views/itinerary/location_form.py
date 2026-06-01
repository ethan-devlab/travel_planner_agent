# coding=utf-8
import logging
from datetime import datetime

from django.utils import timezone

from ...models import Expense, Location

logger = logging.getLogger(__name__)


def _post_list(post_data, name):
    return post_data.getlist(name)


def _list_item(values, index, default=''):
    return values[index] if index < len(values) else default


def _parse_float(value, default=0.0):
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _parse_int(value, default=0):
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _parse_visit_date(value):
    if not value:
        return None
    current_tz = timezone.get_current_timezone()
    parsed = datetime.strptime(value, "%Y-%m-%dT%H:%M")
    return timezone.make_aware(parsed, current_tz)


def _location_rows(post_data):
    names = _post_list(post_data, 'location_name[]')
    methods = _post_list(post_data, 'travel_method[]')
    notes = _post_list(post_data, 'transport_note[]')
    visit_dates = _post_list(post_data, 'visit_date[]')
    latitudes = _post_list(post_data, 'location_latitude[]')
    longitudes = _post_list(post_data, 'location_longitude[]')
    route_orders = _post_list(post_data, 'route_order[]')

    for index, name in enumerate(names):
        yield {
            'index': index,
            'name': name,
            'travel_method': _list_item(methods, index),
            'note': _list_item(notes, index),
            'visit_date': _list_item(visit_dates, index),
            'latitude': _list_item(latitudes, index, None),
            'longitude': _list_item(longitudes, index, None),
            'route_order': _list_item(route_orders, index, index),
        }


def _has_required_location_fields(row):
    return row['name'] and row['travel_method'] and row['visit_date']


def _location_kwargs(itinerary, row):
    return {
        'itinerary': itinerary,
        'name': row['name'],
        'travel_method': row['travel_method'],
        'note': row['note'],
        'visit_date': _parse_visit_date(row['visit_date']),
        'latitude': _parse_float(row['latitude']),
        'longitude': _parse_float(row['longitude']),
        'route_order': _parse_int(row['route_order'], row['index']),
    }


def _save_expenses(location, post_data, row_index):
    expense_types = _post_list(post_data, f'expense_type_{row_index}[]')
    expense_amounts = _post_list(post_data, f'expense_amount_{row_index}[]')
    expense_count = 0

    for expense_type, amount in zip(expense_types, expense_amounts):
        if not expense_type or not amount:
            continue
        Expense.objects.create(
            location=location,
            expense_type=expense_type,
            amount=amount,
        )
        expense_count += 1

    return expense_count


def save_locations_from_post(itinerary, post_data, clear_existing=False):
    if clear_existing:
        deleted_count, _ = itinerary.locations.all().delete()
        logger.info("Cleared %s existing locations for itinerary %s.", deleted_count, itinerary.id)

    created_locations = []
    skipped_count = 0
    expense_count = 0

    for row in _location_rows(post_data):
        if not _has_required_location_fields(row):
            skipped_count += 1
            logger.debug(
                "Skipped incomplete location row %s for itinerary %s.",
                row['index'],
                itinerary.id,
            )
            continue

        try:
            location = Location.objects.create(**_location_kwargs(itinerary, row))
        except ValueError as exc:
            skipped_count += 1
            logger.warning(
                "Skipped itinerary location row %s with invalid visit date: %s",
                row['index'],
                exc,
            )
            continue

        created_locations.append(location)
        expense_count += _save_expenses(location, post_data, row['index'])

    logger.info(
        "Saved %s locations and %s expenses for itinerary %s; skipped %s rows.",
        len(created_locations),
        expense_count,
        itinerary.id,
        skipped_count,
    )

    return created_locations
