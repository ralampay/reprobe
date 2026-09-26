"""Prepare review context using injected sampling, prompting, and token counting."""
from collections.abc import Callable
from dataclasses import replace

from reprobe.chat.types import ChatMessage
from reprobe.review.types import (
    CodebaseInspection, Omission, ReviewError, SourceExcerpt, SourceSample,
)
from reprobe.repositories.sampling import SourceSampler


class PrepareReviewContext:
    def __init__(
        self, inspection: CodebaseInspection, sampler: SourceSampler,
        build_messages: Callable[[tuple[SourceExcerpt, ...]], tuple[ChatMessage, ...]],
        count_tokens: Callable[[tuple[ChatMessage, ...]], int], input_budget: int,
    ) -> None:
        self._inspection = inspection
        self._sampler = sampler
        self._build_messages = build_messages
        self._count_tokens = count_tokens
        self._input_budget = input_budget

    def execute(self) -> SourceSample:
        sample = self._sampler.sample(self._inspection)
        if not sample.excerpts:
            raise ReviewError("No readable, nonempty supported code or instructions are available for review.")
        return self._fit_budget(sample)

    def _fit_budget(self, sample: SourceSample) -> SourceSample:
        excerpts = list(sample.excerpts)
        omissions = list(sample.omissions)
        while self._count_tokens(self._build_messages(tuple(excerpts))) > self._input_budget:
            # Preserve longest-excerpt trimming and stable tie breaking.
            index = max(range(len(excerpts)), key=lambda i: len(excerpts[i].content.encode("utf-8")))
            excerpt = excerpts[index]
            lines = excerpt.content.splitlines()
            if len(lines) > 1:
                excerpts[index] = replace(
                    excerpt, content="\n".join(lines[:max(1, len(lines) // 2)]), truncated=True,
                )
            else:
                omissions.append(Omission(excerpt.path, "context_limit"))
                excerpts.pop(index)
            if not excerpts:
                raise ReviewError("Context is too small for review instructions and repository content; increase --n-ctx, reduce --max-tokens, or shorten the review query.")
        return SourceSample(tuple(excerpts), tuple(omissions))
