import ipaddress
import logging
from django.http import HttpResponseForbidden
from django.conf import settings

logger = logging.getLogger('network')

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