# Architecture

## Implemented behavior and flow

Reprobe performs a bounded, local model-assisted repository review by default.
It recognizes C++, Ruby, Python, Go, JavaScript, and TypeScript source files.
It returns recommendations, never modifies source, executes repository code,
or calls a remote model. Language support is source recognition and model
reasoning, not compiler-backed analysis. `--chat` enables the existing interactive
chat use case instead.

```text
CLI / Python caller
  -> ResolveModelSettings.execute()
       -> GgufMetadataReader.read() -> read-only GGUF metadata
       <- ResolvedModelSettings / concrete ModelConfig
  -> LlamaCppModel.load()                 (one inference load)
  -> EvaluateRepository.execute()
       -> InspectCodebase.execute() -> LocalRepository
       -> SourceContext.prepare() (compatibility facade)
            -> PrepareReviewContext.execute()
                 -> SourceSampler.sample() -> LocalRepository
                 -> injected message builder + model token counting
       -> review_messages() -> ReviewModel.generate_review()
       -> parse_recommendations() -> immutable ReviewResult
  -> LlamaCppModel.close()
  -> review_report() -> JSON stdout
```

The CLI owns resource lifetime and emits the report after model cleanup. Cleanup
failure therefore produces an error report rather than a premature success.
`__main__.py` and the installed `reprobe` entrypoint delegate to `cli.main()`.
Imports perform no model loading, downloads, or network calls.

## Package layout

```text
reprobe/
  cli.py, __main__.py          # CLI composition and entrypoint
  models/                     # Types, settings, GGUF metadata, llama-cpp adapter
  repositories/               # Local repository access and source sampling
  review/                     # Types, commands, context, prompts, response contract
  chat/                       # Types, commands, terminal interaction
  output/                     # JSON report serialization
```

Implementations live in these component packages. Root-level modules such as
`model.py`, `repository.py`, and `review_commands.py` are compatibility exports,
not duplicate implementations. Internal code imports canonical package paths.
Every package initializer contains only its description, so importing a package
does not initialize models or import external inference dependencies.

## Ownership and interfaces

| Component | Responsibility |
| --- | --- |
| `cli.py` | Parse/validate flags, compose dependencies, own lifecycle, choose review/chat, render diagnostics and exit statuses |
| `models/gguf_metadata.py` | Isolate `gguf.GGUFReader`, map the file read-only, extract scalar metadata, release the mapping, translate failures |
| `models/settings.py` | `ResolveModelSettings(model_path, reader, **overrides).execute()` returns immutable resolved settings, selection reasons, and the review input budget |
| `models/types.py` | Backend-independent `ModelConfig`, `ModelMetadata`, and shared validation of explicit or resolved settings |
| `chat/types.py` | Chat messages, replies, and turns; compatibility export of `ModelConfig` |
| `models/llama_cpp.py` | Lazy `llama_cpp` integration, one shared completion routine, token counting, response conversion, resource cleanup; legacy review wrapper |
| `repositories/local.py` | Root validation, deterministic source discovery, language identification, bounded source reads |
| `repositories/sampling.py` | Language-balanced bounded reads and omissions, with no prompt or inference dependency |
| `review/context.py` | `PrepareReviewContext.execute()` coordinates sampling and budget fitting with injected message building and token counting |
| `review/source_context.py` | Compatibility facade supplying the standard sampler and review prompt builder |
| `review/prompt.py` | Construct review messages; compatibility exports for the original schema and parser imports |
| `review/contract.py` | Single response schema, structural validation, evidence checks, and recommendation parsing |
| `review/commands.py` | `InspectCodebase.execute()` and `EvaluateRepository.execute()` coordinate workflows without printing |
| `review/types.py` | Immutable source, sample, inspection, evidence, recommendation, and result values; `ReviewError` |
| `output/json_report.py` | Versioned report serialization; application-owned metadata and error envelope |
| `chat/commands.py`, `chat/terminal.py` | Existing chat command and terminal/session presentation respectively |

Commands accept collaborators through constructors. `ReviewModel` requires only
`count_message_tokens(messages)` and `generate_review(messages)`;
`ChatModel` requires `generate_reply(messages)`. Both return application types,
not backend dictionaries. The small metadata reader protocol exposes
`read(path) -> ModelMetadata`. Repository/context collaborators can be replaced
with lightweight fakes through their existing methods, without inheritance.

`LlamaCppModel` retains explicit `load()`, idempotent successful `close()`, and
context-manager support. Failed cleanup retains the backend handle for retry.
Combined operation/cleanup failures preserve the original cause and report both.
Commands never own model lifetime or print CLI output.

### Dependency direction and compatibility

Model settings policy and the GGUF reader depend on `models.types`, which imports
neither adapter. Shared option validation checks supplied values before metadata
access and checks fully resolved limits when constructing `ModelConfig`. The CLI
normalizes mode defaults and renders validation errors; it does not construct a
placeholder configuration or calculate token budgets.

Source sampling depends only on repository access and source/domain values.
`PrepareReviewContext` receives its sampler, inspection, message builder, token
counter, and input budget through its constructor. It returns `SourceSample` and
does not import the standard prompt or a model adapter. `SourceContext` composes
these components for existing callers and preserves its tuple return value.

