from dataclasses import dataclass
from pathlib import Path

@dataclass(frozen=True)
class SourceCandidate:
    path: str
    language: str


@dataclass(frozen=True)
class CodebaseInspection:
    root: Path
    candidates: tuple[SourceCandidate, ...]
    reason: str

    @property
    def is_codebase(self) -> bool:
        return bool(self.candidates)

    @property
    def languages(self) -> tuple[str, ...]:
        return tuple(sorted({item.language for item in self.candidates}))
