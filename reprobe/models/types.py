"""Backend-independent model metadata, settings, and option validation."""
from dataclasses import dataclass
from math import isfinite
from pathlib import Path


def validate_model_options(
    model_path: Path, *, n_ctx: int | None = None,
    max_tokens: int | None = None, n_gpu_layers: int = 0,
    temperature: float = 0.7, chat_format: str | None = None,
) -> None:
    """Validate known options without inventing values for unresolved limits."""
    if not isinstance(model_path, Path):
        raise ValueError("model_path must be a pathlib.Path")
    for name, value in (("n_ctx", n_ctx), ("max_tokens", max_tokens),
                        ("n_gpu_layers", n_gpu_layers)):
        if value is None and name != "n_gpu_layers":
            continue
        if type(value) is not int:
            raise ValueError(f"{name} must be an integer")
    if type(temperature) not in (int, float):
        raise ValueError("temperature must be a number")
    if chat_format is not None and not isinstance(chat_format, str):
        raise ValueError("chat_format must be a string or None")
    if n_ctx is not None and n_ctx <= 0:
        raise ValueError("--n-ctx must be positive")
    if n_gpu_layers < -1:
        raise ValueError("--n-gpu-layers must be -1 or nonnegative")
    if max_tokens is not None and (max_tokens <= 0 or (n_ctx is not None and max_tokens >= n_ctx)):
        raise ValueError("--max-tokens must be positive and smaller than --n-ctx")
    if not isfinite(temperature) or temperature < 0:
        raise ValueError("--temperature must be finite and nonnegative")
    if chat_format is not None and not chat_format.strip():
        raise ValueError("--chat-format must not be empty")


@dataclass(frozen=True)
class ModelConfig:
    model_path: Path
    n_ctx: int = 4096
    n_gpu_layers: int = 0
    max_tokens: int = 512
    temperature: float = 0.7
    chat_format: str | None = None

    def __post_init__(self) -> None:
        # Concrete configuration must never contain unresolved token settings.
        for name in ("n_ctx", "max_tokens"):
            if getattr(self, name) is None:
                raise ValueError(f"{name} must be an integer")
        validate_model_options(
            self.model_path, n_ctx=self.n_ctx, max_tokens=self.max_tokens,
            n_gpu_layers=self.n_gpu_layers, temperature=self.temperature,
            chat_format=self.chat_format,
        )


@dataclass(frozen=True)
class ModelMetadata:
    architecture: str | None = None
    context_length: int | None = None
