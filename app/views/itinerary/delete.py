# coding=utf-8

from ...models import Itinerary
from django.shortcuts import get_object_or_404, redirect
from django.contrib.auth.decorators import login_required
from django.views.decorators.http import require_POST

@login_required
# @require_POST
def delete_itinerary(request, id):
    itinerary = get_object_or_404(Itinerary, pk=id, owner=request.user)
    itinerary.delete()
    return redirect('my_itineraries')