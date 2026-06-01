# Owner B AI Implementation Brief

## Goal
Implement the Owner B planner-agent tool groups from `docs/planner_agent_tools.md`: `itinerary_review` and `public_itinerary_lookup`.

## Required Context
- Keep the framework boundary intact:
  - Agent factory: `app.agents.planner_agent.build_planner_agent(model)`
  - Tool registry: `app.agents.tool_groups.TOOL_GROUPS`
  - Review tools module: `app.agents.tools.review_tools`
  - Public lookup tools module: `app.agents.tools.public_itinerary_tools`
- Owner A has completed phase-1 design and framework delivery, including the planner-agent page and baseline architecture.
- Owner A has production itinerary-management tools. Do not rewrite or weaken Owner A permissions.
- Owner C owns weather, exchange, and calendar tools. Leave those stubs alone unless explicitly assigned.
- Owner B implementation should build on top of Owner A's established framework without redefining ownership boundaries.

## Limited Real API Testing Authorization
- Limited authorization is granted to use the real OpenAI API for planner-agent verification.
- Keep tests scoped to capabilities defined in `docs/planner_agent_tools.md`.
- The purpose is parity validation: if a user can perform an operation through documented planner tools, the AI flow should be able to perform the same operation.
- Do not expand test coverage into undocumented tools or unrelated experimental behaviors.

## Implementation Requirements
- `itinerary_review`
  - Implement `review_itinerary_on_request(itinerary_id=None, review_focus="")`.
  - Only review when the user explicitly asks for itinerary review in the prompt or tool request. If intent is ambiguous, return a safe response asking for explicit review confirmation.
  - Use server-side authenticated user context from `app.agents.tool_context.get_current_planner_user()`.
  - Allow review for itineraries the user owns or collaborates on. Public itinerary review should be handled only if the request clearly references a public itinerary and does not expose private collaborator data.
  - Review data sources: `app.models.Itinerary`, `Location`, `Expense`, and route waypoint serialization from `app.views.itinerary.route_helpers.serialize_route_waypoints`.
  - Return JSON-serializable dictionaries with status, tool name, itinerary id, review summary, risks, and suggested next actions.

- `public_itinerary_lookup`
  - Implement `search_public_itineraries(query="", location="", budget=None)`.
  - Query only `Itinerary.objects.filter(is_public=True)`.
  - Reuse existing discovery behavior from `app.views.itinerary.search` and template-copy concepts from `app.views.itinerary.template` where practical.
  - Return compact, safe summaries: itinerary id, title, destination, dates, budget, status, tag names, and public stop counts. Do not return private collaborator lists.

## Logging Rules
- Log safe metadata only: tool name, itinerary ids, counts, review focus length, and result counts.
- Do not log full prompts, itinerary descriptions, route notes, API keys, session data, or full model/provider responses.

## Tests To Add
- Explicit review request returns a review for an owned itinerary.
- Ambiguous review intent returns a safe confirmation response.
- Non-owner/non-collaborator cannot review private itinerary data.
- Review includes route waypoint and expense-derived risk signals.
- Public lookup filters private itineraries out.
- Public lookup respects query/location/budget filters.
- Logs do not include descriptions, route notes, or prompt text.
