# Owner C AI Implementation Brief

## Goal
Implement the Owner C planner-agent tool groups from `docs/planner_agent_tools.md`: `travel_context` and `calendar_management`.

## Required Context
- Keep the framework boundary intact:
  - Agent factory: `app.agents.planner_agent.build_planner_agent(model)`
  - Tool registry: `app.agents.tool_groups.TOOL_GROUPS`
  - Travel context tools module: `app.agents.tools.travel_context_tools`
  - Calendar tools module: `app.agents.tools.calendar_tools`
- Owner A has completed phase-1 design and framework delivery, including the planner-agent page and baseline architecture.
- Owner A owns itinerary creation/update/status behavior. Owner B owns review and public lookup. Do not mix those responsibilities into Owner C tools.
- Use authenticated server-side context from `app.agents.tool_context.get_current_planner_user()` for calendar tools.
- Owner C implementation should be a direct build on Owner A's established framework rather than a redesign.

## Limited Real API Testing Authorization
- Limited authorization is granted to use the real OpenAI API for planner-agent verification.
- Keep tests bounded by tool capabilities documented in `docs/planner_agent_tools.md`.
- The goal is capability parity: operations available to users through planner tools should be reproducible by AI through the same documented tool paths.
- Avoid undocumented provider experiments or unrelated tool expansions.

## Implementation Requirements
- `travel_context`
  - Implement `lookup_weather(city="", date="")` by reusing `app.views.weather.weather.fetch_weather_and_forecast`.
  - Implement `convert_currency(from_currency="", to_currency="", amount=0)` by reusing `app.views.exchange.exchange.get_exchange_rate`.
  - Return compact JSON-serializable dictionaries with status, tool name, requested inputs, normalized values, and useful context.
  - Do not introduce new providers unless the existing service functions cannot support the required behavior.
  - Keep provider failures safe and user-readable without exposing raw provider responses.

- `calendar_management`
  - Implement `list_calendar_events(start_date="", end_date="")`, `create_calendar_event(event_payload=None)`, and `delete_calendar_event(event_id=None)`.
  - Calendar tools must require an authenticated user from tool context.
  - Use `app.models.Event` and the existing calendar view/API behavior in `app.views.calendar.calendar` as the source of truth.
  - `delete_calendar_event` must confirm ownership before deletion. If the event is not owned by the authenticated user, return a not-found or permission-safe error without deleting anything.
  - Validate dates and colors before writes. Keep writes transactional where multiple records could be touched.

## Logging Rules
- Log safe metadata only: tool name, event ids, date ranges, counts, city length, currency codes, and error codes.
- Do not log full prompts, API keys, session data, raw weather responses, raw exchange responses, or calendar event details beyond ids/counts.

## Tests To Add
- Weather lookup reuses the existing weather service and formats a safe response.
- Currency conversion reuses the existing exchange service and handles provider errors safely.
- Calendar list returns only the authenticated user's events.
- Calendar create validates payload and assigns the authenticated user as owner.
- Calendar delete removes only the authenticated user's own events.
- Calendar delete cannot remove another user's event.
- Logs do not include provider responses, prompts, or sensitive event descriptions.
