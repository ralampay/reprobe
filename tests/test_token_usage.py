import json
from pathlib import Path
from unittest.mock import Mock, patch

import pytest

from reprobe.chat.types import ChatReply
from reprobe.cli import main
from reprobe.models.llama_cpp import LlamaCppModel, ModelError
from reprobe.models.types import ModelMetadata, TokenUsage
from reprobe.output.json_report import review_report
from reprobe.output.terminal_report import format_report
from reprobe.repositories.local import LocalRepository
from reprobe.review.commands import EvaluateRepository
from reprobe.review.source_context import SourceContext
from reprobe.review.types import ReviewError


def response(usage):
    return {"choices": [{"message": {"role": "assistant", "content": '{"recommendations":[]}'},
                         "finish_reason": "stop"}], "usage": usage}


def command(root, replies):
    (root / "main.py").write_text("pass\n")
    repository = LocalRepository()
    model = Mock()
    model.count_message_tokens.return_value = 100
    model.generate_review.side_effect = replies
    return EvaluateRepository(root, repository, SourceContext(repository), model, 3000)


def test_adapter_translates_actual_backend_usage_without_retokenizing():
    reply = LlamaCppModel._parse_reply(response({"prompt_tokens": 120, "completion_tokens": 30, "total_tokens": 150}))
    assert reply.usage == TokenUsage(120, 30)
    assert reply.usage.total_tokens == 150
    assert LlamaCppModel._parse_reply(response(None)).usage is None


@pytest.mark.parametrize("usage", [[], {}, {"prompt_tokens": True, "completion_tokens": 1},
                                   {"prompt_tokens": 5, "completion_tokens": -1}])
def test_adapter_rejects_invalid_usage(usage):
    with pytest.raises(ValueError, match="token"):
        LlamaCppModel._parse_reply(response(usage))


def test_retry_totals_include_both_generations(tmp_path):
    review = command(tmp_path, [ChatReply('{"recommendations":[', "length", TokenUsage(120, 40)),
                                ChatReply('{"recommendations":[]}', "stop", TokenUsage(130, 20))])
    result = review.execute()
    report = review_report(tmp_path, result=result)
    assert report["token_usage"] == {
        "input_tokens": 250, "output_tokens": 60, "total_tokens": 310, "complete": True,
        "attempts": [{"input_tokens": 120, "output_tokens": 40, "total_tokens": 160},
                     {"input_tokens": 130, "output_tokens": 20, "total_tokens": 150}],
    }
    text = format_report(report)
    assert "310 total (250 input + 60 output; all attempts)" in text
    assert "Preflight" in text and "100 / 3000" in text


def test_validation_failure_retains_usage(tmp_path):
    review = command(tmp_path, [ChatReply('{"invalid":true}', "stop", TokenUsage(120, 20))])
    with pytest.raises(ReviewError) as error:
        review.execute()
    report = review_report(tmp_path, result=review.result, error=error.value)
    assert report["token_usage"]["total_tokens"] == 140
    assert report["status"] == "error"


def test_failed_retry_has_unknown_total_and_preserves_known_attempt(tmp_path):
    review = command(tmp_path, [ChatReply('{"recommendations":[', "length", TokenUsage(120, 40)),
                                ModelError("inference failed")])
    with pytest.raises(ModelError):
        review.execute()
    usage = review_report(tmp_path, result=review.result)["token_usage"]
    assert usage["total_tokens"] is None
    assert not usage["complete"]
    assert usage["attempts"][0]["total_tokens"] == 160
    assert usage["attempts"][1] is None


def test_missing_usage_is_not_estimated_from_preflight(tmp_path):
    result = command(tmp_path, [ChatReply('{"recommendations":[]}', "stop")]).execute()
    report = review_report(tmp_path, result=result)
    assert report["token_usage"]["total_tokens"] is None
    assert "Unavailable" in format_report(report)


def test_no_inference_has_zero_usage():
    assert review_report(Path("repo"))["token_usage"] == {
        "input_tokens": 0, "output_tokens": 0, "total_tokens": 0,
        "complete": True, "attempts": [],
    }


