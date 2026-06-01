# coding=utf-8

from ...forms import SearchForm
from ...models import Itinerary
from django.shortcuts import render
from django.views.decorators.http import require_http_methods


@require_http_methods(["GET"])
def search_itineraries(request):
    form = SearchForm(request.GET or None)
    itineraries = Itinerary.objects.filter(is_public=True)

    if form.is_valid():
        q = form.cleaned_data.get("q")
        travel_method = form.cleaned_data.get("travel_method")
        budget = form.cleaned_data.get("budget")
        location = form.cleaned_data.get("location")
        transport = form.cleaned_data.get("transport")
        start_date = form.cleaned_data.get("start_date")
        end_date = form.cleaned_data.get("end_date")

        if q:
            itineraries = itineraries.filter(title__icontains=q)

        if travel_method:
            itineraries = itineraries.filter(locations__travel_method__icontains=travel_method)

        if budget:
            itineraries = itineraries.filter(budget__icontains=budget)

        if location:
            # three locations can be searched, two for the itinerary and one for the locations
            itineraries = itineraries.filter(locations__name__icontains=location) | \
                          itineraries.filter(title__icontains=location) | \
                          itineraries.filter(location__icontains=location)

        if transport:
            itineraries = itineraries.filter(locations__note__icontains=transport)

        if start_date:
            itineraries = itineraries.filter(start_date__gte=start_date)

        if end_date:
            itineraries = itineraries.filter(end_date__lte=end_date)

        itineraries = itineraries.distinct()

    return render(request, 'itinerary/search.html', {'form': form, 'results': itineraries})
