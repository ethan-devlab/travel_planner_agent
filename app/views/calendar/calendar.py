import datetime
import json
import logging

from django.contrib.auth.decorators import login_required
from django.db import transaction
from django.http import JsonResponse
from django.shortcuts import render
from django.views.decorators.csrf import ensure_csrf_cookie
from django.views.decorators.http import require_http_methods

from ...models import Event

logger = logging.getLogger(__name__)

ALLOWED_EVENT_COLORS = {"orange", "blue", "yellow", "green"}


def _serialize_event(event):
    return {
        'id': str(event.id),
        'eventName': event.event_name,
        'date': event.date.strftime('%Y-%m-%d'),
        'color': event.color,
        'calendar': event.color,
    }


def _parse_event_payload(request):
    try:
        data = json.loads(request.body or b'{}')
    except json.JSONDecodeError:
        return None, JsonResponse({'error': 'Invalid JSON payload'}, status=400)

    if not isinstance(data, dict):
        return None, JsonResponse({'error': 'Payload must be an object'}, status=400)

    return data, None


def _parse_event_fields(data):
    name = str(data.get('eventName') or '').strip()
    if not name:
        return None, JsonResponse({'error': 'eventName is required'}, status=400)

    date_raw = str(data.get('date') or '').strip()
    if not date_raw:
        return None, JsonResponse({'error': 'date is required'}, status=400)

    try:
        date = datetime.datetime.strptime(date_raw, '%Y-%m-%d').date()
    except ValueError:
        return None, JsonResponse({'error': 'date must be YYYY-MM-DD'}, status=400)

    color = str(data.get('color') or '').strip().lower()
    if color not in ALLOWED_EVENT_COLORS:
        return None, JsonResponse({'error': 'color must be one of orange, blue, yellow, or green'}, status=400)

    return {
        'event_name': name,
        'date': date,
        'color': color,
    }, None


@login_required
@ensure_csrf_cookie
@require_http_methods(["GET"])
def calendar_view(request):
    return render(request, 'calendar/calendar.html')


@require_http_methods(["GET"])
def get_events(request):
    if not request.user.is_authenticated:
        return JsonResponse({'error': 'Unauthorized'}, status=401)

    events = Event.objects.filter(owner=request.user).order_by('date', 'id')
    return JsonResponse([_serialize_event(event) for event in events], safe=False)


@require_http_methods(["POST"])
def add_event(request):
    if not request.user.is_authenticated:
        return JsonResponse({'error': 'Unauthorized'}, status=401)

    try:
        data, error_response = _parse_event_payload(request)
        if error_response:
            return error_response

        fields, field_error = _parse_event_fields(data)
        if field_error:
            return field_error

        with transaction.atomic():
            event = Event.objects.create(owner=request.user, **fields)
    except Exception as e:
        logger.warning("Failed to create calendar event for user %s: %s", request.user.id, e)
        return JsonResponse({'error': str(e)}, status=400)

    logger.info("Calendar event %s created by user %s", event.id, request.user.id)
    return JsonResponse({
        'status': 'ok',
        'id': str(event.id),
        'eventName': event.event_name,
        'event': _serialize_event(event),
    })


@require_http_methods(["POST", "PATCH"])
def update_event(request, event_id):
    if not request.user.is_authenticated:
        return JsonResponse({'error': 'Unauthorized'}, status=401)

    event = Event.objects.filter(id=event_id, owner=request.user).first()
    if event is None:
        logger.warning("User %s attempted to update unavailable calendar event %s", request.user.id, event_id)
        return JsonResponse({'error': 'Event not found'}, status=404)

    try:
        data, error_response = _parse_event_payload(request)
        if error_response:
            return error_response

        fields, field_error = _parse_event_fields(data)
        if field_error:
            return field_error

        with transaction.atomic():
            event.event_name = fields['event_name']
            event.date = fields['date']
            event.color = fields['color']
            event.save(update_fields=['event_name', 'date', 'color'])
    except Exception as e:
        logger.warning("Failed to update calendar event %s for user %s: %s", event_id, request.user.id, e)
        return JsonResponse({'error': str(e)}, status=400)

    logger.info("Calendar event %s updated by user %s via %s", event.id, request.user.id, request.method)
    return JsonResponse({
        'status': 'ok',
        'event': _serialize_event(event),
    })


@require_http_methods(["DELETE"])
def delete_event(request, event_id):
    if not request.user.is_authenticated:
        return JsonResponse({'error': 'Unauthorized'}, status=401)

    event = Event.objects.filter(id=event_id, owner=request.user).first()
    if event is None:
        logger.warning("User %s attempted to delete unavailable calendar event %s", request.user.id, event_id)
        return JsonResponse({'error': 'Event not found'}, status=404)

    try:
        event.delete()
        logger.info("Calendar event %s deleted by user %s", event_id, request.user.id)
        return JsonResponse({'status': 'ok'})
    except Exception as e:
        logger.warning("Failed to delete calendar event %s for user %s: %s", event_id, request.user.id, e)
        return JsonResponse({'error': str(e)}, status=400)
