"""Explicit GGUF lifecycle and llama-cpp-python integration."""

from collections.abc import Sequence

from reprobe.chat_types import ChatMessage, ChatReply, ModelConfig


class ModelError(RuntimeError):
    """An actionable model integration failure."""


class LlamaCppModel:
    def __init__(self, config: ModelConfig) -> None:
        self.config = config
        self._model = None

    def load(self) -> None:
        if self._model is not None:
            return
        try:
            path = self.config.model_path.expanduser()
            is_file = path.is_file()
        except (OSError, RuntimeError, ValueError) as exc:
            raise ModelError(
                f"Cannot access model path {self.config.model_path}: {exc}"
            ) from exc
        if not is_file or path.suffix.lower() != ".gguf":
            raise ModelError(f"Model must be an existing GGUF file: {path}")
        try:
            from llama_cpp import Llama
        except (ImportError, OSError) as exc:
            raise ModelError(
                "Cannot import llama-cpp-python; install a working build with "
                "`python -m pip install llama-cpp-python`."
            ) from exc
        try:
            self._model = Llama(
                model_path=str(path),
                n_ctx=self.config.n_ctx,
                n_gpu_layers=self.config.n_gpu_layers,
                chat_format=self.config.chat_format,
                verbose=False,
            )
        except Exception as exc:
            raise ModelError(
                f"Cannot load GGUF model {path}: {exc}. Check model compatibility "
                "with your llama-cpp-python build and available memory."
            ) from exc

    def generate_reply(self, messages: Sequence[ChatMessage]) -> ChatReply:
        if self._model is None:
            raise ModelError("Model is not loaded; call load() before generating replies.")
        try:
            response = self._model.create_chat_completion(
                messages=[{"role": m.role, "content": m.content} for m in messages],
                max_tokens=self.config.max_tokens,
                temperature=self.config.temperature,
                stream=False,
            )
            return self._parse_reply(response)
        except Exception as exc:
            raise ModelError(
                f"Chat generation failed: {exc}. For context limits, restart with shorter history or "
                "increase --n-ctx; for template errors, check --chat-format and "
                "model compatibility."
            ) from exc

    @staticmethod
    def _parse_reply(response: object) -> ChatReply:
        if not isinstance(response, dict):
            raise ValueError("model returned a non-object chat response")
        choices = response.get("choices")
        if not isinstance(choices, list) or not choices or not isinstance(choices[0], dict):
            raise ValueError("model returned no valid chat choice")
        choice = choices[0]
        message = choice.get("message")
        if not isinstance(message, dict) or message.get("role") != "assistant":
            raise ValueError("model returned no assistant message")
        content = message.get("content")
        if not isinstance(content, str) or not content.strip():
            raise ValueError("model returned an empty text reply; check the chat template")
        reason = choice.get("finish_reason")
        if reason not in ("stop", "length"):
            raise ValueError(f"unsupported chat finish reason: {reason!r}")
        return ChatReply(content, reason)

    def close(self) -> None:
        model = self._model
        if model is not None:
            try:
                model.close()
            except Exception as exc:
                raise ModelError(f"Cannot release model resources: {exc}") from exc
            self._model = None

    def __enter__(self) -> "LlamaCppModel":
        self.load()
        return self

    def __exit__(self, exc_type, exc_value, traceback) -> None:
        try:
            self.close()
        except ModelError as cleanup_error:
            if exc_value is None:
                raise
            raise ModelError(
                f"{str(exc_value) or type(exc_value).__name__}; additionally, {cleanup_error}"
            ) from exc_value
