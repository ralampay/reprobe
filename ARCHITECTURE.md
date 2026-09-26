# Architecture

## Implemented behavior and flow

Reprobe performs a bounded, local model-assisted repository review by default.
It recognizes C++, Ruby, Python, Go, JavaScript, and TypeScript source files.
It returns up to the requested number of prioritized recommendations (default one), never modifies source, executes repository code,
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
  -> review_report() -> structured envelope
       -> format_report() -> readable stdout (default)
       -> WriteJsonReport.execute() -> optional JSON file
       -> serialize_report() -> JSON stdout with --output-json -
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
  output/                     # Structured data, terminal reports, JSON export, progress
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
| `models/backend_output.py` | Scoped suppression of Python streams and native stdout/stderr descriptors during backend calls |
| `output/progress.py` | Scoped terminal spinner with elapsed time, plus plain redirected stderr status messages |
| `models/llama_cpp.py` | Lazy `llama_cpp` integration, one shared completion routine, token counting, response conversion, resource cleanup; legacy review wrapper |
| `repositories/local.py` | Root validation, deterministic source discovery, language identification, bounded source reads |
| `repositories/exclusions.py` | Built-in dependency/environment exclusions and scoped ignore matching through lazily imported `pathspec` |
| `repositories/sampling.py` | Language-balanced bounded reads and omissions, with no prompt or inference dependency |
| `review/context.py` | `PrepareReviewContext.execute()` coordinates sampling and budget fitting with injected message building and token counting |
| `review/source_context.py` | Compatibility facade supplying the standard sampler and review prompt builder |
| `review/prompt.py` | Construct review messages; compatibility exports for the original schema and parser imports |
| `review/contract.py` | Single response schema, structural validation, evidence checks, and recommendation parsing |
| `review/commands.py` | `InspectCodebase.execute()` and `EvaluateRepository.execute()` coordinate workflows without printing |
| `review/types.py` | Immutable source, sample, inspection, evidence, recommendation, and result values; `ReviewError` |
| `output/json_report.py` | Versioned structured envelope; application-owned metadata and errors |
| `output/terminal_report.py` | Pure rendering of the structured envelope into a wrapped, optionally colored terminal report |
| `output/files.py` | JSON serialization and `WriteJsonReport.execute()` for atomic file export |
| `chat/commands.py`, `chat/terminal.py` | Existing chat command and terminal/session presentation respectively |

Commands accept collaborators through constructors. `ReviewModel` requires only
`count_message_tokens(messages)` and `generate_review(messages, *, max_recommendations=1)`;
`ChatModel` requires `generate_reply(messages)`. Both return application types,
not backend dictionaries. The small metadata reader protocol exposes
`read(path) -> ModelMetadata`. Repository/context collaborators can be replaced
with lightweight fakes through their existing methods, without inheritance.

`LlamaCppModel` retains explicit `load()`, idempotent successful `close()`, and
context-manager support. Failed cleanup retains the backend handle for retry.
Combined operation/cleanup failures preserve the original cause and report both.
Commands never own model lifetime or print CLI output.

`EvaluateRepository` accepts an optional keyword-only `query` and
`on_progress(stage)` callback. A query scopes recommendation selection while
retaining the default evidence and response-contract requirements. The CLI
normalizes/rejects blank queries and disallows them in chat mode; Python command
callers also receive an explicit error for a blank query. `review_messages` and
`compact_review_messages` accept keyword-only `query=None`. The prompt includes
it separately from source data and requests only relevant findings. Omitting it
preserves the default general-review prompt.

The command emits scan/context/preflight/generate/validate stages, plus retry and empty-source
stages, and is silent by default. The CLI injects `ProgressReporter.update`, owns
metadata/loading/cleanup/completion messages, and stops the reporter before errors.
The chat presenter scopes a reporter around each generation, leaving prompts and
replies untouched. No fictitious tool calls are displayed: stages correspond to
actual routines in this review pipeline.

`ProgressReporter` animates one stderr line with elapsed seconds on a terminal,
using a worker thread and a stop event. Stage changes join the old worker before
starting the next, and context exit restores a clean line and closes resources
on success, failure, or interruption. The reporter duplicates the original terminal
stderr descriptor before backend suppression starts, allowing frames to remain
visible while native stdout/stderr are redirected. Redirected/non-terminal output
uses one plain line per stage and starts no worker. No terminal cursor is hidden.
All progress stays off stdout, and completion follows successful model cleanup.

The inference adapter retains `verbose=False` and suppresses both Python streams
and native file descriptors around backend import, loading, tokenization,
generation, and cleanup. Each suppression scope restores descriptors and streams
on normal return, exceptions, and interrupts. It never spans result rendering;
the spinner uses its independent terminal descriptor. Exceptions retain their
causes and are rendered afterward.
Descriptor redirection is process-wide and intended for this CLI's synchronous
backend calls; unrelated threads writing to the same streams during those calls
would also be silenced. No persistent logging callback or global log level is
changed. The project has no Ollama integration.

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

