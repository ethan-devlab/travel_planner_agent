# coding=utf-8

from ...models import Itinerary
from django.contrib.auth.decorators import login_required
from django.views.decorators.http import require_http_methods
from django.shortcuts import render


@login_required
@require_http_methods(["GET"])
def my_itineraries(request):
    itineraries = Itinerary.objects.filter(owner=request.user).order_by('-updated_at')
    return render(request, 'itinerary/my_itineraries.html', {'itineraries': itineraries})


@login_required
@require_http_methods(["GET"])
def shared_itineraries(request):
    itineraries = Itinerary.objects.filter(collaborators=request.user).order_by('-updated_at')
    return render(request, 'itinerary/shared_itineraries.html', {'itineraries': itineraries})