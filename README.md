# Reprobe

Reprobe loads local GGUF chat models through `llama-cpp-python` and provides
interactive terminal chat. Codebase evaluation, harnesses, and recommendations
are not implemented yet.

## Installation

Use Python 3.10 or newer:

```bash
python -m venv .venv
source .venv/bin/activate
python -m pip install -e .
```

Installation includes `llama-cpp-python`, which may require a C/C++ toolchain.
GPU acceleration requires a backend-enabled build; see the
[backend installation instructions](https://llama-cpp-python.readthedocs.io/en/stable/).
The default runtime uses CPU inference.

## Run

Provide the repository and a local GGUF **chat/instruction model**, not an
embedding model:

```bash
python -m reprobe --model /path/to/chat-model.gguf /path/to/repo
```

Repository evaluation remains scaffolded: the repository argument establishes
the canonical CLI shape but is not accessed yet. The current implementation
then loads the model once and starts an interactive terminal session. Enter one
message per line; each complete reply is printed when ready. Previous turns are
included in subsequent requests. Use `/clear` to reset conversation history,
`/exit` or `/quit` to leave, or EOF (Ctrl+D on Unix). Ctrl+C attempts to close
the model and exits with status 130. A cleanup failure is reported as an error
with status 1.

Optional settings:

| Flag | Default | Purpose |
| --- | --- | --- |
| `--n-ctx` | 4096 | Context token capacity |
| `--n-gpu-layers` | 0 | GPU layers; -1 requests all layers |
| `--max-tokens` | 512 | Maximum tokens per reply; must be less than context size |
| `--temperature` | 0.7 | Nonnegative sampling temperature |
| `--chat-format` | Model metadata/backend default | Explicit template override |

History is held in memory and is not silently trimmed. Generation failures exit
with an error; restart with a larger context or shorter conversation when the
context fills. Model architecture/template support depends on the installed
`llama-cpp-python` build. Empty, malformed, and non-text/tool-call responses
are rejected rather than saved to conversation history. A reply can stop before
`--max-tokens` when the model emits its end token or the context is full.
No models are downloaded automatically.

Exit statuses are 0 for a normal exit, 1 for model/integration failures, 2 for
invalid CLI arguments, and 130 for an interrupt with successful cleanup.

## Use from Python

```python
from pathlib import Path
from reprobe.chat_types import ModelConfig
from reprobe.commands import GenerateChatReply
from reprobe.model import LlamaCppModel

config = ModelConfig(model_path=Path("/path/to/chat-model.gguf"))
with LlamaCppModel(config) as model:
    first = GenerateChatReply(model, (), "Hello").execute()
    second = GenerateChatReply(model, first.history, "What did I just say?").execute()
    print(second.reply.content)
```

Configuration requires a `Path`, integer token/layer settings, and a finite,
nonnegative numeric temperature. Commands return immutable results and do not
print or mutate supplied history. A replacement model only needs
`generate_reply(messages)` returning a `ChatReply`. Adapter operations raise
`ModelError` with the underlying exception retained as a cause.

`load()` reuses an already loaded instance. Successful `close()` is idempotent;
a failed close retains the handle so Python callers can retry cleanup. If both
a session operation and cleanup fail, the error reports both failures and keeps
the original operation's exception chain.

## CLI help

```bash
python -m reprobe --help
```

The repository and `--model` arguments are required for a run. Help does not
import the inference dependency, so it also works with a dependency-free
installation (`python -m pip install -e . --no-deps`).

## Validation

Lightweight tests require neither models nor a GPU:

```bash
python -m unittest discover -s tests -v
```

Run a separate real-model smoke check using your own chat model:

```bash
printf 'Hello\nWhat did I just say?\n/exit\n' | python -m reprobe --model /path/to/chat-model.gguf /path/to/repo
```

See [ARCHITECTURE.md](ARCHITECTURE.md) for Python interfaces and ownership, and
[AGENTS.md](AGENTS.md) for development conventions.
