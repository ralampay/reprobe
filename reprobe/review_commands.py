from pathlib import Path

from reprobe.repository import LocalRepository
from reprobe.review_types import CodebaseInspection

class InspectCodebase:
    def __init__(self, path: Path, repository: LocalRepository) -> None:
        self._path = path
        self._repository = repository

    def execute(self) -> CodebaseInspection:
        root = self._repository.resolve_root(self._path)
        candidates = self._repository.discover(root)
        reason = "recognized_source" if candidates else "no_supported_source"
        return CodebaseInspection(root, candidates, reason)
