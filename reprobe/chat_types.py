"""Backend-independent values exchanged by chat components."""

from dataclasses import dataclass
from math import isfinite
from pathlib import Path
from typing import Literal


@dataclass(frozen=True)
class ChatMessage:
    role: Literal["system", "user", "assistant"]
    content: str


@dataclass(frozen=True)
class ChatReply:
    content: str
    finish_reason: str


@dataclass(frozen=True)
class ChatTurn:
    reply: ChatReply
    history: tuple[ChatMessage, ...]


@dataclass(frozen=True)
class ModelConfig:
    model_path: Path
    n_ctx: int = 4096
    n_gpu_layers: int = 0
    max_tokens: int = 512
    temperature: float = 0.7
    chat_format: str | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.model_path, Path):
            raise ValueError("model_path must be a pathlib.Path")
        for name in ("n_ctx", "n_gpu_layers", "max_tokens"):
            if type(getattr(self, name)) is not int:
                raise ValueError(f"{name} must be an integer")
        if type(self.temperature) not in (int, float):
            raise ValueError("temperature must be a number")
        if self.chat_format is not None and not isinstance(self.chat_format, str):
            raise ValueError("chat_format must be a string or None")
        if self.n_ctx <= 0:
            raise ValueError("--n-ctx must be positive")
        if self.n_gpu_layers < -1:
            raise ValueError("--n-gpu-layers must be -1 or nonnegative")
        if not 0 < self.max_tokens < self.n_ctx:
            raise ValueError("--max-tokens must be positive and smaller than --n-ctx")
        if not isfinite(self.temperature) or self.temperature < 0:
            raise ValueError("--temperature must be finite and nonnegative")
        if self.chat_format is not None and not self.chat_format.strip():
            raise ValueError("--chat-format must not be empty")
