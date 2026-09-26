"""Reusable repository inspection and review workflows."""
from collections.abc import Callable, Sequence
from pathlib import Path
from functools import partial
from dataclasses import replace
from typing import Protocol

from reprobe.chat.types import ChatMessage, ChatReply
from reprobe.repositories.local import LocalRepository
from reprobe.review.contract import parse_recommendations, review_schema
from reprobe.review.prompt import review_messages, compact_review_messages
from reprobe.review.types import CodebaseInspection, ReviewResult, Omission, ReviewError, TruncatedReviewError
from reprobe.review.source_context import SourceContext


class ReviewModel(Protocol):
    """Only inference capabilities required by a bounded review."""
    def count_message_tokens(self, messages: Sequence[ChatMessage]) -> int: ...
    def generate_review(self, messages: Sequence[ChatMessage], *, max_recommendations: int = 1) -> ChatReply: ...


class InspectCodebase:
    def __init__(self, path: Path, repository: LocalRepository, *,
                 instruction_files: Sequence[Path | str] = ()) -> None:
        self._instruction_files = tuple(instruction_files)
        self._path = path
        self._repository = repository

    def execute(self) -> CodebaseInspection:
        root = self._repository.resolve_root(self._path)
        candidates = (self._repository.discover(root, instruction_files=self._instruction_files)
                      if self._instruction_files else self._repository.discover(root))
        reason = "recognized_source" if candidates else "no_supported_source"
        return CodebaseInspection(root, candidates, reason)


class EvaluateRepository:
    """Coordinate inspection, bounded context, generation, and validation."""
    def __init__(self, path: Path, repository: LocalRepository, context: SourceContext,
                 model: ReviewModel, input_budget: int, *,
                 on_progress: Callable[[str], None] | None = None,
                 query: str | None = None, max_recommendations: int = 1,
                 instruction_files: Sequence[Path | str] = ()) -> None:
        if query is not None and not query.strip():
            raise ReviewError("Review query must not be empty.")
        review_schema(max_recommendations)
        self._max_recommendations = max_recommendations
        self._query = query.strip() if query is not None else None
        self._instruction_files = tuple(instruction_files)
        self._path = path
        self._repository = repository
        self._context = context
        self._model = model
        self._input_budget = input_budget
        self._on_progress = on_progress
        self._result: ReviewResult | None = None

    @property
    def result(self) -> ReviewResult | None:
        """Latest immutable coverage snapshot, available even if evaluation fails."""
        return self._result

    def execute(self) -> ReviewResult:
        self._result = None
        self._report_progress("scan")
        inspection = InspectCodebase(self._path, self._repository,
                                     instruction_files=self._instruction_files).execute()
        self._result = ReviewResult(
            inspection, (), tuple(Omission(c.path, "not_sent_to_model") for c in inspection.candidates), (),
            input_budget=self._input_budget,
        )
        if not inspection.is_codebase:
            self._report_progress("empty")
            return self._result
        for attempt in range(2):
            if attempt:
                self._report_progress("retry")
            else:
                self._report_progress("context")
            builder = partial(compact_review_messages if attempt else review_messages,
                              query=self._query, max_recommendations=self._max_recommendations)
            excerpts, omissions = self._context.prepare(
                inspection, self._model.count_message_tokens, self._input_budget,
                build_messages=builder,
            )
            messages = builder(excerpts)
            tokens = self._model.count_message_tokens(messages)
            self._result = ReviewResult(inspection, excerpts, omissions, (), tokens,
                                        self._input_budget, attempt, self._result.token_usage)
            if tokens > self._input_budget:
                raise ReviewError("Review input exceeds the available token budget; increase --n-ctx or reduce --max-tokens.")
            self._report_progress("preflight")
            self._result = replace(self._result, generation_attempts=attempt + 1,
                                   token_usage=self._result.token_usage + (None,))
            self._report_progress("generate")
            if self._max_recommendations == 1:
                reply = self._model.generate_review(messages)
            else:
                reply = self._model.generate_review(messages, max_recommendations=self._max_recommendations)
            self._result = replace(self._result,
                                   token_usage=self._result.token_usage[:-1] + (reply.usage,))
            self._report_progress("validate")
            try:
                recommendations = parse_recommendations(reply, excerpts, max_recommendations=self._max_recommendations)
            except TruncatedReviewError as exc:
                if not attempt:
                    continue
                raise ReviewError(
                    "The model exceeded its output token limit on both the initial review and "
                    "one concise retry. The input prompt fit its budget, but the answer did not fit "
                    "its output allowance. Increase --max-tokens (and --n-ctx if needed), "
                    "or request fewer recommendations with -n. Coverage from the last attempt is retained."
                ) from exc
            self._result = replace(self._result, recommendations=recommendations)
            return self._result
        raise AssertionError("Unreachable review retry state")

    def _report_progress(self, stage: str) -> None:
        if self._on_progress is not None:
            self._on_progress(stage)
