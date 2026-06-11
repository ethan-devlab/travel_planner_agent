import json
import re
import uuid
from decimal import Decimal
from pathlib import Path
from unittest.mock import patch

from django.conf import settings
from django.contrib.auth import get_user_model
from django.test import Client, TestCase, override_settings
from django.urls import reverse
from django.utils import timezone
import requests

from app.utils.budget_currency import infer_budget_currency
from app.models import Event, Itinerary, Tag
from app.views.itinerary.route_helpers import normalize_routing_service_url
from app.views.weather import weather as weather_view

User = get_user_model()


class FakeResponse:
    def __init__(self, payload, error=None):
        self.payload = payload
        self.error = error

    def raise_for_status(self):
        if self.error:
            raise self.error

    def json(self):
        return self.payload


def invoke_tool(tool_obj, **kwargs):
    if hasattr(tool_obj, "invoke"):
        return tool_obj.invoke(kwargs)
    return tool_obj(**kwargs)


class WeatherApiTests(TestCase):
    def test_normalize_weather_city_query_adds_taiwan_for_taichung_alias(self):
        normalized_city, geocoding_query = weather_view.normalize_weather_city_query('台中')

        self.assertEqual(normalized_city, '台中市')
        self.assertEqual(geocoding_query, '台中市, Taiwan')

    def test_geocode_city_uses_first_result_and_keeps_user_city_name(self):
        payload = [
            {'name': 'Taipei', 'lat': 25.0375198, 'lon': 121.5636796, 'country': 'TW'},
            {'name': 'Taibei', 'lat': 34.490729, 'lon': 107.332195, 'country': 'CN'},
        ]

        with patch.object(weather_view.requests, 'get', return_value=FakeResponse(payload)) as request_mock:
            result = weather_view.geocode_city('台北市', 'api-key')

        self.assertEqual(result['city'], '台北市')
        self.assertEqual(result['country'], 'TW')
        self.assertEqual(result['lat'], 25.0375198)
        self.assertEqual(result['lon'], 121.5636796)
        self.assertEqual(request_mock.call_args.kwargs['params']['limit'], 5)

    def test_geocode_city_prefers_taiwan_match_for_taichung_alias(self):
        payload = [
            {'name': 'Taichung', 'lat': 24.1477, 'lon': 120.6736, 'country': 'US'},
            {'name': '台中市', 'lat': 24.1631, 'lon': 120.6478, 'country': 'TW'},
        ]

        with patch.object(weather_view.requests, 'get', return_value=FakeResponse(payload)) as request_mock:
            result = weather_view.geocode_city('台中', 'api-key')

        self.assertEqual(result['city'], '台中市')
        self.assertEqual(result['country'], 'TW')
        self.assertEqual(result['matched_name'], '台中市')
        self.assertEqual(result['lat'], 24.1631)
        self.assertEqual(result['lon'], 120.6478)
        self.assertEqual(request_mock.call_args.kwargs['params']['q'], '台中市, Taiwan')

    def test_geocode_city_empty_response_raises_lookup_error(self):
        with patch.object(weather_view.requests, 'get', return_value=FakeResponse([])):
            with self.assertRaises(weather_view.WeatherLookupError):
                weather_view.geocode_city('Unknown', 'api-key')

    def test_missing_weather_api_key_raises_lookup_error(self):
        with self.assertRaises(weather_view.WeatherLookupError):
            weather_view.geocode_city('Taipei', None)

    def test_current_weather_request_failure_raises_lookup_error(self):
        response = FakeResponse({}, requests.RequestException('service unavailable'))
        with patch.object(weather_view.requests, 'get', return_value=response):
            with self.assertLogs('app.views.weather.weather', level='ERROR'):
                with self.assertRaises(weather_view.WeatherLookupError):
                    weather_view.fetch_current_weather(25.0, 121.0, 'api-key')

    def test_fetch_weather_and_forecast_formats_forecast_without_gust(self):
        current_payload = {
            'main': {'temp': 28, 'feels_like': 30, 'humidity': 70},
            'weather': [{'description': 'clear sky', 'icon': '01d'}],
            'visibility': 10000,
            'wind': {'speed': 3},
            'clouds': {'all': 10},
            'dt': 1710000000,
        }
        forecast_payload = {
            'list': [{
                'dt': 1710003600,
                'main': {
                    'temp': 29,
                    'humidity': 65,
                    'feels_like': 31,
                    'temp_min': 27,
                    'temp_max': 30,
                },
                'weather': [{'description': 'few clouds', 'icon': '02d'}],
                'visibility': 9000,
                'wind': {'speed': 2},
                'clouds': {'all': 25},
                'pop': 0.2,
            }]
        }

        with patch.object(weather_view, 'geocode_city', return_value={'city': 'Taipei', 'lat': 25, 'lon': 121, 'country': 'TW'}), \
             patch.object(weather_view, 'fetch_current_weather', return_value=current_payload), \
             patch.object(weather_view, 'fetch_forecast', return_value=forecast_payload):
            weather_data, forecasts = weather_view.fetch_weather_and_forecast('Taipei', 'api-key')

        self.assertEqual(weather_data['city'], 'Taipei')
        self.assertEqual(weather_data['country'], 'TW')
        self.assertEqual(forecasts[0]['wind_gust'], 0)
        self.assertEqual(forecasts[0]['pop'], 20)


class BudgetCurrencyTests(TestCase):
    def test_infer_budget_currency_prefers_location_hint(self):
        self.assertEqual(infer_budget_currency('Tokyo, Japan'), 'JPY')
        self.assertEqual(infer_budget_currency('台中市'), 'TWD')
        self.assertEqual(infer_budget_currency('Seoul, Korea'), 'KRW')


class UUIDPrimaryKeyTests(TestCase):
    def test_user_id_is_uuid5_from_configured_namespace_and_username(self):
        user = User.objects.create_user(username='CaseSensitiveUser', password='password123')
        expected = uuid.uuid5(uuid.UUID(settings.USER_ID_UUID5_NAMESPACE), 'user:CaseSensitiveUser')

        self.assertEqual(user.id, expected)
        self.assertEqual(user.id.version, 5)

    def test_app_models_and_itinerary_join_rows_use_uuid4_ids(self):
        owner = User.objects.create_user(username='uuid-owner', password='password123')
        collaborator = User.objects.create_user(username='uuid-collaborator', password='password123')
        tag = Tag.objects.create(name='uuid-tag')
        itinerary = Itinerary.objects.create(
            owner=owner,
            title='UUID Trip',
            start_date='2026-06-01',
            end_date='2026-06-02',
            location='Taipei',
            budget='1000.00',
        )
        itinerary.tags.add(tag)
        itinerary.collaborators.add(collaborator)
        location = itinerary.locations.create(
            name='Taipei 101',
            travel_method='walk',
            visit_date='2026-06-01T09:00:00+08:00',
            latitude=25.0339,
            longitude=121.5645,
            route_order=0,
        )
        expense = location.expenses.create(expense_type='ticket', amount='500.00')
        event = Event.objects.create(owner=owner, event_name='UUID Event', date='2026-06-01', color='green')

        from app.models import ItineraryCollaborator, ItineraryTag

        uuid4_values = [
            tag.id,
            itinerary.id,
            location.id,
            expense.id,
            event.id,
            ItineraryTag.objects.get(itinerary=itinerary, tag=tag).id,
            ItineraryCollaborator.objects.get(itinerary=itinerary, user=collaborator).id,
        ]
        for value in uuid4_values:
            self.assertIsInstance(value, uuid.UUID)
            self.assertEqual(value.version, 4)

    def test_integer_itinerary_url_no_longer_matches(self):
        response = self.client.get('/itinerary/1/')

        self.assertEqual(response.status_code, 404)


class ItineraryRouteTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username='owner', password='password123')
        self.client.login(username='owner', password='password123')

    def test_create_itinerary_saves_coordinates_and_route_order(self):
        response = self.client.post(reverse('create'), {
            'title': 'Taipei Weekend',
            'start_date': '2026-06-01',
            'end_date': '2026-06-03',
            'location': 'Taipei',
            'budget': '1000',
            'budget_currency_choice': 'AUTO',
            'description': 'Short city route',
            'status': 'draft',
            'location_name[]': ['Second Stop', 'First Stop'],
            'travel_method[]': ['walk', 'walk'],
            'transport_note[]': ['Riverside', 'Station'],
            'visit_date[]': ['2026-06-01T10:00', '2026-06-01T09:00'],
            'location_latitude[]': ['25.050000', '25.037520'],
            'location_longitude[]': ['121.570000', '121.563680'],
            'route_order[]': ['1', '0'],
            'expense_type_0[]': ['transport'],
            'expense_amount_0[]': ['12.50'],
        })

        self.assertEqual(response.status_code, 302)
        itinerary = Itinerary.objects.get(title='Taipei Weekend')
        locations = list(itinerary.locations.all())
        self.assertEqual([location.name for location in locations], ['First Stop', 'Second Stop'])
        self.assertEqual(locations[0].route_order, 0)
        self.assertAlmostEqual(locations[0].latitude, 25.03752)
        self.assertAlmostEqual(locations[0].longitude, 121.56368)
        self.assertEqual(locations[1].expenses.get().amount, Decimal('12.50'))
        self.assertEqual(itinerary.budget_currency, 'TWD')

    def test_detail_page_renders_route_waypoint_data(self):
        itinerary = Itinerary.objects.create(
            owner=self.user,
            title='Route Detail',
            start_date='2026-06-01',
            end_date='2026-06-02',
            location='Taipei',
            budget='500',
        )
        itinerary.locations.create(
            name='Start',
            travel_method='walk',
            visit_date='2026-06-01T09:00:00+08:00',
            latitude=25.03752,
            longitude=121.56368,
            route_order=0,
        )
        itinerary.locations.create(
            name='End',
            travel_method='walk',
            visit_date='2026-06-01T10:00:00+08:00',
            latitude=25.05,
            longitude=121.57,
            route_order=1,
        )

        response = self.client.get(reverse('itinerary_detail', args=[itinerary.id]))

        self.assertContains(response, 'route-waypoints-data')
        self.assertContains(response, '25.03752')
        self.assertContains(response, '121.56368')

    def test_routing_service_url_normalizes_public_osrm_host_and_profile(self):
        service_url, profile = normalize_routing_service_url('router.project-osrm.org/driving')

        self.assertEqual(service_url, 'https://router.project-osrm.org/route/v1')
        self.assertEqual(profile, 'driving')

    @override_settings(ROUTING_SERVICE_URL='router.project-osrm.org/driving')
    def test_create_page_renders_normalized_routing_configuration(self):
        response = self.client.get(reverse('create'))

        self.assertContains(response, 'data-routing-service-url="https://router.project-osrm.org/route/v1"')
        self.assertContains(response, 'data-routing-profile="driving"')

    def test_create_page_renders_location_reorder_controls(self):
        response = self.client.get(reverse('create'))

        self.assertContains(response, 'data-location-move="up"')
        self.assertContains(response, 'data-location-move="down"')
        self.assertContains(response, "moveLocation(this, 'up')")
        self.assertContains(response, '<option value="hsr">搭高鐵</option>', html=True)

    def test_create_page_renders_sync_to_calendar_option(self):
        response = self.client.get(reverse('create'))

        self.assertContains(response, 'name="sync_to_calendar"')
        self.assertContains(response, '只有狀態為 ongoing 的行程會同步')

    def test_create_form_renders_budget_currency_option(self):
        response = self.client.get(reverse('create'))

        self.assertContains(response, 'name="budget_currency_choice"')
        self.assertContains(response, '自動依地點判斷')

    def test_create_itinerary_infers_budget_currency_from_location(self):
        response = self.client.post(reverse('create'), {
            'title': 'Tokyo Budget',
            'start_date': '2026-06-01',
            'end_date': '2026-06-03',
            'location': 'Tokyo, Japan',
            'budget': '1000',
            'budget_currency_choice': 'AUTO',
            'description': 'Currency inference test',
            'status': 'draft',
            'location_name[]': ['Tokyo Tower'],
            'travel_method[]': ['walk'],
            'transport_note[]': [''],
            'visit_date[]': ['2026-06-01T10:00'],
            'location_latitude[]': ['35.6586'],
            'location_longitude[]': ['139.7454'],
            'route_order[]': ['0'],
        })

        self.assertEqual(response.status_code, 302)
        itinerary = Itinerary.objects.get(title='Tokyo Budget')
        self.assertEqual(itinerary.budget_currency, 'JPY')

    def test_create_itinerary_respects_manual_budget_currency(self):
        response = self.client.post(reverse('create'), {
            'title': 'Tokyo USD Budget',
            'start_date': '2026-06-01',
            'end_date': '2026-06-03',
            'location': 'Tokyo, Japan',
            'budget': '1000',
            'budget_currency_choice': 'USD',
            'description': 'Manual currency test',
            'status': 'draft',
            'location_name[]': ['Tokyo Tower'],
            'travel_method[]': ['walk'],
            'transport_note[]': [''],
            'visit_date[]': ['2026-06-01T10:00'],
            'location_latitude[]': ['35.6586'],
            'location_longitude[]': ['139.7454'],
            'route_order[]': ['0'],
        })

        self.assertEqual(response.status_code, 302)
        itinerary = Itinerary.objects.get(title='Tokyo USD Budget')
        self.assertEqual(itinerary.budget_currency, 'USD')

    def test_create_itinerary_accepts_hsr_travel_method(self):
        response = self.client.post(reverse('create'), {
            'title': 'HSR Trip',
            'start_date': '2026-06-01',
            'end_date': '2026-06-03',
            'location': 'Taiwan',
            'budget': '1000',
            'budget_currency_choice': 'AUTO',
            'description': 'High speed rail test',
            'status': 'draft',
            'location_name[]': ['台中站'],
            'travel_method[]': ['hsr'],
            'transport_note[]': [''],
            'visit_date[]': ['2026-06-01T10:00'],
            'location_latitude[]': ['24.1120'],
            'location_longitude[]': ['120.6150'],
            'route_order[]': ['0'],
        })

        self.assertEqual(response.status_code, 302)
        itinerary = Itinerary.objects.get(title='HSR Trip')
        self.assertEqual(itinerary.locations.get().travel_method, 'hsr')

    def test_create_itinerary_syncs_calendar_when_checked_and_ongoing(self):
        response = self.client.post(reverse('create'), {
            'title': 'Taichung Trip',
            'start_date': '2026-06-01',
            'end_date': '2026-06-03',
            'location': 'Taichung',
            'budget': '1000',
            'budget_currency_choice': 'AUTO',
            'description': 'Trip sync test',
            'status': 'ongoing',
            'sync_to_calendar': 'on',
            'location_name[]': ['Museum', 'Night Market'],
            'travel_method[]': ['walk', 'walk'],
            'transport_note[]': ['', ''],
            'visit_date[]': ['2026-06-01T10:00', '2026-06-01T18:00'],
            'location_latitude[]': ['24.1477', '24.1374'],
            'location_longitude[]': ['120.6736', '120.6869'],
            'route_order[]': ['0', '1'],
        }, follow=True)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(Event.objects.count(), 2)
        self.assertEqual(
            list(Event.objects.order_by('date', 'event_name').values_list('event_name', flat=True)),
            ['Taichung Trip｜Museum', 'Taichung Trip｜Night Market'],
        )
        messages_text = ' '.join(str(message) for message in response.context['messages'])
        self.assertIn('已同步 2 筆行程到行事曆', messages_text)

    def test_create_itinerary_does_not_sync_calendar_when_not_ongoing(self):
        response = self.client.post(reverse('create'), {
            'title': 'Draft Trip',
            'start_date': '2026-06-01',
            'end_date': '2026-06-03',
            'location': 'Taipei',
            'budget': '1000',
            'budget_currency_choice': 'AUTO',
            'description': 'Draft sync test',
            'status': 'draft',
            'sync_to_calendar': 'on',
            'location_name[]': ['Museum'],
            'travel_method[]': ['walk'],
            'transport_note[]': [''],
            'visit_date[]': ['2026-06-01T10:00'],
            'location_latitude[]': ['25.03752'],
            'location_longitude[]': ['121.56368'],
            'route_order[]': ['0'],
        }, follow=True)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(Event.objects.count(), 0)
        messages_text = ' '.join(str(message) for message in response.context['messages'])
        self.assertIn('只有進行中的行程才會同步到行事曆', messages_text)


class ItineraryEditPersistenceTests(TestCase):
    def setUp(self):
        self.owner = User.objects.create_user(username='owner', password='password123')
        self.collaborator = User.objects.create_user(username='helper', password='password123')
        self.other_user = User.objects.create_user(username='other', password='password123')
        self.client.login(username='owner', password='password123')

    def _itinerary(self, **overrides):
        values = {
            'owner': self.owner,
            'title': 'Editable Trip',
            'start_date': '2026-06-01',
            'end_date': '2026-06-03',
            'location': 'Taipei',
            'budget': '750.00',
            'budget_currency': 'TWD',
            'description': 'Original description',
            'status': 'draft',
        }
        values.update(overrides)
        return Itinerary.objects.create(**values)

    def _edit_payload(self, **overrides):
        values = {
            'title': 'Updated Trip',
            'start_date': '2026-06-01',
            'end_date': '2026-06-03',
            'location': 'Taipei',
            'budget': '900.00',
            'budget_currency_choice': 'AUTO',
            'description': 'Updated description',
            'status': 'ongoing',
            'custom_tags': '',
            'collaborators': '',
        }
        values.update(overrides)
        return values

    def test_public_itinerary_cannot_be_edited_by_non_collaborator(self):
        itinerary = self._itinerary(is_public=True)
        self.client.logout()
        self.client.login(username='other', password='password123')

        response = self.client.get(reverse('edit_itinerary', args=[itinerary.id]))

        self.assertEqual(response.status_code, 403)

    def test_owner_and_collaborator_can_edit_itinerary(self):
        itinerary = self._itinerary()
        itinerary.collaborators.add(self.collaborator)

        owner_response = self.client.post(
            reverse('edit_itinerary', args=[itinerary.id]),
            data=self._edit_payload(title='Owner Update', collaborators='helper'),
        )
        self.assertEqual(owner_response.status_code, 302)

        self.client.logout()
        self.client.login(username='helper', password='password123')
        collaborator_response = self.client.post(
            reverse('edit_itinerary', args=[itinerary.id]),
            data=self._edit_payload(title='Collaborator Update'),
        )

        self.assertEqual(collaborator_response.status_code, 302)
        itinerary.refresh_from_db()
        self.assertEqual(itinerary.title, 'Collaborator Update')

    def test_edit_replaces_tags_and_collaborators_exactly(self):
        itinerary = self._itinerary()
        itinerary.tags.add(Tag.objects.create(name='old'))
        itinerary.collaborators.add(self.other_user)

        response = self.client.post(
            reverse('edit_itinerary', args=[itinerary.id]),
            data=self._edit_payload(custom_tags='new, beach, new', collaborators='helper'),
        )

        self.assertEqual(response.status_code, 302)
        self.assertEqual(set(itinerary.tags.values_list('name', flat=True)), {'new', 'beach'})
        self.assertEqual(list(itinerary.collaborators.values_list('username', flat=True)), ['helper'])

    def test_edit_clears_collaborators_when_field_is_blank(self):
        itinerary = self._itinerary()
        itinerary.collaborators.add(self.collaborator)

        response = self.client.post(
            reverse('edit_itinerary', args=[itinerary.id]),
            data=self._edit_payload(collaborators=''),
        )

        self.assertEqual(response.status_code, 302)
        self.assertEqual(itinerary.collaborators.count(), 0)

    def test_missing_collaborator_adds_error_message_without_adding_user(self):
        itinerary = self._itinerary()

        response = self.client.post(
            reverse('edit_itinerary', args=[itinerary.id]),
            data=self._edit_payload(collaborators='missing-user'),
            follow=True,
        )

        message_text = ' '.join(str(message) for message in response.context['messages'])
        self.assertEqual(response.status_code, 200)
        self.assertIn('missing-user', message_text)
        self.assertEqual(itinerary.collaborators.count(), 0)

    def test_invalid_location_visit_date_is_logged_and_skipped(self):
        itinerary = self._itinerary()
        payload = self._edit_payload()
        payload.update({
            'location_name[]': ['Museum'],
            'travel_method[]': ['walk'],
            'transport_note[]': [''],
            'visit_date[]': ['not-a-date'],
            'location_latitude[]': ['25.037520'],
            'location_longitude[]': ['121.563680'],
            'route_order[]': ['0'],
        })

        with self.assertLogs('app.views.itinerary.location_form', level='WARNING') as logs:
            response = self.client.post(reverse('edit_itinerary', args=[itinerary.id]), data=payload)

        self.assertEqual(response.status_code, 302)
        self.assertIn('invalid visit date', ' '.join(logs.output))
        self.assertEqual(itinerary.locations.count(), 0)

    def test_edit_saves_locations_in_swapped_route_order(self):
        itinerary = self._itinerary()
        payload = self._edit_payload()
        payload.update({
            'location_name[]': ['Museum', 'Cafe'],
            'travel_method[]': ['walk', 'walk'],
            'transport_note[]': ['', ''],
            'visit_date[]': ['2026-06-01T11:00', '2026-06-01T09:00'],
            'location_latitude[]': ['25.047000', '25.037520'],
            'location_longitude[]': ['121.517000', '121.563680'],
            'route_order[]': ['1', '0'],
        })

        response = self.client.post(reverse('edit_itinerary', args=[itinerary.id]), data=payload)

        self.assertEqual(response.status_code, 302)
        self.assertEqual(
            list(itinerary.locations.values_list('name', flat=True)),
            ['Cafe', 'Museum'],
        )

    def test_edit_page_renders_location_reorder_controls(self):
        itinerary = self._itinerary()

        response = self.client.get(reverse('edit_itinerary', args=[itinerary.id]))

        self.assertContains(response, 'data-location-move="up"')
        self.assertContains(response, 'data-location-move="down"')

    def test_edit_page_renders_ai_check_widget(self):
        itinerary = self._itinerary()

        response = self.client.get(reverse('edit_itinerary', args=[itinerary.id]))

        self.assertContains(response, 'data-ai-check-widget')
        self.assertContains(response, reverse('ai_itinerary_check', args=[itinerary.id]))
        self.assertContains(response, 'data-check-type="overall"')
        self.assertContains(response, 'data-check-type="budget"')

    def test_ai_itinerary_check_rejects_non_collaborator(self):
        itinerary = self._itinerary(is_public=True)
        self.client.logout()
        self.client.login(username='other', password='password123')

        response = self.client.post(
            reverse('ai_itinerary_check', args=[itinerary.id]),
            data=json.dumps({'check_type': 'overall'}),
            content_type='application/json',
        )

        self.assertEqual(response.status_code, 403)
        self.assertFalse(response.json()['success'])

    def test_ai_itinerary_check_rejects_invalid_check_type(self):
        itinerary = self._itinerary()

        response = self.client.post(
            reverse('ai_itinerary_check', args=[itinerary.id]),
            data=json.dumps({'check_type': 'unknown'}),
            content_type='application/json',
        )

        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()['error'], 'invalid_check_type')

    def test_ai_itinerary_check_invokes_planner_agent_with_saved_itinerary(self):
        itinerary = self._itinerary()

        class FakeAgent:
            payload = None

            def invoke(self, payload):
                self.payload = payload
                return {
                    'structured_response': {
                        'summary': 'Route and budget look reviewable.',
                        'actions': ['Confirm travel time between saved stops.'],
                        'key_data': [{'label': 'Itinerary', 'value': str(itinerary.id)}],
                        'next_steps': ['Review the route order.'],
                    }
                }

        fake_agent = FakeAgent()
        with patch(
            'app.views.itinerary.edit.build_openai_chat_model',
            return_value=object(),
        ) as model_mock, patch(
            'app.views.itinerary.edit.build_planner_agent',
            return_value=fake_agent,
        ) as agent_mock:
            response = self.client.post(
                reverse('ai_itinerary_check', args=[itinerary.id]),
                data=json.dumps({'check_type': 'route'}),
                content_type='application/json',
            )

        payload = response.json()
        prompt = fake_agent.payload['messages'][0]['content']
        self.assertEqual(response.status_code, 200)
        self.assertTrue(payload['success'])
        self.assertEqual(payload['check_type'], 'route')
        self.assertEqual(payload['summary'], 'Route and budget look reviewable.')
        self.assertIn(f'itinerary_id={itinerary.id}', prompt)
        self.assertIn('review_itinerary_on_request', prompt)
        self.assertIn('Do not ask for confirmation', prompt)
        model_mock.assert_called_once_with()
        agent_mock.assert_called_once()

    def test_ai_itinerary_check_returns_safe_configuration_error(self):
        from app.agents.planner_agent import PlannerAgentConfigurationError

        itinerary = self._itinerary()

        with patch(
            'app.views.itinerary.edit.build_openai_chat_model',
            side_effect=PlannerAgentConfigurationError('missing model'),
        ):
            response = self.client.post(
                reverse('ai_itinerary_check', args=[itinerary.id]),
                data=json.dumps({'check_type': 'budget'}),
                content_type='application/json',
            )

        payload = response.json()
        self.assertEqual(response.status_code, 200)
        self.assertFalse(payload['success'])
        self.assertIn('規劃助手目前尚未完成設定', payload['message'])


class CalendarCsrfTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username='calendar-owner', password='password123')
        self.other_user = User.objects.create_user(username='calendar-other', password='password123')
        self.client = Client(enforce_csrf_checks=True)
        self.client.login(username='calendar-owner', password='password123')

    def _csrf_headers(self):
        response = self.client.get(reverse('calendar'))

        self.assertEqual(response.status_code, 200)
        self.assertIn(settings.CSRF_COOKIE_NAME, self.client.cookies)
        return {'HTTP_X_CSRFTOKEN': self.client.cookies[settings.CSRF_COOKIE_NAME].value}

    def _event_payload(self):
        return json.dumps({
            'eventName': 'Museum visit',
            'date': '2026-06-12',
            'color': 'green',
        })

    def test_add_event_without_csrf_token_is_forbidden(self):
        response = self.client.post(
            reverse('add_event'),
            data=self._event_payload(),
            content_type='application/json',
        )

        self.assertEqual(response.status_code, 403)
        self.assertEqual(Event.objects.count(), 0)

    def test_add_event_with_csrf_token_creates_event(self):
        response = self.client.post(
            reverse('add_event'),
            data=self._event_payload(),
            content_type='application/json',
            **self._csrf_headers(),
        )

        event = Event.objects.get()
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()['status'], 'ok')
        self.assertEqual(response.json()['id'], str(event.id))
        self.assertEqual(event.owner, self.user)
        self.assertEqual(event.event_name, 'Museum visit')
        self.assertEqual(event.color, 'green')

    def test_delete_event_without_csrf_token_is_forbidden(self):
        event = Event.objects.create(
            owner=self.user,
            event_name='Dinner',
            date='2026-06-12',
            color='orange',
        )

        response = self.client.delete(reverse('delete_event', args=[event.id]))

        self.assertEqual(response.status_code, 403)
        self.assertTrue(Event.objects.filter(id=event.id).exists())

    def test_delete_event_with_csrf_token_deletes_own_event(self):
        event = Event.objects.create(
            owner=self.user,
            event_name='Dinner',
            date='2026-06-12',
            color='orange',
        )

        response = self.client.delete(
            reverse('delete_event', args=[event.id]),
            **self._csrf_headers(),
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()['status'], 'ok')
        self.assertFalse(Event.objects.filter(id=event.id).exists())

    def test_delete_event_with_csrf_token_cannot_delete_another_users_event(self):
        event = Event.objects.create(
            owner=self.other_user,
            event_name='Private dinner',
            date='2026-06-12',
            color='orange',
        )

        with self.assertLogs('app.views.calendar.calendar', level='WARNING'):
            response = self.client.delete(
                reverse('delete_event', args=[event.id]),
                **self._csrf_headers(),
            )

        self.assertEqual(response.status_code, 404)
        self.assertTrue(Event.objects.filter(id=event.id).exists())


class AuthViewTests(TestCase):
    def test_register_valid_user_logs_in_and_redirects_to_search(self):
        response = self.client.post(reverse('register'), {
            'username': 'new-user',
            'email': 'new@example.com',
            'password1': 'StrongPassword123',
            'password2': 'StrongPassword123',
        })

        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, reverse('search'))
        self.assertTrue(User.objects.filter(username='new-user').exists())
        self.assertIn('_auth_user_id', self.client.session)

    def test_register_invalid_user_renders_error_message(self):
        response = self.client.post(reverse('register'), {
            'username': '',
            'email': 'bad@example.com',
            'password1': 'StrongPassword123',
            'password2': 'mismatch',
        })

        message_text = ' '.join(str(message) for message in response.context['messages'])
        self.assertEqual(response.status_code, 200)
        self.assertIn('註冊失敗', message_text)

    def test_login_success_failure_and_logout(self):
        User.objects.create_user(username='auth-user', password='password123')

        failed = self.client.post(reverse('login'), {
            'username': 'auth-user',
            'password': 'wrong-password',
        })
        failed_messages = ' '.join(str(message) for message in failed.context['messages'])
        self.assertEqual(failed.status_code, 200)
        self.assertIn('帳戶或密碼錯誤', failed_messages)

        logged_in = self.client.post(reverse('login'), {
            'username': 'auth-user',
            'password': 'password123',
        })
        self.assertEqual(logged_in.status_code, 302)
        self.assertEqual(logged_in.url, reverse('search'))
        self.assertIn('_auth_user_id', self.client.session)

        logged_out = self.client.get(reverse('logout'))
        self.assertEqual(logged_out.status_code, 302)
        self.assertEqual(logged_out.url, reverse('search'))
        self.assertNotIn('_auth_user_id', self.client.session)


class PlannerAgentViewTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username='planner-user', password='password123')

    def test_planner_agent_page_requires_login(self):
        response = self.client.get(reverse('planner_agent'))

        self.assertEqual(response.status_code, 302)
        self.assertIn('/login/', response.url)

    def test_planner_agent_page_renders_from_sidebar_nav(self):
        self.client.login(username='planner-user', password='password123')

        response = self.client.get(reverse('planner_agent'))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'href="/planner-agent/"')
        self.assertContains(response, '規劃助手')
        self.assertContains(response, '我可以幫你')
        self.assertNotContains(response, 'itinerary_management')
        self.assertContains(response, 'appendPlannerLoadingCard')
        self.assertContains(response, "parsedEvent.name === 'result'")

    def test_planner_agent_page_renders_session_history(self):
        self.client.login(username='planner-user', password='password123')
        session = self.client.session
        session['planner_agent_history'] = [{
            'user': 'Show my trips',
            'assistant': 'You have one Taipei trip',
        }]
        session.save()

        response = self.client.get(reverse('planner_agent'))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Show my trips')
        self.assertContains(response, 'You have one Taipei trip')

    def test_planner_agent_post_invokes_langchain_and_renders_response(self):
        self.client.login(username='planner-user', password='password123')

        class FakeAgent:
            payload = None

            def invoke(self, payload):
                self.payload = payload
                return {
                    'structured_response': {
                        'summary': '台北行程已更新。',
                        'actions': ['更新預算'],
                        'key_data': [{'label': '預算', 'value': '10000 USD'}],
                        'next_steps': ['確認住宿選項'],
                    }
                }

        fake_agent = FakeAgent()
        with patch(
            'app.views.planner_agent.planner_agent.build_openai_chat_model',
            return_value=object(),
        ) as model_mock, patch(
            'app.views.planner_agent.planner_agent.build_planner_agent',
            return_value=fake_agent,
        ) as agent_mock:
            response = self.client.post(reverse('planner_agent'), {'prompt': 'Plan a Taipei food trip'})

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Plan a Taipei food trip')
        self.assertContains(response, '台北行程已更新。')
        self.assertEqual(fake_agent.payload['messages'][0]['content'], 'Plan a Taipei food trip')
        model_mock.assert_called_once_with()
        agent_mock.assert_called_once()
        self.assertEqual(self.client.session['planner_agent_history'][-1]['assistant'], '台北行程已更新。')

    def test_planner_agent_post_keeps_only_five_session_rounds(self):
        self.client.login(username='planner-user', password='password123')
        session = self.client.session
        session['planner_agent_history'] = [
            {'user': f'old {index}', 'assistant': f'answer {index}'}
            for index in range(5)
        ]
        session.save()

        class FakeAgent:
            payload = None

            def invoke(self, payload):
                self.payload = payload
                return {
                    'structured_response': {
                        'summary': 'new answer',
                        'actions': [],
                        'key_data': [],
                        'next_steps': [],
                    }
                }

        fake_agent = FakeAgent()
        with patch(
            'app.views.planner_agent.planner_agent.build_openai_chat_model',
            return_value=object(),
        ), patch(
            'app.views.planner_agent.planner_agent.build_planner_agent',
            return_value=fake_agent,
        ):
            response = self.client.post(reverse('planner_agent'), {'prompt': 'new question'})

        history = self.client.session['planner_agent_history']
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(history), 5)
        self.assertEqual(history[0]['user'], 'old 1')
        self.assertEqual(history[-1]['user'], 'new question')
        self.assertEqual(history[-1]['assistant'], 'new answer')
        self.assertEqual(fake_agent.payload['messages'][-1]['content'], 'new question')

    def test_planner_agent_stream_returns_chunks_and_saves_history(self):
        from langchain_core.messages import AIMessageChunk

        self.client.login(username='planner-user', password='password123')

        class FakeAgent:
            payload = None

            def stream(self, payload, **kwargs):
                self.payload = payload
                yield {'type': 'messages', 'data': (AIMessageChunk(content='Partial '), {'langgraph_node': 'model'})}
                yield {'type': 'messages', 'data': (AIMessageChunk(content='answer'), {'langgraph_node': 'model'})}
                yield {
                    'type': 'updates',
                    'data': {
                        'model': {
                            'structured_response': {
                                'summary': 'Partial answer summary',
                                'actions': ['Action item'],
                                'key_data': [{'label': 'Trip', 'value': 'Taipei'}],
                                'next_steps': ['Next step'],
                            },
                            'messages': [{'type': 'ai', 'content': 'raw final message'}],
                        }
                    },
                }

        fake_agent = FakeAgent()
        with patch(
            'app.views.planner_agent.planner_agent.build_openai_chat_model',
            return_value=object(),
        ), patch(
            'app.views.planner_agent.planner_agent.build_planner_agent',
            return_value=fake_agent,
        ):
            response = self.client.post(reverse('planner_agent_stream'), {'prompt': 'stream this'})
            streamed_text = b''.join(response.streaming_content).decode()

        self.assertEqual(response.status_code, 200)
        self.assertIn('event: token', streamed_text)
        self.assertIn('event: result', streamed_text)
        self.assertIn('"summary": "Partial answer summary"', streamed_text)
        self.assertIn('event: done', streamed_text)
        self.assertIn('data: null', streamed_text)
        self.assertNotIn('data: {}', streamed_text)
        self.assertNotIn('{\"status\"', streamed_text)
        self.assertEqual(self.client.session['planner_agent_history'][-1]['user'], 'stream this')
        self.assertEqual(self.client.session['planner_agent_history'][-1]['assistant'], 'Partial answer summary')

    def test_planner_agent_stream_does_not_expose_tool_messages(self):
        from langchain_core.messages import AIMessageChunk, ToolMessage

        self.client.login(username='planner-user', password='password123')

        class FakeAgent:
            def stream(self, payload, **kwargs):
                yield {'type': 'messages', 'data': (ToolMessage(content='{"status":"ok","secret":"tool-data"}', tool_call_id='call-1'), {'langgraph_node': 'tools'})}
                yield {'type': 'messages', 'data': (AIMessageChunk(content='Visible answer'), {'langgraph_node': 'model'})}
                yield {
                    'type': 'updates',
                    'data': {
                        'model': {
                            'structured_response': {
                                'summary': 'Visible answer summary',
                                'actions': [],
                                'key_data': [],
                                'next_steps': [],
                            },
                            'messages': [{'type': 'ai', 'content': 'Visible answer'}],
                        }
                    },
                }

        with patch(
            'app.views.planner_agent.planner_agent.build_openai_chat_model',
            return_value=object(),
        ), patch(
            'app.views.planner_agent.planner_agent.build_planner_agent',
            return_value=FakeAgent(),
        ):
            response = self.client.post(reverse('planner_agent_stream'), {'prompt': 'list'})
            streamed_text = b''.join(response.streaming_content).decode()

        self.assertIn('Visible answer', streamed_text)
        self.assertNotIn('tool-data', streamed_text)
        self.assertNotIn('{"status"', self.client.session['planner_agent_history'][-1]['assistant'])
        self.assertEqual(self.client.session['planner_agent_history'][-1]['assistant'], 'Visible answer summary')

    def test_planner_agent_stream_uses_fallback_card_when_structured_response_missing(self):
        from langchain_core.messages import AIMessageChunk

        self.client.login(username='planner-user', password='password123')

        class FakeAgent:
            def stream(self, payload, **kwargs):
                yield {'type': 'messages', 'data': (AIMessageChunk(content='Fallback '), {'langgraph_node': 'model'})}
                yield {'type': 'messages', 'data': (AIMessageChunk(content='summary'), {'langgraph_node': 'model'})}

        with patch(
            'app.views.planner_agent.planner_agent.build_openai_chat_model',
            return_value=object(),
        ), patch(
            'app.views.planner_agent.planner_agent.build_planner_agent',
            return_value=FakeAgent(),
        ):
            response = self.client.post(reverse('planner_agent_stream'), {'prompt': 'fallback please'})
            streamed_text = b''.join(response.streaming_content).decode()

        self.assertEqual(response.status_code, 200)
        self.assertIn('event: result', streamed_text)
        self.assertIn('"summary": "Fallback summary"', streamed_text)
        self.assertIn('event: done', streamed_text)
        self.assertNotIn('data: {}', streamed_text)
        self.assertEqual(self.client.session['planner_agent_history'][-1]['assistant'], 'Fallback summary')

    def test_planner_agent_post_returns_safe_configuration_error(self):
        from app.agents.planner_agent import PlannerAgentConfigurationError

        self.client.login(username='planner-user', password='password123')

        with patch(
            'app.views.planner_agent.planner_agent.build_openai_chat_model',
            side_effect=PlannerAgentConfigurationError('missing model'),
        ):
            response = self.client.post(reverse('planner_agent'), {'prompt': 'Plan a Taipei food trip'})

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, '規劃助手目前尚未完成設定')


class PlannerAgentFactoryTests(TestCase):
    def test_build_planner_agent_configures_structured_response_schema(self):
        from app.agents.planner_agent import PlannerStructuredResponse, build_planner_agent
        from langchain.agents.structured_output import ToolStrategy

        with patch('app.agents.planner_agent.all_planner_tools', return_value=[]), patch(
            'langchain.agents.create_agent',
            return_value='fake-agent',
        ) as create_agent_mock:
            result = build_planner_agent(model=object())

        self.assertEqual(result, 'fake-agent')
        response_format = create_agent_mock.call_args.kwargs['response_format']
        self.assertIsInstance(response_format, ToolStrategy)
        self.assertIs(response_format.schema, PlannerStructuredResponse)


