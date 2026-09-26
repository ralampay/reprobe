"""Explicit model-aware configuration policy, independent of inference."""
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

from reprobe.models.types import ModelConfig, ModelMetadata, validate_model_options


REVIEW_TEMPLATE_RESERVATION = 512


class MetadataReader(Protocol):
    def read(self, path: Path) -> ModelMetadata: ...


@dataclass(frozen=True)
class ResolvedModelSettings:
    config: ModelConfig
    architecture: str | None
    model_context_length: int | None
    context_source: str
    output_source: str
    diagnostics: tuple[str, ...]

    @property
    def review_input_budget(self) -> int:
        return self.config.n_ctx - self.config.max_tokens - REVIEW_TEMPLATE_RESERVATION


class ResolveModelSettings:
    def __init__(self, model_path: Path, reader: MetadataReader, *,
                 n_ctx: int | None = None, max_tokens: int | None = None,
                 n_gpu_layers: int = 0, temperature: float = 0.2,
                 chat_format: str | None = None) -> None:
        self._path = model_path
        self._reader = reader
        self._context = n_ctx
        self._output = max_tokens
        self._options = dict(n_gpu_layers=n_gpu_layers, temperature=temperature, chat_format=chat_format)

    def execute(self) -> ResolvedModelSettings:
        validate_model_options(
            self._path, n_ctx=self._context, max_tokens=self._output, **self._options,
        )
        metadata = self._reader.read(self._path)
        context = self._context if self._context is not None else min(metadata.context_length or 4096, 8192)
        output = self._output if self._output is not None else min(2048, context // 4)
        config = ModelConfig(self._path, n_ctx=context, max_tokens=output, **self._options)
        diagnostics = []
        if metadata.context_length is None and self._context is None:
            diagnostics.append("GGUF context metadata absent; using fallback context of 4096 tokens.")
        if metadata.context_length and context > metadata.context_length:
            diagnostics.append("Explicit context exceeds the model training context; backend/model support is required.")
        return ResolvedModelSettings(
            config, metadata.architecture, metadata.context_length,
            "explicit" if self._context is not None else ("model_metadata_capped" if metadata.context_length else "fallback"),
            "explicit" if self._output is not None else "context_policy", tuple(diagnostics),
        )