def test_cli_exports_actual_usage(tmp_path, capsys):
    path = tmp_path / "model.gguf"
    path.touch()
    (tmp_path / "main.py").write_text("pass")
    model = Mock()
    model.count_message_tokens.return_value = 100
    model.generate_review.return_value = ChatReply('{"recommendations":[]}', "stop", TokenUsage(124, 6))
    adapter = Mock()
    adapter.__enter__ = Mock(return_value=model)
    adapter.__exit__ = Mock(return_value=False)
    destination = tmp_path / "report.json"
    with patch("reprobe.cli.GgufMetadataReader.read", return_value=ModelMetadata("llama", 8192)), patch("reprobe.cli.LlamaCppModel", return_value=adapter):
        assert main(["--model", str(path), str(tmp_path), "--output-json", str(destination)]) == 0
    assert json.loads(destination.read_text())["token_usage"]["total_tokens"] == 130
    assert "130 total (124 input + 6 output; all attempts)" in capsys.readouterr().out


def resolved_settings(training_context=262144, configured=8192):
    from reprobe.models.settings import ResolveModelSettings
    reader = Mock()
    reader.read.return_value = ModelMetadata("qwen35", training_context)
    return ResolveModelSettings(Path("model.gguf"), reader, n_ctx=configured).execute()


def test_context_usage_distinguishes_model_max_and_configured_window(tmp_path):
    result = command(tmp_path, [ChatReply('{"recommendations":[]}', "stop", TokenUsage(711, 207))]).execute()
    report = review_report(tmp_path, resolved_settings(), result)
    assert report["context_usage"] == {
        "configured_context_tokens": 8192, "model_context_tokens": 262144,
        "attempts": [{"attempt": 1, "used_tokens": 918,
                      "configured_context_percent": 11.21, "model_context_percent": 0.35,
                      "remaining_context_tokens": 7274}],
    }
    text = format_report(report)
    assert "262,144 tokens (GGUF training context)" in text
    assert "8,192 tokens configured; 2,048 output token limit" in text
    assert "918 / 8,192 tokens" in text
    assert "11.21% configured" in text
    assert "0.35% model max" in text


def test_retry_context_percentages_are_not_cumulative(tmp_path):
    result = command(tmp_path, [ChatReply('{"recommendations":[', "length", TokenUsage(5000, 1000)),
                                ChatReply('{"recommendations":[]}', "stop", TokenUsage(5000, 500))]).execute()
    report = review_report(tmp_path, resolved_settings(), result)
    assert report["token_usage"]["total_tokens"] == 11500
    attempts = report["context_usage"]["attempts"]
    assert [a["used_tokens"] for a in attempts] == [6000, 5500]
    assert [a["configured_context_percent"] for a in attempts] == [73.24, 67.14]
    text = format_report(report)
    assert "Attempt 1: 6,000 / 8,192 tokens" in text
    assert "Attempt 2: 5,500 / 8,192 tokens" in text


def test_unknown_model_max_does_not_use_fallback_as_maximum(tmp_path):
    result = command(tmp_path, [ChatReply('{"recommendations":[]}', "stop", TokenUsage(900, 100))]).execute()
    report = review_report(tmp_path, resolved_settings(None, 4096), result)
    usage = report["context_usage"]
    assert usage["model_context_tokens"] is None
    assert usage["attempts"][0]["model_context_percent"] is None
    assert usage["attempts"][0]["configured_context_percent"] == 24.41
    assert "Unknown (GGUF context metadata absent)" in format_report(report)


def test_unknown_attempt_usage_has_no_context_percentage(tmp_path):
    result = command(tmp_path, [ChatReply('{"recommendations":[]}', "stop")]).execute()
    report = review_report(tmp_path, resolved_settings(), result)
    assert report["context_usage"]["attempts"] == [{
        "attempt": 1, "used_tokens": None, "configured_context_percent": None,
        "model_context_percent": None, "remaining_context_tokens": None,
    }]
    assert "Attempt 1: unavailable" in format_report(report)


def test_context_usage_without_settings_or_generation():
    report = review_report(Path("repo"))
    assert report["context_usage"] == {
        "configured_context_tokens": None, "model_context_tokens": None, "attempts": [],
    }
    assert "0 tokens (no inference attempts)" in format_report(report)
