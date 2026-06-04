# coding=utf-8
import datetime
import logging
import os
import re

from django.conf import settings
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.views.decorators.http import require_http_methods
from django.shortcuts import redirect, render
from dotenv import load_dotenv
import requests

load_dotenv("env/.env")

logger = logging.getLogger(__name__)

GEOCODING_URL = settings.GEOCODING_URL
CURRENT_WEATHER_URL = settings.CURRENT_WEATHER_URL
FORECAST_URL = settings.FORECAST_URL
REQUEST_TIMEOUT_SECONDS = settings.REQUEST_TIMEOUT_SECONDS

TAIWAN_CITY_ALIASES = {
    "台北": "台北市",
    "臺北": "台北市",
    "新北": "新北市",
    "桃園": "桃園市",
    "台中": "台中市",
    "臺中": "台中市",
    "台南": "台南市",
    "臺南": "台南市",
    "高雄": "高雄市",
    "基隆": "基隆市",
    "新竹": "新竹市",
    "嘉義": "嘉義市",
    "宜蘭": "宜蘭縣",
    "新竹縣": "新竹縣",
    "苗栗": "苗栗縣",
    "彰化": "彰化縣",
    "南投": "南投縣",
    "雲林": "雲林縣",
    "嘉義縣": "嘉義縣",
    "屏東": "屏東縣",
    "台東": "台東縣",
    "臺東": "台東縣",
    "花蓮": "花蓮縣",
    "澎湖": "澎湖縣",
    "金門": "金門縣",
    "連江": "連江縣",
}


class WeatherLookupError(Exception):
    pass


@login_required
@require_http_methods(["GET", "POST"])
def index(request):
    api_key = settings.WEATHER_API_KEY

    if request.method == 'POST':
        city = request.POST.get('city', '').strip()
        if not city:
            messages.error(request, "Please enter a city name.")
            return redirect('weather')

        try:
            weather_data, daily_forecasts = fetch_weather_and_forecast(city, api_key)
        except WeatherLookupError as exc:
            logger.warning("Weather lookup failed for city '%s': %s", city, exc)
            messages.error(request, str(exc))
            return redirect('weather')

        return render(request, 'weather/index.html', {
            'weather_data': weather_data,
            'daily_forecasts': daily_forecasts,
        })

    return render(request, 'weather/index.html')


def geocode_city(city, api_key, limit=5):
    if not api_key:
        raise WeatherLookupError("Weather API key is missing.")

    normalized_city, geocoding_query = normalize_weather_city_query(city)
    try:
        response = requests.get(
            GEOCODING_URL,
            params={'q': geocoding_query, 'limit': limit, 'appid': api_key},
            timeout=REQUEST_TIMEOUT_SECONDS,
        )
        response.raise_for_status()
        data = response.json()
    except requests.RequestException as exc:
        logger.exception("OpenWeather geocoding request failed")
        raise WeatherLookupError("Unable to query city coordinates right now.") from exc

    if not data:
        raise WeatherLookupError("City not found. Please use a more specific city name.")

    first_result = _select_best_geocode_result(data, normalized_city)
    return {
        'city': normalized_city,
        'lat': first_result['lat'],
        'lon': first_result['lon'],
        'country': first_result.get('country', ''),
        'matched_name': first_result.get('name', normalized_city),
        'matched_state': first_result.get('state', ''),
    }


def fetch_current_weather(lat, lon, api_key):
    return _openweather_get(CURRENT_WEATHER_URL, lat, lon, api_key)


def fetch_forecast(lat, lon, api_key):
    return _openweather_get(FORECAST_URL, lat, lon, api_key)


def _openweather_get(url, lat, lon, api_key):
    try:
        response = requests.get(
            url,
            params={'lat': lat, 'lon': lon, 'units': 'metric', 'appid': api_key},
            timeout=REQUEST_TIMEOUT_SECONDS,
        )
        response.raise_for_status()
        return response.json()
    except requests.RequestException as exc:
        logger.exception("OpenWeather weather request failed")
        raise WeatherLookupError("Unable to query weather data right now.") from exc


def fetch_weather_and_forecast(city, api_key):
    geocoded = geocode_city(city, api_key)
    weather_response = fetch_current_weather(geocoded['lat'], geocoded['lon'], api_key)
    forecast_response = fetch_forecast(geocoded['lat'], geocoded['lon'], api_key)

    weather_data = {
        'city': geocoded['city'],
        'country': geocoded['country'],
        'temperature': weather_response['main']['temp'],
        'feels_like': weather_response['main']['feels_like'],
        'description': str(weather_response['weather'][0]['description']).capitalize(),
        'icon': weather_response['weather'][0]['icon'],
        'humidity': weather_response['main']['humidity'],
        'visibility': round(weather_response.get('visibility', 0) / 1000, 2),
        'wind_speed': round(weather_response['wind']['speed'] * 3.6, 2),
        'cloudiness': weather_response['clouds']['all'],
        'date': datetime.datetime.fromtimestamp(weather_response['dt']).strftime('%b %d'),
        'time': datetime.datetime.fromtimestamp(weather_response['dt']).strftime("%I:%M %p"),
    }

    daily_forecasts = []
    for daily_data in forecast_response.get('list', [])[:25]:
        wind = daily_data.get('wind', {})
        daily_forecasts.append({
            'day': datetime.datetime.fromtimestamp(daily_data['dt']).strftime('%A'),
            'date': datetime.datetime.fromtimestamp(daily_data['dt']).strftime("%b %d"),
            'time': datetime.datetime.fromtimestamp(daily_data['dt']).strftime("%I:%M %p"),
            'temperature': daily_data['main']['temp'],
            'description': str(daily_data['weather'][0]['description']).capitalize(),
            'icon': daily_data['weather'][0]['icon'],
            'humidity': daily_data['main']['humidity'],
            'visibility': round(daily_data.get('visibility', 0) / 1000, 2),
            'wind_speed': round(wind.get('speed', 0) * 3.6, 2),
            'wind_gust': round(wind.get('gust', 0) * 3.6, 2),
            'feels_like': daily_data['main']['feels_like'],
            'temp_min': daily_data['main']['temp_min'],
            'temp_max': daily_data['main']['temp_max'],
            'cloudiness': daily_data['clouds']['all'],
            'pop': round(daily_data.get('pop', 0) * 100, 2),
        })

    return weather_data, daily_forecasts


def normalize_weather_city_query(city):
    normalized_city = re.sub(r"\s+", " ", str(city or "").strip())
    alias_key = normalized_city.replace("臺", "台")
    canonical_city = TAIWAN_CITY_ALIASES.get(alias_key, normalized_city)

    if canonical_city.endswith(("市", "縣")) and "taiwan" not in canonical_city.lower():
        return canonical_city, f"{canonical_city}, Taiwan"
    return canonical_city, canonical_city


def _select_best_geocode_result(results, normalized_city):
    canonical_city = normalized_city.replace("臺", "台")

    for result in results:
        result_name = str(result.get('name', '')).replace("臺", "台")
        if result.get('country') == 'TW' and result_name == canonical_city:
            return result

    for result in results:
        if result.get('country') == 'TW':
            return result

    return results[0]
