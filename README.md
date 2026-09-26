# Reprobe

Review a repository using a **local GGUF chat/instruction model**. Reprobe
recognizes C++, Ruby, Python, Go, JavaScript, and TypeScript and produces a
focused terminal report with the highest-priority fixes, improvements, or
features supported by the sampled code (one by default). You can also save the structured JSON.
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
# Show the report and also save its structured data:
python -m reprobe --model /path/to/model.gguf /path/to/repo --output-json review.json
# JSON-only stdout for pipelines:
reprobe --model /path/to/model.gguf /path/to/repo --output-json - > review.json
```

Choose how many top recommendations to request with `-n` (default: `1`):

```bash
python -m reprobe --model /path/to/model.gguf /path/to/repo -n 5 \
  --query "look for inefficiencies or antipatterns" --output-json review.json
```

Terminal findings are rendered with Rich as separate item cards: numbered panels,
priority-colored borders, a proposed-fix synopsis, evidence, and unchecked action
and validation checklists. The review summary and token usage appear above the
cards. Borders and spacing stay readable when color is disabled. Findings are displayed and
exported in priority order, each with its own synopsis,
evidence, suggested changes, and validation steps. The model returns fewer than
requested when evidence is insufficient rather than inventing findings. `-n` must
be a positive integer and is unavailable with `--chat`. It does not automatically
increase token limits; if a larger report truncates, increase `--max-tokens` (and
`--n-ctx` if needed) or request fewer findings. Usage totals cover the entire review.

Focus a review with an optional query (quote it as one argument):

```bash
python -m reprobe --model /path/to/model.gguf /path/to/repo \
  --query "look for inefficiencies in the code or antipatterns"
```

With `--query`, the model selects up to the requested number of evidence-backed recommendations relevant to
that request, or returns no recommendation if the sample does not support one.
Without it, the default general review prompt applies. The query is retained on
retries and included in the input token budget; it does not change file sampling
or enable code execution. Blank queries and combining `--query` with `--chat`
are rejected. The model-path flag is `--model`.

Reprobe loads the model once, reviews a bounded sample, shows a readable report,
and exits. The report includes a priority/category badge for each recommendation,
a short synopsis, source evidence, suggested changes, validation steps, coverage, and token usage. On a terminal,
an animated spinner and elapsed seconds show the active
routine: model inspection/loading, source scanning, context fitting, input-budget
checking, generation, validation, retries, and cleanup. Chat replies also have a
spinner while generating. It stops before user input, replies, or error messages.
Redirected stderr gets plain stage lines without animation or escape sequences.
Progress stays on stderr. Backend debug output is suppressed; actionable errors
remain visible. Terminal report headings use color only on a TTY; set `NO_COLOR`
to disable it. Redirected reports are plain text.
This project uses `llama-cpp-python` directly, not an Ollama service.
Sampling defaults to at most 12
readable files, round-robin across detected languages, with the first 80 lines
per file and a 64 KiB read cap. Excerpts shrink further to fit the model context.
The report identifies supplied ranges, truncation, and omitted files.
Prompts use compact JSON with numbered source-line pairs to reduce input overhead.
A bounded per-model cache avoids repeatedly tokenizing unchanged messages during
context fitting and preflight checks; it is cleared when the model closes.

Discovery excludes dependencies, build output, caches, and symlinks before
sampling. This includes `env`/`ENV`, `.venv`, `node_modules`, `vendor`,
`third_party`, `site-packages`, `.tox`, and `.nox`. Renamed Python/Conda environments
are detected by `pyvenv.cfg` or `conda-meta` markers.

Root and nested `.gitignore` files are respected, even without Git installed.
For additional exclusions, create `.reprobeignore` in the reviewed root using
Git ignore syntax, for example:

```gitignore
custom-dependencies/
generated-client/
*.generated.ts
```

Root `.reprobeignore` rules take precedence over `.gitignore`; negations can
restore files only inside directories that are still traversed. Built-in
exclusions and symlink protection cannot be overridden. Rules apply to tracked
and untracked files alike; parent/global Git ignores are not consulted. First-party
`src`, `lib`, `tests`, and `examples` remain eligible unless explicitly ignored.
Excluded files are outside discovery counts and never sent to the model.

This is a sampled review, not
an exhaustive audit or compiler analysis. Findings need human review. An empty
recommendation list is valid when there is insufficient evidence. Discovery counts
all eligible source files, but the model sees only the reported excerpts. It is
instructed to compare those excerpts as one repository and choose the requested number of top actionable
priorities, rather than produce an item for every file. The priority label remains
honest: the strongest finding can be medium or low when no high-risk issue is
supported by evidence.

`--output-json PATH` writes the full versioned envelope, including coverage,
model settings, recommendation, and any runtime errors, while retaining the
readable terminal display. Nothing is saved unless requested. The parent directory
must exist; an existing destination is replaced atomically after serialization.
A save failure is reported on stderr and returns exit code 1 while keeping the
terminal report. The model file cannot be used as the export destination.
`--output-json -` emits only JSON on stdout. Neither form is available with `--chat`.

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
| `--output-json PATH` | Not saved | Export JSON; use `-` for JSON-only stdout |

## JSON contract

The exported envelope has the same keys on success and runtime failure.
`recommendations` contains zero to `-n` items (default: one). Example fields
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
    "partial": false,
    "input_tokens": 900,
    "input_budget": 2560,
    "generation_attempts": 1
  },
  "token_usage": {
    "input_tokens": 940,
    "output_tokens": 160,
    "total_tokens": 1100,
    "complete": true,
    "attempts": [{"input_tokens": 940, "output_tokens": 160, "total_tokens": 1100}]
  },
  "context_usage": {
    "configured_context_tokens": 4096,
    "model_context_tokens": 4096,
    "attempts": [{
      "attempt": 1,
      "used_tokens": 1100,
      "configured_context_percent": 26.86,
      "model_context_percent": 26.86,
      "remaining_context_tokens": 2996
    }]
  },
  "recommendations": [{
    "id": "R001",
    "category": "improvement",
    "priority": "medium",
    "title": "Validate empty input",
    "synopsis": "Blank input can cause processing failures. Reject empty values before processing to prevent those failures.",
    "evidence": [{"path": "main.py", "start_line": 2, "end_line": 3, "explanation": "Input is used without checking for an empty value."}],
    "suggested_changes": ["Reject empty input before processing."],
    "validation_steps": ["Test empty and nonempty input."]
  }],
  "errors": []
}
```