class ItineraryManagementTests(TestCase):
    def setUp(self):
        self.owner = User.objects.create_user(username='trip-owner', password='password123')
        self.collaborator = User.objects.create_user(username='trip-helper', password='password123')
        self.other_user = User.objects.create_user(username='trip-other', password='password123')

    def _itinerary(self, **overrides):
        values = {
            'owner': self.owner,
            'title': 'Taipei Trip',
            'start_date': '2026-06-01',
            'end_date': '2026-06-03',
            'location': 'Taipei',
            'budget': '500.00',
            'status': 'draft',
        }
        values.update(overrides)
        return Itinerary.objects.create(**values)

    def _draft_payload(self, **overrides):
        values = {
            'title': 'Agent Draft',
            'start_date': '2026-06-01',
            'end_date': '2026-06-03',
            'location': 'Taipei',
            'budget': '1200.00',
            'description': 'DO_NOT_LOG_SECRET itinerary detail',
            'status': 'draft',
            'is_public': False,
            'tags': ['food', 'food', 'weekend'],
            'collaborators': ['trip-helper'],
            'locations': [{
                'name': 'Museum',
                'travel_method': 'walk',
                'visit_date': '2026-06-01T10:00',
                'latitude': 25.047,
                'longitude': 121.517,
                'route_order': 0,
                'note': 'DO_NOT_LOG_SECRET location note',
                'expenses': [{'expense_type': 'ticket', 'amount': '15.50'}],
            }],
        }
        values.update(overrides)
        return values

    def test_create_itinerary_with_locations_expenses_and_safe_logs(self):
        from app.agents.services.itinerary_management import create_or_update_itinerary_for_user

        with patch(
            'app.agents.services.itinerary_management._geocode_location_coordinates',
            return_value=(25.047, 121.517),
        ), self.assertLogs('app.agents.services.itinerary_management', level='INFO') as logs:
            result = create_or_update_itinerary_for_user(self.owner, self._draft_payload())

        itinerary = Itinerary.objects.get(title='Agent Draft')
        location = itinerary.locations.get()
        log_text = ' '.join(logs.output)
        self.assertEqual(result['status'], 'ok')
        self.assertEqual(result['action'], 'created')
        self.assertEqual(itinerary.owner, self.owner)
        self.assertEqual(list(itinerary.tags.values_list('name', flat=True)), ['food', 'weekend'])
        self.assertEqual(list(itinerary.collaborators.values_list('username', flat=True)), ['trip-helper'])
        self.assertEqual(location.expenses.get().amount, Decimal('15.50'))
        self.assertNotIn('DO_NOT_LOG_SECRET', log_text)

    def test_create_itinerary_infers_budget_currency_in_agent_service(self):
        from app.agents.services.itinerary_management import create_or_update_itinerary_for_user

        with patch(
            'app.agents.services.itinerary_management._geocode_location_coordinates',
            return_value=(35.6586, 139.7454),
        ):
            result = create_or_update_itinerary_for_user(self.owner, self._draft_payload(
                title='Tokyo Agent Draft',
                location='Tokyo, Japan',
            ))

        itinerary = Itinerary.objects.get(title='Tokyo Agent Draft')
        self.assertEqual(result['status'], 'ok')
        self.assertEqual(itinerary.budget_currency, 'JPY')

    def test_create_itinerary_accepts_activity_locations_without_travel_method(self):
        from app.agents.services.itinerary_management import create_or_update_itinerary_for_user

        nominatim_results = [
            FakeResponse([{'lat': '35.6586', 'lon': '139.7454'}]),
            FakeResponse([{'lat': '35.7148', 'lon': '139.7967'}]),
        ]
        with patch('app.agents.services.itinerary_management._throttle_nominatim_request'), patch(
            'app.agents.services.itinerary_management.requests.get',
            side_effect=nominatim_results,
        ) as request_mock:
            result = create_or_update_itinerary_for_user(self.owner, {
                'title': 'Tokyo Summer',
                'start_date': '2026-06-01',
                'end_date': '2026-06-02',
                'location': 'Tokyo, Japan',
                'budget': '1000.00',
                'activities': [
                    {'name': 'Tokyo Tower', 'visit_date': '2026-06-01', 'note': 'Night view'},
                    {'name': 'Senso-ji Temple', 'visit_date': '2026-06-02'},
                ],
            })

        itinerary = Itinerary.objects.get(title='Tokyo Summer')
        locations = list(itinerary.locations.all())
        self.assertEqual(result['status'], 'ok')
        self.assertEqual([location.name for location in locations], ['Tokyo Tower', 'Senso-ji Temple'])
        self.assertEqual([location.travel_method for location in locations], ['walk', 'walk'])
        self.assertAlmostEqual(locations[0].latitude, 35.6586)
        self.assertAlmostEqual(locations[0].longitude, 139.7454)
        self.assertAlmostEqual(locations[1].latitude, 35.7148)
        self.assertAlmostEqual(locations[1].longitude, 139.7967)
        self.assertEqual(request_mock.call_args_list[0].kwargs['params']['q'], 'Tokyo Tower, Tokyo, Japan')
        self.assertEqual(request_mock.call_args_list[1].kwargs['params']['q'], 'Senso-ji Temple, Tokyo, Japan')

    def test_create_itinerary_ignores_model_coordinates_and_uses_nominatim(self):
        from app.agents.services.itinerary_management import create_or_update_itinerary_for_user

        response = FakeResponse([{'lat': '35.6586', 'lon': '139.7454'}])
        with patch('app.agents.services.itinerary_management._throttle_nominatim_request'), patch(
            'app.agents.services.itinerary_management.requests.get',
            return_value=response,
        ) as geocode_mock:
            result = create_or_update_itinerary_for_user(self.owner, {
                'title': 'Manual Coordinates',
                'start_date': '2026-06-01',
                'end_date': '2026-06-02',
                'location': 'Tokyo',
                'budget': '1000.00',
                'locations': [{
                    'name': 'Known Stop',
                    'visit_date': '2026-06-01',
                    'latitude': 35.0,
                    'longitude': 139.0,
                }],
            })

        location = Itinerary.objects.get(title='Manual Coordinates').locations.get()
        self.assertEqual(result['status'], 'ok')
        self.assertAlmostEqual(location.latitude, 35.6586)
        self.assertAlmostEqual(location.longitude, 139.7454)
        geocode_mock.assert_called_once()

    def test_create_itinerary_uses_nominatim_for_places(self):
        from app.agents.services.itinerary_management import create_or_update_itinerary_for_user

        response = FakeResponse([{'lat': '35.6586', 'lon': '139.7454'}])
        with patch(
            'app.agents.services.itinerary_management._throttle_nominatim_request',
        ), patch(
            'app.agents.services.itinerary_management.requests.get',
            return_value=response,
        ) as request_mock:
            result = create_or_update_itinerary_for_user(self.owner, {
                'title': 'Nominatim Geocode',
                'start_date': '2026-06-01',
                'end_date': '2026-06-02',
                'location': 'Tokyo, Japan',
                'budget': '1000.00',
                'locations': [{'name': 'Tokyo Tower', 'visit_date': '2026-06-01'}],
            })

        location = Itinerary.objects.get(title='Nominatim Geocode').locations.get()
        self.assertEqual(result['status'], 'ok')
        self.assertAlmostEqual(location.latitude, 35.6586)
        self.assertAlmostEqual(location.longitude, 139.7454)
        self.assertEqual(request_mock.call_args.kwargs['params']['q'], 'Tokyo Tower, Tokyo, Japan')
        self.assertIn('User-Agent', request_mock.call_args.kwargs['headers'])

    def test_list_user_itineraries_returns_owned_and_shared_only(self):
        from app.agents.services.itinerary_management import list_user_itineraries_for_user

        owned = self._itinerary(title='Owned Trip')
        shared = self._itinerary(title='Shared Trip', owner=self.other_user)
        shared.collaborators.add(self.owner)
        self._itinerary(title='Hidden Other Trip', owner=self.other_user)
        owned.locations.create(
            name='Owned Stop',
            travel_method='walk',
            visit_date='2026-06-01T09:00:00+08:00',
            latitude=25,
            longitude=121,
            route_order=0,
        )

        result = list_user_itineraries_for_user(self.owner)

        titles = [itinerary['title'] for itinerary in result['itineraries']]
        relationships = {itinerary['title']: itinerary['relationship'] for itinerary in result['itineraries']}
        self.assertEqual(result['status'], 'ok')
        self.assertEqual(set(titles), {'Owned Trip', 'Shared Trip'})
        self.assertEqual(relationships['Owned Trip'], 'owner')
        self.assertEqual(relationships['Shared Trip'], 'collaborator')
        self.assertNotIn('Hidden Other Trip', titles)

    def test_list_user_itineraries_tool_uses_bound_context(self):
        from app.agents.tool_context import planner_tool_user
        from app.agents.tools.itinerary_tools import list_user_itineraries

        self._itinerary(title='Tool Visible Trip')

        with planner_tool_user(self.owner):
            result = invoke_tool(list_user_itineraries, include_shared=True, limit=5)

        self.assertEqual(result['status'], 'ok')
        self.assertEqual(result['itineraries'][0]['title'], 'Tool Visible Trip')

    def test_update_owned_itinerary_replaces_only_explicit_locations(self):
        from app.agents.services.itinerary_management import create_or_update_itinerary_for_user

        itinerary = self._itinerary(title='Before Update')
        itinerary.locations.create(
            name='Old Stop',
            travel_method='walk',
            visit_date='2026-06-01T09:00:00+08:00',
            latitude=25,
            longitude=121,
            route_order=0,
        )

        with patch(
            'app.agents.services.itinerary_management._geocode_location_coordinates',
            return_value=(24.1, 120.6),
        ):
            result = create_or_update_itinerary_for_user(self.owner, self._draft_payload(
                itinerary_id=itinerary.id,
                title='After Update',
                replace_locations=True,
                locations=[{
                    'name': 'New Stop',
                    'travel_method': 'train',
                    'visit_date': '2026-06-02T09:00',
                    'latitude': 24.1,
                    'longitude': 120.6,
                    'route_order': 0,
                    'expenses': [],
                }],
            ))

        itinerary.refresh_from_db()
        self.assertEqual(result['status'], 'ok')
        self.assertEqual(result['action'], 'updated')
        self.assertEqual(itinerary.title, 'After Update')
        self.assertEqual(list(itinerary.locations.values_list('name', flat=True)), ['New Stop'])

    def test_patch_update_date_only_preserves_location_name_and_time(self):
        from app.agents.services.itinerary_management import create_or_update_itinerary_for_user

        itinerary = self._itinerary(title='Patch Date Only')
        first = itinerary.locations.create(
            name='台北101',
            travel_method='walk',
            visit_date='2026-06-01T09:30:00+08:00',
            latitude=25.0339,
            longitude=121.5645,
            route_order=0,
        )
        second = itinerary.locations.create(
            name='士林夜市',
            travel_method='walk',
            visit_date='2026-06-01T19:00:00+08:00',
            latitude=25.0880,
            longitude=121.5250,
            route_order=1,
        )

        result = create_or_update_itinerary_for_user(self.owner, {
            'itinerary_id': itinerary.id,
            'locations': [{
                'route_order': 0,
                'visit_date': '2026-06-03',
            }],
        })

        first.refresh_from_db()
        second.refresh_from_db()
        first_local = timezone.localtime(first.visit_date)
        second_local = timezone.localtime(second.visit_date)
        self.assertEqual(result['status'], 'ok')
        self.assertEqual(first.name, '台北101')
        self.assertEqual(first_local.date().isoformat(), '2026-06-03')
        self.assertEqual(first_local.hour, 9)
        self.assertEqual(first_local.minute, 30)
        self.assertEqual(second.name, '士林夜市')
        self.assertEqual(second_local.date().isoformat(), '2026-06-01')

    def test_patch_update_ignores_unrequested_location_rename(self):
        from app.agents.services.itinerary_management import create_or_update_itinerary_for_user

        itinerary = self._itinerary(title='Rename Guard')
        location = itinerary.locations.create(
            name='台北101',
            travel_method='walk',
            visit_date='2026-06-01T09:00:00+08:00',
            latitude=25.0339,
            longitude=121.5645,
            route_order=0,
        )

        result = create_or_update_itinerary_for_user(self.owner, {
            'itinerary_id': itinerary.id,
            'locations': [{
                'route_order': 0,
                'name': 'Taipei 101',
                'visit_date': '2026-06-02T10:00',
            }],
        })

        location.refresh_from_db()
        location_local = timezone.localtime(location.visit_date)
        self.assertEqual(result['status'], 'ok')
        self.assertEqual(location.name, '台北101')
        self.assertEqual(location_local.date().isoformat(), '2026-06-02')
        self.assertEqual(location_local.hour, 10)

    def test_patch_update_adds_new_location_without_replacing_existing(self):
        from app.agents.services.itinerary_management import create_or_update_itinerary_for_user

        itinerary = self._itinerary(title='Patch Add Location')
        itinerary.locations.create(
            name='台北101',
            travel_method='walk',
            visit_date='2026-06-01T09:00:00+08:00',
            latitude=25.0339,
            longitude=121.5645,
            route_order=0,
        )

        with patch(
            'app.agents.services.itinerary_management._geocode_location_coordinates',
            return_value=(25.0478, 121.5319),
        ):
            result = create_or_update_itinerary_for_user(self.owner, {
                'itinerary_id': itinerary.id,
                'locations': [{
                    'name': '西門町',
                    'travel_method': 'walk',
                    'visit_date': '2026-06-01T14:00',
                }],
            })

        names = list(itinerary.locations.values_list('name', flat=True))
        self.assertEqual(result['status'], 'ok')
        self.assertEqual(set(names), {'台北101', '西門町'})

    def test_collaborator_can_update_status(self):
        from app.agents.services.itinerary_management import manage_itinerary_status_for_user

        itinerary = self._itinerary()
        itinerary.collaborators.add(self.collaborator)

        result = manage_itinerary_status_for_user(self.collaborator, itinerary.id, 'ongoing')

        itinerary.refresh_from_db()
        self.assertEqual(result['status'], 'ok')
        self.assertEqual(itinerary.status, 'ongoing')

    def test_unrelated_user_cannot_update_itinerary(self):
        from app.agents.services.itinerary_management import create_or_update_itinerary_for_user

        itinerary = self._itinerary()

        result = create_or_update_itinerary_for_user(self.other_user, {
            'itinerary_id': itinerary.id,
            'title': 'Blocked Update',
        })

        itinerary.refresh_from_db()
        self.assertEqual(result['status'], 'error')
        self.assertEqual(result['error_code'], 'itinerary_not_found')
        self.assertNotEqual(itinerary.title, 'Blocked Update')

    def test_invalid_status_is_rejected(self):
        from app.agents.services.itinerary_management import manage_itinerary_status_for_user

        itinerary = self._itinerary()

        result = manage_itinerary_status_for_user(self.owner, itinerary.id, 'archived')

        itinerary.refresh_from_db()
        self.assertEqual(result['status'], 'error')
        self.assertEqual(result['error_code'], 'invalid_status')
        self.assertEqual(itinerary.status, 'draft')

    def test_malformed_itinerary_id_is_rejected(self):
        from app.agents.services.itinerary_management import manage_itinerary_status_for_user

        result = manage_itinerary_status_for_user(self.owner, 'not-a-uuid', 'ongoing')

        self.assertEqual(result['status'], 'error')
        self.assertEqual(result['error_code'], 'invalid_itinerary_id')

    def test_owner_can_delete_owned_itinerary(self):
        from app.agents.services.itinerary_management import delete_itinerary_for_user

        itinerary = self._itinerary(title='Delete Owned')

        result = delete_itinerary_for_user(self.owner, itinerary.id)

        self.assertEqual(result['status'], 'ok')
        self.assertEqual(result['tool'], 'delete_itinerary')
        self.assertEqual(result['itinerary_id'], str(itinerary.id))
        self.assertFalse(Itinerary.objects.filter(id=itinerary.id).exists())

    def test_non_owner_cannot_delete_itinerary(self):
        from app.agents.services.itinerary_management import delete_itinerary_for_user

        itinerary = self._itinerary(title='Delete Forbidden')
        itinerary.collaborators.add(self.collaborator)

        result = delete_itinerary_for_user(self.collaborator, itinerary.id)

        self.assertEqual(result['status'], 'error')
        self.assertEqual(result['error_code'], 'itinerary_not_found')
        self.assertTrue(Itinerary.objects.filter(id=itinerary.id).exists())

    def test_tool_requires_authenticated_context(self):
        from app.agents.tools.itinerary_tools import manage_itinerary_status

        result = invoke_tool(manage_itinerary_status, itinerary_id='not-a-uuid', status='ongoing')

        self.assertEqual(result['status'], 'error')
        self.assertEqual(result['error_code'], 'authentication_required')

    def test_tool_uses_bound_authenticated_context(self):
        from app.agents.tool_context import planner_tool_user
        from app.agents.tools.itinerary_tools import manage_itinerary_status

        itinerary = self._itinerary()

        with planner_tool_user(self.owner):
            result = invoke_tool(manage_itinerary_status, itinerary_id=str(itinerary.id), status='completed')

        itinerary.refresh_from_db()
        self.assertEqual(result['status'], 'ok')
        self.assertEqual(itinerary.status, 'completed')

    def test_delete_tool_uses_bound_authenticated_context(self):
        from app.agents.tool_context import planner_tool_user
        from app.agents.tools.itinerary_tools import delete_itinerary

        itinerary = self._itinerary(title='Delete Tool Context')

        with planner_tool_user(self.owner):
            result = invoke_tool(delete_itinerary, itinerary_id=str(itinerary.id))

        self.assertEqual(result['status'], 'ok')
        self.assertFalse(Itinerary.objects.filter(id=itinerary.id).exists())


