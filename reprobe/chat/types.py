"""Backend-independent values exchanged by chat components."""

from dataclasses import dataclass
from typing import Literal

from reprobe.models.types import TokenUsage

# Compatibility export: model configuration is shared by chat and review.
from reprobe.models.types import ModelConfig as ModelConfig


@dataclass(frozen=True)
class ChatMessage:
    role: Literal["system", "user", "assistant"]
    content: str


@dataclass(frozen=True)
class ChatReply:
    content: str
    finish_reason: str
    usage: TokenUsage | None = None


@dataclass(frozen=True)
class ChatTurn:
    reply: ChatReply
    history: tuple[ChatMessage, ...]
