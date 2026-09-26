"""Compatibility exports; implementation lives in :mod:`reprobe.chat.terminal`."""
from reprobe.chat.terminal import (
    ChatModel as ChatModel,
    GenerateChatReply as GenerateChatReply,
    chat as chat,
)

__all__ = ['ChatModel', 'GenerateChatReply', 'chat']
