# Architecture

## Implemented components

- `reprobe/__main__.py` delegates to `cli.main()`; package imports have no runtime initialization.
- `reprobe/cli.py` parses options, validates mode combinations, constructs model configuration and the adapter, owns its session lifetime, and renders errors/exit statuses.
- `reprobe/chat_types.py` contains immutable application-owned `ModelConfig`, `ChatMessage`, `ChatReply`, and `ChatTurn` values. Configuration validates Python input types and runtime limits without importing a backend.
- `reprobe/model.py` implements `LlamaCppModel`: explicit `load()`, `generate_reply(messages)`, and idempotent `close()`, with context-manager support. Only this module imports/calls `llama_cpp`, lazily on loading. It validates backend responses before translating them into application values and wraps integration errors with causes in `ModelError`. Only nonblank assistant text with a `stop` or `length` finish reason is accepted.
- `reprobe/commands.py` implements `GenerateChatReply(model, history, user_input).execute()`. It returns a `ChatTurn` with the reply and new immutable history, without mutating input history or printing. The structural `ChatModel` protocol describes the single generation capability needed by this command, allowing independent adapters and lightweight fakes without inheritance.
- `reprobe/terminal.py` owns terminal input/output, session history, and slash commands. It calls the command for each nonblank message and displays complete replies.

```text
CLI composition / Python caller
    -> model lifecycle (load / close)
    -> terminal presentation
        -> GenerateChatReply.execute()
            -> ChatModel.generate_reply(messages)
                -> LlamaCppModel -> llama-cpp-python
        <- ChatTurn (reply and updated history)
```

Python callers can construct `ModelConfig(model_path=Path(...))`, enter a
`LlamaCppModel(config)` context, and invoke `GenerateChatReply(model, history,
user_input).execute()` independently of the CLI. Messages and replies contain
application types, not external library schemas. Model instances and conversation
history are session-local; no network calls or global model state are introduced.

Chat requires `--chat --model PATH` and no repository. Runtime settings are
explicit CLI/configuration inputs. Defaults use CPU inference, 4096 context
tokens, 512 maximum reply tokens, temperature 0.7, and backend template selection.
History is in memory, reset by `/clear`, and never automatically truncated.
Failures leave caller-owned history unchanged and terminate CLI chat with a
nonzero status. EOF and exit commands return 0; Ctrl+C returns 130 when cleanup
succeeds. The adapter attempts cleanup on every exit from a loaded session.
A cleanup failure returns status 1 and retains the backend handle for an explicit
retry by Python callers. Combined operation/cleanup failures report both errors
without replacing the original operation's cause chain. Successful close clears
the handle and is idempotent; loading again after a successful close is allowed.

## Evaluation remains planned

`python -m reprobe REPOSITORY` preserves the scaffold notice without accessing
the repository. Evaluation commands, harness rules, repository traversal, and
recommendation presentation remain unimplemented. Future commands should inject
focused model/repository collaborators and return structured findings. Harness
rules belong with their harnesses; source access belongs in repository components.
Automatic source modification is outside the current scope.

## Validation boundaries

`tests/` covers command behavior, terminal interaction, CLI validation,
configuration, backend response validation, and lifecycle failures using lightweight fakes. Real GGUF checks are separate manual
smoke commands documented in README; local model paths are not runtime defaults.