class PlannerAgentToolRegistryTests(TestCase):
    def test_registry_exposes_exactly_five_documented_tool_groups(self):
        from app.agents.tool_groups import TOOL_GROUPS

        docs = (settings.BASE_DIR / 'docs' / 'planner_agent_tools.md').read_text(encoding='utf-8')

        self.assertEqual(len(TOOL_GROUPS), 5)
        self.assertNotIn('Owner ', docs)
        for group in TOOL_GROUPS:
            self.assertIn(group.name, docs)
            self.assertIn(group.module_path, docs)
            self.assertGreater(len(group.tools), 0)


class PlannerAgentToolTests(TestCase):
    def setUp(self):
        self.owner = User.objects.create_user(username='review-owner', password='password123')
        self.collaborator = User.objects.create_user(username='review-helper', password='password123')
        self.other_user = User.objects.create_user(username='review-other', password='password123')

    def _itinerary(self, **overrides):
        values = {
            'owner': self.owner,
            'title': 'Taipei Review',
            'start_date': '2026-06-01',
            'end_date': '2026-06-03',
            'location': 'Taipei',
            'budget': '30000.00',
            'description': 'DO_NOT_LOG_SECRET description',
            'is_public': False,
            'status': 'draft',
        }
        values.update(overrides)
        return Itinerary.objects.create(**values)

    def test_review_owned_itinerary_returns_safe_review(self):
        from app.agents.tool_context import planner_tool_user
        from app.agents.tools.review_tools import review_itinerary_on_request

        itinerary = self._itinerary()
        location = itinerary.locations.create(
            name='Taipei 101',
            travel_method='walk',
            note='DO_NOT_LOG_SECRET route note',
            visit_date='2026-06-02T09:00:00+08:00',
            latitude=25.0339,
            longitude=121.5645,
            route_order=0,
        )
        location.expenses.create(expense_type='ticket', amount='500.00')

        with self.assertLogs('app.agents.tools.review_tools', level='INFO') as logs, planner_tool_user(self.owner):
            result = invoke_tool(review_itinerary_on_request, itinerary_id=str(itinerary.id), review_focus='budget and route')

        log_text = ' '.join(logs.output)
        self.assertEqual(result['status'], 'ok')
        self.assertEqual(result['tool'], 'review_itinerary_on_request')
        self.assertEqual(result['itinerary_id'], str(itinerary.id))
        self.assertEqual(result['review_summary']['relationship'], 'owner')
        self.assertEqual(result['review_summary']['route_waypoint_count'], 1)
        self.assertEqual(result['review_summary']['expense_total'], '500.00')
        self.assertNotIn('DO_NOT_LOG_SECRET', log_text)
        self.assertNotIn('DO_NOT_LOG_SECRET', json.dumps(result))

    def test_review_without_itinerary_id_returns_confirmation_response(self):
        from app.agents.tool_context import planner_tool_user
        from app.agents.tools.review_tools import review_itinerary_on_request

        with planner_tool_user(self.owner):
            result = invoke_tool(review_itinerary_on_request)

        self.assertEqual(result['status'], 'confirmation_required')
        self.assertEqual(result['error_code'], 'missing_itinerary_context')

    def test_review_rejects_malformed_itinerary_id(self):
        from app.agents.tool_context import planner_tool_user
        from app.agents.tools.review_tools import review_itinerary_on_request

        with planner_tool_user(self.owner):
            result = invoke_tool(review_itinerary_on_request, itinerary_id='not-a-uuid')

        self.assertEqual(result['status'], 'error')
        self.assertEqual(result['error_code'], 'invalid_itinerary_id')

    def test_private_itinerary_review_denies_non_collaborator(self):
        from app.agents.tool_context import planner_tool_user
        from app.agents.tools.review_tools import review_itinerary_on_request

        itinerary = self._itinerary(is_public=False)

        with planner_tool_user(self.other_user):
            result = invoke_tool(review_itinerary_on_request, itinerary_id=str(itinerary.id))

        self.assertEqual(result['status'], 'error')
        self.assertEqual(result['error_code'], 'itinerary_not_found')

    def test_review_includes_route_and_expense_risk_signals(self):
        from app.agents.tool_context import planner_tool_user
        from app.agents.tools.review_tools import review_itinerary_on_request

        itinerary = self._itinerary(budget='1000.00')
        location = itinerary.locations.create(
            name='Coordinate Missing Stop',
            travel_method='walk',
            visit_date='2026-06-02T09:00:00+08:00',
            latitude=0,
            longitude=0,
            route_order=0,
        )
        location.expenses.create(expense_type='ticket', amount='1200.00')

        with planner_tool_user(self.owner):
            result = invoke_tool(review_itinerary_on_request, itinerary_id=str(itinerary.id))

        risk_codes = {risk['code'] for risk in result['risks']}
        self.assertIn('missing_route_coordinates', risk_codes)
        self.assertIn('expenses_over_budget', risk_codes)
        self.assertEqual(result['review_summary']['route_waypoint_count'], 0)

    def test_search_public_itineraries_filters_private_results_out(self):
        from app.agents.tools.public_itinerary_tools import search_public_itineraries

        public = self._itinerary(title='Public Taipei Trip', is_public=True)
        self._itinerary(title='Private Taipei Trip', is_public=False)

        result = invoke_tool(search_public_itineraries, query='Taipei')

        self.assertEqual(result['status'], 'ok')
        self.assertEqual(result['count'], 1)
        self.assertEqual(result['itineraries'][0]['id'], str(public.id))

    def test_search_public_itineraries_respects_query_location_and_max_budget(self):
        from app.agents.tools.public_itinerary_tools import search_public_itineraries

        match = self._itinerary(title='Taipei Food Trip', location='Taipei', budget='25000.00', is_public=True)
        match.tags.add(Tag.objects.create(name='food'))
        match.locations.create(
            name='Shilin Night Market',
            travel_method='walk',
            visit_date='2026-06-02T19:00:00+08:00',
            latitude=25.088,
            longitude=121.524,
            route_order=0,
        )
        self._itinerary(title='Taipei Luxury Trip', location='Taipei', budget='40000.00', is_public=True)
        self._itinerary(title='Tokyo Food Trip', location='Tokyo', budget='20000.00', is_public=True)

        result = invoke_tool(search_public_itineraries, query='Taipei', location='Shilin', budget='30000')

        self.assertEqual(result['status'], 'ok')
        self.assertEqual(result['count'], 1)
        self.assertEqual(result['itineraries'][0]['id'], str(match.id))
        self.assertEqual(result['itineraries'][0]['tag_names'], ['food'])
        self.assertEqual(result['itineraries'][0]['public_stop_count'], 1)

    def test_search_public_itineraries_logs_safe_metadata_only(self):
        from app.agents.tools.public_itinerary_tools import search_public_itineraries

        self._itinerary(title='DO_NOT_LOG_SECRET title', location='Taipei', is_public=True)

        with self.assertLogs('app.agents.tools.public_itinerary_tools', level='INFO') as logs:
            result = invoke_tool(search_public_itineraries, query='DO_NOT_LOG_SECRET', location='Taipei')

        log_text = ' '.join(logs.output)
        self.assertEqual(result['status'], 'ok')
        self.assertNotIn('DO_NOT_LOG_SECRET', log_text)

    def test_copy_public_itinerary_requires_authenticated_context(self):
        from app.agents.tools.public_itinerary_tools import copy_public_itinerary_to_my_items

        result = invoke_tool(copy_public_itinerary_to_my_items, public_itinerary_id='not-a-uuid')

        self.assertEqual(result['status'], 'error')
        self.assertEqual(result['error_code'], 'authentication_required')

    def test_copy_public_itinerary_creates_private_copy(self):
        from app.agents.tool_context import planner_tool_user
        from app.agents.tools.public_itinerary_tools import copy_public_itinerary_to_my_items

        source = self._itinerary(
            title='Japan Public Trip',
            location='Tokyo',
            budget='50000.00',
            budget_currency='JPY',
            is_public=True,
            status='completed',
        )

        with planner_tool_user(self.other_user):
            result = invoke_tool(copy_public_itinerary_to_my_items, public_itinerary_id=str(source.id))

        source.refresh_from_db()
        new_itinerary = Itinerary.objects.get(id=result['new_itinerary_id'])
        self.assertEqual(result['status'], 'ok')
        self.assertEqual(result['tool'], 'copy_public_itinerary_to_my_items')
        self.assertEqual(result['source_itinerary_id'], str(source.id))
        self.assertEqual(result['title'], 'Japan Public Trip')
        self.assertEqual(result['message'], '已將公共行程複製到你的項目。')
        self.assertEqual(new_itinerary.title, source.title)
        self.assertEqual(new_itinerary.start_date, source.start_date)
        self.assertEqual(new_itinerary.end_date, source.end_date)
        self.assertEqual(new_itinerary.location, source.location)
        self.assertEqual(new_itinerary.budget, source.budget)
        self.assertEqual(new_itinerary.budget_currency, source.budget_currency)
        self.assertEqual(new_itinerary.description, source.description)
        self.assertEqual(new_itinerary.status, 'draft')

    def test_copy_public_itinerary_rejects_private_source(self):
        from app.agents.tool_context import planner_tool_user
        from app.agents.tools.public_itinerary_tools import copy_public_itinerary_to_my_items

        source = self._itinerary(is_public=False)

        with planner_tool_user(self.other_user):
            result = invoke_tool(copy_public_itinerary_to_my_items, public_itinerary_id=str(source.id))

        self.assertEqual(result['status'], 'error')
        self.assertEqual(result['error_code'], 'public_itinerary_not_found')
        self.assertFalse(Itinerary.objects.filter(owner=self.other_user, title=source.title).exists())

    def test_copy_public_itinerary_owner_is_bound_user(self):
        from app.agents.tool_context import planner_tool_user
        from app.agents.tools.public_itinerary_tools import copy_public_itinerary_to_my_items

        source = self._itinerary(is_public=True)

        with planner_tool_user(self.other_user):
            result = invoke_tool(copy_public_itinerary_to_my_items, public_itinerary_id=str(source.id))

        new_itinerary = Itinerary.objects.get(id=result['new_itinerary_id'])
        self.assertEqual(new_itinerary.owner, self.other_user)

    def test_copy_public_itinerary_result_is_not_public(self):
        from app.agents.tool_context import planner_tool_user
        from app.agents.tools.public_itinerary_tools import copy_public_itinerary_to_my_items

        source = self._itinerary(is_public=True)

        with planner_tool_user(self.other_user):
            result = invoke_tool(copy_public_itinerary_to_my_items, public_itinerary_id=str(source.id))

        new_itinerary = Itinerary.objects.get(id=result['new_itinerary_id'])
        self.assertFalse(new_itinerary.is_public)

    def test_copy_public_itinerary_copies_locations_and_expenses(self):
        from app.agents.tool_context import planner_tool_user
        from app.agents.tools.public_itinerary_tools import copy_public_itinerary_to_my_items

        source = self._itinerary(title='Nested Public Trip', is_public=True)
        first = source.locations.create(
            name='Tokyo Tower',
            travel_method='train',
            note='Observation deck',
            visit_date='2026-06-02T09:00:00+08:00',
            latitude=35.6586,
            longitude=139.7454,
            route_order=0,
        )
        first.expenses.create(expense_type='ticket', amount='1200.00')
        first.expenses.create(expense_type='transport', amount='300.00')
        source.locations.create(
            name='Senso-ji',
            travel_method='walk',
            note='Temple visit',
            visit_date='2026-06-02T13:00:00+08:00',
            latitude=35.7148,
            longitude=139.7967,
            route_order=1,
        )

        with planner_tool_user(self.other_user):
            result = invoke_tool(copy_public_itinerary_to_my_items, public_itinerary_id=str(source.id))

        new_itinerary = Itinerary.objects.get(id=result['new_itinerary_id'])
        new_locations = list(new_itinerary.locations.prefetch_related('expenses'))
        self.assertEqual(result['location_count'], 2)
        self.assertEqual(result['expense_count'], 2)
        self.assertEqual([location.name for location in new_locations], ['Tokyo Tower', 'Senso-ji'])
        self.assertEqual(new_locations[0].travel_method, 'train')
        self.assertEqual(new_locations[0].note, 'Observation deck')
        self.assertAlmostEqual(new_locations[0].latitude, 35.6586)
        self.assertAlmostEqual(new_locations[0].longitude, 139.7454)
        self.assertEqual(new_locations[0].route_order, 0)
        self.assertEqual(
            list(new_locations[0].expenses.order_by('expense_type').values_list('expense_type', 'amount')),
            [('ticket', Decimal('1200.00')), ('transport', Decimal('300.00'))],
        )

    def test_copy_public_itinerary_copies_tags_without_collaborators(self):
        from app.agents.tool_context import planner_tool_user
        from app.agents.tools.public_itinerary_tools import copy_public_itinerary_to_my_items

        source = self._itinerary(is_public=True)
        source.tags.add(Tag.objects.create(name='food'), Tag.objects.create(name='family'))
        source.collaborators.add(self.collaborator)

        with planner_tool_user(self.other_user):
            result = invoke_tool(copy_public_itinerary_to_my_items, public_itinerary_id=str(source.id))

        new_itinerary = Itinerary.objects.get(id=result['new_itinerary_id'])
        self.assertEqual(set(new_itinerary.tags.values_list('name', flat=True)), {'food', 'family'})
        self.assertEqual(new_itinerary.collaborators.count(), 0)


