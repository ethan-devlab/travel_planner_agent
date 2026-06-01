"""Tool group registry for the planner agent framework."""

from dataclasses import dataclass
from typing import Callable

from .tools import calendar_tools, itinerary_tools, public_itinerary_tools, review_tools, travel_context_tools


@dataclass(frozen=True)
class ToolGroup:
    name: str
    owner: str
    description: str
    module_path: str
    tools: tuple[Callable, ...]


TOOL_GROUPS = (
    ToolGroup(
        name="itinerary_management",
        owner="Owner A",
        description="Suggest, create, modify, and manage user itineraries.",
        module_path="app.agents.tools.itinerary_tools",
        tools=itinerary_tools.TOOLS,
    ),
    ToolGroup(
        name="itinerary_review",
        owner="Owner B",
        description="Review an itinerary only after the user asks for a review.",
        module_path="app.agents.tools.review_tools",
        tools=review_tools.TOOLS,
    ),
    ToolGroup(
        name="travel_context",
        owner="Owner C",
        description="Query weather forecasts and currency exchange context.",
        module_path="app.agents.tools.travel_context_tools",
        tools=travel_context_tools.TOOLS,
    ),
    ToolGroup(
        name="public_itinerary_lookup",
        owner="Owner B",
        description="Search and summarize public itinerary references.",
        module_path="app.agents.tools.public_itinerary_tools",
        tools=public_itinerary_tools.TOOLS,
    ),
    ToolGroup(
        name="calendar_management",
        owner="Owner C",
        description="Create, list, update, and delete user calendar events.",
        module_path="app.agents.tools.calendar_tools",
        tools=calendar_tools.TOOLS,
    ),
)


def all_planner_tools():
    return [tool for group in TOOL_GROUPS for tool in group.tools]


def planner_tool_group_count():
    return len(TOOL_GROUPS)

