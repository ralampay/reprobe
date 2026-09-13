"""Regression coverage for backend validation and lifecycle failures."""

import contextlib
import io
from pathlib import Path
import sys
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

from reprobe.chat_types import ChatMessage, ModelConfig
from reprobe.cli import main
from reprobe.commands import GenerateChatReply
from reprobe.model import LlamaCppModel, ModelError


def response(content="answer", reason="stop", role="assistant"):
    return {"choices": [{
        "message": {"role": role, "content": content},
        "finish_reason": reason,
    }]}


class ModelErrorTests(unittest.TestCase):
    def setUp(self):
        self.backend = Mock()
        self.constructor = Mock(return_value=self.backend)
        self.adapter = LlamaCppModel(ModelConfig(Path("model.gguf")))
        for patcher in (
            patch.object(Path, "is_file", return_value=True),
            patch.dict(sys.modules, {
                "llama_cpp": SimpleNamespace(Llama=self.constructor),
            }),
        ):
            patcher.start()
            self.addCleanup(patcher.stop)

    def test_invalid_replies_do_not_commit_a_turn(self):
        invalid = [None, {}, {"choices": []}, {"choices": [None]},
                   response(None), response(""), response("  \n"),
                   response(reason=None), response(reason="tool_calls"),
                   response(role="user")]
        history = [ChatMessage("user", "previous")]
        with self.adapter:
            for value in invalid:
                with self.subTest(response=value):
                    self.backend.create_chat_completion.return_value = value
                    with self.assertRaises(ModelError) as raised:
                        GenerateChatReply(self.adapter, history, "next").execute()
                    self.assertIsInstance(raised.exception.__cause__, ValueError)
                    self.assertEqual(history, [ChatMessage("user", "previous")])
        self.backend.close.assert_called_once()

    def test_length_reply_preserves_text(self):
        self.backend.create_chat_completion.return_value = response(" answer\n", "length")
        with self.adapter:
            turn = GenerateChatReply(self.adapter, [], "hello").execute()
        self.assertEqual(turn.reply.content, " answer\n")
        self.assertEqual(turn.reply.finish_reason, "length")

    def test_failed_close_can_be_retried(self):
        self.adapter.load()
        original = OSError("release failed")
        self.backend.close.side_effect = [original, None]
        with self.assertRaises(ModelError) as raised:
            self.adapter.close()
        self.assertIs(raised.exception.__cause__, original)
        self.adapter.close()
        self.adapter.close()
        self.assertEqual(self.backend.close.call_count, 2)
        with self.assertRaisesRegex(ModelError, "not loaded"):
            self.adapter.generate_reply([])

    def test_cleanup_preserves_original_exception_chain(self):
        original = ValueError("context exhausted")
        self.backend.create_chat_completion.side_effect = original
        self.backend.close.side_effect = OSError("release failed")
        with self.assertRaises(ModelError) as raised:
            with self.adapter:
                self.adapter.generate_reply([ChatMessage("user", "hello")])
        self.assertIn("context exhausted", str(raised.exception))
        self.assertIn("release failed", str(raised.exception))
        self.assertIs(raised.exception.__cause__.__cause__, original)

    def test_path_errors_are_translated_before_import(self):
        original = PermissionError("access denied")
        with patch.object(Path, "is_file", side_effect=original):
            with self.assertRaisesRegex(ModelError, "Cannot access model path") as raised:
                self.adapter.load()
        self.assertIs(raised.exception.__cause__, original)
        self.constructor.assert_not_called()

    def test_cli_reports_cleanup_failure(self):
        self.backend.close.side_effect = OSError("release failed")
        with patch("reprobe.cli.chat", side_effect=KeyboardInterrupt()):
            with contextlib.redirect_stdout(io.StringIO()):
                with contextlib.redirect_stderr(io.StringIO()) as stderr:
                    status = main(["--model", "model.gguf", "repo"])
        self.assertEqual(status, 1)
        self.assertIn("KeyboardInterrupt", stderr.getvalue())
        self.assertIn("release failed", stderr.getvalue())


class ConfigTests(unittest.TestCase):
    def test_invalid_python_configuration(self):
        cases = [
            {"model_path": "model.gguf"}, {"n_ctx": 1.5}, {"n_ctx": True},
            {"n_ctx": 0}, {"n_gpu_layers": -2}, {"n_gpu_layers": False},
            {"max_tokens": 0}, {"max_tokens": 4096}, {"max_tokens": 2.5},
            {"temperature": "0.7"}, {"temperature": True},
            {"temperature": float("inf")}, {"temperature": float("nan")},
            {"temperature": -0.1}, {"chat_format": 123}, {"chat_format": " "},
        ]
        for values in cases:
            with self.subTest(values=values), self.assertRaises(ValueError):
                ModelConfig(**{"model_path": Path("model.gguf"), **values})

    def test_explicit_zero_temperature_and_gpu_all(self):
        config = ModelConfig(Path("model.gguf"), temperature=0, n_gpu_layers=-1)
        self.assertEqual(config.temperature, 0)
        self.assertEqual(config.n_gpu_layers, -1)
