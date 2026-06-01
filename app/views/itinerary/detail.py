# coding=utf-8

from ...models import Itinerary
from .route_helpers import routing_context, serialize_route_waypoints
from django.shortcuts import render, get_object_or_404
from django.http import HttpResponseForbidden
from django.views.decorators.http import require_http_methods

@require_http_methods(["GET"])
def itinerary_detail(request, id):
    itinerary = get_object_or_404(Itinerary, pk=id)
    if not itinerary.is_public and itinerary.owner != request.user and request.user not in itinerary.collaborators.all():
        return HttpResponseForbidden("You do not have permission to view this itinerary.")
    context = {
        'itinerary': itinerary,
        'route_waypoints': serialize_route_waypoints(itinerary),
    }
    context.update(routing_context())
    return render(request, 'itinerary/itinerary_detail.html', context)
