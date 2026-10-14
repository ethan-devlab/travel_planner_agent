# Travel Planner Agent: Repository Instructions

## Scope and Workflow

This project is a Django travel planner with server-rendered templates, plain JavaScript, Tailwind CSS, and a LangChain planner agent. Use the current source and tests to establish behavior before changing it.

1. Inspect the working-tree status, the relevant entry point, its helpers, and nearby tests. Preserve existing user changes.
2. State the intended behavior and a narrow validation plan. For material design or product decisions, propose a solution, request review, then divide the approved work into tasks. Proceed with routine work already authorized by the user.
3. Implement the smallest coherent change and run focused checks as the work progresses. Split units when their responsibilities become hard to follow; keep unrelated refactors outside the task.
4. Report the outcome, changed files, validation results, skipped checks, and remaining risks. Distinguish source inspection, mocked tests, browser behavior, and live provider results.

Write code comments, commit messages, and pull-request descriptions in English. Use Traditional Chinese for responses and planner replies. Write documentation using ASD-STE100 style.

請作為我的技術解釋專家。接下來當我向你提問或請你解釋複雜概念時，請借用 ASD-STE100 (Simplified Technical English) 的八成寫作風格來回答我：
1. 請使用短句子（每句不超過 20 個字），一個句子只說一件事。
2. 核心專有名詞要保持前後一致。
3. 使用主動語態，明確說出是誰、在什麼條件下、做什麼動作。
4. 消除所有含糊的贅詞（如：適當的、可能視情況、若干因素）。

Prefer parallel work for independent, bounded tasks with explicit ownership and acceptance criteria; the parent reviews integration and validation. Use GPT-6 Luna MAX for subagents. Use permitted native tools.

Prefer clean contracts over compatibility adapters. Before changing persisted data or an external contract, explain the effect and migration requirements; obtain review when the change exceeds the authorized scope. Favor practical performance improvements supported by query or runtime evidence.

## Source Map

| Area | Start here |
| --- | --- |
| Setup and dependencies | `README.md`, `requirements.txt`, `package.json` |
| Django configuration and root routes | `travel_planner_agent/settings.py`, `travel_planner_agent/urls.py` |
| Application routes | `app/urls.py` |
| Data and form validation | `app/models.py`, `app/forms.py`, `app/migrations/` |
| Itinerary views and persistence | `app/views/itinerary/`; inspect `location_form.py`, `persistence.py`, `route_helpers.py`, and `calendar_sync.py` for shared behavior |
| Planner factory, registry, and user context | `app/agents/planner_agent.py`, `app/agents/tool_groups.py`, `app/agents/tool_context.py` |
| Planner tools and itinerary service | `app/agents/tools/`, `app/agents/services/itinerary_management.py` |
| Review evidence and geocoding | `app/agents/services/itinerary_review.py`, `route_review.py`, `geography_review.py`, and `nominatim.py` |
| Planner chat and streaming | `app/views/planner_agent/planner_agent.py` |
| Calendar, weather, exchange, and authentication | Corresponding modules under `app/views/` |
| UI and route/calendar behavior | `app/templates/`, `app/static/itinerary/js/`, `app/static/calendar/js/` |
| CSS source and build | `app/static/src/input.css`, scripts in `package.json` |
| Automated behavior checks | Django `TestCase` classes in `app/tests.py` |

For planner tools, schemas, permissions, chat history, streaming, configuration, or paid validation, read [`docs/planner_agent_tools.md`](docs/planner_agent_tools.md) before editing. Keep that document aligned when these contracts change. Follow URL imports to locate active views; similarly named files are not evidence that a module is used.

Consult current primary documentation and dependency source when changing external API or framework usage. Check the installed version as well as declared dependencies. Do not install packages or build a retrieval index solely to satisfy a discovery preference.

## Data and Access Rules

- Use the custom `app.User` model through Django's user-model APIs. User IDs are UUID5 values derived from the configured namespace and username at creation; domain and join-row IDs use UUID4. Keep UUID routes, relations, and serialization consistent. Changing `USER_ID_UUID5_NAMESPACE` affects new user identity generation and requires explicit review.
- Distinguish public visibility, collaboration, and ownership. Public trips can be viewed, but public visibility does not grant edit permission. Itinerary edits allow the owner or collaborators; deletion requires ownership. Calendar events belong to one user. Enforce checks in the server/tool path, not only in the UI or a model prompt.
- Preserve CSRF protection and allowed HTTP methods for mutations. Test both authorized and unauthorized callers when access behavior changes. Diagnose request rejection through `app/middleware.py` and settings before changing network policy.
- Use `Decimal` for stored budgets and expenses. Reuse `app/utils/budget_currency.py` for supported currencies, inference, and display; do not compare amounts in different currencies as though they were equivalent.
- Use Django timezone utilities for visit datetimes. The application timezone is configured in settings. A calendar event stores a date, while a location can store a visit datetime; preserve that distinction.
- Location order is persisted in `route_order`. Route serialization excludes the `0.0, 0.0` placeholder. Check editor, persistence, and preview together when changing route order or coordinates.
- Web itinerary forms and planner tools have different update semantics. Web edit persistence replaces location rows; planner updates normally patch them. Schema defaults can turn omitted fields into supplied values. Verify the actual payload and service path before claiming preservation of existing values.
- Planner tools obtain the authenticated user through `planner_tool_user`; model-supplied IDs are lookup inputs, not authority. Keep mutation checks in the tool/service layer. A prompt requesting review is not a read-only tool restriction.
- Review focus controls external evidence: `overall` requests route and geography, `route` requests route only, `stops` requests geography only, and `budget` requests neither. Review preserves trip/location/expense data, but geography checks can write `ReverseGeocodeCache`. Keep skipped, unavailable, estimated, and verified evidence distinct.
- Reuse existing calendar-sync behavior for itinerary imports: only ongoing trips are eligible, events belong to the itinerary owner, and repeated imports use `get_or_create`. Verify the caller's permission checks as well as the helper.

