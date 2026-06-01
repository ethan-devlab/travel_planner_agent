# coding=utf-8
import logging
from urllib.parse import urlparse, urlunparse

from django.conf import settings

logger = logging.getLogger(__name__)

ROUTING_PROFILES = {'driving', 'walking', 'cycling'}


def normalize_routing_service_url(raw_url):
    value = (raw_url or '').strip().rstrip('/')
    if not value:
        return '', 'driving'

    if not value.startswith('https://'):
        value = f'https://{value.lstrip("/")}'

    parsed = urlparse(value)
    path_parts = [part for part in parsed.path.split('/') if part]
    profile = 'driving'

    if path_parts and path_parts[-1] in ROUTING_PROFILES:
        profile = path_parts.pop()

    if path_parts[-2:] != ['route', 'v1']:
        path_parts.extend(['route', 'v1'])

    normalized_path = '/' + '/'.join(path_parts)
    normalized_url = urlunparse((parsed.scheme, parsed.netloc, normalized_path, '', '', ''))
    if normalized_url != raw_url:
        logger.info('Normalized ROUTING_SERVICE_URL for Leaflet Routing Machine.')

    return normalized_url, profile


def routing_context():
    service_url, profile = normalize_routing_service_url(settings.ROUTING_SERVICE_URL)
    return {
        'routing_service_url': service_url,
        'routing_profile': profile,
    }


def serialize_route_waypoints(itinerary):
    waypoints = []
    for location in itinerary.locations.all():
        if location.latitude == 0 and location.longitude == 0:
            continue
        waypoints.append({
            'name': location.name,
            'lat': location.latitude,
            'lng': location.longitude,
        })
    return waypoints
