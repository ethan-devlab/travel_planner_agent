# coding=utf-8

from ...models import Itinerary
from .calendar_sync import sync_itinerary_to_calendar
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.views.decorators.http import require_http_methods, require_POST
from django.shortcuts import render, get_object_or_404, redirect


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


@login_required
@require_POST
def sync_itinerary_calendar(request, id):
    itinerary = get_object_or_404(Itinerary, pk=id, owner=request.user)
    result = sync_itinerary_to_calendar(itinerary, itinerary.locations.all())

    if result["status"] == "skipped":
        messages.info(request, "只有進行中的行程才可以匯入行事曆。")
    else:
        messages.success(request, f"已匯入 {result['created_count']} 筆行程到行事曆。")

    return redirect('my_itineraries')
