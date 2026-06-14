"""Provider-neutral LangChain planner agent factory."""

import logging

from django.conf import settings
from pydantic import BaseModel, Field

from .tool_groups import all_planner_tools, planner_tool_group_count

logger = logging.getLogger(__name__)

PLANNER_AGENT_SYSTEM_PROMPT = """
You are the TravelPlanner planner agent. Use only the provided tools to plan,
review, query travel context, search public itineraries, and manage calendar
events. Do not claim a tool action succeeded unless the tool result says it did.
Always respond in concise Traditional Chinese.
When updating existing itineraries, do not rename or translate existing location
names unless the user explicitly asks to rename them.
When setting visit dates, always include a visit time (HH:MM) and avoid changing
other location details unless explicitly requested.
itinerary_id, database id, internal id, primary keys, and technical field names
are only for internal tool use. Never show them in user-visible summary,
actions, key_data, or next_steps. If a tool result contains itinerary_id or
other internal identifiers, refer to the trip as 目前行程, 此行程, or by the
itinerary title instead.
Do not output internal risk codes such as country_mismatch,
visit_date_outside_trip, or expenses_over_budget. Explain issues in natural
Traditional Chinese with user-friendly terms such as 景點, 造訪日期, 預算, and 路線.
**Do not** answer non-planner questions. Politely decline and suggest the user ask a travel-related question or use a tool if they ask something unrelated to travel planning.
"""


class PlannerAgentConfigurationError(RuntimeError):
    """Raised when the planner agent cannot be built from local configuration."""


class PlannerResponseKeyData(BaseModel):
    """Structured key-value facts used by the planner reply card."""

    label: str = Field(description="欄位名稱，使用簡短繁體中文。")
    value: str = Field(description="欄位值，使用簡短繁體中文。")


class PlannerStructuredResponse(BaseModel):
    """Structured planner-agent response rendered by the web UI."""

    summary: str = Field(description="整體摘要，最多兩句，使用繁體中文。")
    actions: list[str] = Field(default_factory=list, description="已完成或建議動作，每項一句。")
    key_data: list[PlannerResponseKeyData] = Field(default_factory=list, description="重點資料清單。")
    next_steps: list[str] = Field(default_factory=list, description="後續建議步驟，每項一句。")


def build_openai_chat_model():
    """Build the configured OpenAI chat model for planner-agent execution."""
    if not settings.OPENAI_API_KEY:
        raise PlannerAgentConfigurationError("OPENAI_API_KEY is not configured.")
    if not settings.PLANNER_AGENT_MODEL:
        raise PlannerAgentConfigurationError("MODEL is not configured.")

    try:
        from langchain_openai import ChatOpenAI
    except ImportError as exc:
        raise PlannerAgentConfigurationError("Install langchain-openai before running the planner agent.") from exc

    logger.info("Building planner agent OpenAI chat model from configured model name.")
    return ChatOpenAI(
        model=settings.PLANNER_AGENT_MODEL,
        api_key=settings.OPENAI_API_KEY,
        streaming=True,
    )


def build_planner_agent(model):
    """Build the LangChain agent once a concrete chat model is supplied."""
    if model is None:
        raise PlannerAgentConfigurationError("A LangChain chat model is required.")

    try:
        from langchain.agents import create_agent
        from langchain.agents.structured_output import ToolStrategy
    except ImportError as exc:
        raise PlannerAgentConfigurationError("Install langchain before building the planner agent.") from exc

    tools = all_planner_tools()
    logger.info(
        "Building planner agent with %s tool groups and %s tools.",
        planner_tool_group_count(),
        len(tools),
    )
    return create_agent(
        model=model,
        tools=tools,
        system_prompt=PLANNER_AGENT_SYSTEM_PROMPT.strip(),
        response_format=ToolStrategy(PlannerStructuredResponse),
    )
