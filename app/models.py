# coding=utf-8
import logging
import uuid

from django.conf import settings
from django.db import models
from django.contrib.auth.models import AbstractUser

from .utils.budget_currency import BUDGET_CURRENCY_CHOICES, format_budget

logger = logging.getLogger(__name__)


def _user_uuid5_namespace():
    return uuid.UUID(settings.USER_ID_UUID5_NAMESPACE)


def user_uuid5(username):
    return uuid.uuid5(_user_uuid5_namespace(), f"user:{username}")


class User(AbstractUser):
    id = models.UUIDField(primary_key=True, editable=False)

    def save(self, *args, **kwargs):
        if not self.id:
            self.id = user_uuid5(self.username)
            logger.debug("Generated UUID5 user id for username length %s.", len(self.username or ""))
        super().save(*args, **kwargs)


class Tag(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
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
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    owner = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='itineraries')
    title = models.CharField(max_length=100)
    start_date = models.DateField()
    end_date = models.DateField()
    location = models.CharField(max_length=100, blank=True, default='')
    budget = models.DecimalField(max_digits=10, decimal_places=2)
    budget_currency = models.CharField(max_length=3, choices=BUDGET_CURRENCY_CHOICES, default='TWD')
    is_public = models.BooleanField(default=False)
    tags = models.ManyToManyField(Tag, through='ItineraryTag', blank=True)
    collaborators = models.ManyToManyField(settings.AUTH_USER_MODEL, through='ItineraryCollaborator', related_name='shared_itineraries', blank=True)
    updated_at = models.DateTimeField(auto_now=True)
    description = models.TextField(blank=True)
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.DRAFT)

    @property
    def budget_display(self):
        return format_budget(self.budget, self.budget_currency)


class Location(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
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


class ReverseGeocodeCache(models.Model):
    """Persistent provider result for a normalized coordinate pair."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    provider = models.CharField(max_length=32, default='nominatim')
    coordinate_key = models.CharField(max_length=64)
    latitude = models.FloatField()
    longitude = models.FloatField()
    city = models.CharField(max_length=150, blank=True, default='')
    state = models.CharField(max_length=150, blank=True, default='')
    country = models.CharField(max_length=150, blank=True, default='')
    country_code = models.CharField(max_length=2, blank=True, default='')
    display_name = models.TextField(blank=True, default='')
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=['provider', 'coordinate_key'],
                name='unique_reverse_geocode_provider_coordinate',
            ),
        ]


class Expense(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
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
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    owner = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='events')
    event_name = models.CharField(max_length=100)
    date = models.DateField()
    color = models.CharField(max_length=20)

    def __str__(self):
        return f"{self.event_name} - {self.date}"


class ItineraryTag(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    itinerary = models.ForeignKey(Itinerary, on_delete=models.CASCADE)
    tag = models.ForeignKey(Tag, on_delete=models.CASCADE)

    class Meta:
        db_table = 'app_itinerary_tags'
        unique_together = (('itinerary', 'tag'),)


class ItineraryCollaborator(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    itinerary = models.ForeignKey(Itinerary, on_delete=models.CASCADE)
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)

    class Meta:
        db_table = 'app_itinerary_collaborators'
        unique_together = (('itinerary', 'user'),)
