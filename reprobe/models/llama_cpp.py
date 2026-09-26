"""Explicit GGUF lifecycle and llama-cpp-python integration."""

from collections.abc import Sequence
from typing import Any

from reprobe.chat.types import ChatMessage, ChatReply
from reprobe.models.types import ModelConfig


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
        return self._complete(messages, operation="Chat")

    def count_message_tokens(self, messages: Sequence[ChatMessage]) -> int:
        """Count message content, reserving template overhead at composition."""
        if self._model is None:
            raise ModelError("Model is not loaded; call load() before token counting.")
        try:
            return sum(len(self._model.tokenize(m.content.encode("utf-8"), add_bos=False)) for m in messages)
        except Exception as exc:
            raise ModelError(f"Cannot tokenize review input: {exc}") from exc

    def generate_structured(self, messages: Sequence[ChatMessage],
                            schema: dict[str, Any]) -> ChatReply:
        """Generate against a caller-owned JSON schema, without review rules."""
        return self._complete(messages, schema=schema, operation="Structured")

    def generate_review(self, messages: Sequence[ChatMessage]) -> ChatReply:
        """Compatibility entrypoint for the original review-model capability."""
        from reprobe.review.contract import REVIEW_SCHEMA
        return self._complete(messages, schema=REVIEW_SCHEMA, operation="Review")

    def _complete(self, messages: Sequence[ChatMessage], *, operation: str,
                  schema: dict[str, Any] | None = None) -> ChatReply:
        if self._model is None:
            action = {"Chat": "generating replies", "Review": "reviewing",
                      "Structured": "generating structured replies"}[operation]
            raise ModelError(f"Model is not loaded; call load() before {action}.")
        try:
            options = {} if schema is None else {
                "response_format": {"type": "json_object", "schema": schema},
            }
            response = self._model.create_chat_completion(
                messages=[{"role": m.role, "content": m.content} for m in messages],
                max_tokens=self.config.max_tokens,
                temperature=self.config.temperature,
                stream=False,
                **options,
            )
            return self._parse_reply(response)
        except Exception as exc:
            if operation == "Chat":
                guidance = (
                    "For context limits, restart with shorter history or increase --n-ctx; "
                    "for template errors, check --chat-format and model compatibility."
                )
            elif operation == "Review":
                guidance = (
                    "Increase --n-ctx or reduce --max-files/--max-lines-per-file for context errors; "
                    "check --chat-format for template errors."
                )
            else:
                guidance = "For context limits, shorten input or increase --n-ctx; check --chat-format for template errors."
            raise ModelError(f"{operation} generation failed: {exc}. {guidance}") from exc

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