Discovery prunes symlinks, dependency/build directories, and caches before
sampling. Built-in directory names are case-insensitive; virtual environments
with arbitrary names are recognized by `pyvenv.cfg` or `conda-meta` markers.
`repositories/exclusions.py` owns this policy and isolates the `pathspec`
Git-ignore matcher. `LocalRepository` carries ancestor `.gitignore` scopes down
the walk; deeper rules override ancestors, then root `.reprobeignore` rules take
precedence. Excluded directories are never descended into, so a negation cannot
restore a file beneath a pruned parent. Built-in exclusions cannot be negated.
Linked ignore files are skipped; unreadable/invalid ignore files produce a
`RepositoryError` with cause instead of silently broadening discovery.
Only ignore files within the supplied root are considered, without requiring
Git or consulting its index; tracked files matching a rule are also excluded.
Excluded files are outside coverage counts. Ordinary first-party `lib`, `tests`,
and `examples` directories remain eligible. The CLI and review commands have no
ignore-matching responsibility. Sampling cycles through languages
alphabetically and paths lexicographically, selecting at most 12 readable files.
Each read is capped at 64 KiB and 80 lines by default. Binary/non-UTF-8, empty,
unreadable, and omitted source files are recorded with reasons when a review can
proceed. If no readable source remains, review fails explicitly.

Review prompts serialize the schema and source data with compact JSON separators.
Source lines are `[line_number, source_text]` pairs, with explicit excerpt ranges;
the system prompt explains this encoding. Evidence validation and report formats
are unchanged. The adapter caches message token counts per model instance using
an eight-entry least-recently-used cache, only for messages of at most 65,536
characters. It stores counts rather than token arrays, skips caching failures,
and clears cached text/counts on successful close. This avoids repeated tokenizer
calls for unchanged instructions and final preflight messages.

The context preparer counts message content with the loaded model's tokenizer,
uses `ResolvedModelSettings.review_input_budget` to reserve output tokens plus
512 tokens for template overhead, and progressively
halves the longest excerpt or omits a one-line excerpt until it fits. The
reservation is an estimate: custom templates can still exceed it, in which case
the adapter returns an actionable context error. At least one source line must
fit. Source text is treated as untrusted data in the prompt.

The prompt asks the model to compare the entire supplied sample and choose the
requested number of highest-priority actionable issues, weighing impact and evidence. It prioritizes
correctness, security, reliability, and data-loss risks over style or speculative
features, and asks the evidence explanation to justify the issue's impact. It
must not inflate priority or emit one finding per file. The generation schema
and application validator both enforce the requested maximum, using
`review_schema(max_recommendations)`; `REVIEW_SCHEMA` remains the one-item default
for existing imports. The schema builder returns independent schemas to avoid
cross-request mutation. `EvaluateRepository` validates a positive integer limit
and passes it to prompting, generation, parsing, and retry instructions. The CLI
exposes `-n COUNT`, default one, and rejects it in chat mode. Existing one-item
model collaborators still receive the original one-argument generation call;
collaborators supporting multiple findings accept the new keyword. The parser
stably sorts by priority before assigning IDs. Terminal and JSON output include
all returned findings, each with a synopsis. Insufficient evidence permits fewer
findings. Token settings are unchanged; the limit does not trigger extra model
calls, and aggregate usage covers the complete review.
The contract bounds titles to 120 characters, synopses to 360 characters,
explanations/steps to 240 characters,
evidence lists to two entries, and change/test lists to three entries. Application
validation independently enforces these bounds, fields, enums, types, nonempty
steps, and evidence within supplied line ranges. An empty recommendation list is valid.

After context fitting, `EvaluateRepository` checks the final prompt token count
against the available input budget before each inference attempt. On incomplete
JSON with a `length` finish reason, it retries once with a compact prompt asking
for concise findings with the same requested count. `SourceContext.prepare` accepts an optional keyword-only
`build_messages` collaborator; the command supplies the actual prompt builder
for each attempt, including the query and retry instructions. Context fitting
therefore counts that exact input rather than estimating additional overhead;
the model instance and configured output/context limits are unchanged. Complete,
validated JSON is accepted with either `stop` or `length`. Other invalid output
is not retried, and partial JSON is never salvaged as a successful report.

The command exposes a read-only `result` property with immutable snapshots after
inspection, context preparation, and generation attempts. The CLI reads the last
snapshot if execution fails, preserving discovered languages, supplied ranges,
omissions, input-token count/budget, and attempt count in the error envelope.
Pre-context failures record discovered sources as not sent to the model. These
coverage fields are additive within the version 1.0 envelope. A retry that also
truncates raises an actionable error that distinguishes input and output limits. Evidence validation verifies locations,
not semantic correctness of model claims; users still review proposed changes.

### Inference token accounting

