"""Write structured reports atomically without mixing terminal formatting into JSON."""
import json
import os
from pathlib import Path
import tempfile
from typing import Any


class ReportWriteError(RuntimeError):
    """A report could not be saved to its requested destination."""


def serialize_report(report: dict[str, Any]) -> str:
    return json.dumps(report, indent=2, ensure_ascii=False) + "\n"


class WriteJsonReport:
    def __init__(self, path: Path, report: dict[str, Any]) -> None:
        self._path = path.expanduser()
        self._report = report

    def execute(self) -> Path:
        temporary: Path | None = None
        try:
            content = serialize_report(self._report)
            with tempfile.NamedTemporaryFile(
                mode="w", encoding="utf-8", dir=self._path.parent,
                prefix=f".{self._path.name}.", suffix=".tmp", delete=False,
            ) as stream:
                temporary = Path(stream.name)
                stream.write(content)
            os.replace(temporary, self._path)
            return self._path
        except OSError as exc:
            raise ReportWriteError(
                f"Cannot save JSON report to {self._path}: {exc}. "
                "Check that the parent directory exists and is writable."
            ) from exc
        finally:
            if temporary is not None:
                temporary.unlink(missing_ok=True)
