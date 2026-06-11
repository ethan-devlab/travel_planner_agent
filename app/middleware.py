import ipaddress
import logging
import time
from django.http import HttpResponseForbidden
from django.conf import settings
from django.shortcuts import redirect

from .demo import cleanup_expired_demo_sessions, expire_demo_session_if_needed

logger = logging.getLogger('network')
demo_logger = logging.getLogger(__name__)
_last_demo_cleanup_at = 0.0
_DEMO_CLEANUP_INTERVAL_SECONDS = 10 * 60

class IPRangeRestrictionMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response
        
        # Load CIDR strings from settings and convert them to ip_network objects
        allowed_ranges = getattr(settings, 'ALLOWED_IP_RANGES', [])
        self.allowed_networks = [ipaddress.ip_network(net) for net in allowed_ranges]

    def __call__(self, request):
        # 1. Extract the IP address
        # Use HTTP_X_FORWARDED_FOR for reverse proxy setups, otherwise use REMOTE_ADDR
        x_forwarded_for = request.META.get('HTTP_X_FORWARDED_FOR')
        if x_forwarded_for:
            ip_str = x_forwarded_for.split(',')[0].strip()
        else:
            ip_str = request.META.get('REMOTE_ADDR')

        # 2. Validate the IP address format
        try:
            client_ip = ipaddress.ip_address(ip_str)
            logger.debug(f"Processing request from IP: {client_ip}")
        except ValueError:
            logger.warning(f"Invalid IP Address Format: {ip_str}")
            return HttpResponseForbidden("Invalid IP Address Format.")

        # 3. Check if the IP falls within any allowed range
        # Always allow localhost for development convenience
        if client_ip.is_loopback:
            return self.get_response(request)

        is_allowed = any(client_ip in network for network in self.allowed_networks)

        if not is_allowed:
            logger.warning(f"Access Denied: IP {client_ip} is not whitelisted.")
            return HttpResponseForbidden("Access Denied: Your IP is not whitelisted.")

        logger.info(f"Access Granted: IP {client_ip} is whitelisted.")
        return self.get_response(request)


class DemoSessionMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        _cleanup_expired_demo_sessions_periodically()
        if request.path != "/demo-login/" and expire_demo_session_if_needed(request):
            return redirect(settings.LOGIN_URL)
        return self.get_response(request)


def _cleanup_expired_demo_sessions_periodically():
    global _last_demo_cleanup_at
    now = time.monotonic()
    if now - _last_demo_cleanup_at < _DEMO_CLEANUP_INTERVAL_SECONDS:
        return
    _last_demo_cleanup_at = now
    deleted_count = cleanup_expired_demo_sessions()
    if deleted_count:
        demo_logger.info("Opportunistic demo cleanup removed %s expired sessions.", deleted_count)
