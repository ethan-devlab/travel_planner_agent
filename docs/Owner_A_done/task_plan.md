# Task Plan: Owner A Planner-Agent Implementation

## Goal
Implement Owner A's production itinerary-management tools, enable planner-agent POST execution through LangChain/OpenAI, and leave implementation handoff docs for Owner B and Owner C.

## Current Phase
Phase 5

## Phases

### Phase 1: Requirements & Discovery
- [x] Capture Owner A scope from the user-approved plan.
- [x] Inspect current planner-agent scaffolding and itinerary persistence paths.
- [x] Record baseline constraints and first findings.
- **Status:** complete

### Phase 2: Implementation
- [x] Add OpenAI/LangChain configuration and planner execution helpers.
- [x] Add Owner A itinerary-management service layer.
- [x] Replace Owner A stubs with typed production tools.
- [x] Keep Owner B/C tools registered as stubs.
- **Status:** complete

### Phase 3: Handoff Docs
- [x] Create `docs/Owner_B.md` for review and public itinerary lookup work.
- [x] Create `docs/Owner_C.md` for travel context and calendar work.
- **Status:** complete

### Phase 4: Testing & Verification
- [x] Add Owner A service/tool/view tests.
- [x] Install or verify LangChain/OpenAI dependencies.
- [x] Run focused tests and full Django test suite.
- **Status:** complete

### Phase 5: Delivery
- [x] Review changed files.
- [x] Summarize verification and any unresolved environment limits.
- **Status:** complete

## Key Questions
1. Should planner-agent POST invoke LangChain now? Answer: yes, with Owner A production tools and Owner B/C stubs still registered.
2. Should Owner A tools mutate data? Answer: yes, immediately with authenticated-user permission constraints and safe logging.

## Decisions Made
| Decision | Rationale |
|----------|-----------|
| Use `.env` key `MODEL` for the OpenAI chat model. | The key already exists in local configuration and was specified by the plan. |
| Keep B/C tools registered as stubs. | The tool registry must continue exposing all five documented groups while Owner A ships first. |
| Put itinerary write rules in a service layer. | Keeps LangChain wrappers thin and makes permissions, validation, transactions, tests, and logging easier to audit. |
| Return JSON-serializable dictionaries from tools. | Predictable for LangChain, tests, and future UI handling. |

## Errors Encountered
| Error | Attempt | Resolution |
|-------|---------|------------|
| `git status --short` reported that the workspace is not a Git repository. | 1 | Continue within the provided workspace without attempting repository repair; use file inspection and tests for safety. |
| Existing planner POST test expected the old stub response. | 1 | Updated the test to assert patched LangChain invocation and safe configuration fallback. |
| Dependency install failed in sandbox due blocked network access. | 1 | Re-ran pip install with approved escalation; dependencies installed successfully. |
| Safe configuration test attempted real provider path after dependencies were installed. | 1 | Patched the test to force `PlannerAgentConfigurationError` without network access. |
| Agent factory sanity check was run before Django settings were configured. | 1 | Re-ran through `manage.py shell`; agent built successfully. |

## Notes
- Do not log prompts, secrets, descriptions, session data, or provider responses.
- Mutating tools must require authenticated server-side context.
- Calendar deletion, review gating, and travel-context provider work belong to Owner B/C docs, not Owner A implementation.
