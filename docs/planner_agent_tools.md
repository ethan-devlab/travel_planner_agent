# Planner Agent Tools

This document describes the current planner-agent implementation and its tool boundaries. The app exposes one `planner_agent` framework with five implemented tool groups and 14 registered tools. The source files linked below are the source of truth.

## Framework Boundary

- Agent factory: [`build_planner_agent(model)`](../app/agents/planner_agent.py), which uses LangChain `create_agent` and `ToolStrategy(PlannerStructuredResponse)`.
- Model factory: `build_openai_chat_model()`, which builds `ChatOpenAI` with streaming enabled. The agent factory accepts a supplied model; the web entry points use this OpenAI model factory.
- Tool registry: [`app.agents.tool_groups.TOOL_GROUPS`](../app/agents/tool_groups.py). `all_planner_tools()` flattens all five groups for each agent.
- User context: [`planner_tool_user(user)`](../app/agents/tool_context.py) binds the authenticated Django user through a `ContextVar` and resets it after execution. Tools obtain the user from this context, not from model-supplied owner fields.
- Tool decorator: [`planner_tool`](../app/agents/tools/common.py) creates LangChain tools when the dependency is installed. Its plain-callable fallback does not provide a working agent runtime.
- Rule: planner responses must stay inside documented tool boundaries. The system prompt forbids claims of success without a successful tool result and declines questions outside travel planning.

## Web Execution and Response Contract

The routes are defined in [`app/urls.py`](../app/urls.py). Planner chat execution is in [`app/views/planner_agent/planner_agent.py`](../app/views/planner_agent/planner_agent.py).

| Route | Method | Behavior |
| --- | --- | --- |
| `planner-agent/` | GET, POST | Requires login. GET renders the chat page; a nonblank POST `prompt` invokes the agent and stores its summary. |
| `planner-agent/stream/` | POST | Requires login and a nonblank form `prompt`; blank input returns HTTP 400. Streams server-sent events with `token`, final `result`, and `done` events. |
| `edit/<uuid:id>/ai-check/` | POST | Requires login and edit permission. Accepts JSON `check_type`: `overall`, `stops`, `route`, or `budget`. Returns a review card based on saved itinerary data. |

- The stream uses `stream_mode=["messages", "updates"]` and `version="v2"`. It selects AI text chunks and skips tool-call chunks. The final `result` contains a response card.
- Response cards contain `summary`, `actions`, `key_data` (`label`/`value` pairs), and `next_steps`. Missing structured output uses a summary-only fallback card. The regular POST renders the summary rather than the full card.
- Django session key `planner_agent_history` keeps at most five rounds of user prompts and assistant summaries. These rounds are passed back as messages; full tool results and response cards are not stored in this history.
- The system prompt requires concise Traditional Chinese. It instructs the model to hide database UUIDs, technical field names, and internal risk codes from all visible response fields. This is a prompt rule, not a general output-redaction filter.
- Configuration and execution errors produce generic user-facing messages. A completed HTTP response or SSE `done` event is not proof that a requested mutation succeeded.
- The edit-page AI check uses no chat history. Its prompt requests `review_itinerary_on_request` with the selected `check_type`, saved data only, and no itinerary mutations. It still builds the agent with the full tool registry; the endpoint does not restrict it to review tools. Its JSON response also includes `data_sources` for OSRM/OpenStreetMap or Nominatim/OpenStreetMap attribution. Budget checks return an empty attribution list. See [`app/views/itinerary/edit.py`](../app/views/itinerary/edit.py).

## Configuration

[`travel_planner_agent/settings.py`](../travel_planner_agent/settings.py) loads `env/.env`.

