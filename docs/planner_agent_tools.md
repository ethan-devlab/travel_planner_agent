# Planner Agent Tools

This document defines the planner-agent scope. The app exposes one `planner_agent` framework with five tool groups. Owner A has completed phase-1 design and framework delivery (agent page plus architecture baseline), and Owner B/Owner C should implement remaining groups on top of this foundation.

## Framework Boundary

- Agent factory: `app.agents.planner_agent.build_planner_agent(model)`
- Tool registry: `app.agents.tool_groups.TOOL_GROUPS`
- UI route: `planner-agent/`
- Rule: planner responses must stay inside documented tool boundaries, and model output must not claim tool success without successful tool results.

## Ownership Baseline

- Owner A completed the baseline framework and production `itinerary_management` path.
- Owner B and Owner C should focus on implementation within their assigned tool groups without changing the shared framework contract unless explicitly requested.

## Limited Real OpenAI API Testing Authorization

- Limited authorization is granted to use the real OpenAI API for planner-agent validation.
- These tests are for parity verification: if a user can do something through documented planner tools, the AI should also be able to do it through the same documented tool interfaces.
- Testing scope must remain bounded by the tool groups and call targets documented in this file.

## Tool Groups

| Owner | Tool group | Module | Future app call targets | Status |
| --- | --- | --- | --- | --- |
| Owner A | `itinerary_management` | `app.agents.tools.itinerary_tools` | `app.models.Itinerary`, `app.models.Location`, `app.views.itinerary.location_form`, `app.views.itinerary.persistence`, `app.views.itinerary.delete` | Implemented |
| Owner B | `itinerary_review` | `app.agents.tools.review_tools` | `app.models.Itinerary`, `app.models.Location`, `app.models.Expense`, route waypoint serialization | Stub only |
| Owner C | `travel_context` | `app.agents.tools.travel_context_tools` | `app.views.weather.weather.fetch_weather_and_forecast`, `app.views.exchange.exchange.get_exchange_rate` | Stub only |
| Owner B | `public_itinerary_lookup` | `app.agents.tools.public_itinerary_tools` | `app.views.itinerary.search`, `app.views.itinerary.template`, public `Itinerary` querysets | Stub only |
| Owner C | `calendar_management` | `app.agents.tools.calendar_tools` | `app.models.Event`, `app.views.calendar.calendar` event APIs | Stub only |

## Implementation Notes

- Tool functions must log safe metadata only, such as tool name, object IDs, counts, or prompt length.
- Do not log full prompts, itinerary descriptions, API keys, session data, or weather/currency provider responses.
- Owner A itinerary management includes listing the authenticated user's owned/shared itineraries, suggesting changes, creating/updating itinerary drafts, deleting owned itineraries, geocoding saved location rows, and updating itinerary status.
- Owner A create/update location coordinates must always be resolved through Nominatim. Planner-agent payload latitude/longitude values are not trusted and must be ignored.
- Owner A itinerary location updates are patch-based by default to prevent accidental rewrites. Full replacement must be explicit with `replace_locations=true`.
- When planner-agent sets visit dates, it must include visit time and must not rename existing location names/language unless the user explicitly asks.
- Review tools must only run when the user explicitly asks for itinerary review.
- Calendar deletion tools must confirm ownership before deleting events.
- Weather and currency tools should reuse existing service functions before adding new providers.
- 
