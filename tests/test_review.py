import json
from pathlib import Path
from unittest.mock import Mock, patch

import pytest

from reprobe.chat.types import ChatReply
from reprobe.cli import main
from reprobe.models.gguf_metadata import ModelMetadata
from reprobe.models.llama_cpp import ModelError
from reprobe.repositories.local import LocalRepository
from reprobe.review.commands import EvaluateRepository, InspectCodebase
from reprobe.review.prompt import ReviewError, parse_recommendations
from reprobe.review.types import SourceExcerpt
from reprobe.review.source_context import SourceContext


def recommendation(path="main.py", end=1):
    return {"category": "improvement", "priority": "medium", "title": "Validate input",
            "synopsis": 'Validate user input before processing to prevent failures caused by blank values.',
            "evidence": [{"path": path, "start_line": 1, "end_line": end, "explanation": "Unchecked input"}],
            "suggested_changes": ["Reject blank values before processing."],
            "validation_steps": ["Test a blank input."]}


def fake_model(items=()):
    model = Mock()
    model.count_message_tokens.return_value = 100
    model.generate_review.return_value = ChatReply(json.dumps({"recommendations": list(items)}), "stop")
    return model


def test_evaluate_command_without_inference_dependency(tmp_path):
    (tmp_path / "main.py").write_text("value = input()\n")
    repository = LocalRepository()
    model = fake_model([recommendation()])
    result = EvaluateRepository(tmp_path, repository, SourceContext(repository), model, 3000).execute()
    assert result.recommendations[0].id == "R001"
    assert result.recommendations[0].evidence[0].path == "main.py"
    assert result.inspection.languages == ("python",)
    assert "value = input()" in model.generate_review.call_args.args[0][1].content


def test_empty_repository_never_generates(tmp_path):
    repository = LocalRepository()
    model = fake_model()
    result = EvaluateRepository(tmp_path, repository, SourceContext(repository), model, 3000).execute()
    assert not result.inspection.is_codebase
    model.generate_review.assert_not_called()


def test_round_robin_and_coverage(tmp_path):
    for name in ("a.py", "b.py", "c.rb", "d.go", "e.ts", "f.js", "g.cpp"):
        (tmp_path / name).write_text("one\ntwo\nthree\n")
    (tmp_path / "bad.py").write_bytes(b"\xff")
    repository = LocalRepository()
    inspection = InspectCodebase(tmp_path, repository).execute()
    excerpts, omitted = SourceContext(repository, 6, 2).prepare(inspection, lambda _: 100, 1000)
    assert len({e.language for e in excerpts}) == 6
    assert all(e.truncated and e.end_line == 2 for e in excerpts)
    assert {o.path for o in omitted} == {"b.py", "bad.py"}


def test_unreadable_and_binary_omissions(tmp_path):
    (tmp_path / "main.py").write_text("pass\n")
    (tmp_path / "bad.py").write_bytes(b"\0")
    (tmp_path / "unreadable.rb").write_text("puts 1\n")
    repository = LocalRepository()
    original = repository.read_excerpt
    from reprobe.repositories.local import RepositoryError
    def read(root, candidate, limit):
        if candidate.path == "unreadable.rb":
            raise RepositoryError("Cannot read unreadable.rb: permission denied")
        return original(root, candidate, limit)
    with patch.object(repository, "read_excerpt", side_effect=read):
        excerpts, omissions = SourceContext(repository).prepare(InspectCodebase(tmp_path, repository).execute(), lambda _: 1, 100)
    assert [e.path for e in excerpts] == ["main.py"]
    assert any(o.reason == "binary_or_non_utf8" for o in omissions)
    assert any("permission denied" in o.reason for o in omissions)


def test_token_budget_shrinks_excerpts(tmp_path):
    (tmp_path / "main.py").write_text("x = 1\n" * 80)
    repository = LocalRepository()
    count = lambda messages: len(json.loads(messages[1].content)["source_excerpts"][0]["lines"])
    excerpts, _ = SourceContext(repository).prepare(InspectCodebase(tmp_path, repository).execute(), count, 10)
    assert excerpts[0].end_line == 10
    assert excerpts[0].truncated
    with pytest.raises(ReviewError, match="Context is too small"):
        SourceContext(repository).prepare(InspectCodebase(tmp_path, repository).execute(), lambda _: 100, 1)


@pytest.mark.parametrize("content,reason", [
    ("not json", "stop"), ('{"recommendations":[', "length"),
    (json.dumps({"recommendations": [recommendation("unseen.py")]}), "stop"),
    (json.dumps({"recommendations": [recommendation(end=99)]}), "stop"),
    ('{"recommendations":[],"extra":true}', "stop"),
])
def test_rejects_untrustworthy_output(content, reason):
    with pytest.raises(ReviewError):
        parse_recommendations(ChatReply(content, reason), (SourceExcerpt("main.py", "python", "pass", False),))


