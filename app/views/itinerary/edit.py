# coding=utf-8

from ...forms import ItineraryForm
from ...models import Itinerary
from .location_form import save_locations_from_post
from .persistence import save_itinerary_relations_from_post
from .route_helpers import routing_context
from django.db import transaction
from django.shortcuts import render, get_object_or_404, redirect
from django.contrib.auth.decorators import login_required
from django.views.decorators.http import require_http_methods
from django.http import HttpResponseForbidden
from django.contrib import messages


def _can_edit_itinerary(itinerary, user):
    return itinerary.owner_id == user.id or itinerary.collaborators.filter(pk=user.pk).exists()


@login_required
@require_http_methods(["GET", "POST"])
def edit_itinerary(request, id):
    itinerary = get_object_or_404(Itinerary, pk=id)
    if not _can_edit_itinerary(itinerary, request.user):
        return HttpResponseForbidden("You do not have permission to edit this itinerary.")

    locations = itinerary.locations.all()

    if request.method == 'POST':
        form = ItineraryForm(request.POST, instance=itinerary)
        if form.is_valid():
            with transaction.atomic():
                itinerary = form.save()
                save_itinerary_relations_from_post(itinerary, request.POST, request)
                save_locations_from_post(itinerary, request.POST, clear_existing=True)

            messages.success(request, f'行程 「{itinerary.title}」 已成功更新！')
            return redirect(request.path)
    else:
        initial = {
            'custom_tags': ', '.join([t.name for t in itinerary.tags.all()]),
            'collaborators': ', '.join([c.username for c in itinerary.collaborators.all()])
        }
        form = ItineraryForm(instance=itinerary, initial=initial)

    context = {
        'form': form,
        'locations': locations
    }
    context.update(routing_context())
    return render(request, 'itinerary/edit_itinerary.html', context)
