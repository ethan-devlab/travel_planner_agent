"""Explicit itinerary review tool stubs."""

from .common import not_implemented_response


def review_itinerary_on_request(itinerary_id=None, review_focus=""):
    """Review an itinerary only when the user requests review."""
    return not_implemented_response("review_itinerary_on_request", "itinerary review")


TOOLS = (
    review_itinerary_on_request,
)

