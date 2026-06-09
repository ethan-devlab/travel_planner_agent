# Planner Agent Tools

This document defines the planner-agent scope. The app exposes one `planner_agent` framework with five tool groups, and the shared architecture is already in place.

## Framework Boundary

- Agent factory: `app.agents.planner_agent.build_planner_agent(model)`
- Tool registry: `app.agents.tool_groups.TOOL_GROUPS`
- UI route: `planner-agent/`
- Rule: planner responses must stay inside documented tool boundaries, and model output must not claim tool success without successful tool results.

## Scope Baseline

- The baseline framework and production `itinerary_management` path are implemented.
- Remaining tool groups should extend the shared framework contract only when needed and only with explicit intent.

## Limited Real OpenAI API Testing Authorization

- Limited authorization is granted to use the real OpenAI API for planner-agent validation.
- These tests are for parity verification: if a user can do something through documented planner tools, the AI should also be able to do it through the same documented tool interfaces.
- Testing scope must remain bounded by the tool groups and call targets documented in this file.

## Tool Groups

| Tool group | Module | Future app call targets | Status | Notes |
| --- | --- | --- | --- | --- |
| `itinerary_management` | `app.agents.tools.itinerary_tools` | `app.models.Itinerary`, `app.models.Location`, `app.views.itinerary.location_form`, `app.views.itinerary.persistence`, `app.views.itinerary.delete` | Implemented | Suggest, create, modify, and manage itineraries. |
| `itinerary_review` | `app.agents.tools.review_tools` | `app.models.Itinerary`, `app.models.Location`, `app.models.Expense`, route waypoint serialization | Stub only | Review an itinerary only after an explicit user request. |
| `travel_context` | `app.agents.tools.travel_context_tools` | `app.views.weather.weather.fetch_weather_and_forecast`, `app.views.exchange.exchange.get_exchange_rate` | Stub only | Query weather forecasts and currency exchange context. |
| `public_itinerary_lookup` | `app.agents.tools.public_itinerary_tools` | `app.views.itinerary.search`, `app.views.itinerary.template`, public `Itinerary` querysets | Stub only | Search and summarize public itinerary references. |
| `calendar_management` | `app.agents.tools.calendar_tools` | `app.models.Event`, `app.views.calendar.calendar` event APIs | Stub only | Create, list, update, and delete calendar events. |

## Implementation Notes

- Tool functions must log safe metadata only, such as tool name, object IDs, counts, or prompt length.
- Do not log full prompts, itinerary descriptions, API keys, session data, or weather/currency provider responses.
- Itinerary management includes listing the authenticated user's owned/shared itineraries, suggesting changes, creating/updating itinerary drafts, deleting owned itineraries, geocoding saved location rows, and updating itinerary status.
- Create/update location coordinates must always be resolved through Nominatim. Planner-agent payload latitude/longitude values are not trusted and must be ignored.
- Itinerary location updates are patch-based by default to prevent accidental rewrites. Full replacement must be explicit with `replace_locations=true`.
- When planner-agent sets visit dates, it must include visit time and must not rename existing location names/language unless the user explicitly asks.
- Review tools must only run when the user explicitly asks for itinerary review.
- Calendar deletion tools must confirm ownership before deleting events.
- Weather and currency tools should reuse existing service functions before adding new providers.