@pytest.mark.parametrize("failure,exit_code", [(None, 0), (ModelError("generation failed"), 1), (KeyboardInterrupt(), 130)])
def test_cli_emits_one_json_object_and_cleans_up(tmp_path, capsys, failure, exit_code):
    model_path = tmp_path / "model.gguf"
    model_path.touch()
    (tmp_path / "main.py").write_text("pass\n")
    model = fake_model([recommendation()])
    if failure:
        model.generate_review.side_effect = failure
    adapter = Mock()
    adapter.__enter__ = Mock(return_value=model)
    adapter.__exit__ = Mock(return_value=False)
    with patch("reprobe.cli.GgufMetadataReader.read", return_value=ModelMetadata("llama", 8192)), patch("reprobe.cli.LlamaCppModel", return_value=adapter):
        status = main(["--output-json", "-", "--model", str(model_path), str(tmp_path)])
    assert status == exit_code
    report = json.loads(capsys.readouterr().out)
    assert report["status"] == ("error" if failure else "completed")
    assert report["model"]["context_tokens"] == 8192
    assert report["model"]["output_tokens"] == 2048
    adapter.__exit__.assert_called_once()


def test_cli_invalid_repository_still_has_json_error(tmp_path, capsys):
    model = tmp_path / "model.gguf"
    model.touch()
    assert main(["--output-json", "-", "--model", str(model), str(tmp_path / "missing")]) == 1
    report = json.loads(capsys.readouterr().out)
    assert report["errors"][0]["code"] == "RepositoryError"


def test_adapter_requests_schema_and_uses_backend_tokenizer():
    from reprobe.chat.types import ChatMessage, ModelConfig
    from reprobe.models.llama_cpp import LlamaCppModel
    from reprobe.review.prompt import REVIEW_SCHEMA
    model = LlamaCppModel(ModelConfig(Path("m.gguf"), max_tokens=1024))
    backend = Mock()
    backend.tokenize.return_value = [1, 2, 3]
    backend.create_chat_completion.return_value = {"choices": [{
        "message": {"role": "assistant", "content": '{"recommendations":[]}'},
        "finish_reason": "stop",
    }]}
    model._model = backend
    messages = (ChatMessage("system", "review"), ChatMessage("user", "source"))
    assert model.count_message_tokens(messages) == 6
    reply = model.generate_review(messages)
    assert reply.content == '{"recommendations":[]}'
    arguments = backend.create_chat_completion.call_args.kwargs
    assert arguments["response_format"] == {"type": "json_object", "schema": REVIEW_SCHEMA}
    assert arguments["max_tokens"] == 1024
    model.close()
    backend.close.assert_called_once()


def test_cli_metadata_failure_is_json(tmp_path, capsys):
    path = tmp_path / "broken.gguf"
    path.write_bytes(b"bad model")
    assert main(["--output-json", "-", "--model", str(path), str(tmp_path)]) == 1
    report = json.loads(capsys.readouterr().out)
    assert report["status"] == "error"
    assert report["errors"][0]["code"] == "MetadataError"
    assert report["model"] is None


def test_cli_cleanup_failure_discards_recommendations(tmp_path, capsys):
    path = tmp_path / "model.gguf"
    path.touch()
    (tmp_path / "main.py").write_text("pass\n")
    adapter = Mock()
    adapter.__enter__ = Mock(return_value=fake_model([recommendation()]))
    adapter.__exit__ = Mock(side_effect=ModelError("Cannot release model resources"))
    with patch("reprobe.cli.GgufMetadataReader.read", return_value=ModelMetadata("llama", 4096)), patch("reprobe.cli.LlamaCppModel", return_value=adapter):
        assert main(["--output-json", "-", "--model", str(path), str(tmp_path)]) == 1
    report = json.loads(capsys.readouterr().out)
    assert report["status"] == "error"
    assert report["recommendations"] == []
    assert report["coverage"]["reviewed_files"] == 1


def test_large_single_line_is_bounded(tmp_path):
    (tmp_path / "main.py").write_text("x" * 100000)
    repository = LocalRepository()
    inspection = InspectCodebase(tmp_path, repository).execute()
    text, truncated = repository.read_excerpt(tmp_path, inspection.candidates[0], 80)
    assert truncated
    assert len(text.encode()) <= 65536


def test_review_progress_events_and_default_silence(tmp_path, capsys):
    (tmp_path / "main.py").write_text("pass\n")
    repository = LocalRepository()
    events = []
    model = fake_model()
    EvaluateRepository(tmp_path, repository, SourceContext(repository), model, 3000,
                       on_progress=events.append).execute()
    assert events == ["scan", "context", "preflight", "generate", "validate"]
    model.generate_review.side_effect = ModelError("generation failed")
    events.clear()
    with pytest.raises(ModelError):
        EvaluateRepository(tmp_path, repository, SourceContext(repository), model, 3000,
                           on_progress=events.append).execute()
    assert events == ["scan", "context", "preflight", "generate"]
    assert capsys.readouterr().out == ""
