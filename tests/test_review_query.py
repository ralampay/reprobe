import json
from unittest.mock import Mock, patch

import pytest

from reprobe.chat.types import ChatReply
from reprobe.cli import main
from reprobe.models.types import ModelMetadata
from reprobe.repositories.local import LocalRepository
from reprobe.review.commands import EvaluateRepository
from reprobe.review.prompt import review_messages
from reprobe.review.source_context import SourceContext
from reprobe.review.types import ReviewError


def test_query_is_retained_on_retry_and_counted_during_fitting(tmp_path):
    (tmp_path / "main.py").write_text("x = 1\n" * 8)
    repository = LocalRepository()
    model = Mock()
    query = "look for inefficiencies or antipatterns"
    def count(messages):
        request = json.loads(messages[1].content)
        assert request["review_query"] == query
        extra = 2 if "This is a retry" in messages[0].content else 0
        return 10 + extra + sum(len(e["lines"]) for e in request["source_excerpts"])
    model.count_message_tokens.side_effect = count
    model.generate_review.side_effect = [
        ChatReply('{"recommendations":[', "length"),
        ChatReply('{"recommendations":[]}', "stop"),
    ]
    result = EvaluateRepository(tmp_path, repository, SourceContext(repository),
                                model, 14, query=query).execute()
    calls = model.generate_review.call_args_list
    assert len(calls) == 2
    assert all(count(call.args[0]) <= 14 for call in calls)
    assert result.excerpts[0].end_line == 2
    assert result.generation_attempts == 2
    assert "Do not substitute an unrelated" in calls[0].args[0][0].content


def test_query_that_cannot_fit_fails_without_inference(tmp_path):
    (tmp_path / "main.py").write_text("pass")
    repository = LocalRepository()
    model = Mock()
    model.count_message_tokens.side_effect = lambda messages: len(
        json.loads(messages[1].content)["review_query"])
    with pytest.raises(ReviewError, match="Context is too small"):
        EvaluateRepository(tmp_path, repository, SourceContext(repository), model,
                           20, query="x" * 21).execute()
    model.generate_review.assert_not_called()


def test_no_query_keeps_default_prompt():
    assert review_messages(()) == review_messages((), query=None)
    assert "review_query" not in json.loads(review_messages(())[1].content)
    assert "Focus the review on that request" not in review_messages(())[0].content


def test_cli_passes_query_to_review(tmp_path, capsys):
    path = tmp_path / "model.gguf"
    path.touch()
    (tmp_path / "main.py").write_text("pass")
    model = Mock()
    model.count_message_tokens.return_value = 100
    model.generate_review.return_value = ChatReply('{"recommendations":[]}', "stop")
    adapter = Mock()
    adapter.__enter__ = Mock(return_value=model)
    adapter.__exit__ = Mock(return_value=False)
    with patch("reprobe.cli.GgufMetadataReader.read", return_value=ModelMetadata("llama", 8192)), patch("reprobe.cli.LlamaCppModel", return_value=adapter):
        assert main(["--model", str(path), str(tmp_path), "--query", "  Find inefficiencies  ",
                     "--output-json", "-"]) == 0
    assert json.loads(model.generate_review.call_args.args[0][1].content)["review_query"] == "Find inefficiencies"
    assert json.loads(capsys.readouterr().out)["status"] == "completed"


@pytest.mark.parametrize("args", [["--query", " "], ["--query", "test", "--chat"], ["--query"]])
def test_invalid_cli_query_fails_before_model_access(tmp_path, args, capsys):
    path = tmp_path / "model.gguf"
    path.touch()
    with patch("reprobe.cli.GgufMetadataReader.read") as read:
        with pytest.raises(SystemExit) as error:
            main(["--model", str(path), str(tmp_path), *args])
    assert error.value.code == 2
    read.assert_not_called()
    assert "--query" in capsys.readouterr().err


def test_python_command_rejects_blank_query_before_repository_access(tmp_path):
    repository = Mock()
    with pytest.raises(ReviewError, match="query must not be empty"):
        EvaluateRepository(tmp_path, repository, Mock(), Mock(), 3000, query="  ")
    repository.resolve_root.assert_not_called()
