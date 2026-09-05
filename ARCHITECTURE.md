# Architecture

## Current scaffold

- `reprobe/__init__.py`: package declaration with no runtime initialization.
- `reprobe/__main__.py`: module entrypoint delegating to the CLI.
- `reprobe/cli.py`: argument parsing and the bootstrap notice.
- `pyproject.toml`: package metadata, build configuration, and dependencies.

The flat package layout supports `python -m reprobe ./path/to/repo` directly
from the checkout as well as after installation. The only current behavior is
argument parsing and a notice; there are no evaluation commands yet.

## Intended boundaries

As features are implemented, follow this dependency direction:

```text
CLI / Python caller
    -> composition boundary
        -> command.execute()
            -> focused harness / repository components
            -> model interface backed by a llama-cpp-python adapter
    -> presentation of structured results
```

Commands coordinate logical routines. Harnesses define evaluation criteria and
interpret results. Repository components handle source selection and reading.
The model adapter owns GGUF loading and inference details. Presentation owns
user-facing recommendations and output formats.

These are future responsibilities, not implemented packages or interfaces.
Introduce modules only when a requested feature needs them. Keep model loading
explicit and lazy so package imports and CLI help remain lightweight.

The intended outcome is high-level findings and recommendations. Automatic
source modification is outside the current project scope.
