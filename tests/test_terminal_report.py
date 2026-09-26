import json
from pathlib import Path
from unittest.mock import Mock, patch

import pytest

from reprobe.chat.types import ChatReply
from reprobe.cli import main
from reprobe.models.types import ModelMetadata
from reprobe.output.files import ReportWriteError, WriteJsonReport
from reprobe.output.terminal_report import format_report
from reprobe.review.contract import parse_recommendations
from reprobe.review.prompt import review_messages
from reprobe.review.types import ReviewError, SourceExcerpt


def finding():
    return {"category": "fix", "priority": "high", "title": "Reject blank input",
            "evidence": [{"path": "main.py", "start_line": 1, "end_line": 1,
                          "explanation": "Empty input reaches processing without validation."}],
            "suggested_changes": ["Reject an empty value before processing."],
            "validation_steps": ["Test blank input and a valid value."]}


def run_review(tmp_path, extra=(), items=None):
    path = tmp_path / "model.gguf"
    path.touch()
    (tmp_path / "main.py").write_text("value = input()\n")
    model = Mock()
    model.count_message_tokens.return_value = 100
    model.generate_review.return_value = ChatReply(json.dumps({
        "recommendations": [finding()] if items is None else items,
    }), "stop")
    adapter = Mock()
    adapter.__enter__ = Mock(return_value=model)
    adapter.__exit__ = Mock(return_value=False)
    with patch("reprobe.cli.GgufMetadataReader.read", return_value=ModelMetadata("llama", 8192)), patch("reprobe.cli.LlamaCppModel", return_value=adapter):
        return main(["--model", str(path), str(tmp_path), *extra])


def test_readable_default_and_no_implicit_export(tmp_path, capsys):
    assert run_review(tmp_path) == 0
    output = capsys.readouterr().out
    for expected in ("REPROBE / PRIORITY REVIEW", "TOP RECOMMENDATION", "[HIGH] [FIX]",
                     "Reject blank input", "main.py:1", "SUGGESTED CHANGE", "HOW TO VALIDATE"):
        assert expected in output
    assert "\x1b" not in output
    assert not list(tmp_path.glob("*.json"))


def test_export_preserves_structure_and_readable_output(tmp_path, capsys):
    destination = tmp_path / "result.json"
    assert run_review(tmp_path, ["--output-json", str(destination)]) == 0
    captured = capsys.readouterr()
    report = json.loads(destination.read_text())
    assert "TOP RECOMMENDATION" in captured.out
    assert "JSON report saved" in captured.err
    assert len(report["recommendations"]) == 1
    assert report["recommendations"][0]["title"] == "Reject blank input"
    assert report["coverage"]["reviewed_files"] == 1
    assert "\x1b" not in destination.read_text()


def test_json_stdout_mode_remains_machine_readable(tmp_path, capsys):
    assert run_review(tmp_path, ["--output-json", "-"]) == 0
    assert json.loads(capsys.readouterr().out)["recommendations"][0]["priority"] == "high"


def test_empty_finding_is_an_explicit_terminal_state(tmp_path, capsys):
    assert run_review(tmp_path, items=[]) == 0
    assert "NO ACTIONABLE RECOMMENDATION" in capsys.readouterr().out


def test_export_failure_keeps_readable_result_and_returns_failure(tmp_path, capsys):
    assert run_review(tmp_path, ["--output-json", str(tmp_path / "missing" / "result.json")]) == 1
    captured = capsys.readouterr()
    assert "TOP RECOMMENDATION" in captured.out
    assert "Cannot save JSON report" in captured.err


def test_error_report_is_also_exported(tmp_path, capsys):
    model = tmp_path / "bad.gguf"
    model.write_bytes(b"bad model")
    destination = tmp_path / "error.json"
    assert main(["--model", str(model), str(tmp_path), "--output-json", str(destination)]) == 1
    assert json.loads(destination.read_text())["status"] == "error"
    assert "REVIEW FAILED" in capsys.readouterr().out


def test_export_does_not_replace_existing_file_on_failure(tmp_path):
    destination = tmp_path / "report.json"
    destination.write_text('"previous"')
    with patch("reprobe.output.files.os.replace", side_effect=PermissionError("denied")):
        with pytest.raises(ReportWriteError) as error:
            WriteJsonReport(destination, {"status": "completed"}).execute()
    assert error.value.__cause__ is not None
    assert destination.read_text() == '"previous"'
    assert list(tmp_path.iterdir()) == [destination]


def test_successful_export_replaces_existing_report(tmp_path):
    path = tmp_path / "report.json"
    path.write_text('"previous"')
    WriteJsonReport(path, {"status": "completed"}).execute()
    assert json.loads(path.read_text()) == {"status": "completed"}


def test_multiple_findings_are_rejected_and_prompt_prioritizes_globally():
    source = (SourceExcerpt("main.py", "python", "value = input()", False),)
    with pytest.raises(ReviewError, match="array"):
        parse_recommendations(ChatReply(json.dumps({"recommendations": [finding(), finding()]}), "stop"), source)
    prompt = review_messages(source)[0].content
    assert "ONE highest-priority" in prompt
    assert "not one recommendation per file" in prompt
    assert "honest priority" in prompt
    assert "require a concrete failing behavior" in prompt


def test_terminal_escapes_control_characters_and_wraps_long_text(tmp_path, capsys):
    destination = tmp_path / "report.json"
    run_review(tmp_path, ["--output-json", str(destination)])
    capsys.readouterr()
    report = json.loads(destination.read_text())
    report["recommendations"][0]["title"] = "\x1b[31m" + "very long title " * 15
    plain = format_report(report, width=40)
    assert "\x1b" not in plain
    assert all(len(line) <= 40 for line in plain.splitlines())
    assert "\x1b[1;36m" in format_report(report, color=True)


def test_chat_rejects_output_file_and_model_cannot_be_overwritten(tmp_path):
    model = tmp_path / "model.gguf"
    model.touch()
    for args in (["--chat", "--output-json", str(tmp_path / "report.json")],
                 ["--output-json", str(model)]):
        with pytest.raises(SystemExit) as exc:
            main(["--model", str(model), str(tmp_path), *args])
        assert exc.value.code == 2