Each recommendation includes `synopsis`: a short, self-contained explanation of
the problem, proposed fix, and expected benefit. It is displayed under `SYNOPSIS`
and exported as `recommendations[0].synopsis`, ready for a future text-to-speech
consumer. The model is instructed to use one or two plain-language sentences,
without Markdown, code, file paths, or line references, and to describe a proposed
fix rather than claim it was applied. The field is required and limited to 360
characters; whitespace is normalized. Empty/error reports have no recommendation
synopsis. Speech synthesis itself is not implemented.

The terminal report displays actual backend-reported usage, for example:

```text
Tokens used 1,100 total (940 input + 160 output; all attempts)
```

The report also shows the model's maximum training context from GGUF metadata,
the configured context window, and actual context usage for each attempt:

```text
Model max   262,144 tokens (GGUF training context)
Context     8,192 tokens configured; 2,048 output token limit
Context used Attempt 1: 918 / 8,192 tokens (11.21% configured; 0.35% model max)
```

The `context_usage` JSON object contains both context limits and per-attempt
used tokens, percentages, and remaining configured-context tokens. Usage is
actual backend-reported input plus output, including template tokens. Retries
use separate windows, so cumulative usage is never divided by one context limit.
The GGUF training context is a model reference limit, not a guarantee that your
hardware/backend can run that window or generate that many output tokens. Missing
metadata is shown as unknown; missing usage gives null percentages. Limits are
reported without changing your runtime settings.

The JSON `token_usage` object includes aggregate input/output/total counts and
per-attempt counts, including truncated attempts before a retry. Input includes
chat-template tokens reported by the backend; output includes the generated
structured response. These are inference token counts, not a hardware-work or
billing measurement. The separate `Preflight` line is the content-only input
budget check, not consumed-token usage. If any attempted generation lacks usage,
aggregate counts are `null`, `complete` is false, and the display says unavailable;
known per-attempt counts remain in JSON. No inference means zero tokens.
Usage survives recommendation-validation errors and cleanup failures.

Statuses are `completed`, `no_supported_source`, and `error`. Categories are
`fix`, `improvement`, and `feature`; priorities are `high`, `medium`, and `low`.
Runtime errors populate `errors` with `code` and `message`, leave recommendations
empty, and preserve available metadata. Model is null until settings resolve;
coverage is populated as soon as inspection succeeds and retained on later
failures. Coverage includes input tokens, the available input budget, and the
number of generation attempts. The input budget reserves output tokens and
512 tokens for chat-template overhead; custom template overhead remains an estimate.

Before inference, source excerpts are fitted to the input budget and the final
prompt is checked again. A fitted prompt cannot guarantee the answer will fit
its separate output limit. To reduce overruns, review fields and list lengths
are bounded. If generation ends with incomplete JSON at the output limit,
Reprobe retries once using the same limits and requested count, asking for concise
recommendations and re-fitting source context for that prompt. It does not reload
the model or silently increase explicit token limits.

A complete, validated JSON response is usable even if generation hit the token
limit afterward. Partial JSON is never repaired or reported as success. If the
retry also truncates, the error explains how to increase `--max-tokens` (and
`--n-ctx` if needed) or reduce `--max-files`; coverage from the attempted review
remains available. Invalid schemas or evidence outside supplied source are
reported as errors without a retry.

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
with `--no-deps` and separately install `pytest`, `gguf`, `pathspec`, and `rich`.

Run real inference separately with your own GGUF:

```bash
python -m reprobe --model /path/to/model.gguf . --output-json review.json
python -m json.tool review.json
printf 'Hello\n/exit\n' | python -m reprobe --model /path/to/model.gguf . --chat
```

See [ARCHITECTURE.md](ARCHITECTURE.md) for ownership, interfaces, token policy,
data flow, and extension guidance.
