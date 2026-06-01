# Findings & Decisions

## Requirements
- Implement Owner A's `itinerary_management` group as production Django-backed LangChain tools.
- Enable `planner-agent/` POST execution through LangChain/OpenAI now.
- Keep Owner B and Owner C tool groups registered as stubs.
- Create `docs/Owner_B.md` and `docs/Owner_C.md` for downstream AI implementers.
- Add tests for Owner A service/tool behavior and patched planner-agent view execution.

## Research Findings
- `docs/planner_agent_tools.md` defines `itinerary_management` as Owner A's group, with future targets `Itinerary`, `Location`, `location_form`, and `persistence`.
- Current `app.agents.planner_agent.build_planner_agent(model)` already wraps `langchain.agents.create_agent`.
- Current `app.views.planner_agent.planner_agent_view` is a POST stub and must be changed to invoke the agent.
- Existing itinerary form flows use `ItineraryForm`, `save_itinerary_relations_from_post`, and `save_locations_from_post`; the Owner A tools need structured equivalents rather than model-supplied POST data.
- Local `.env` contains `OPENAI_API_KEY` and `MODEL`; neither value should be logged.
- The current Python environments did not have LangChain installed during planning, although `requirements.txt` lists `langchain`.
- The first focused planner test run after implementation failed only because the old view test still expected the previous stub message.
- Installing dependencies in sandbox failed with a socket permission error; approved escalation allowed `langchain`, `langchain-openai`, and test dependencies to install.
- After real LangChain packages were installed, the configuration-fallback test needed to patch `build_openai_chat_model` to avoid a real provider call.
- A runtime agent factory check built successfully with `FakeListChatModel`, returning a LangChain `CompiledStateGraph`.

## Technical Decisions
| Decision | Rationale |
|----------|-----------|
| Add a dedicated Owner A service module. | Prevents permissions and validation from being spread across LangChain decorators. |
| Use server-side tool context for the authenticated user. | Prevents the model from selecting or spoofing a `user_id`. |
| Replace locations only when `locations` is present in the payload. | Matches the chosen mutation policy: update only explicitly present fields. |
| Keep existing form persistence behavior intact. | Reduces blast radius and protects current create/edit tests. |
| Use fallback no-op tool decoration when LangChain is missing. | Keeps Django imports and tests usable before dependency installation while still exposing real LangChain tools when installed. |

## Issues Encountered
| Issue | Resolution |
|-------|------------|
| Git metadata is unavailable from this workspace. | Proceed with careful file edits and test verification; do not run destructive Git commands. |
| Old planner-agent POST assertion failed after enabling execution. | Replaced it with patched-agent invocation coverage plus a safe configuration fallback test. |
| Sandbox network blocked dependency installation. | Re-ran the same pip install with approved escalation. |
| Test isolation changed after dependencies were installed. | Patched the config-fallback branch directly rather than depending on missing local dependencies. |
| Agent factory check initially missed Django settings. | Reran through `manage.py shell` so Django initialized before importing app models. |

## Resources
- `docs/planner_agent_tools.md`
- `app/agents/planner_agent.py`
- `app/agents/tool_groups.py`
- `app/agents/tools/itinerary_tools.py`
- `app/views/planner_agent/planner_agent.py`
- `app/views/itinerary/location_form.py`
- `app/views/itinerary/persistence.py`
- `app/models.py`
- `docs/Owner_B.md`
- `docs/Owner_C.md`
- `requirements.txt`

## Visual/Browser Findings
- No visual/browser findings for this implementation phase.
