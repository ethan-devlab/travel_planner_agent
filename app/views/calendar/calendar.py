from django.http import JsonResponse
from django.shortcuts import render
from django.views.decorators.csrf import ensure_csrf_cookie
from django.views.decorators.http import require_http_methods
from django.contrib.auth.decorators import login_required
from ...models import Event
import json
import datetime
import logging

logger = logging.getLogger(__name__)

@login_required
@ensure_csrf_cookie
@require_http_methods(["GET"])
def calendar_view(request):
    return render(request, 'calendar/calendar.html')


@require_http_methods(["GET"])
def get_events(request):
    if not request.user.is_authenticated:
        return JsonResponse({'error': 'Unauthorized'}, status=401)
    
    events = Event.objects.filter(owner=request.user)
    data = []
    for event in events:
        data.append({
            'id': str(event.id),
            'eventName': event.event_name,
            'date': event.date.strftime('%Y-%m-%d'),
            'color': event.color,
            'calendar': event.color
        })
    return JsonResponse(data, safe=False)

@require_http_methods(["POST"])
def add_event(request):
    if not request.user.is_authenticated:
        return JsonResponse({'error': 'Unauthorized'}, status=401)
    
    if request.method == 'POST':
        try:
            data = json.loads(request.body)
            name = data.get('eventName')
            date = datetime.datetime.strptime(data.get('date'), '%Y-%m-%d').date()
            color = data.get('color')
            
            event = Event.objects.create(owner=request.user, event_name=name, date=date, color=color)
            logger.info("Calendar event %s created by user %s", event.id, request.user.id)
            return JsonResponse({
                'status': 'ok', 
                'id': str(event.id),
                'eventName': name
            })
        except Exception as e:
            logger.warning("Failed to create calendar event for user %s: %s", request.user.id, e)
            return JsonResponse({'error': str(e)}, status=400)
    return JsonResponse({'error': 'Invalid method'}, status=405)

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