`models.types.TokenUsage` holds backend-independent input/output counts and a
computed total. `ChatReply.usage` is optional, retaining the existing two-argument
constructor. The llama-cpp adapter maps response `usage.prompt_tokens` and
`usage.completion_tokens` into this value without additional tokenization or
inference. Present but malformed counts are integration errors; absent usage is
unknown, never inferred from configured limits or preflight counts.

`ReviewResult.token_usage` stores one optional value per inference attempt.
`EvaluateRepository` records an unknown slot before invoking generation, replaces
it on reply, and preserves previous attempts across retries and error snapshots.
Usage is retained before recommendation validation. The serializer adds
`token_usage` to the version 1.0 envelope: aggregate `input_tokens`,
`output_tokens`, `total_tokens`, `complete`, and an ordered `attempts` list.
If any attempt is unknown, aggregate counts are null and complete is false;
known attempts remain visible. No inference has zero counts and an empty list.

The terminal renderer labels actual usage `Tokens used` and the separate input
budget estimate `Preflight`. Totals include all attempts, including truncated
responses. These backend-reported counts include template input and generated
output; they do not measure cached-versus-computed tokens or device utilization.

`output/json_report.py` derives `context_usage` from resolved model settings and
backend usage, without loading or querying the model again. It includes
`configured_context_tokens`, `model_context_tokens` (GGUF training context), and
per-attempt `used_tokens`, `configured_context_percent`, `model_context_percent`,
and `remaining_context_tokens`. Percentages use actual input plus output, rounded
to two decimals; remaining tokens use the configured window and floor at zero.
Retries are independent context windows, so cumulative totals are never used as
context occupancy. Missing settings, training metadata, or usage yield null
fields rather than invented limits or percentages. No inference has no attempt
entries. The terminal shows `Model max`, configured `Context` and output limit,
and a `Context used` line for each attempt. GGUF training context is reported as
a reference limit rather than a claim about hardware capacity or maximum output.

## Output, errors, and extensibility

The version 1.0 envelope always has `schema_version`, `status`, `repository`,
`languages`, `model`, `coverage`, `token_usage`, `context_usage`, `recommendations`, and `errors`. Runtime failures
use the same envelope with empty recommendations. Before settings/review are
available, model is null and coverage is empty; after inspection, partial coverage
is retained on failure. The default stdout display is a readable report rendered
from that same envelope. It shows priority/category, title, synopsis, cited evidence,
change steps, validation, coverage, and explicit empty/error states. The CLI
chooses terminal width and enables color only on a TTY unless `NO_COLOR` is set
or `TERM=dumb`. The renderer strips control characters from model/path text and
wraps long content. `output/terminal_report.py` uses Rich panels for numbered item
cards, with priority-colored borders, titles, a PROPOSED status, synopsis, evidence,
and unchecked action/validation checklists. Rich tables align summary metadata
and checklist markers. A local Console renders into StringIO, so `format_report`
remains a pure string-returning presentation interface; CLI stdout ownership and
JSON exports are unchanged. All model/path strings are sanitized and passed as
literal Text, never Rich markup. Explicit width/color settings preserve redirected
output and NO_COLOR behavior. Rich adds no inference or domain dependency. Help/argument errors and explicit chat retain conventional text.

`Recommendation.synopsis` is a required nonempty field in the generation schema,
validated alongside the rest of the finding and normalized to single-spaced text
by the parser. The prompt requests one or two standalone spoken-language sentences
covering problem, proposed change, and benefit, avoiding Markdown/code/location
references or claims of an applied fix. This is generated in the existing review
call and retained on concise retries (which request shorter fields). Report
serialization includes it at `recommendations[0].synopsis`; the terminal renders
the same text under `SYNOPSIS`. Future speech integration can consume this field
without parsing presentation text. No speech dependency or additional inference
is introduced. The dataclass defaults to an empty string for existing Python
constructors, but new model replies must supply a valid synopsis. Empty/error
reports keep an empty recommendation list rather than invent a fix synopsis.
The response contract validates structure/length, not semantic speaking quality.

`--output-json PATH` keeps the readable display and additionally saves the full
envelope, including runtime failures. `WriteJsonReport` serializes first, writes
a temporary UTF-8 file beside the destination, and atomically replaces the target.
It does not create missing parent directories. A failure preserves any old report,
cleans up the temporary file, and raises `ReportWriteError` with its cause; the CLI
renders the error and exits 1. Existing report files may be replaced, but the CLI
rejects the model file as an export destination. No file is written by default.
`--output-json -` selects JSON-only stdout for automation. The flag is invalid
with `--chat`. The envelope and Python review interfaces remain structured in
both modes. Diagnostics go to stderr. Status codes are
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

Spinner tests use both in-memory terminals and a real PTY, including animation
while native descriptors are suppressed. Recovery tests cover concise retries,
complete JSON at the token limit, retry exhaustion, context-fit failures, explicit
limit preservation, and retained error coverage. A real Qwen3.5-0.8B GGUF review
was also validated with the default 8192/2048 context/output configuration.
