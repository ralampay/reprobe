"""Immutable repository review values and application errors."""
from dataclasses import dataclass
from pathlib import Path

from reprobe.models.types import TokenUsage


class ReviewError(RuntimeError):
    """Review cannot produce a trustworthy structured result."""


class TruncatedReviewError(ReviewError):
    """Output ended before a complete JSON document was produced."""


@dataclass(frozen=True)
class SourceCandidate:
    path: str
    language: str
    kind: str = "code"
    explicit: bool = False


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
        return tuple(sorted({item.language for item in self.candidates if item.kind == "code"}))


@dataclass(frozen=True)
class SourceExcerpt:
    path: str
    language: str
    content: str
    truncated: bool
    kind: str = "code"

    @property
    def end_line(self) -> int:
        return len(self.content.splitlines())


@dataclass(frozen=True)
class Omission:
    path: str
    reason: str


@dataclass(frozen=True)
class Evidence:
    path: str
    start_line: int
    end_line: int
    explanation: str


@dataclass(frozen=True)
class Recommendation:
    id: str
    category: str
    priority: str
    title: str
    evidence: tuple[Evidence, ...]
    suggested_changes: tuple[str, ...]
    validation_steps: tuple[str, ...]
    synopsis: str = ""


@dataclass(frozen=True)
class ReviewResult:
    inspection: CodebaseInspection
    excerpts: tuple[SourceExcerpt, ...]
    omissions: tuple[Omission, ...]
    recommendations: tuple[Recommendation, ...]
    input_tokens: int | None = None
    input_budget: int | None = None
    generation_attempts: int = 0
    token_usage: tuple[TokenUsage | None, ...] = ()


@dataclass(frozen=True)
class SourceSample:
    excerpts: tuple[SourceExcerpt, ...]
    omissions: tuple[Omission, ...]
