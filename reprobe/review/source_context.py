"""Compatibility facade composing source sampling with default review prompting."""
from collections.abc import Callable

from reprobe.chat.types import ChatMessage
from reprobe.review.context import PrepareReviewContext
from reprobe.repositories.local import LocalRepository
from reprobe.review.prompt import review_messages
from reprobe.review.types import CodebaseInspection, Omission, SourceExcerpt
from reprobe.repositories.sampling import SourceSampler


class SourceContext:
    def __init__(self, repository: LocalRepository, max_files: int = 12, max_lines: int = 80):
        self._sampler = SourceSampler(repository, max_files, max_lines)

    def prepare(self, inspection: CodebaseInspection,
                count_tokens: Callable[[tuple[ChatMessage, ...]], int],
                input_budget: int, *,
                build_messages: Callable[[tuple[SourceExcerpt, ...]], tuple[ChatMessage, ...]] = review_messages,
                ) -> tuple[tuple[SourceExcerpt, ...], tuple[Omission, ...]]:
        sample = PrepareReviewContext(
            inspection, self._sampler, build_messages, count_tokens, input_budget,
        ).execute()
        return sample.excerpts, sample.omissions
