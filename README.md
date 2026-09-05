# Reprobe

Reprobe will use local GGUF models through `llama-cpp-python` to evaluate
codebases via harnesses, identify issues and improvement opportunities, and
produce high-level recommendations.

This repository currently contains only the Python project scaffold. It does
not inspect repositories, load models, execute harnesses, or generate recommendations.

## Run the scaffold

With Python 3.10 or newer, run from this directory:

```bash
python -m reprobe ./path/to/repo
python -m reprobe --help
```

The CLI accepts a repository path and prints a scaffold notice. It does not
validate or access that path yet. No third-party dependencies are needed for
this initial CLI.

## Development installation

```bash
python -m venv .venv
source .venv/bin/activate
python -m pip install -e .
```

The project declares `llama-cpp-python` as its inference dependency; a full
installation installs it, although the scaffold does not import it yet.
To install only the scaffold without dependencies, use
`python -m pip install -e . --no-deps` instead.

See [AGENTS.md](AGENTS.md) for development conventions and
[ARCHITECTURE.md](ARCHITECTURE.md) for package boundaries and intended direction.