| Environment variable | Use |
| --- | --- |
| `OPENAI_API_KEY` | Required by the web model factory. |
| `MODEL` | Required model name; exposed as `settings.PLANNER_AGENT_MODEL`. |
| `WEATHER_API_KEY` | Used by the existing weather service. |
| `EXCHANGE_API_KEY` | Used by the existing exchange-rate service. |
| `GEOCODING_URL`, `CURRENT_WEATHER_URL`, `FORECAST_URL` | Weather service URLs; these do not configure itinerary Nominatim lookups. |
| `REQUEST_TIMEOUT_SECONDS` | Request timeout used by itinerary geocoding, OSRM route evidence, and the weather service. |
| `NOMINATIM_BASE_URL` | Shared forward/reverse geocoding base URL; defaults to `https://nominatim.openstreetmap.org`. |
| `NOMINATIM_USER_AGENT` | Identifying User-Agent for Nominatim requests. |
| `NOMINATIM_MIN_INTERVAL_SECONDS` | Shared geocoding request interval within one Python process; defaults to 1 second. |
| `REVERSE_GEOCODE_CACHE_DAYS` | Freshness window for persistent reverse-geocoding evidence; defaults to 90 days. |
| `ROUTING_SERVICE_URL` | OSRM-compatible base/service URL for route display and driving review evidence. |

Normal Django startup also requires the project's `USER_ID_UUID5_NAMESPACE` setting. Dependencies are listed in [`requirements.txt`](../requirements.txt), including `langchain>=1.0`, `langchain-openai`, and `pydantic`. A runnable environment must support the streaming API used by the source; the dependency lower bound alone does not establish that compatibility.

## Limited Real OpenAI API Testing Authorization

- Limited authorization is granted to use the real OpenAI API for planner-agent validation.
- These tests are for parity verification: if a user can do something through documented planner tools, the AI should also be able to do it through the same documented tool interfaces.
- Testing scope must remain bounded by the tool groups and call targets documented in this file.

## Tool Groups

| Tool group | Module | Current call targets | Status | Tools |
| --- | --- | --- | --- | --- |
| `itinerary_management` | `app.agents.tools.itinerary_tools` | `app.agents.services.itinerary_management`, itinerary/location/expense/tag models, Nominatim | Implemented | 5 |
| `itinerary_review` | `app.agents.tools.review_tools` | `Itinerary` querysets, saved locations/expenses, `itinerary_review` services, OSRM, cached Nominatim geography | Implemented | 1 |
| `travel_context` | `app.agents.tools.travel_context_tools` | `fetch_weather_and_forecast`, `get_exchange_rate`, configured currency catalog | Implemented | 2 |
| `public_itinerary_lookup` | `app.agents.tools.public_itinerary_tools` | Public `Itinerary` querysets, itinerary/location/expense models | Implemented | 2 |
| `calendar_management` | `app.agents.tools.calendar_tools` | `app.models.Event` | Implemented | 4 |

The itinerary and calendar tools use their service/model paths directly. They do not call the corresponding web form or calendar HTTP endpoints. The unregistered `not_implemented_response` helper remains in `common.py`; it does not make these groups stubs.

### Itinerary Management

Source: [`itinerary_tools.py`](../app/agents/tools/itinerary_tools.py) and [`services/itinerary_management.py`](../app/agents/services/itinerary_management.py).

All five tools require an authenticated user context. Update and suggestion access is limited to owned or collaborative itineraries. Deletion requires ownership.

| Tool | Inputs | Result or effect |
| --- | --- | --- |
| `list_user_itineraries` | `include_shared=true`, `limit=10` | Returns owned itineraries and, by default, collaborative itineraries, newest update first. Limit is clamped to 1–25; invalid limits fall back to 10. |
| `suggest_itinerary_changes` | Optional `itinerary_id`, `travel_goal=""` | Returns generic suggestions without an ID, or suggestions based on an editable itinerary. Does not apply changes. |
| `create_or_update_itinerary` | `draft_payload` | Creates an itinerary for the bound user, or updates an editable itinerary identified by `draft_payload.itinerary_id`. Returns the serialized itinerary and `action`. |
| `manage_itinerary_status` | `itinerary_id`, `status` | Sets `draft`, `ongoing`, `completed`, or `cancelled` on an editable itinerary. |
| `delete_itinerary` | `itinerary_id` | Deletes an owned itinerary. |

