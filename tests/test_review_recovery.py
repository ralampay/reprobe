import json
from unittest.mock import Mock, patch

import pytest

from reprobe.chat.types import ChatReply
from reprobe.cli import main
from reprobe.models.types import ModelMetadata
from reprobe.repositories.local import LocalRepository
from reprobe.review.commands import EvaluateRepository
from reprobe.review.contract import parse_recommendations
from reprobe.review.source_context import SourceContext
from reprobe.review.types import ReviewError


def make_command(tmp_path, replies, budget=3000):
    (tmp_path / "main.py").write_text("pass\n")
    model = Mock()
    model.count_message_tokens.return_value = 100
    model.generate_review.side_effect = replies
    repository = LocalRepository()
    events = []
    command = EvaluateRepository(tmp_path, repository, SourceContext(repository), model,
                                 budget, on_progress=events.append)
    return command, model, events


def test_complete_json_at_output_limit_is_usable():
    assert parse_recommendations(ChatReply('{"recommendations":[]}', "length"), ()) == ()


def test_truncated_answer_retries_once_with_compact_prompt(tmp_path):
    command, model, events = make_command(tmp_path, [
        ChatReply('{"recommendations":[', "length"),
        ChatReply('{"recommendations":[]}', "stop"),
    ])
    result = command.execute()
    assert result.generation_attempts == 2
    assert result.input_tokens == 100 and result.input_budget == 3000
    assert model.generate_review.call_count == 2
    assert "at most ONE" in model.generate_review.call_args.args[0][0].content
    assert events.count("retry") == 1
    assert result.inspection.languages == ("python",)
    assert result.excerpts[0].path == "main.py"


def test_repeated_truncation_keeps_coverage_and_stops(tmp_path):
    command, model, _ = make_command(tmp_path, [ChatReply('{"recommendations":[', "length")] * 2)
    with pytest.raises(ReviewError, match="both the initial review and one concise retry") as error:
        command.execute()
    assert error.value.__cause__ is not None
    assert command.result.generation_attempts == 2
    assert command.result.excerpts[0].path == "main.py"
    assert command.result.recommendations == ()
    assert model.generate_review.call_count == 2


def test_preflight_failure_preserves_discovery_without_generating(tmp_path):
    command, model, _ = make_command(tmp_path, [], budget=1)
    with pytest.raises(ReviewError, match="Context is too small"):
        command.execute()
    assert command.result.inspection.languages == ("python",)
    assert len(command.result.inspection.candidates) == 1
    assert command.result.generation_attempts == 0
    model.generate_review.assert_not_called()


def test_invalid_evidence_or_schema_is_not_retried(tmp_path):
    command, model, events = make_command(tmp_path, [ChatReply('{"oops":[]}', "stop")])
    with pytest.raises(ReviewError, match="Invalid structured review"):
        command.execute()
    assert model.generate_review.call_count == 1
    assert "retry" not in events


def test_cli_failure_preserves_last_attempt_and_explicit_limits(tmp_path, capsys):
    path = tmp_path / "model.gguf"
    path.touch()
    (tmp_path / "main.py").write_text("pass\n")
    model = Mock()
    model.count_message_tokens.return_value = 100
    model.generate_review.return_value = ChatReply('{"recommendations":[', "length")
    adapter = Mock()
    adapter.__enter__ = Mock(return_value=model)
    adapter.__exit__ = Mock(return_value=False)
    with patch("reprobe.cli.GgufMetadataReader.read", return_value=ModelMetadata("qwen35", 262144)), patch("reprobe.cli.LlamaCppModel", return_value=adapter) as factory:
        assert main(["--output-json", "-", "--model", str(path), str(tmp_path), "--n-ctx", "4096", "--max-tokens", "256"]) == 1
    report = json.loads(capsys.readouterr().out)
    assert report["languages"] == ["python"]
    assert report["coverage"]["discovered_files"] == 1
    assert report["coverage"]["reviewed_files"] == 1
    assert report["coverage"]["generation_attempts"] == 2
    assert report["model"]["output_tokens"] == 256
    assert report["model"]["context_tokens"] == 4096
    factory.assert_called_once()
    adapter.__exit__.assert_called_once()
