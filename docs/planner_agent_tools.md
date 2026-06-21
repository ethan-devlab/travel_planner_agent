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
| `itinerary_review` | `app.agents.tools.review_tools` | `app.models.Itinerary`, `app.models.Location`, `app.models.Expense`, OSRM route evidence, cached Nominatim geography | Implemented | Review saved itinerary structure, stops, route timing/order, transport evidence, and budget only after an explicit request. It does not mutate saved itinerary, location, or expense rows. |
| `travel_context` | `app.agents.tools.travel_context_tools` | `app.views.weather.weather.fetch_weather_and_forecast`, `app.views.exchange.exchange.get_exchange_rate` | Stub only | Query weather forecasts and currency exchange context. |
| `public_itinerary_lookup` | `app.agents.tools.public_itinerary_tools` | `app.views.itinerary.search`, `app.views.itinerary.template`, public `Itinerary` querysets | Stub only | Search and summarize public itinerary references. |
| `calendar_management` | `app.agents.tools.calendar_tools` | `app.models.Event`, `app.views.calendar.calendar` event APIs | Implemented | Create, list, update, and delete calendar events. |

## Implementation Notes

- Tool functions must log safe metadata only, such as tool name, object IDs, counts, or prompt length.
- Do not log full prompts, itinerary descriptions, API keys, session data, or weather/currency provider responses.
- Itinerary management includes listing the authenticated user's owned/shared itineraries, suggesting changes, creating/updating itinerary drafts, deleting owned itineraries, geocoding saved location rows, and updating itinerary status.
- Create/update location coordinates must always be resolved through Nominatim. Planner-agent payload latitude/longitude values are not trusted and must be ignored.
- Itinerary location updates are patch-based by default to prevent accidental rewrites. Full replacement must be explicit with `replace_locations=true`.
- When planner-agent sets visit dates, it must include visit time and must not rename existing location names/language unless the user explicitly asks.
- Review tools must only run when the user explicitly asks for itinerary review.
- Review tools do not modify user itinerary data such as `Itinerary`, `Location`, or `Expense` rows. `stops` and `overall` reviews may create or refresh `ReverseGeocodeCache` rows as an external geography evidence cache.
- Review focus is explicit: `route` runs route evidence, `stops` runs reverse geocoding, `overall` runs both, and `budget` avoids external route/geography requests. Budget review primary risks must stay focused on expense and budget signals rather than route-only or stop-only fixes such as missing route coordinates.
- OSRM is treated as driving-only. Walking duration is an estimate; bus, train, HSR, plane, and boat require separate timetable or operator confirmation.
- Nominatim reverse results are persistently cached, throttled to the configured interval, and attributed to OpenStreetMap in the AI-check UI. The current throttle in `app/agents/services/nominatim.py` is process-local only: it spaces requests inside one Python process and does not enforce a global limit across gunicorn workers, multiple processes, or multiple machines.
- Public `nominatim.openstreetmap.org` usage must follow the official [OSMF Nominatim Usage Policy](https://operations.osmfoundation.org/policies/nominatim/): total application traffic must stay at or below 1 request per second, requests must send a valid identifying User-Agent or Referer, OpenStreetMap attribution must be displayed, and repeated results must be cached. Small user-triggered usage is acceptable when traffic stays moderate. Production or high-traffic deployments should use a self-hosted Nominatim instance, a commercial geocoding provider, a centralized proxy, or a DB/Redis-backed distributed throttle.
- Calendar update and deletion tools must confirm ownership before mutating events.
- Weather and currency tools should reuse existing service functions before adding new providers.