`draft_payload` uses the `ItineraryDraftPayload` schema:

- Creation requires `title`, `start_date`, `end_date`, and a non-negative numeric `budget`. Dates use `YYYY-MM-DD`, with start on or before end.
- Optional itinerary fields are `location`, `budget_currency`, `description`, `is_public`, and `status`. Creation can infer currency from the destination; omission on update preserves the current currency. `AUTO` requests inference.
- `tags` contains tag names; `collaborators` contains existing usernames. At the service layer, an omitted relation field is preserved and a supplied list replaces it. The Pydantic draft schema defines empty-list defaults for both fields; callers must account for schema defaults when preparing updates.
- Put planned stops in `locations`. Each `LocationDraft` has `name`, optional `location_id`, `travel_method` (default `walk`), `visit_date`, `route_order`, `note`, and `expenses`. Travel methods are `boat`, `plane`, `walk`, `car`, `hsr`, `train`, and `bus`. Each expense has `expense_type` (`meal`, `lodging`, `transport`, `ticket`, `shopping`, or `other`) and a non-negative `amount`.
- Updates patch locations by default. Matching tries location UUID, unique route order, then a case-insensitive name. Unmatched entries create new stops and require a name, travel method, and visit date. `replace_locations=true` deletes existing stops and creates the supplied list; an empty list clears all stops.
- Existing stop patches can change visit time, note, route order, travel method, and expenses. A supplied expense list replaces that stop's expenses. Existing stop patches ignore name changes and model-supplied coordinates. An explicit rename request does not bypass this service behavior.
- `LocationDraft` also defines defaults of `travel_method="walk"`, `note=""`, and `expenses=[]`. If schema-populated defaults reach the patch service, their field presence can overwrite the travel method and clear notes or expenses. The service's omission behavior must not be assumed for every schema-based tool call.
- The planner prompt requires a date and time when setting visits. The service also accepts date-only values: existing stops with a saved visit time retain that local time; otherwise the default is 09:00 plus a non-negative route order, capped at 20:00. For creation/full replacement, omitted order uses the row index. An appended patch stop without a supplied order defaults to 09:00 before its route order is assigned. Date-only acceptance is a service fallback, not the preferred planner payload.
- New stops and full replacements resolve coordinates through the shared [`nominatim.py`](../app/agents/services/nominatim.py) service, ignoring supplied latitude/longitude. The lookup tries the place plus destination, then the place alone, with the configured process-local request interval. Failed or empty lookups save `0.0, 0.0`; successful itinerary saving does not prove successful geocoding. Existing stop patches retain their coordinates.

### Itinerary Review

Source: [`review_tools.py`](../app/agents/tools/review_tools.py) and [`services/itinerary_review.py`](../app/agents/services/itinerary_review.py).

`review_itinerary_on_request(itinerary_id=None, check_type="overall")` requires authenticated context and permits owned, collaborative, or public itineraries. Missing itinerary context returns `status="confirmation_required"`; invalid UUIDs, inaccessible itineraries, or unsupported check types return errors. Public visibility permits review through the tool but does not grant access to the edit-page AI-check endpoint.

The tool does not modify `Itinerary`, `Location`, or `Expense` rows. `overall` and `stops` can create or refresh `ReverseGeocodeCache` rows. Review is therefore read-only for saved trip data, but not for all database tables.

| `check_type` | Collected evidence |
| --- | --- |
| `overall` | Route timing/order and reverse-geocoded city/country facts. |
| `stops` | Reverse-geocoded city/country facts; no route-service or order analysis. |
| `route` | Route timing/order; no reverse geocoding. |
| `budget` | Saved budget/expenses; no route or geography provider requests. |

Results include `check_type`, `review_summary`, `saved_locations`, `location_geographies`, `routes`, `route_order_analysis`, `ai_review_guidance`, `risks`, and `suggested_next_actions`. Saved facts include dates, transport methods, route order, expense totals/types, tags, and route/geography counts. Notes are summarized by presence and character count rather than returned in full.

