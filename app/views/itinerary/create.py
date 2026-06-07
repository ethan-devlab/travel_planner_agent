# coding=utf-8

from ...forms import ItineraryForm
from ...utils.budget_currency import resolve_budget_currency
from .location_form import save_locations_from_post
from .persistence import save_itinerary_relations_from_post
from .route_helpers import routing_context
from .calendar_sync import sync_itinerary_to_calendar
from django.db import transaction
from django.shortcuts import render, redirect
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.views.decorators.http import require_http_methods
import logging

logger = logging.getLogger(__name__)


@login_required
@require_http_methods(["GET", "POST"])
def create_itinerary(request):
    if request.method == 'POST':
        form = ItineraryForm(request.POST)
        if form.is_valid():
            with transaction.atomic():
                itinerary = form.save(commit=False)
                itinerary.owner = request.user
                itinerary.budget_currency = resolve_budget_currency(
                    itinerary.location,
                    form.cleaned_data.get("budget_currency_choice"),
                )
                itinerary.save()
                form.save_m2m()
                save_itinerary_relations_from_post(itinerary, request.POST, request)
                created_locations = save_locations_from_post(itinerary, request.POST)
                _sync_itinerary_to_calendar_if_requested(
                    itinerary,
                    created_locations,
                    request.POST,
                    request,
                )

            return redirect('itinerary_detail', id=itinerary.id)
    else:
        form = ItineraryForm()
    context = {'form': form}

    context.update(routing_context())
    return render(request, 'itinerary/create_itinerary.html', context)


def _sync_itinerary_to_calendar_if_requested(itinerary, locations, post_data, request):
    if post_data.get('sync_to_calendar') != 'on':
        return

    result = sync_itinerary_to_calendar(itinerary, locations)
    if result["status"] == "skipped":
        messages.info(request, "只有進行中的行程才會同步到行事曆。")
        return

    messages.success(request, f"已同步 {result['created_count']} 筆行程到行事曆。")
    logger.info("Create itinerary flow synced itinerary %s to %s calendar events.", itinerary.id, result["created_count"])
