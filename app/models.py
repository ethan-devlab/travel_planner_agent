# coding=utf-8
from django.db import models
from django.contrib.auth.models import User

from .utils.budget_currency import BUDGET_CURRENCY_CHOICES, format_budget


class Tag(models.Model):
    name = models.CharField(max_length=30)

    def __str__(self):
        return self.name


class TravelMethod(models.TextChoices):
    BOAT = 'boat', 'Boat'
    PLANE = 'plane', 'Plane'
    WALK = 'walk', 'Walk'
    CAR = 'car', 'Car'
    HSR = 'hsr', 'High Speed Rail'
    TRAIN = 'train', 'Train'
    BUS = 'bus', 'Bus'


class Status(models.TextChoices):
    DRAFT = 'draft', 'Draft',
    ONGOING = 'ongoing', 'Ongoing',
    COMPLETED = 'completed', 'Completed',
    CANCELLED = 'cancelled', 'Cancelled',


class Itinerary(models.Model):
    owner = models.ForeignKey(User, on_delete=models.CASCADE, related_name='itineraries')
    title = models.CharField(max_length=100)
    start_date = models.DateField()
    end_date = models.DateField()
    location = models.CharField(max_length=100, blank=True, default='')
    budget = models.DecimalField(max_digits=10, decimal_places=2)
    budget_currency = models.CharField(max_length=3, choices=BUDGET_CURRENCY_CHOICES, default='TWD')
    is_public = models.BooleanField(default=False)
    tags = models.ManyToManyField(Tag, blank=True)
    collaborators = models.ManyToManyField(User, related_name='shared_itineraries', blank=True)
    updated_at = models.DateTimeField(auto_now=True)
    description = models.TextField(blank=True)
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.DRAFT)

    @property
    def budget_display(self):
        return format_budget(self.budget, self.budget_currency)


class Location(models.Model):
    itinerary = models.ForeignKey(Itinerary, on_delete=models.CASCADE, related_name='locations')
    name = models.CharField(max_length=100)
    visit_date = models.DateTimeField(null=True)
    travel_method = models.CharField(max_length=10, choices=TravelMethod.choices)
    latitude = models.FloatField()
    longitude = models.FloatField()
    route_order = models.PositiveIntegerField(default=0)
    note = models.TextField(blank=True)

    class Meta:
        ordering = ['route_order', 'visit_date', 'id']


class Expense(models.Model):
    EXPENSE_TYPE_CHOICES = [
        ('meal', 'Meal'),
        ('lodging', 'Lodging'),
        ('transport', 'Transport'),
        ('ticket', 'Ticket'),
        ('shopping', 'Shopping'),
        ('other', 'Other')
    ]
    location = models.ForeignKey(Location, on_delete=models.CASCADE, related_name='expenses')
    expense_type = models.CharField(max_length=20, choices=EXPENSE_TYPE_CHOICES)
    amount = models.DecimalField(max_digits=10, decimal_places=2)


class Event(models.Model):
    owner = models.ForeignKey(User, on_delete=models.CASCADE, related_name='events')
    event_name = models.CharField(max_length=100)
    date = models.DateField()
    color = models.CharField(max_length=20)

    def __str__(self):
        return f"{self.event_name} - {self.date}"
