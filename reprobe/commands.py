"""Reusable chat workflow commands without terminal or backend dependencies."""

from collections.abc import Sequence
from typing import Protocol

from reprobe.chat_types import ChatMessage, ChatReply, ChatTurn


class ChatModel(Protocol):
    """The single capability required by a chat turn, including test fakes."""

    def generate_reply(self, messages: Sequence[ChatMessage]) -> ChatReply: ...


class GenerateChatReply:
    def __init__(
        self, model: ChatModel, history: Sequence[ChatMessage], user_input: str
    ) -> None:
        self._model = model
        self._history = tuple(history)
        self._user_input = user_input

    def execute(self) -> ChatTurn:
        if not self._user_input.strip():
            raise ValueError("Chat input must not be blank")
        messages = self._history + (ChatMessage("user", self._user_input),)
        reply = self._model.generate_reply(messages)
        return ChatTurn(reply, messages + (ChatMessage("assistant", reply.content),))
