"""Regression checks for prompt size and bounded tokenizer reuse."""
import json
from pathlib import Path
from unittest.mock import Mock

import pytest

from reprobe.chat.types import ChatMessage
from reprobe.models.llama_cpp import LlamaCppModel, ModelError
from reprobe.models.types import ModelConfig
from reprobe.review.prompt import review_messages
from reprobe.review.types import SourceExcerpt


def adapter():
    model = LlamaCppModel(ModelConfig(Path("unused.gguf")))
    backend = Mock()
    backend.tokenize.side_effect = lambda content, **_: list(content)
    model._model = backend
    return model, backend


def test_only_changed_messages_are_retokenized():
    model, backend = adapter()
    system = ChatMessage("system", "instructions")
    first = (system, ChatMessage("user", "source"))
    assert model.count_message_tokens(first) == 18
    assert model.count_message_tokens(first) == 18
    assert model.count_message_tokens((system, ChatMessage("user", "short"))) == 17
    assert backend.tokenize.call_count == 3
    model.close()
    model._model = backend  # Simulate loading a fresh tokenizer.
    assert model.count_message_tokens(first) == 18
    assert backend.tokenize.call_count == 5


def test_cache_evicts_old_messages_and_does_not_retain_large_inputs():
    model, backend = adapter()
    for i in range(9):
        model.count_message_tokens((ChatMessage("user", str(i)),))
    model.count_message_tokens((ChatMessage("user", "0"),))
    assert backend.tokenize.call_count == 10
    large = (ChatMessage("user", "x" * 65537),)
    model.count_message_tokens(large)
    model.count_message_tokens(large)
    assert backend.tokenize.call_count == 12


def test_tokenization_failure_is_not_cached():
    model, backend = adapter()
    backend.tokenize.side_effect = [ValueError("tokenizer failed"), [1, 2]]
    messages = (ChatMessage("user", "source"),)
    with pytest.raises(ModelError, match="Cannot tokenize"):
        model.count_message_tokens(messages)
    assert model.count_message_tokens(messages) == 2
    assert backend.tokenize.call_count == 2


def test_compact_source_lines_preserve_exact_text_and_locations():
    source = 'print("hello")\n\n    # café \\ path'
    messages = review_messages((SourceExcerpt("src/a.py", "python", source, False),))
    excerpt = json.loads(messages[1].content)["source_excerpts"][0]
    assert excerpt["lines"] == [[1, 'print("hello")'], [2, ""], [3, "    # café \\ path"]]
    assert excerpt["start_line"] == 1
    assert excerpt["end_line"] == 3
    assert "[line_number, source_text]" in messages[0].content
