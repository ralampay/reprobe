"""Reusable repository inspection and review workflows."""
from collections.abc import Sequence
from pathlib import Path
from typing import Protocol

from reprobe.chat.types import ChatMessage, ChatReply
from reprobe.repositories.local import LocalRepository
from reprobe.review.contract import parse_recommendations
from reprobe.review.prompt import review_messages
from reprobe.review.types import CodebaseInspection, ReviewResult
from reprobe.review.source_context import SourceContext


class ReviewModel(Protocol):
    """Only inference capabilities required by a bounded review."""
    def count_message_tokens(self, messages: Sequence[ChatMessage]) -> int: ...
    def generate_review(self, messages: Sequence[ChatMessage]) -> ChatReply: ...


class InspectCodebase:
    def __init__(self, path: Path, repository: LocalRepository) -> None:
        self._path = path
        self._repository = repository

    def execute(self) -> CodebaseInspection:
        root = self._repository.resolve_root(self._path)
        candidates = self._repository.discover(root)
        reason = "recognized_source" if candidates else "no_supported_source"
        return CodebaseInspection(root, candidates, reason)


class EvaluateRepository:
    """Coordinate inspection, bounded context, generation, and validation."""
    def __init__(self, path: Path, repository: LocalRepository, context: SourceContext,
                 model: ReviewModel, input_budget: int) -> None:
        self._path = path
        self._repository = repository
        self._context = context
        self._model = model
        self._input_budget = input_budget

    def execute(self) -> ReviewResult:
        inspection = InspectCodebase(self._path, self._repository).execute()
        if not inspection.is_codebase:
            return ReviewResult(inspection, (), (), ())
        excerpts, omissions = self._context.prepare(
            inspection, self._model.count_message_tokens, self._input_budget,
        )
        reply = self._model.generate_review(review_messages(excerpts))
        recommendations = parse_recommendations(reply, excerpts)
        return ReviewResult(inspection, excerpts, omissions, recommendations)
