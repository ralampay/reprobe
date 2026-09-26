import json
from pathlib import Path
from unittest.mock import Mock, patch

import pytest

from reprobe.chat.types import ChatMessage, ChatReply
from reprobe.cli import main
from reprobe.models.llama_cpp import LlamaCppModel
from reprobe.models.types import ModelConfig, ModelMetadata
from reprobe.output.json_report import review_report
from reprobe.output.terminal_report import format_report
from reprobe.repositories.local import LocalRepository
from reprobe.review.commands import EvaluateRepository
from reprobe.review.contract import REVIEW_SCHEMA, parse_recommendations, review_schema
from reprobe.review.source_context import SourceContext
from reprobe.review.types import ReviewError, SourceExcerpt


def findings(count):
    return [{"category": "fix", "priority": "medium", "title": f"Fix issue {i}",
             "synopsis": f"Address issue {i} to prevent failures.",
             "evidence": [{"path": "main.py", "start_line": 1, "end_line": 1, "explanation": "Unchecked input."}],
             "suggested_changes": [f"Change {i}"], "validation_steps": [f"Test {i}"]}
            for i in range(1, count + 1)]


def test_five_findings_survive_retry_and_render_all_sections(tmp_path):
    (tmp_path / "main.py").write_text("pass")
    repository = LocalRepository()
    model = Mock()
    model.count_message_tokens.return_value = 100
    model.generate_review.side_effect = [ChatReply('{"recommendations":[', "length"),
                                         ChatReply(json.dumps({"recommendations": findings(5)}), "stop")]
    result = EvaluateRepository(tmp_path, repository, SourceContext(repository), model, 3000,
                                query="Look for failures", max_recommendations=5).execute()
    assert len(result.recommendations) == 5
    assert [r.id for r in result.recommendations] == [f"R{i:03}" for i in range(1, 6)]
    for call in model.generate_review.call_args_list:
        assert call.kwargs == {"max_recommendations": 5}
        assert "top 5 distinct" in call.args[0][0].content
        assert '"maxItems":5' in call.args[0][0].content
        assert json.loads(call.args[0][1].content)["review_query"] == "Look for failures"
    assert "at most 5" in model.generate_review.call_args.args[0][0].content
    report = review_report(tmp_path, result=result)
    text = format_report(report)
    assert "ITEM 5 OF 5" in text
    assert text.count("SYNOPSIS") == 5
    assert all(item["synopsis"] in text for item in report["recommendations"])


def test_limit_validation_priority_sorting_and_schema_isolation():
    items = findings(3)
    for item, priority in zip(items, ("low", "high", "medium")):
        item["priority"] = priority
    reply = ChatReply(json.dumps({"recommendations": items}), "stop")
    excerpts = (SourceExcerpt("main.py", "python", "pass", False),)
    with pytest.raises(ReviewError, match="array"):
        parse_recommendations(reply, excerpts, max_recommendations=2)
    result = parse_recommendations(reply, excerpts, max_recommendations=5)
    assert [r.priority for r in result] == ["high", "medium", "low"]
    assert result[0].id == "R001" and result[0].title == "Fix issue 2"
    schema = review_schema(5)
    schema["properties"]["recommendations"]["items"]["properties"]["title"]["maxLength"] = 1
    assert REVIEW_SCHEMA["properties"]["recommendations"]["maxItems"] == 1
    assert review_schema()["properties"]["recommendations"]["items"]["properties"]["title"]["maxLength"] == 120


def test_adapter_passes_selected_limit_to_backend():
    model = LlamaCppModel(ModelConfig(Path("model.gguf")))
    model._model = Mock()
    model._model.create_chat_completion.return_value = {"choices": [{
        "message": {"role": "assistant", "content": '{"recommendations":[]}'}, "finish_reason": "stop"}]}
    model.generate_review((ChatMessage("user", "review"),), max_recommendations=5)
    schema = model._model.create_chat_completion.call_args.kwargs["response_format"]["schema"]
    assert schema["properties"]["recommendations"]["maxItems"] == 5


def test_cli_exports_and_displays_five(tmp_path, capsys):
    path = tmp_path / "model.gguf"
    path.touch()
    (tmp_path / "main.py").write_text("pass")
    model = Mock()
    model.count_message_tokens.return_value = 100
    model.generate_review.return_value = ChatReply(json.dumps({"recommendations": findings(5)}), "stop")
    adapter = Mock()
    adapter.__enter__ = Mock(return_value=model)
    adapter.__exit__ = Mock(return_value=False)
    destination = tmp_path / "report.json"
    with patch("reprobe.cli.GgufMetadataReader.read", return_value=ModelMetadata("llama", 8192)), patch("reprobe.cli.LlamaCppModel", return_value=adapter):
        assert main(["--model", str(path), str(tmp_path), "-n", "5", "--output-json", str(destination)]) == 0
    assert len(json.loads(destination.read_text())["recommendations"]) == 5
    assert "ITEM 5 OF 5" in capsys.readouterr().out


@pytest.mark.parametrize("arguments", [["-n", "0"], ["-n", "-1"], ["-n", "five"], ["-n", "1", "--chat"]])
def test_invalid_cli_counts_fail_before_loading(tmp_path, arguments):
    path = tmp_path / "model.gguf"
    path.touch()
    with patch("reprobe.cli.GgufMetadataReader.read") as read:
        with pytest.raises(SystemExit) as error:
            main(["--model", str(path), str(tmp_path), *arguments])
    assert error.value.code == 2
    read.assert_not_called()


@pytest.mark.parametrize("count", [0, -1, True, 1.5])
def test_python_command_rejects_invalid_count(count):
    with pytest.raises(ValueError, match="positive integer"):
        EvaluateRepository(Path("repo"), Mock(), Mock(), Mock(), 3000, max_recommendations=count)
