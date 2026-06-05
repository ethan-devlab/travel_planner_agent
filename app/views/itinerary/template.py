# coding=utf-8

from ...forms import ItineraryForm
from ...models import Itinerary, Location, Expense
from django.contrib.auth.models import User
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.views.decorators.http import require_http_methods
from django.contrib import messages
from django.utils.timezone import get_current_timezone


@require_http_methods(["GET"])
def template_list(request):
    templates = Itinerary.objects.filter(is_public=True)
    return render(request, 'itinerary/template_list.html', {'templates': templates})


@login_required
@require_http_methods(["GET", "POST"])
def copy_itinerary(request):
    if request.method == 'POST':
        owner_username = request.POST.get('owner_username')
        id_ = request.POST.get('itinerary_id')

        # Get the original itinerary
        owner = get_object_or_404(User, username=owner_username)
        original_itinerary = get_object_or_404(Itinerary, pk=id_, owner=owner)

        try:
            # Create new itinerary by copying data
            new_itinerary = Itinerary.objects.create(
                owner=request.user,
                title=f"{original_itinerary.title} (副本)",
                location=original_itinerary.location,
                description=original_itinerary.description,
                start_date=original_itinerary.start_date,
                end_date=original_itinerary.end_date,
                budget=original_itinerary.budget,
                budget_currency=original_itinerary.budget_currency,
            )

            new_itinerary.save()

            # Copy tags
            for tag in original_itinerary.tags.all():
                new_itinerary.tags.add(tag)

            # Copy locations and expenses
            tz = get_current_timezone()
            for location in original_itinerary.locations.all():
                new_location = Location.objects.create(
                    itinerary=new_itinerary,
                    name=location.name,
                    travel_method=location.travel_method,
                    note=location.note,
                    visit_date=location.visit_date.astimezone(tz) if location.visit_date else None,
                    latitude=location.latitude,
                    longitude=location.longitude,
                    route_order=location.route_order,
                )

                # Copy expenses for this location
                for expense in location.expenses.all():
                    Expense.objects.create(
                        location=new_location,
                        expense_type=expense.expense_type,
                        amount=expense.amount
                    )

            messages.success(request, f'成功複製行程 "{original_itinerary.title}"！')
            return redirect('itinerary_detail', id=new_itinerary.pk)

        except Exception as e:
            messages.error(request, f'複製行程時發生錯誤：{str(e)}')
            return redirect('template_list')

    return redirect('template_list')
