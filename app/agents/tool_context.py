"""Request-scoped context for authenticated planner-agent tool calls."""

from contextlib import contextmanager
from contextvars import ContextVar

_current_planner_user = ContextVar("current_planner_user", default=None)


@contextmanager
def planner_tool_user(user):
    """Bind the authenticated Django user while a planner agent invokes tools."""
    token = _current_planner_user.set(user)
    try:
        yield
    finally:
        _current_planner_user.reset(token)


def get_current_planner_user():
    return _current_planner_user.get()