Non-budget reviews check missing or single stops, missing coordinates or visit times, and visits outside trip dates. Every focus checks expenses against the budget; amounts at or above 90% produce a near-budget signal, and amounts over budget produce an over-budget signal. Budget reviews keep route/stop issues out of their primary risks and actions.

Route evidence is computed by [`route_review.py`](../app/agents/services/route_review.py), [`route_leg_timing.py`](../app/agents/services/route_leg_timing.py), and [`route_order_analysis.py`](../app/agents/services/route_order_analysis.py):

- Dated stops are grouped by local date and ordered by `route_order` and UUID. Cross-day gaps are excluded. Each destination stop's transport method describes the incoming connection; the first stop's method is ignored.
- OSRM requests use the driving profile. At least two valid same-day coordinates are needed for a route request. Car distance/time uses OSRM evidence; road snapping over 500 metres produces a coordinate warning.
- Walking time is estimated from great-circle distance multiplied by 1.25, at 4.8 km/h. Walks over 5 km or 90 estimated minutes produce a warning. Bus, train, HSR, plane, and boat need timetable/operator confirmation; plane connections under 100 km produce a practicality warning.
- Timing compares scheduled stop start times. It does not include attraction dwell time. A non-positive interval is a chronological conflict; an interval shorter than estimated travel is insufficient. Remaining time below the greater of 15 minutes or 20% of estimated travel is tight.
- Order analysis needs at least three same-day stops with valid coordinates. OSRM trip optimization fixes the first and last stops. A detour requires both at least 15 extra minutes and 20% extra time. For non-car transport, driving order evidence is advisory.
- `not_requested` means the selected focus intentionally skipped route/order analysis. `not_applicable` includes the reason that the saved stops do not meet its requirements. Unavailable or unverified evidence must not be described as a passed check.

Geography evidence is computed by [`geography_review.py`](../app/agents/services/geography_review.py) and [`nominatim.py`](../app/agents/services/nominatim.py). Coordinates must be finite, in range, and different from `0,0`. Reverse results use a persistent cache keyed by provider and coordinates rounded to five decimal places. Fresh data is reused; successful refreshes update the cache. If refresh fails, existing stale data is returned with a stale flag. Without cache data, geography is unavailable. Multiple resolved countries prompt confirmation of an intended cross-border trip rather than an automatic rejection.

