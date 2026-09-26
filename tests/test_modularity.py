"""Compatibility and independently usable boundaries introduced by refactoring."""
from pathlib import Path
from unittest.mock import Mock, patch

import pytest

from reprobe.chat_types import ChatMessage
from reprobe.cli import main
from reprobe.context_commands import PrepareReviewContext
from reprobe.model import LlamaCppModel, ModelError
from reprobe.model_settings import ResolveModelSettings
from reprobe.model_types import ModelConfig, ModelMetadata
from reprobe.repository import LocalRepository
from reprobe.review_contract import REVIEW_SCHEMA, parse_recommendations
from reprobe.review_types import (
    CodebaseInspection, Omission, ReviewError, SourceExcerpt, SourceSample,
)
from reprobe.source_sampling import SourceSampler


def test_original_type_and_contract_imports_are_preserved():
    from reprobe.chat_types import ModelConfig as OldConfig
    from reprobe.gguf_metadata import ModelMetadata as OldMetadata
    from reprobe.review_prompt import ReviewError as OldError
    from reprobe.review_prompt import REVIEW_SCHEMA as OldSchema
    from reprobe.review_prompt import parse_recommendations as old_parse
    assert OldConfig is ModelConfig
    assert OldMetadata is ModelMetadata
    assert OldError is ReviewError
    assert OldSchema is REVIEW_SCHEMA
    assert old_parse is parse_recommendations


@pytest.mark.parametrize("options", [
    {"n_ctx": False}, {"max_tokens": 0}, {"n_gpu_layers": -2},
    {"temperature": float("nan")}, {"temperature": True}, {"chat_format": " "},
    {"n_ctx": 2048, "max_tokens": 2048},
])
def test_invalid_explicit_settings_fail_before_metadata_access(options):
    reader = Mock()
    with pytest.raises(ValueError):
        ResolveModelSettings(Path("model.gguf"), reader, **options).execute()
    reader.read.assert_not_called()


@pytest.mark.parametrize("arguments", [
    ["--n-gpu-layers", "-2"], ["--temperature", "nan"],
    ["--chat-format", " "], ["--n-ctx", "2048", "--max-tokens", "2048"],
])
def test_cli_configuration_errors_precede_metadata_access(tmp_path, arguments, capsys):
    path = tmp_path / "model.gguf"
    path.touch()
    with patch("reprobe.cli.GgufMetadataReader.read") as read:
        with pytest.raises(SystemExit) as raised:
            main(["--model", str(path), str(tmp_path), *arguments])
    assert raised.value.code == 2
    read.assert_not_called()
    captured = capsys.readouterr()
    assert "usage:" in captured.err
    assert captured.out == ""


def test_resolved_budget_preserves_template_and_output_reservations():
    reader = Mock()
    reader.read.return_value = ModelMetadata("llama", 32768)
    settings = ResolveModelSettings(Path("model.gguf"), reader, max_tokens=3000).execute()
    assert settings.review_input_budget == 8192 - 3000 - 512
    assert settings.config.max_tokens == 3000


def test_sampler_returns_coverage_without_model_or_prompting(tmp_path):
    (tmp_path / "a.py").write_text("first\nsecond\n")
    (tmp_path / "b.py").write_text("pass\n")
    (tmp_path / "c.rb").write_bytes(b"\0")
    repository = LocalRepository()
    inspection = CodebaseInspection(tmp_path, repository.discover(tmp_path), "recognized_source")
    sample = SourceSampler(repository, max_files=2, max_lines=1).sample(inspection)
    assert [e.path for e in sample.excerpts] == ["a.py", "b.py"]
    assert sample.excerpts[0].truncated
    assert sample.omissions == (Omission("c.rb", "binary_or_non_utf8"),)


def test_prepare_context_uses_injected_messages_and_preserves_input():
    inspection = CodebaseInspection(Path("repo"), (), "recognized_source")
    sample = SourceSample((SourceExcerpt("main.py", "python", "one\ntwo\nthree\nfour", False),), ())
    sampler = Mock()
    sampler.sample.return_value = sample
    builder = Mock(side_effect=lambda excerpts: (ChatMessage("user", str(excerpts[0].end_line)),))
    counter = Mock(side_effect=lambda messages: int(messages[0].content))
    result = PrepareReviewContext(inspection, sampler, builder, counter, 2).execute()
    sampler.sample.assert_called_once_with(inspection)
    assert result.excerpts[0].content == "one\ntwo"
    assert result.excerpts[0].truncated
    assert sample.excerpts[0].end_line == 4
    assert not sample.excerpts[0].truncated
    assert [c.args[0][0].content for c in counter.call_args_list] == ["4", "2"]


def test_prepare_context_rejects_empty_sample_before_prompting():
    sampler, builder, counter = Mock(), Mock(), Mock()
    sampler.sample.return_value = SourceSample((), ())
    with pytest.raises(ReviewError, match="No readable"):
        PrepareReviewContext(CodebaseInspection(Path("repo"), (), "no_supported_source"),
                             sampler, builder, counter, 1000).execute()
    builder.assert_not_called()
    counter.assert_not_called()


def test_structured_generation_accepts_caller_schema_without_review_fields():
    schema = {"type": "object", "properties": {"answer": {"type": "integer"}}}
    adapter = LlamaCppModel(ModelConfig(Path("model.gguf")))
    backend = Mock()
    adapter._model = backend
    backend.create_chat_completion.return_value = {"choices": [{
        "message": {"role": "assistant", "content": '{"answer":42}'}, "finish_reason": "stop",
    }]}
    messages = (ChatMessage("user", "Answer"),)
    assert adapter.generate_structured(messages, schema).content == '{"answer":42}'
    assert backend.create_chat_completion.call_args.kwargs["response_format"] == {
        "type": "json_object", "schema": schema,
    }
    backend.create_chat_completion.side_effect = ValueError("backend failed")
    with pytest.raises(ModelError, match="Structured generation failed") as raised:
        adapter.generate_structured(messages, schema)
    assert isinstance(raised.value.__cause__, ValueError)
    adapter.close()
    backend.close.assert_called_once()


@pytest.mark.parametrize("entrypoint", ["generate_reply", "generate_review", "generate_structured"])
def test_completion_entrypoints_share_validation_and_cleanup(entrypoint):
    adapter = LlamaCppModel(ModelConfig(Path("model.gguf")))
    backend = Mock()
    adapter._model = backend
    backend.create_chat_completion.return_value = {"choices": []}
    arguments = ((ChatMessage("user", "hello"),),)
    if entrypoint == "generate_structured":
        arguments += ({"type": "object"},)
    with pytest.raises(ModelError) as raised:
        with adapter:
            getattr(adapter, entrypoint)(*arguments)
    assert isinstance(raised.value.__cause__, ValueError)
    backend.close.assert_called_once()
