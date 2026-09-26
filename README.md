# Reprobe

Review a repository using a **local GGUF chat/instruction model**. Reprobe
recognizes C++, Ruby, Python, Go, JavaScript, and TypeScript and produces a
consistent JSON report containing suggested fixes, improvements, or features.
It does not modify files, execute repository code, or download models.

## Install

Use Python 3.10 or newer:

```bash
python -m venv .venv
source .venv/bin/activate
python -m pip install -e .
```

`llama-cpp-python` may require a C/C++ toolchain. CPU inference is the default;
GPU acceleration requires a compatible build. See its
[installation instructions](https://llama-cpp-python.readthedocs.io/en/stable/).
The `gguf` dependency reads model metadata before inference starts.

## Run a review

Supply a compatible local chat/instruction GGUF, not an embedding model:

```bash
reprobe --model /path/to/model.gguf /path/to/repo
# Equivalent module invocation; save the JSON report:
python -m reprobe --model /path/to/model.gguf /path/to/repo > review.json
```

Reprobe loads the model once, reviews a bounded sample, prints one JSON object,
and exits. Progress/diagnostics go to stderr. Sampling defaults to at most 12
readable files, round-robin across detected languages, with the first 80 lines
per file and a 64 KiB read cap. Excerpts shrink further to fit the model context.
The report identifies supplied ranges, truncation, and omitted files.

Dependency/build directories, common caches and symlinks are excluded;
`.gitignore` rules are not currently interpreted. This is a sampled review, not
an exhaustive audit or compiler analysis. Findings need human review. An empty
recommendation list is valid when there is insufficient evidence.

## Automatic token settings

Reprobe examines GGUF architecture/context metadata before loading inference:

| Setting | Default |
| --- | --- |
| Context tokens | Model training context, capped at 8192 |
| Context if metadata is absent | 4096, with a diagnostic |
| Output tokens | One quarter of resolved context, capped at 2048 |
| Template reservation | 512 tokens, in addition to output allowance |

A 4096-context model gets 4096 context / 1024 output tokens; a 32768-context model
gets 8192 / 2048. These conservative defaults do not benchmark your hardware.
Corrupt GGUF files fail explicitly rather than silently using fallback settings.

Explicit values take precedence independently:

```bash
reprobe --model model.gguf ./repo --n-ctx 16384
reprobe --model model.gguf ./repo --max-tokens 1500
reprobe --model model.gguf ./repo --n-ctx 16384 --max-tokens 3000
```

Output must be positive and smaller than context. Explicit values are never
silently adjusted. Context beyond the model's training context produces a
diagnostic and requires backend/model support. Token settings and their selection
sources appear in the JSON report. A custom template may exceed the reserved
overhead; increase context or reduce sampling if generation reports a limit.

| Other flag | Default | Purpose |
| --- | --- | --- |
| `--max-files` | 12 | Maximum sampled files |
| `--max-lines-per-file` | 80 | Maximum sampled lines per file |
| `--n-gpu-layers` | 0 | GPU layers; -1 requests all |
| `--temperature` | 0.2 review / 0.7 chat | Nonnegative sampling temperature |
| `--chat-format` | Model/backend default | Override chat template |
| `--chat` | Off | Interactive chat instead of review |

## JSON contract

The envelope has the same keys on success and runtime failure. Example fields
below illustrate one recommendation; actual findings depend on the supplied code:

```json
{
  "schema_version": "1.0",
  "status": "completed",
  "repository": "/project",
  "languages": ["python"],
  "model": {
    "path": "model.gguf",
    "architecture": "llama",
    "training_context_tokens": 4096,
    "context_tokens": 4096,
    "output_tokens": 1024,
    "context_source": "model_metadata_capped",
    "output_source": "context_policy",
    "diagnostics": []
  },
  "coverage": {
    "discovered_files": 1,
    "reviewed_files": 1,
    "supplied_ranges": [{"path": "main.py", "start_line": 1, "end_line": 5, "truncated": false}],
    "omissions": [],
    "partial": false
  },
  "recommendations": [{
    "id": "R001",
    "category": "improvement",
    "priority": "medium",
    "title": "Validate empty input",
    "evidence": [{"path": "main.py", "start_line": 2, "end_line": 3, "explanation": "Input is used without checking for an empty value."}],
    "suggested_changes": ["Reject empty input before processing."],
    "validation_steps": ["Test empty and nonempty input."]
  }],
  "errors": []
}
```

Statuses are `completed`, `no_supported_source`, and `error`. Categories are
`fix`, `improvement`, and `feature`; priorities are `high`, `medium`, and `low`.
Runtime errors populate `errors` with `code` and `message`, leave recommendations
empty, and preserve available metadata. Model is null until settings resolve;
coverage is empty until a review result exists. Truncated/invalid JSON or evidence
outside the supplied source is rejected, not printed as a successful review.

Exit codes: 0 for completed/empty reviews, 1 for runtime errors, 2 for invalid
arguments, and 130 for interruption with successful cleanup. Help and argparse
errors use conventional text, outside the review JSON contract.

## Interactive chat

```bash
python -m reprobe --model model.gguf ./repo --chat
```

The repository argument is retained but is not inspected in chat mode. Enter a
message per line; use `/clear`, `/exit`, `/quit`, or EOF. History is in memory and
is not silently truncated. Chat also uses model-aware token defaults and explicit
overrides. The chat Python API remains available:

```python
from pathlib import Path
from reprobe.models.gguf_metadata import GgufMetadataReader
from reprobe.models.settings import ResolveModelSettings
from reprobe.models.llama_cpp import LlamaCppModel
from reprobe.chat.commands import GenerateChatReply

settings = ResolveModelSettings(Path("model.gguf"), GgufMetadataReader()).execute()
with LlamaCppModel(settings.config) as model:
    turn = GenerateChatReply(model, (), "Hello").execute()
    print(turn.reply.content)
```

Python callers can also provide a concrete `ModelConfig` directly; its historical
4096/512 token defaults are unchanged. Automatic selection is explicit through
`ResolveModelSettings`. Review commands return immutable results without printing.

For a programmatic repository review:

```python
from reprobe.repositories.local import LocalRepository
from reprobe.review.commands import EvaluateRepository
from reprobe.review.source_context import SourceContext
from reprobe.output.json_report import review_report

repository = LocalRepository()
with LlamaCppModel(settings.config) as model:
    result = EvaluateRepository(
        Path("./repo"), repository, SourceContext(repository), model,
        settings.review_input_budget,
    ).execute()
report = review_report(result.inspection.root, settings, result)
```

Implementations are grouped under `reprobe.models`, `reprobe.repositories`,
`reprobe.review`, `reprobe.chat`, and `reprobe.output`. Shared types live in
`reprobe.models.types`. Previous flat imports such as `reprobe.chat_types` and
`reprobe.gguf_metadata` remain supported through compatibility exports.
Source sampling can be used
independently through `SourceSampler.sample()`. For custom context preparation,
`PrepareReviewContext(...).execute()` accepts a sampler, message builder, token
counter, and input budget. `LlamaCppModel.generate_structured(messages, schema)`
supports caller-supplied JSON schemas; existing chat/review methods are unchanged.

## Validation

```bash
python -m pip install -e '.[dev]'
python -m pytest -q
python -m reprobe --help
reprobe --help
```

Tests use fake inference models and small metadata-only GGUF fixtures; no GPU or
inference weights are needed. For a lightweight development environment install
with `--no-deps` and separately install `pytest` and `gguf`.

Run real inference separately with your own GGUF:

```bash
python -m reprobe --model /path/to/model.gguf . > review.json
python -m json.tool review.json
printf 'Hello\n/exit\n' | python -m reprobe --model /path/to/model.gguf . --chat
```

See [ARCHITECTURE.md](ARCHITECTURE.md) for ownership, interfaces, token policy,
data flow, and extension guidance.
