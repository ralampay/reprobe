"""Reprobe-owned status messages, separate from JSON and chat responses."""
import os
import sys
import threading
import time


def _stage_message(stage: str) -> str:
    messages = {
        "metadata": "Inspecting local model metadata...",
        "scan": "Scanning repository code or instruction files...",
        "context": "Selecting code and instruction excerpts and fitting the model context...",
        "generate": "Generating recommendations with the local model...",
        "retry": "Output limit reached; retrying once with one concise recommendation...",
        "preflight": "Input token budget checked; output allowance reserved.",
        "validate": "Validating recommendations and file references...",
        "empty": "No supported code or instruction files found.",
        "close": "Releasing model resources...",
        "complete": "Review complete.",
        "chat_ready": "Local model ready for chat.",
        "chat_generate": "Generating reply...",
    }
    return messages[stage]


def report_progress(stage: str) -> None:
    print(f"reprobe: {_stage_message(stage)}", file=sys.stderr, flush=True)


class ProgressReporter:
    """Animate current work on terminals; retain plain status lines elsewhere."""

    def __init__(self, stream=None, interval: float = 0.1):
        if interval <= 0:
            raise ValueError("spinner interval must be positive")
        self._stream = stream
        self._interval = interval
        self._wake = threading.Event()
        self._thread = None
        self._owned_stream = None
        self._animated = False
        self._message = ""

    def __enter__(self):
        self._stream = self._stream if self._stream is not None else sys.stderr
        self._animated = self._stream.isatty()
        if self._animated:
            # Keep the UI visible while backend descriptors 1/2 are redirected.
            try:
                descriptor = self._stream.fileno()
            except (AttributeError, OSError):
                pass  # In-memory terminal substitutes used by Python callers.
            else:
                self._owned_stream = os.fdopen(
                    os.dup(descriptor), "w", encoding=self._stream.encoding or "utf-8",
                    errors="replace", buffering=1,
                )
                self._stream = self._owned_stream
        return self

    def update(self, stage: str) -> None:
        self.message(_stage_message(stage), active=stage not in {"empty", "complete", "chat_ready"})

    def message(self, message: str, *, active: bool = True) -> None:
        self.stop()
        self._message = message
        if not self._animated or not active:
            print(f"reprobe: {message}", file=self._stream, flush=True)
            return
        self._wake.clear()
        self._started = time.monotonic()
        self._render(0)
        self._thread = threading.Thread(target=self._animate, name="reprobe-progress", daemon=True)
        self._thread.start()

    def _render(self, frame: int) -> None:
        elapsed = int(time.monotonic() - self._started)
        # One short line avoids wrapping when a model path is long.
        symbol = "|/-\\"[frame % 4]
        text = f"reprobe: {symbol} {self._message} ({elapsed}s)"
        self._stream.write("\r\x1b[2K" + text[:max(1, self._columns() - 1)])
        self._stream.flush()

    def _columns(self) -> int:
        try:
            return max(1, os.get_terminal_size(self._stream.fileno()).columns)
        except (AttributeError, OSError, ValueError):
            return 80

    def _animate(self) -> None:
        frame = 1
        while not self._wake.wait(self._interval):
            try:
                self._render(frame)
            except (OSError, ValueError):
                return  # A closed terminal must not crash the inference operation.
            frame += 1

    def stop(self) -> None:
        if self._thread is not None:
            self._wake.set()
            self._thread.join()
            self._thread = None
            self._stream.write("\r\x1b[2K" + f"reprobe: {self._message}"[:max(1, self._columns() - 1)] + "\n")
            self._stream.flush()

    def __exit__(self, exc_type, exc_value, traceback) -> None:
        try:
            self.stop()
        finally:
            if self._owned_stream is not None:
                self._owned_stream.close()
                self._owned_stream = None
