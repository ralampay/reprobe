"""Terminal animation remains alive during native backend suppression."""
from io import StringIO
import os
import subprocess
import sys
import threading

import pytest

from reprobe.output.progress import ProgressReporter


class Terminal(StringIO):
    def __init__(self):
        super().__init__()
        self.animated = threading.Event()
        self.frames = 0

    def isatty(self):
        return True

    def write(self, text):
        result = super().write(text)
        if text.startswith("\r"):
            self.frames += 1
            if self.frames >= 2:
                self.animated.set()
        return result


def test_animation_updates_while_operation_runs_and_stops_on_interrupt():
    terminal = Terminal()
    progress = ProgressReporter(terminal, interval=0.01)
    with pytest.raises(KeyboardInterrupt):
        with progress:
            progress.update("generate")
            assert terminal.animated.wait(2)
            raise KeyboardInterrupt()
    assert progress._thread is None
    assert terminal.getvalue().endswith("Generating recommendations with the local model...\n")
    assert "(0s)" in terminal.getvalue()


def test_redirected_progress_is_plain_and_has_no_thread():
    stream = StringIO()
    with ProgressReporter(stream) as progress:
        progress.update("generate")
        progress.update("retry")
        progress.update("complete")
        assert progress._thread is None
    assert "\x1b" not in stream.getvalue()
    assert "\r" not in stream.getvalue()
    assert len(stream.getvalue().splitlines()) == 3


@pytest.mark.skipif(os.name != "posix", reason="PTY regression requires POSIX")
def test_spinner_survives_suppressed_native_descriptors():
    import fcntl
    import pty
    import struct
    import termios
    master, slave = pty.openpty()
    fcntl.ioctl(slave, termios.TIOCSWINSZ, struct.pack("HHHH", 24, 100, 0, 0))
    script = '''
import os, time
from reprobe.output.progress import ProgressReporter
from reprobe.models.backend_output import suppress_backend_output
with ProgressReporter(interval=0.01) as progress:
    progress.update("generate")
    with suppress_backend_output():
        print("BACKEND DEBUG")
        os.write(2, b"NATIVE DEBUG\\n")
        time.sleep(0.1)
print('{"ok": true}')
'''
    try:
        result = subprocess.run([sys.executable, "-c", script], stdout=subprocess.PIPE,
                                stderr=slave, text=True, timeout=5)
        os.set_blocking(master, False)
        output = os.read(master, 65536).decode()
        assert result.returncode == 0
        assert result.stdout == '{"ok": true}\n'
        assert "DEBUG" not in output
        assert output.count("\x1b[2K") >= 3
        assert "Generating recommendations" in output
    finally:
        os.close(master)
        os.close(slave)
