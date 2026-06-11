# coding=utf-8

from django.urls import path
from .views.auth import auth
from .views.itinerary import my_itinerary, search, create, edit, delete, detail, template
from .views.weather import weather
from .views.exchange import exchange
from .views.calendar import calendar
from .views.planner_agent import planner_agent

urlpatterns = [
    path('', search.search_itineraries, name='search'),
    path('search/', search.search_itineraries, name='search'),
    path('create/', create.create_itinerary, name='create'),
    path('templates/', template.template_list, name='template_list'),
    path('weather/', weather.index, name='weather'),
    path('copy/', template.copy_itinerary, name='copy_itinerary'),
    path('login/', auth.login_view, name='login'),
    path('demo-login/', auth.demo_login_view, name='demo_login'),
    path('logout/', auth.logout_view, name='logout'),
    path('register/', auth.register, name='register'),
    path('itinerary/<uuid:id>/', detail.itinerary_detail, name='itinerary_detail'),
    path('my-itineraries/', my_itinerary.my_itineraries, name='my_itineraries'),
    path('shared-itineraries/', my_itinerary.shared_itineraries, name='shared_itineraries'),
    path('my-itineraries/<uuid:id>/sync-calendar/', my_itinerary.sync_itinerary_calendar, name='sync_itinerary_calendar'),
    path('edit/<uuid:id>/', edit.edit_itinerary, name='edit_itinerary'),
    path('edit/<uuid:id>/ai-check/', edit.ai_itinerary_check, name='ai_itinerary_check'),
    path('delete/<uuid:id>/', delete.delete_itinerary, name='delete_itinerary'),
    path('exchange/', exchange.exchange_view, name='exchange'),
    path('calendar/', calendar.calendar_view, name='calendar'),
    path('planner-agent/', planner_agent.planner_agent_view, name='planner_agent'),
    path('planner-agent/stream/', planner_agent.planner_agent_stream_view, name='planner_agent_stream'),
    path('api/events/', calendar.get_events, name='get_events'),
    path('api/add_event/', calendar.add_event, name='add_event'),
    path('api/update_event/<uuid:event_id>/', calendar.update_event, name='update_event'),
    path('api/delete_event/<uuid:event_id>/', calendar.delete_event, name='delete_event'),
]