class ItineraryDiscoveryViewTests(TestCase):
    def setUp(self):
        self.owner = User.objects.create_user(username='discover-owner', password='password123')
        self.collaborator = User.objects.create_user(username='discover-helper', password='password123')
        self.client.login(username='discover-owner', password='password123')

    def _itinerary(self, **overrides):
        values = {
            'owner': self.owner,
            'title': 'Taipei Food Tour',
            'start_date': '2026-06-01',
            'end_date': '2026-06-03',
            'location': 'Taipei',
            'budget': '1200.00',
            'description': 'Night market route',
            'is_public': True,
            'status': 'draft',
        }
        values.update(overrides)
        return Itinerary.objects.create(**values)

    def test_search_filters_public_itineraries(self):
        match = self._itinerary()
        match.locations.create(
            name='Shilin Night Market',
            travel_method='walk',
            note='MRT transfer',
            visit_date='2026-06-02T19:00:00+08:00',
            latitude=25.088,
            longitude=121.524,
            route_order=0,
        )
        self._itinerary(title='Hidden Taipei Food Tour', is_public=False)
        self._itinerary(title='Tokyo Museum Day', location='Tokyo', budget='3000.00')

        response = self.client.get(reverse('search'), {
            'q': 'Taipei',
            'travel_method': 'walk',
            'budget': '1200',
            'location': 'Shilin',
            'transport': 'MRT',
            'start_date': '2026-06-01',
            'end_date': '2026-06-03',
        })

        self.assertEqual(response.status_code, 200)
        self.assertEqual(list(response.context['results']), [match])

    def test_my_and_shared_itinerary_pages_render_expected_cards(self):
        owned = self._itinerary(title='Owned Trip', is_public=False)
        shared = self._itinerary(title='Shared Trip', is_public=False)
        shared.collaborators.add(self.collaborator)

        mine = self.client.get(reverse('my_itineraries'))
        self.client.logout()
        self.client.login(username='discover-helper', password='password123')
        shared_response = self.client.get(reverse('shared_itineraries'))

        self.assertContains(mine, owned.title)
        self.assertContains(mine, '匯入行事曆')
        self.assertContains(shared_response, shared.title)
        self.assertNotContains(mine, '由 discover-owner 共享')
        self.assertContains(shared_response, '由 discover-owner 共享')
        self.assertNotContains(shared_response, '匯入行事曆')

    def test_owner_can_delete_itinerary(self):
        itinerary = self._itinerary(title='Delete Me', is_public=False)

        response = self.client.post(reverse('delete_itinerary', args=[itinerary.id]))

        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, reverse('my_itineraries'))
        self.assertFalse(Itinerary.objects.filter(id=itinerary.id).exists())

    def test_owner_can_import_ongoing_itinerary_to_calendar_from_my_page(self):
        itinerary = self._itinerary(title='Import Me', is_public=False, status='ongoing')
        itinerary.locations.create(
            name='Museum',
            travel_method='walk',
            note='',
            visit_date='2026-06-02T10:00:00+08:00',
            latitude=25.03752,
            longitude=121.56368,
            route_order=0,
        )

        response = self.client.post(reverse('sync_itinerary_calendar', args=[itinerary.id]), follow=True)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(Event.objects.count(), 1)
        self.assertEqual(Event.objects.get().event_name, 'Import Me｜Museum')
        messages_text = ' '.join(str(message) for message in response.context['messages'])
        self.assertIn('已匯入 1 筆行程到行事曆', messages_text)

    def test_import_calendar_skips_non_ongoing_itinerary(self):
        itinerary = self._itinerary(title='Draft Import', is_public=False, status='draft')

        response = self.client.post(reverse('sync_itinerary_calendar', args=[itinerary.id]), follow=True)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(Event.objects.count(), 0)
        messages_text = ' '.join(str(message) for message in response.context['messages'])
        self.assertIn('只有進行中的行程才可以匯入行事曆', messages_text)


