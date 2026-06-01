# coding=utf-8
from django.contrib import admin
from .models import Itinerary, Tag, Location, Expense, Event


# Register your models here.
@admin.register(Itinerary)
class ItineraryAdmin(admin.ModelAdmin):
    list_display = ("title", "owner", "start_date", "end_date", "budget", "is_public", "status", "updated_at")
    list_filter = ("is_public", "start_date")
    search_fields = ("title", "owner__username")


@admin.register(Tag)
class TagAdmin(admin.ModelAdmin):
    list_display = ("name",)


@admin.register(Location)
class LocationAdmin(admin.ModelAdmin):
    list_display = ("name", "visit_date", "travel_method")
    list_filter = ("travel_method",)


admin.site.register(Expense)
admin.site.register(Event)