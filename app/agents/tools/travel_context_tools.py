"""Weather and currency tool stubs."""

from .common import not_implemented_response


def lookup_weather(city="", date=""):
    """Look up weather data after implementation."""
    return not_implemented_response("lookup_weather", "weather lookup")


def convert_currency(from_currency="", to_currency="", amount=0):
    """Convert currency after implementation."""
    return not_implemented_response("convert_currency", "currency conversion")


TOOLS = (
    lookup_weather,
    convert_currency,
)

