"""Shared, policy-aware Nominatim forward and reverse geocoding."""

import logging
import threading
import time as time_module
from datetime import timedelta

import requests
from django.conf import settings
from django.utils import timezone

from app.models import ReverseGeocodeCache

logger = logging.getLogger(__name__)

PROVIDER = "nominatim"
CITY_FIELDS = ("city", "town", "village", "municipality", "county")
_request_lock = threading.Lock()
_next_request_at = 0.0


def forward_geocode(location_name, geocoding_context=""):
    """Resolve coordinates using the contextual query first, then the bare name."""
    queries = _unique_in_order([
        _geocoding_query(location_name, geocoding_context),
        location_name,
    ])
    for query in queries:
        coordinates = _forward_request(query)
        if coordinates:
            logger.info("Nominatim forward geocoding succeeded for query length %s.", len(query))
            return coordinates
    logger.warning("Nominatim forward geocoding found no coordinates for location length %s.", len(location_name))
    return None


def reverse_geocode_cached(latitude, longitude):
    """Return normalized geography, preferring fresh and then stale persistent cache data."""
    coordinate_key = normalized_coordinate_key(latitude, longitude)
    cached = ReverseGeocodeCache.objects.filter(
        provider=PROVIDER,
        coordinate_key=coordinate_key,
    ).first()
    if cached and _is_fresh(cached):
        logger.info("Nominatim reverse geocoding cache hit.")
        return _serialize_cache(cached, cache_status="hit", stale=False)

    geography = _reverse_request(latitude, longitude)
    if geography:
        cache, _ = ReverseGeocodeCache.objects.update_or_create(
            provider=PROVIDER,
            coordinate_key=coordinate_key,
            defaults={
                "latitude": latitude,
                "longitude": longitude,
                **geography,
            },
        )
        cache_status = "refresh" if cached else "miss"
        logger.info("Nominatim reverse geocoding stored a %s result.", cache_status)
        return _serialize_cache(cache, cache_status=cache_status, stale=False)

    if cached:
        logger.warning("Nominatim reverse geocoding failed; returning stale cached data.")
        return _serialize_cache(cached, cache_status="stale", stale=True)

    logger.warning("Nominatim reverse geocoding failed without cached data.")
    return {
        "status": "geography_unavailable",
        "provider": PROVIDER,
        "cache_status": "miss",
        "stale": False,
        "city": "",
        "state": "",
        "country": "",
        "country_code": "",
        "display_name": "",
    }


def normalized_coordinate_key(latitude, longitude):
    return f"{float(latitude):.5f},{float(longitude):.5f}"


def _forward_request(query):
    payload = _get_json(
        "search",
        params={"q": query, "format": "json", "limit": 1},
    )
    if not isinstance(payload, list):
        return None

    for result in payload:
        latitude = _parse_float(result.get("lat"))
        longitude = _parse_float(result.get("lon"))
        if latitude is not None and longitude is not None and not (latitude == 0 and longitude == 0):
            return latitude, longitude
    return None


def _reverse_request(latitude, longitude):
    payload = _get_json(
        "reverse",
        params={
            "lat": latitude,
            "lon": longitude,
            "format": "jsonv2",
            "addressdetails": 1,
            "layer": "address",
            "accept-language": "zh-TW,en",
        },
    )
    if not isinstance(payload, dict):
        return None

    address = payload.get("address")
    if not isinstance(address, dict):
        return None
    geography = {
        "city": next((str(address.get(field) or "").strip() for field in CITY_FIELDS if address.get(field)), ""),
        "state": str(address.get("state") or "").strip(),
        "country": str(address.get("country") or "").strip(),
        "country_code": str(address.get("country_code") or "").strip().upper()[:2],
        "display_name": str(payload.get("display_name") or "").strip(),
    }
    return geography if geography["city"] or geography["country"] else None


def _get_json(path, params):
    try:
        _throttle_request()
        response = requests.get(
            f"{settings.NOMINATIM_BASE_URL.rstrip('/')}/{path}",
            params=params,
            headers={
                "Accept": "application/json",
                "User-Agent": settings.NOMINATIM_USER_AGENT,
            },
            timeout=settings.REQUEST_TIMEOUT_SECONDS,
        )
        response.raise_for_status()
        return response.json()
    except (requests.RequestException, ValueError) as exc:
        logger.warning("Nominatim %s request failed with %s.", path, exc.__class__.__name__)
        return None


def _throttle_request():
    global _next_request_at
    with _request_lock:
        now = time_module.monotonic()
        delay = _next_request_at - now
        if delay > 0:
            time_module.sleep(delay)
        _next_request_at = time_module.monotonic() + settings.NOMINATIM_MIN_INTERVAL_SECONDS


def _is_fresh(cache):
    max_age = timedelta(days=settings.REVERSE_GEOCODE_CACHE_DAYS)
    return cache.updated_at >= timezone.now() - max_age


def _serialize_cache(cache, cache_status, stale):
    return {
        "status": "ok",
        "provider": cache.provider,
        "cache_status": cache_status,
        "stale": stale,
        "city": cache.city,
        "state": cache.state,
        "country": cache.country,
        "country_code": cache.country_code,
        "display_name": cache.display_name,
    }


def _geocoding_query(location_name, geocoding_context=""):
    context = str(geocoding_context or "").strip()
    if not context or context.casefold() in location_name.casefold():
        return location_name
    return f"{location_name}, {context}"


def _unique_in_order(values):
    seen = set()
    unique_values = []
    for value in values:
        if value in seen:
            continue
        seen.add(value)
        unique_values.append(value)
    return unique_values


def _parse_float(value):
    try:
        return float(value)
    except (TypeError, ValueError):
        return None