The Nominatim throttle is process-local. It does not enforce a total limit across workers, processes, or machines. Public-service use must follow the [OSMF Nominatim Usage Policy](https://operations.osmfoundation.org/policies/nominatim/), including an application-wide maximum of one request per second, an identifying User-Agent or Referer, attribution, and caching. Use a self-hosted/commercial provider or a centralized/distributed throttle when deployment traffic requires it.

Review should run only after an explicit user request. The tool function itself does not receive or verify an explicit-request flag.

### Travel Context

Source: [`travel_context_tools.py`](../app/agents/tools/travel_context_tools.py).

| Tool | Inputs | Result and limits |
| --- | --- | --- |
| `lookup_weather` | Required `city`, optional `date` in `YYYY-MM-DD` | Reuses `app.views.weather.weather.fetch_weather_and_forecast`. Returns compact current weather, forecast rows, match count, and available forecast date labels. Without a date, returns up to five rows. With a date, filters existing rows by their `%b %d` label. |
| `convert_currency` | `from_currency`, `to_currency`, non-negative `amount` (default 0) | Uppercases and validates codes against `app.views.exchange.exchange.currencies`; calls `get_exchange_rate`. Returns the rate, converted amount, and a two-decimal display string. |

A weather date selects from the service's short forecast; it does not fetch historical or arbitrary future weather. Matching labels do not include a year. Zero matching rows can still have `status="ok"`. Provider failures return generic tool errors. These tool functions do not check user context themselves; the planner web routes require login.

### Public Itinerary Lookup and Copy

Source: [`public_itinerary_tools.py`](../app/agents/tools/public_itinerary_tools.py).

- `search_public_itineraries(query="", location="", budget=None)` searches only public itineraries. `query` matches title; `location` matches destination, title, or stop name. `budget` is a non-negative maximum compared directly to stored budgets, without currency conversion. Returns at most 10 summaries ordered by newest update and ID. The function does not require user context.
- `copy_public_itinerary_to_my_items(public_itinerary_id)` requires authenticated context and a public source UUID. It creates a new private draft owned by the bound user and copies trip fields, tags, stops, stored coordinates, and expenses in a transaction. It does not copy collaborators, geocode again, or modify the source. Returns source/new itinerary IDs, title, and copied counts.
- The copy tool's description instructs the planner to ask which public itinerary is intended when a name is ambiguous. This is model guidance; the tool receives a concrete UUID.

### Calendar Management

Source: [`calendar_tools.py`](../app/agents/tools/calendar_tools.py).

All calendar tools require authenticated context and operate only on events owned by that user.

| Tool | Inputs | Result or effect |
| --- | --- | --- |
| `list_calendar_events` | Optional `start_date`, `end_date` | Lists owned events ordered by date and ID, with inclusive date bounds. Rejects invalid or reversed ranges. |
| `create_calendar_event` | `event_payload` | Creates an owned event. |
| `update_calendar_event` | `event_id`, `event_payload` | Updates an owned event; requires the complete event payload, not a partial patch. |
| `delete_calendar_event` | `event_id` | Deletes an owned event. |

Event payloads use `eventName`, `date` (`YYYY-MM-DD`), and `color` (`orange`, `blue`, `yellow`, or `green`). Name must be nonblank. The service accepts a mapping, a Pydantic payload, or a JSON-object string. Events contain a date rather than start/end times. Serialized events include `id`, `eventName`, `date`, `color`, and `calendar` (the same color value).

## Tool Results and Logging

- Tool functions must log safe metadata only, such as tool name, object IDs, counts, or prompt length.
- Do not log full prompts, itinerary descriptions, API keys, session data, or weather/currency provider responses.
- Successful tool results use `status="ok"` and `tool`, plus tool-specific data. Errors generally use `status="error"`, `tool`, `error_code`, and `message`. Missing review context uses `confirmation_required`.
- UUIDs and risk codes in results are for internal tool coordination. The planner should use trip titles and user-friendly explanations in visible replies.
- Mutation tools enforce their data-access checks; model instructions about review intent, ambiguity, output language, and visible identifiers are separate from these checks.

## Validation

Existing tests are in [`app/tests.py`](../app/tests.py). For focused local validation:

```bash
./.venv/Scripts/python.exe manage.py test app.tests.PlannerAgentToolRegistryTests app.tests.PlannerAgentFactoryTests app.tests.PlannerAgentViewTests app.tests.ItineraryManagementTests app.tests.PlannerAgentToolTests app.tests.ItineraryReviewEvidenceTests app.tests.TravelContextToolTests app.tests.CalendarManagementToolTests --noinput
```

These tests cover tool registration, structured-response setup, chat and SSE handling, user access, location patching/geocoding, review facts and risks, public copying, travel-context provider handling, and calendar ownership. `ItineraryReviewEvidenceTests` covers focus selection, route estimates/order, geography cache reuse, and stale fallback. Agent/provider boundaries are mocked; passing tests do not establish live OpenAI, weather, exchange-rate, Nominatim, OSRM, or browser behavior.

For the saved-itinerary AI-check endpoint, also run `app.tests.ItineraryEditPersistenceTests`. Its AI-check tests mock agent execution and cover permission checks, focus validation, saved itinerary context, evidence instructions, provider attribution, and safe configuration errors.

The limited real OpenAI API authorization above remains bounded to these documented capabilities. It is not a requirement to make paid API calls during every documentation update.

## Framework References

The local source defines this application's contract. For the underlying APIs, see the current LangChain documentation for [structured output and `ToolStrategy`](https://docs.langchain.com/oss/python/langchain/structured-output) and [streaming](https://docs.langchain.com/oss/python/langchain/streaming).
