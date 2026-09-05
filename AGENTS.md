# Reprobe Instructions

Reprobe is a Python CLI for evaluating codebases through harnesses using local
GGUF models via `llama-cpp-python`. Its intended output is high-level issues,
improvement opportunities, and recommendations.

The project is currently a scaffold. Do not add evaluation logic, speculative
frameworks, or empty future packages unless the task requests them.

## Development Workflow

For meaningful changes, follow:

`INSPECT -> PLAN -> IMPLEMENT -> VALIDATE -> REVIEW -> REFINE -> REVALIDATE`

- Inspect relevant code, configuration, tests, and `ARCHITECTURE.md` first.
- Identify established patterns and make the smallest coherent change.
- Validate the changed behavior using relevant checks and CLI smoke commands.
- Review correctness, command boundaries, dependency isolation, and error paths.
- Fix material issues and repeat relevant validation before completion.
- Review the final diff; remove debug code and unrelated changes.

## Command Pattern

Implement non-trivial logical routines and workflow orchestration as dedicated
command classes. This is the default convention for future evaluation work.

- Name commands with verb-first intent, such as `EvaluateRepository`,
  `RunHarness`, or `GenerateRecommendations`. These are examples, not existing APIs.
- Inject required inputs and collaborators through `__init__`.
- Use `execute()` as the single default public workflow entrypoint.
- Return structured results; reusable commands must not print CLI output.
- Keep commands callable from Python and tests without starting the CLI.
- Break multi-step routines into focused private methods or collaborators.
- Use small functions for stateless helpers and pure transformations.
- Prefer composition over inheritance; do not build generic command containers.

A command coordinates a use case. It may validate workflow preconditions,
determine execution order, invoke collaborators, and return findings. It must
not absorb model loading, source traversal, serialization, or presentation
details that belong to focused components.

## CLI and Dependency Boundaries

- Keep `__main__.py` limited to entrypoint delegation.
- Keep `cli.py` and any future `runner.py` thin: parse or normalize options,
  construct dependencies, invoke commands, and present results.
- Keep inference, harness evaluation, and substantial workflow branching out
  of the CLI and runner.
- Isolate `llama-cpp-python` calls behind a focused adapter when implemented.
- Inject replaceable model and repository collaborators into commands.
- Read environment settings at the composition boundary and pass values inward.
- Avoid import-time model loading, network calls, and mutable global state.
- Accept model paths and runtime choices explicitly; avoid machine-specific
  paths or assumptions about GPU availability.
- Do not introduce registries, factories, protocols, or base classes until
  a concrete feature needs that boundary.

## Modularity and Configuration

- Give each module one responsibility: command, harness, repository access,
  model integration, configuration, or presentation.
- Keep harness-specific rules close to their harness; extract shared behavior
  only when it represents the same reusable capability.
- Keep dependency direction consistent with `ARCHITECTURE.md`.
- Prefer explicit configuration and small public interfaces over hidden state.
- Keep external library schemas and types from spreading into workflow logic.
- Preserve existing public invocation unless the task explicitly changes it.

## Errors and Testing

- Make failures specific and actionable; do not swallow exceptions.
- Translate integration failures at the boundary with enough context to
  explain them, preserving the cause with `raise ... from exc` when wrapping.
- Keep user-facing error rendering at the CLI boundary.
- Test material command behavior through `execute()` with lightweight injected
  fakes; ordinary workflow tests should not require a GGUF model or GPU.
- Add regression coverage for bug fixes when practical.
- Keep real-model integration checks separate from lightweight checks.
- Do not add tests that merely mirror trivial scaffold code.

Current smoke checks:

```bash
python -m reprobe --help
python -m reprobe ./path/to/repo
```

Missing required arguments should produce argparse usage and a nonzero exit.
The scaffold notice must not claim that an evaluation ran.

## Documentation and Completion

- Treat `ARCHITECTURE.md` as the architecture reference and review it for code
  or configuration changes.
- Update it when ownership, dependency direction, public interfaces, commands,
  or workflow data flow changes. Distinguish plans from implemented behavior.
- Keep setup and user-facing usage in `README.md`.
- Before finishing, verify the requested scope, relevant validation results,
  module placement, command conventions, and absence of unnecessary coupling.
