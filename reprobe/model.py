"""Compatibility exports; implementation lives in :mod:`reprobe.models.llama_cpp`."""
from reprobe.models.llama_cpp import (
    ChatMessage as ChatMessage,
    ChatReply as ChatReply,
    LlamaCppModel as LlamaCppModel,
    ModelConfig as ModelConfig,
    ModelError as ModelError,
)

__all__ = ['ChatMessage', 'ChatReply', 'LlamaCppModel', 'ModelConfig', 'ModelError']
