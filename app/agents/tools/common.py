"""Shared helpers for planner agent tools."""

import logging

logger = logging.getLogger(__name__)


try:
    from langchain_core.tools import tool as _langchain_tool
except ImportError:
    _langchain_tool = None


def planner_tool(*tool_args, **tool_kwargs):
    """Decorate a callable as a LangChain tool when LangChain is installed."""
    if _langchain_tool:
        return _langchain_tool(*tool_args, **tool_kwargs)

    if tool_args and callable(tool_args[0]) and len(tool_args) == 1 and not tool_kwargs:
        return tool_args[0]

    def decorator(func):
        logger.warning("LangChain is not installed; exposing %s as a plain callable.", func.__name__)
        return func

    return decorator


def not_implemented_response(tool_name, capability):
    logger.info("Planner agent tool stub called for %s.", tool_name)
    return {
        "status": "not_implemented",
        "tool": tool_name,
        "capability": capability,
        "message": "Planner agent framework is defined, but this tool is not implemented yet.",
    }
