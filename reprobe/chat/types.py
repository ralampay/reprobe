"""Backend-independent values exchanged by chat components."""

from dataclasses import dataclass
from typing import Literal

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


@dataclass(frozen=True)
class ChatTurn:
    reply: ChatReply
    history: tuple[ChatMessage, ...]
