import contextlib
import io
from pathlib import Path
import subprocess
import sys
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

from reprobe.chat_types import ChatMessage, ChatReply, ModelConfig
from reprobe.cli import main
from reprobe.commands import GenerateChatReply
from reprobe.model import LlamaCppModel, ModelError
from reprobe.terminal import chat


class ChatTests(unittest.TestCase):
    def test_turns_preserve_history_without_mutation(self):
        model = Mock()
        model.generate_reply.return_value = ChatReply("hello", "stop")
        history = [ChatMessage("user", "earlier"), ChatMessage("assistant", "reply")]
        result = GenerateChatReply(model, history, "next").execute()
        self.assertEqual(len(history), 2)
        self.assertEqual(result.history, tuple(history) + (
            ChatMessage("user", "next"), ChatMessage("assistant", "hello")))
        model.generate_reply.assert_called_once_with(tuple(history) + (ChatMessage("user", "next"),))
        model.generate_reply.side_effect = ModelError("failed")
        with self.assertRaises(ModelError):
            GenerateChatReply(model, history, "fail").execute()
        self.assertEqual(len(history), 2)

    def test_blank_command_input(self):
        model = Mock()
        with self.assertRaises(ValueError):
            GenerateChatReply(model, [], "  ").execute()
        model.generate_reply.assert_not_called()

    def test_terminal_clear_blank_and_exit(self):
        model = Mock()
        model.generate_reply.return_value = ChatReply("answer", "length")
        with patch("builtins.input", side_effect=[" ", "one", "two", "/clear", "three", "/exit"]), contextlib.redirect_stdout(io.StringIO()) as output:
            chat(model)
        calls = model.generate_reply.call_args_list
        self.assertEqual([len(call.args[0]) for call in calls], [1, 3, 1])
        self.assertIn("token limit", output.getvalue())

    def test_eof_and_quit(self):
        for end in [EOFError(), "/quit"]:
            with patch("builtins.input", side_effect=[end]), contextlib.redirect_stdout(io.StringIO()):
                chat(Mock())

    def test_cli_invalid_arguments(self):
        for args in [[], ["--chat"], ["repo", "--chat", "--model", "m.gguf"],
                     ["repo", "--model", "m.gguf"], ["repo", "--temperature", "0"],
                     ["--chat", "--model", "m.gguf", "--n-ctx", "0"],
                     ["--chat", "--model", "m.gguf", "--temperature", "nan"]]:
            with self.subTest(args=args), contextlib.redirect_stderr(io.StringIO()), self.assertRaises(SystemExit) as raised:
                main(args)
            self.assertEqual(raised.exception.code, 2)

    def test_cli_cleanup_on_all_chat_exits(self):
        for failure, status in [(None, 0), (KeyboardInterrupt(), 130), (ModelError("broken"), 1)]:
            backend = Mock()
            with patch.object(Path, "is_file", return_value=True), patch.dict(sys.modules, {"llama_cpp": SimpleNamespace(Llama=Mock(return_value=backend))}), patch("reprobe.cli.chat", side_effect=failure), contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
                self.assertEqual(main(["--chat", "--model", "m.gguf"]), status)
            backend.close.assert_called_once()

    def test_lazy_help_and_scaffold(self):
        script = "from reprobe.cli import main; import sys; main(['repo']); assert 'llama_cpp' not in sys.modules"
        result = subprocess.run([sys.executable, "-c", script], capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("not implemented", result.stdout)
        result = subprocess.run([sys.executable, "-m", "reprobe", "--help"], capture_output=True, text=True)
        self.assertEqual(result.returncode, 0)
        self.assertIn("--chat", result.stdout)


class ModelTests(unittest.TestCase):
    def test_adapter_load_conversion_and_close(self):
        backend = Mock()
        backend.create_chat_completion.return_value = {"choices": [{"message": {"role": "assistant", "content": "hi"}, "finish_reason": "stop"}]}
        constructor = Mock(return_value=backend)
        with patch.object(Path, "is_file", return_value=True), patch.dict(sys.modules, {"llama_cpp": SimpleNamespace(Llama=constructor)}):
            adapter = LlamaCppModel(ModelConfig(Path("m.gguf")))
            with adapter:
                adapter.load()
                self.assertEqual(adapter.generate_reply([ChatMessage("user", "hello")]), ChatReply("hi", "stop"))
            adapter.close()
        constructor.assert_called_once()
        self.assertEqual(backend.create_chat_completion.call_args.kwargs["messages"], [{"role": "user", "content": "hello"}])
        backend.close.assert_called_once()
        with self.assertRaises(ModelError):
            adapter.generate_reply([])

    def test_bad_path_and_dependency(self):
        with self.assertRaisesRegex(ModelError, "existing GGUF"):
            LlamaCppModel(ModelConfig(Path("missing.gguf"))).load()
        with patch.object(Path, "is_file", return_value=True), patch.dict(sys.modules, {"llama_cpp": None}), self.assertRaisesRegex(ModelError, "install a working build"):
            LlamaCppModel(ModelConfig(Path("m.gguf"))).load()

    def test_backend_errors_preserve_cause(self):
        original = ValueError("unsupported architecture")
        with patch.object(Path, "is_file", return_value=True), patch.dict(sys.modules, {"llama_cpp": SimpleNamespace(Llama=Mock(side_effect=original))}), self.assertRaises(ModelError) as raised:
            LlamaCppModel(ModelConfig(Path("m.gguf"))).load()
        self.assertIs(raised.exception.__cause__, original)
        backend = Mock()
        adapter = LlamaCppModel(ModelConfig(Path("m.gguf")))
        adapter._model = backend
        for result in [{}, {"choices": [{"message": {"content": None}}]}]:
            backend.create_chat_completion.return_value = result
            with self.assertRaises(ModelError):
                adapter.generate_reply([])


if __name__ == "__main__":
    unittest.main()
