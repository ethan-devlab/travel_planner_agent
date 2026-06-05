# Owner C Findings & Fixes

## Scope
- Implemented `travel_context` in `app.agents.tools.travel_context_tools`
- Implemented `calendar_management` in `app.agents.tools.calendar_tools`
- Added Owner C coverage in `app/tests.py`

## Bugs and Environment Issues

### 1. README folder name mismatch
- Symptom: `README.md` said `cd travel_planner_agent`, but the actual repository folder here is `traver_planner_agent`.
- Risk: teammates can think setup failed when `cd` is the real issue.
- Resolution: updated `README.md` to use `cd traver_planner_agent`.

### 2. Django port 8000 already in use
- Symptom: `python3 manage.py runserver` returned `Error: That port is already in use.`
- Root cause: another local Python process was already listening on `127.0.0.1:8000`.
- Resolution: confirmed the app itself still boots by running `python manage.py runserver 127.0.0.1:8001`.
- Working fallback: use `python3 manage.py runserver 8001` when `8000` is occupied.

### 3. Exchange view provider-error path produced the wrong UX
- Symptom: when `get_exchange_rate()` returned an `Exception` object, the view still continued to `amount * rate`, which fell into a generic exception path.
- Root cause: the provider-error branch showed a message but did not return early.
- Resolution: updated `app/views/exchange/exchange.py` to return immediately after surfacing the provider message.

### 4. Exchange module loaded `.env` from an inconsistent path
- Symptom: `app/views/exchange/exchange.py` loaded `.env` from `.env`, while project settings load from `env/.env`.
- Risk: direct module usage and local debugging can see different environment behavior from the Django app.
- Resolution: aligned the exchange module to `load_dotenv("env/.env")`.

### 5. Planner-agent weather lookups could misinterpret Taiwan city aliases
- Symptom: asking for `台中` could rely on session memory or a provider's first geocoding result instead of globally resolving to `台中市`.
- Root cause: the shared weather service passed the raw city string to geocoding and always used the first returned match.
- Resolution: normalized common Taiwan city aliases in the shared weather service and prefer exact Taiwan matches before falling back to other geocoding results.

### 6. Local database schema lagged behind the new budget currency field
- Symptom: local Django writes failed with `app_itinerary has no column named budget_currency`.
- Root cause: code and migration were added, but the local `db.sqlite3` had not run the new migration yet.
- Resolution: ran `python manage.py migrate` so `app.0009_itinerary_budget_currency` was applied locally.

## Implementation Notes
- Weather tool reuses `app.views.weather.weather.fetch_weather_and_forecast`.
- Currency tool reuses `app.views.exchange.exchange.get_exchange_rate`.
- Calendar tools require authenticated planner-tool context from `app.agents.tool_context.get_current_planner_user()`.
- Calendar writes validate date and color before creating records.
- Calendar deletion is owner-scoped and returns a permission-safe not-found response for other users' events.
- Itinerary budget now stores an explicit `budget_currency` and can auto-infer the saved currency from the destination text when the user selects auto mode.
- Tool logs only contain safe metadata such as tool name, ids, counts, range flags, city length, currency pairs, and error categories.

## Verification
- Passed:
  - `./django_project/bin/python manage.py test app.tests.OwnerCTravelContextToolTests app.tests.OwnerCCalendarManagementToolTests -v 2`
  - `./django_project/bin/python manage.py test app.tests.CalendarCsrfTests -v 2`
  - `./django_project/bin/python manage.py test app.tests.WeatherApiTests app.tests.PlannerAgentToolRegistryTests -v 2`

## Covered by Tests
- Weather lookup formats safe tool output and filters forecast rows by requested date label.
- Weather provider failures do not leak provider details into tool results or logs.
- Taiwan city aliases such as `台中` normalize to `台中市, Taiwan` before geocoding and prefer `country=TW` matches.
- Currency conversion reuses the exchange service and hides provider error details safely.
- Calendar listing only returns the authenticated user's events.
- Calendar creation validates payload, assigns the authenticated owner, and avoids logging event names.
- Calendar deletion removes only the owner's event and cannot delete another user's event.