Prompt construction and response parsing depend on the single review contract.
`LlamaCppModel.generate_structured(messages, schema)` accepts a caller-owned JSON
schema; backend response-format dictionaries remain inside the model adapter.
The existing `generate_review(messages)` method is a compatibility wrapper that
supplies the review schema and retains review-specific error messages. Both it
and chat use the same private completion/response-validation path. Only that
legacy wrapper imports the review contract; generic inference has no prompt
construction or evidence-validation responsibility.

Existing constructors, methods, and imports remain available. Canonical locations
include `reprobe.models.types.ModelConfig`, `reprobe.models.types.ModelMetadata`,
`reprobe.review.contract.parse_recommendations`, and `reprobe.review.types.ReviewError`.
The original flat modules explicitly re-export the same objects, including prior
aliases such as `ModelConfig` from `reprobe.chat_types` and `ModelMetadata` from
`reprobe.gguf_metadata`. There is no second implementation or wrapping subclass.

Dependency direction remains unchanged: CLI composition depends on component
packages; model settings and adapters depend on shared model types; repository
sampling depends on local access and review data values; review commands compose
sampling, prompting, and model capabilities; output serialization consumes values.
The model adapter's legacy review method imports the review contract only when
called. New code imports canonical modules rather than compatibility exports.

Tests patch the canonical module where a dependency is looked up (for example,
`reprobe.repositories.local.os.walk`). CLI composition dependencies are still
patched through `reprobe.cli`. Backward-compatible imports do not promise that
patching an old module attribute changes a canonical module's globals.

Setuptools discovers all `reprobe*` packages. Both the wheel and editable install
retain the `reprobe.cli:main` entrypoint and compatibility modules. No registries,
factories, base classes, or new dependencies are introduced by the package layout.

## Token policy and review limits

GGUF `general.architecture` selects `<architecture>.context_length`. The default
context is the smaller of that training context and 8192; absent metadata falls
back to 4096 with a diagnostic. Default output allowance is
`min(2048, resolved_context // 4)`. Explicit `--n-ctx` and `--max-tokens` replace
only their corresponding settings. Invalid combinations are rejected, never
silently adjusted. An explicit context above training context is permitted with
a diagnostic; actual support depends on the model/backend.

Metadata inspection uses a read-only memory map and does not construct an
inference model or load tensor weights into inference memory. Metadata reader
objects do not escape the adapter. Corrupt files or invalid metadata are errors,
not fallback cases. `ModelConfig` remains a concrete configuration value with
its historical Python defaults; Python callers opt into automatic selection by
using `ResolveModelSettings`. CLI review and chat both use automatic selection.

These defaults are conservative policy, not hardware benchmarking. GPU layers
remain explicit, defaulting to CPU. Review temperature defaults to 0.2 and chat
temperature to 0.7. The report records resolved settings and their origins.

Discovery skips symlink entries, dependency/build directories and common caches.
It does not implement `.gitignore` matching. Sampling cycles through languages
alphabetically and paths lexicographically, selecting at most 12 readable files.
Each read is capped at 64 KiB and 80 lines by default. Binary/non-UTF-8, empty,
unreadable, and omitted source files are recorded with reasons when a review can
proceed. If no readable source remains, review fails explicitly.

The context preparer counts message content with the loaded model's tokenizer,
uses `ResolvedModelSettings.review_input_budget` to reserve output tokens plus
512 tokens for template overhead, and progressively
halves the longest excerpt or omits a one-line excerpt until it fits. The
reservation is an estimate: custom templates can still exceed it, in which case
the adapter returns an actionable context error. At least one source line must
fit. Source text is treated as untrusted data in the prompt.

Structured generation requests at most three recommendations using a JSON schema.
Application validation independently enforces fields, enums, types, nonempty
steps, and evidence within supplied line ranges. Truncated output is rejected.
An empty recommendation list is valid. Evidence validation verifies locations,
not semantic correctness of model claims; users still review proposed changes.

## Output, errors, and extensibility

The version 1.0 envelope always has `schema_version`, `status`, `repository`,
`languages`, `model`, `coverage`, `recommendations`, and `errors`. Runtime failures
use the same envelope with empty recommendations. Before settings/review are
available, model is null and coverage is empty. Help/argument errors and explicit
chat output retain conventional text. Diagnostics go to stderr. Status codes are
0 (completed or no supported source), 1 (runtime failure), 2 (invalid arguments),
and 130 (interrupt with successful cleanup).

Extend language support in repository recognition with matching fixtures. Add
review rules in the prompt and review contract; introduce a separate
harness only when a concrete use case needs one. Alternative local adapters
implement the small review/chat capabilities without changing commands. Change
token policy in settings resolution, metadata parsing in its adapter, and report
rendering in presentation. Keep external schemas inside integration modules and
review-contract handling. Do not introduce registries, generic command containers,
or empty future packages.

Full-repository chunked analysis, compiler integration, automatic patches, model
downloads, hardware tuning, and additional harnesses are not implemented.

## Validation

Pytest covers commands with injected fake models, supported languages and source
sampling, metadata-only GGUF fixtures, early option validation, token policy and overrides, structured
response validation, CLI envelopes, and backend lifecycle/error paths. Lightweight
checks require no inference model or GPU. Real-model smoke checks are separate;
see README for commands and installation.

Refactor regression coverage also exercises the sampler independently, context
preparation with injected builders/counters, arbitrary-schema generation, and
legacy import identities. Deterministic CLI comparisons preserve report contents,
diagnostics, and exit statuses for success, generation failure, cleanup failure,
and interruption.
