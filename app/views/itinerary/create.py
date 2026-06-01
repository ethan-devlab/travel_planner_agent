# coding=utf-8

from ...forms import ItineraryForm
from .location_form import save_locations_from_post
from .persistence import save_itinerary_relations_from_post
from .route_helpers import routing_context
from django.db import transaction
from django.shortcuts import render, redirect
from django.contrib.auth.decorators import login_required
from django.views.decorators.http import require_http_methods


@login_required
@require_http_methods(["GET", "POST"])
def create_itinerary(request):
    if request.method == 'POST':
        form = ItineraryForm(request.POST)
        if form.is_valid():
            with transaction.atomic():
                itinerary = form.save(commit=False)
                itinerary.owner = request.user
                itinerary.save()
                form.save_m2m()
                save_itinerary_relations_from_post(itinerary, request.POST, request)
                save_locations_from_post(itinerary, request.POST)

            return redirect('itinerary_detail', id=itinerary.id)
    else:
        form = ItineraryForm()
    context = {'form': form}

    context.update(routing_context())
    return render(request, 'itinerary/create_itinerary.html', context)