## UI, Providers, and Logging

- Extend the existing templates, CSS theme, and JavaScript modules. Keep product text in the established Traditional Chinese style. Static hygiene tests require emoji-free templates/static sources and the shared Tailwind stylesheet.
- Edit `app/static/src/input.css` for CSS changes, then use the existing build script. `app/static/dist/app.css` is generated; the root `static/` directory is the collection target. Verify tracking status before staging generated output.
- Production static files use `ManifestStaticFilesStorage` outside test runs. Use `{% static %}` with a real asset path and preserve content-hashed cache handling; validate `collectstatic` when changing production asset configuration.
- Tailwind source scanning is explicit in `input.css`. Check those paths when adding templates or JavaScript-generated classes; a successful build alone does not prove a new class is included.
- Reuse existing weather, exchange, routing, and geocoding helpers. Preserve timeouts and safe error responses. Mock provider boundaries for routine tests; use live calls only within the user's authorization, including the bounded planner validation authorization documented above.
- Forward and reverse Nominatim queries share `app/agents/services/nominatim.py`; the configured throttle is process-local, not a deployment-wide rate limit. Preserve provider attribution and cache behavior when changing geography evidence.
- Add comments for useful contracts and non-obvious decisions. Add logs at meaningful operation and failure boundaries using safe metadata such as tool names, IDs, counts, and input lengths. Keep prompts, descriptions, session contents, credentials, and raw provider responses out of logs.
- Prompt instructions govern planner language and visible identifiers. Do not report them as enforced redaction or data-access controls. Claim tool success from tool results, not HTTP completion or an SSE `done` event.

## Local Commands and Configuration

Run commands from the repository root. Use PowerShell for Windows operations and an existing Python environment. The examples below use `.venv`; if it is absent, select an available environment instead of silently installing dependencies.

```powershell
.\.venv\Scripts\python.exe manage.py check
.\.venv\Scripts\python.exe manage.py test app.tests.<TestClass> --noinput
.\.venv\Scripts\python.exe manage.py runserver 127.0.0.1:8000
npm run build:css
git diff --check
```

Settings load `env/.env` relative to the working directory. `DJANGO_SECRET_KEY` and `USER_ID_UUID5_NAMESPACE` are required at startup. Planner execution also needs `OPENAI_API_KEY` and `MODEL`; weather and exchange use their own keys. Inspect variable names or example configuration without printing secret values.

Treat `db.sqlite3`, `env/.env`, local analysis configuration, and logs as sensitive local state even if tracked or present in the workspace. Never infer permission to publish their contents from tracking status. Use Django's test database for automated checks; avoid resets, writes, or migrations against the development database unless required and authorized. Include a Django migration when changing models, and inspect existing migrations before designing a data conversion.

## Validation Selection

Start with the affected classes in `app/tests.py`; use individual test methods when they cover the change completely.

| Change | Relevant test classes |
| --- | --- |
| User identity or model IDs | `UUIDPrimaryKeyTests`, `AuthViewTests` |
| Itinerary forms, routes, or currency | `ItineraryRouteTests`, `ItineraryEditPersistenceTests`, `BudgetCurrencyTests` |
| Discovery, sharing, or templates | `ItineraryDiscoveryViewTests`, `ItineraryTemplateViewTests` |
| Planner registration, factory, or chat/SSE | `PlannerAgentToolRegistryTests`, `PlannerAgentFactoryTests`, `PlannerAgentViewTests` |
| Planner itinerary mutations | `ItineraryManagementTests` |
| Planner review or public lookup/copy | `PlannerAgentToolTests`; review providers/cache/order also use `ItineraryReviewEvidenceTests` |
| Weather or exchange | `WeatherApiTests`, `TravelContextToolTests` |
| Calendar HTTP or tools | `CalendarCsrfTests`, `CalendarManagementToolTests` |
| Templates or static assets | `StaticHygieneTests`, affected view tests, CSS build when relevant |

For shared models, permissions, or cross-module changes, broaden to the affected callers or `manage.py test app --noinput`. For schema changes, inspect `makemigrations --check --dry-run` and test the migration when applicable. This repository defines CSS build/watch scripts, not an npm test or lint script; use commands that actually exist.

For user-visible behavior, exercise the real page when a browser and local server are available. State what was exercised. Mocked agent/provider tests do not establish live service or browser behavior.

Use explicit query ordering when order is part of the contract. For unordered relations such as itinerary tags, compare membership rather than assuming insertion order. If a check fails, establish the cause before retrying; separate existing failures from regressions and do not alter unrelated code merely to obtain a green run.

Before delivery, check the diff for unrelated changes and secret values. Stage or commit only when requested, and include only the requested completed work.