class ItineraryTemplateViewTests(TestCase):
    def setUp(self):
        self.owner = User.objects.create_user(username='template-owner', password='password123')
        self.user = User.objects.create_user(username='template-user', password='password123')
        self.client.login(username='template-user', password='password123')

    def test_template_list_shows_public_templates_only(self):
        public = Itinerary.objects.create(
            owner=self.owner,
            title='Public Template',
            start_date='2026-06-01',
            end_date='2026-06-03',
            location='Taipei',
            budget='1000.00',
            is_public=True,
        )
        private = Itinerary.objects.create(
            owner=self.owner,
            title='Private Template',
            start_date='2026-06-01',
            end_date='2026-06-03',
            location='Taipei',
            budget='1000.00',
            is_public=False,
        )

        response = self.client.get(reverse('template_list'))

        self.assertEqual(list(response.context['templates']), [public])
        self.assertContains(response, public.title)
        self.assertNotContains(response, private.title)

    def test_copy_itinerary_copies_tags_locations_and_expenses(self):
        tag = Tag.objects.create(name='food')
        original = Itinerary.objects.create(
            owner=self.owner,
            title='Copy Source',
            start_date='2026-06-01',
            end_date='2026-06-03',
            location='Taipei',
            budget='1000.00',
            budget_currency='JPY',
            description='Template description',
            is_public=True,
        )
        original.tags.add(tag)
        location = original.locations.create(
            name='Museum',
            travel_method='walk',
            note='Short walk',
            visit_date='2026-06-02T10:00:00+08:00',
            latitude=25.03752,
            longitude=121.56368,
            route_order=0,
        )
        location.expenses.create(expense_type='ticket', amount='15.50')

        response = self.client.post(reverse('copy_itinerary'), {
            'owner_username': self.owner.username,
            'itinerary_id': original.id,
        })

        copied = Itinerary.objects.get(owner=self.user, title='Copy Source (副本)')
        copied_location = copied.locations.get()
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, reverse('itinerary_detail', args=[copied.id]))
        self.assertEqual(list(copied.tags.all()), [tag])
        self.assertEqual(copied_location.name, location.name)
        self.assertEqual(copied_location.expenses.get().amount, Decimal('15.50'))
        self.assertEqual(copied.budget_currency, 'JPY')

    def test_copy_itinerary_get_redirects_to_template_list(self):
        response = self.client.get(reverse('copy_itinerary'))

        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, reverse('template_list'))


class TravelContextToolTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username='travel-user', password='password123')
        self.client.login(username='travel-user', password='password123')

    def test_lookup_weather_reuses_existing_service_and_formats_safe_response(self):
        from app.agents.tools.travel_context_tools import lookup_weather
        from app.agents.tool_context import planner_tool_user

        weather_data = {
            'city': 'Taipei',
            'country': 'TW',
            'temperature': 28,
            'feels_like': 31,
            'description': 'Clear sky',
            'humidity': 70,
            'wind_speed': 10.5,
            'date': 'Jun 12',
            'time': '09:00 AM',
        }
        forecast_data = [
            {
                'day': 'Thursday',
                'date': 'Jun 12',
                'time': '12:00 PM',
                'temperature': 29,
                'description': 'Sunny',
                'humidity': 65,
                'wind_speed': 9.1,
                'pop': 10,
            },
            {
                'day': 'Friday',
                'date': 'Jun 13',
                'time': '09:00 AM',
                'temperature': 27,
                'description': 'Cloudy',
                'humidity': 72,
                'wind_speed': 8.4,
                'pop': 20,
            },
        ]

        with patch(
            'app.agents.tools.travel_context_tools.fetch_weather_and_forecast',
            return_value=(weather_data, forecast_data),
        ) as weather_mock, planner_tool_user(self.user):
            result = invoke_tool(lookup_weather, city='Taipei', date='2026-06-12')

        weather_mock.assert_called_once()
        self.assertEqual(result['status'], 'ok')
        self.assertEqual(result['tool'], 'lookup_weather')
        self.assertEqual(result['normalized_values']['city'], 'Taipei')
        self.assertEqual(result['normalized_values']['date'], '2026-06-12')
        self.assertEqual(result['forecast_match_count'], 1)
        self.assertEqual(result['forecast'][0]['date_label'], 'Jun 12')

    def test_lookup_weather_hides_provider_details_in_error_and_logs(self):
        from app.agents.tools.travel_context_tools import lookup_weather
        from app.agents.tool_context import planner_tool_user
        from app.views.weather.weather import WeatherLookupError

        with patch(
            'app.agents.tools.travel_context_tools.fetch_weather_and_forecast',
            side_effect=WeatherLookupError('DO_NOT_LOG_SECRET provider payload'),
        ), self.assertLogs('app.agents.tools.travel_context_tools', level='WARNING') as logs, planner_tool_user(self.user):
            result = invoke_tool(lookup_weather, city='Taipei', date='2026-06-12')

        log_text = ' '.join(logs.output)
        self.assertEqual(result['status'], 'error')
        self.assertEqual(result['error_code'], 'weather_lookup_failed')
        self.assertNotIn('DO_NOT_LOG_SECRET', result['message'])
        self.assertNotIn('DO_NOT_LOG_SECRET', log_text)

    def test_convert_currency_reuses_existing_service(self):
        from app.agents.tools.travel_context_tools import convert_currency

        with patch('app.agents.tools.travel_context_tools.get_exchange_rate', return_value=31.25) as rate_mock:
            result = invoke_tool(convert_currency, from_currency='usd', to_currency='twd', amount='10')

        rate_mock.assert_called_once_with('USD', 'TWD')
        self.assertEqual(result['status'], 'ok')
        self.assertEqual(result['exchange_rate'], 31.25)
        self.assertEqual(result['converted_amount_display'], '312.50')

    def test_convert_currency_hides_provider_errors(self):
        from app.agents.tools.travel_context_tools import convert_currency

        with patch(
            'app.agents.tools.travel_context_tools.get_exchange_rate',
            return_value=Exception('DO_NOT_LOG_SECRET provider payload'),
        ), self.assertLogs('app.agents.tools.travel_context_tools', level='WARNING') as logs:
            result = invoke_tool(convert_currency, from_currency='USD', to_currency='TWD', amount='10')

        log_text = ' '.join(logs.output)
        self.assertEqual(result['status'], 'error')
        self.assertEqual(result['error_code'], 'exchange_lookup_failed')
        self.assertNotIn('DO_NOT_LOG_SECRET', result['message'])
        self.assertNotIn('DO_NOT_LOG_SECRET', log_text)

    def test_exchange_view_returns_provider_message_without_type_error(self):
        with patch(
            'app.views.exchange.exchange.get_exchange_rate',
            return_value=Exception('Provider unavailable'),
        ):
            response = self.client.post(reverse('exchange'), {
                'from_currency': 'USD',
                'to_currency': 'TWD',
                'amount': '10',
            }, follow=True)

        self.assertEqual(response.status_code, 200)
        messages = list(response.context['messages'])
        self.assertTrue(any('Provider unavailable' in str(message) for message in messages))


class CalendarManagementToolTests(TestCase):
    def setUp(self):
        self.owner = User.objects.create_user(username='calendar-tool-owner', password='password123')
        self.other_user = User.objects.create_user(username='calendar-tool-other', password='password123')

    def test_list_calendar_events_returns_only_authenticated_users_events(self):
        from app.agents.tools.calendar_tools import list_calendar_events
        from app.agents.tool_context import planner_tool_user

        Event.objects.create(owner=self.owner, event_name='DO_NOT_LOG_SECRET owner event', date='2026-06-12', color='green')
        Event.objects.create(owner=self.other_user, event_name='other event', date='2026-06-13', color='orange')

        with planner_tool_user(self.owner):
            result = invoke_tool(list_calendar_events, start_date='2026-06-01', end_date='2026-06-30')

        self.assertEqual(result['status'], 'ok')
        self.assertEqual(result['count'], 1)
        self.assertEqual(result['events'][0]['color'], 'green')
        self.assertEqual(result['events'][0]['date'], '2026-06-12')

    def test_create_calendar_event_validates_payload_assigns_owner_and_keeps_logs_safe(self):
        from app.agents.tools.calendar_tools import create_calendar_event
        from app.agents.tool_context import planner_tool_user

        payload = {
            'eventName': 'DO_NOT_LOG_SECRET trip planning',
            'date': '2026-06-18',
            'color': 'blue',
        }

        with self.assertLogs('app.agents.tools.calendar_tools', level='INFO') as logs, planner_tool_user(self.owner):
            result = invoke_tool(create_calendar_event, event_payload=payload)

        event = Event.objects.get()
        log_text = ' '.join(logs.output)
        self.assertEqual(result['status'], 'ok')
        self.assertEqual(event.owner, self.owner)
        self.assertEqual(event.color, 'blue')
        self.assertNotIn('DO_NOT_LOG_SECRET', log_text)

    def test_create_calendar_event_rejects_invalid_color(self):
        from app.agents.tools.calendar_tools import create_calendar_event
        from app.agents.tool_context import planner_tool_user

        with planner_tool_user(self.owner):
            result = invoke_tool(create_calendar_event, event_payload={
                'eventName': 'Bad color',
                'date': '2026-06-18',
                'color': 'purple',
            })

        self.assertEqual(result['status'], 'error')
        self.assertEqual(result['error_code'], 'invalid_color')
        self.assertEqual(Event.objects.count(), 0)

    def test_delete_calendar_event_removes_only_owned_event(self):
        from app.agents.tools.calendar_tools import delete_calendar_event
        from app.agents.tool_context import planner_tool_user

        event = Event.objects.create(owner=self.owner, event_name='Delete me', date='2026-06-18', color='yellow')

        with planner_tool_user(self.owner):
            result = invoke_tool(delete_calendar_event, event_id=str(event.id))

        self.assertEqual(result['status'], 'ok')
        self.assertFalse(Event.objects.filter(id=event.id).exists())

    def test_delete_calendar_event_cannot_remove_other_users_event(self):
        from app.agents.tools.calendar_tools import delete_calendar_event
        from app.agents.tool_context import planner_tool_user

        event = Event.objects.create(owner=self.other_user, event_name='Private dinner', date='2026-06-18', color='yellow')

        with self.assertLogs('app.agents.tools.calendar_tools', level='WARNING'), planner_tool_user(self.owner):
            result = invoke_tool(delete_calendar_event, event_id=str(event.id))

        self.assertEqual(result['status'], 'error')
        self.assertEqual(result['error_code'], 'event_not_found')
        self.assertTrue(Event.objects.filter(id=event.id).exists())


class StaticHygieneTests(TestCase):
    def test_templates_static_sources_and_currency_data_have_no_emoji(self):
        emoji_pattern = re.compile(r'[\U0001F300-\U0001FAFF\u2600-\u27BF]')
        roots = [
            settings.BASE_DIR / 'app' / 'templates',
            settings.BASE_DIR / 'app' / 'static' / 'src',
            settings.BASE_DIR / 'app' / 'static' / 'itinerary',
            settings.BASE_DIR / 'app' / 'static' / 'calendar',
        ]
        files = []
        for root in roots:
            files.extend(path for path in Path(root).rglob('*') if path.is_file())
        files.append(settings.BASE_DIR / 'app' / 'views' / 'exchange' / 'currencies.json')

        offenders = [
            str(path.relative_to(settings.BASE_DIR))
            for path in files
            if emoji_pattern.search(path.read_text(encoding='utf-8'))
        ]

        self.assertEqual(offenders, [])

    def test_base_templates_reference_tailwind_output(self):
        common_base = (settings.BASE_DIR / 'app' / 'templates' / 'common' / 'base.html').read_text(encoding='utf-8')
        auth_base = (settings.BASE_DIR / 'app' / 'templates' / 'auth' / 'base.html').read_text(encoding='utf-8')

        self.assertIn("dist/app.css", common_base)
        self.assertIn("dist/app.css", auth_base)
        self.assertNotIn("bootstrap", common_base.lower())
        self.assertNotIn("bootstrap", auth_base.lower())
