"""Tool group registry for the planner agent framework."""

from dataclasses import dataclass
from typing import Callable

from .tools import calendar_tools, itinerary_tools, public_itinerary_tools, review_tools, travel_context_tools


@dataclass(frozen=True)
class ToolGroup:
    name: str
    description: str
    module_path: str
    tools: tuple[Callable, ...]


TOOL_GROUPS = (
    ToolGroup(
        name="itinerary_management",
        description="建議、新增、修改並管理使用者行程。",
        module_path="app.agents.tools.itinerary_tools",
        tools=itinerary_tools.TOOLS,
    ),
    ToolGroup(
        name="itinerary_review",
        description="僅在使用者明確要求時審閱行程。",
        module_path="app.agents.tools.review_tools",
        tools=review_tools.TOOLS,
    ),
    ToolGroup(
        name="travel_context",
        description="查詢天氣預報與匯率相關情境資訊。",
        module_path="app.agents.tools.travel_context_tools",
        tools=travel_context_tools.TOOLS,
    ),
    ToolGroup(
        name="public_itinerary_lookup",
        description="搜尋並摘要公開行程參考內容。",
        module_path="app.agents.tools.public_itinerary_tools",
        tools=public_itinerary_tools.TOOLS,
    ),
    ToolGroup(
        name="calendar_management",
        description="建立、列出、更新並刪除使用者行事曆事件。",
        module_path="app.agents.tools.calendar_tools",
        tools=calendar_tools.TOOLS,
    ),
)


def all_planner_tools():
    return [tool for group in TOOL_GROUPS for tool in group.tools]


def planner_tool_group_count():
    return len(TOOL_GROUPS)
