"""Scoped suppression of Python and native backend console output."""
from contextlib import ExitStack, contextmanager, redirect_stderr, redirect_stdout
from collections.abc import Iterator
import os
import sys


@contextmanager
def suppress_backend_output() -> Iterator[None]:
    """Restore streams and descriptors even when inference raises or is interrupted.

    Native libraries write directly to descriptors 1/2, bypassing Python streams.
    Descriptor redirection is process-wide; use only around synchronous backend
    operations, never around the application session or its progress rendering.
    """
    sys.stdout.flush()
    sys.stderr.flush()
    with ExitStack() as stack:
        sink = stack.enter_context(open(os.devnull, "w"))
        for descriptor in (1, 2):
            saved = os.dup(descriptor)
            stack.callback(os.close, saved)
            stack.callback(os.dup2, saved, descriptor)
            os.dup2(sink.fileno(), descriptor)
        stack.enter_context(redirect_stdout(sink))
        stack.enter_context(redirect_stderr(sink))
        yield
