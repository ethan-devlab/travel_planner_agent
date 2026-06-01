## Core Philosophy and Principles

- **Deep Analysis**: Analyze problems from first principles and use tools effectively to improve efficiency.
- **Fact-Based Work**: Treat facts as the highest priority. If any assumption, statement, or implementation is incorrect, identify and correct it directly.

## Development Workflow

- **Progressive Development**: Iterate through multiple rounds of discussion to clarify and implement requirements. Before starting any design or coding work, complete the necessary research and resolve all open questions.
- **Structured Process**: Strictly follow this sequence: propose a solution → request review → break it down into concrete tasks.

## Output Requirements

- **Language**: All responses, reasoning summaries, plans, and task lists must be written in English. Use Traditional Chinese or mixed Chinese-English only when necessary.

---

## Design for High Performance While Preserving Practical Usability

Prioritize high-performance design, but ensure the implementation remains usable, maintainable, and practical.

## No Backward Compatibility

Do not preserve backward compatibility by default. Break old formats freely when doing so results in a cleaner, better, or more correct design.

## Suitable Comments and Logs Are Required

Never write code without appropriate comments and logs.

## Mandatory Decomposition When Readability Drops

When a file, function, component, module, or task exceeds a reasonable complexity threshold and readability begins to decline, split it into smaller, clearer units.

## Prefer Multi-Agent Parallelization

Prefer using multi-agent workflows. Decompose work into tasks that can be developed in parallel to improve efficiency.

## Always Check Latest Documentation and Source Code

Always consult the latest documentation and, preferably, source code whenever relevant, because APIs, libraries, frameworks, and best practices may have changed since model training.

## Default Skill Usage

Always use the `$karpathy-guidelines` skill by default, unless the user explicitly disables it or the skill is unavailable.

## Project Analysis Principles

1. **Analyze the project structure deeply**: Understand the technology stack, architecture patterns, and dependency relationships.
2. **Understand business requirements**: Analyze the project goals, feature modules, and user needs.
3. **Identify key modules**: Locate core components, service layers, and data models.
4. **Provide best practices**: Offer technical recommendations and optimization strategies based on the project’s specific characteristics.