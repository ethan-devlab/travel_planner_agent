"""Public itinerary lookup tool stubs."""

from .common import not_implemented_response


def search_public_itineraries(query="", location="", budget=None):
    """Search public itineraries after implementation."""
    return not_implemented_response("search_public_itineraries", "public itinerary lookup")


TOOLS = (
    search_public_itineraries,
)

