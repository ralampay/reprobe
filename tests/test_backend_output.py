"""Noisy Python/native backend output stays out of reports and progress."""
import json
import os
from pathlib import Path
import sys
from types import SimpleNamespace
from unittest.mock import Mock, patch

import pytest

from reprobe.chat.types import ChatMessage
from reprobe.cli import main
from reprobe.models.backend_output import suppress_backend_output
from reprobe.models.llama_cpp import LlamaCppModel, ModelError
from reprobe.models.types import ModelConfig, ModelMetadata


def noise():
    print("PYTHON STDOUT DEBUG")
    print("PYTHON STDERR DEBUG", file=sys.stderr)
    os.write(1, b"NATIVE STDOUT DEBUG\n")
    os.write(2, b"NATIVE STDERR DEBUG\n")


def noisy_backend(failure=None, cleanup_failure=None):
    backend = Mock()
    def complete(**kwargs):
        noise()
        if failure is not None:
            raise failure
        return {"choices": [{"message": {
            "role": "assistant", "content": '{"recommendations":[]}',
        }, "finish_reason": "stop"}]}
    def close():
        noise()
        if cleanup_failure is not None:
            raise cleanup_failure
    def tokenize(*args, **kwargs):
        noise()
        return [1]
    backend.create_chat_completion.side_effect = complete
    backend.close.side_effect = close
    backend.tokenize.side_effect = tokenize
    def load(**kwargs):
        noise()
        return backend
    return backend, SimpleNamespace(Llama=load)


def test_cli_uses_own_progress_and_emits_only_json(tmp_path, capfd):
    model_path = tmp_path / "model.gguf"
    model_path.touch()
    (tmp_path / "main.py").write_text("pass\n")
    backend, module = noisy_backend()
    with patch.dict(sys.modules, {"llama_cpp": module}), patch(
        "reprobe.cli.GgufMetadataReader.read", return_value=ModelMetadata("llama", 4096),
    ):
        assert main(["--output-json", "-", "--model", str(model_path), str(tmp_path)]) == 0
    captured = capfd.readouterr()
    assert "DEBUG" not in captured.out + captured.err
    assert json.loads(captured.out)["status"] == "completed"
    expected = ["Inspecting", "Loading", "Scanning", "Selecting", "Input token", "Generating", "Validating", "Releasing", "Review complete"]
    lines = captured.err.splitlines()
    assert len(lines) == len(expected)
    assert all(line.startswith("reprobe:") and stage in line for line, stage in zip(lines, expected))
    backend.close.assert_called_once()


@pytest.mark.parametrize("failure", [ValueError("generation broke"), KeyboardInterrupt()])
def test_backend_failure_restores_streams_and_keeps_cause(tmp_path, capfd, failure):
    path = tmp_path / "model.gguf"
    path.touch()
    backend, module = noisy_backend(failure)
    stdout, stderr = sys.stdout, sys.stderr
    with patch.dict(sys.modules, {"llama_cpp": module}):
        expected = ModelError if isinstance(failure, ValueError) else KeyboardInterrupt
        with pytest.raises(expected) as raised:
            with LlamaCppModel(ModelConfig(path)) as model:
                model.generate_reply((ChatMessage("user", "hello"),))
    if expected is ModelError:
        assert raised.value.__cause__ is failure
    assert sys.stdout is stdout and sys.stderr is stderr
    print("restored stdout")
    os.write(2, b"restored stderr\n")
    captured = capfd.readouterr()
    assert captured.out == "restored stdout\n"
    assert captured.err == "restored stderr\n"
    backend.close.assert_called_once()


def test_cleanup_failure_is_visible_after_suppression(tmp_path, capfd):
    path = tmp_path / "model.gguf"
    path.touch()
    (tmp_path / "main.py").write_text("pass\n")
    backend, module = noisy_backend(cleanup_failure=OSError("release failed"))
    with patch.dict(sys.modules, {"llama_cpp": module}), patch(
        "reprobe.cli.GgufMetadataReader.read", return_value=ModelMetadata("llama", 4096),
    ):
        assert main(["--output-json", "-", "--model", str(path), str(tmp_path)]) == 1
    captured = capfd.readouterr()
    assert "DEBUG" not in captured.out + captured.err
    assert "release failed" in captured.err
    assert "Review complete" not in captured.err
    assert json.loads(captured.out)["errors"][0]["code"] == "ModelError"


def test_suppression_can_be_nested_and_restores_python_capture(capfd):
    from contextlib import redirect_stdout
    from io import StringIO
    output = StringIO()
    with redirect_stdout(output):
        with suppress_backend_output():
            noise()
            with suppress_backend_output():
                noise()
        print("visible")
    assert output.getvalue() == "visible\n"
    captured = capfd.readouterr()
    assert captured.out == captured.err == ""
