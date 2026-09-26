"""Bounded sampling across agent instructions and code languages without model logic."""
from collections import defaultdict, deque
from collections.abc import Iterator

from reprobe.repositories.local import LocalRepository, RepositoryError
from reprobe.review.types import (
    CodebaseInspection, Omission, SourceCandidate, SourceExcerpt, SourceSample,
)


def _ordered_candidates(candidates: tuple[SourceCandidate, ...]) -> Iterator[SourceCandidate]:
    groups: dict[str, deque[SourceCandidate]] = defaultdict(deque)
    for candidate in candidates:
        groups["" if candidate.kind == "instruction" else candidate.language].append(candidate)
    # The empty language key puts instructions first without inventing a language.
    if "" in groups:
        groups[""] = deque(sorted(groups[""], key=lambda c: (
            not c.explicit, c.path.count("/"), c.path,
        )))
    while any(groups.values()):
        for language in sorted(groups):
            if groups[language]:
                yield groups[language].popleft()


class SourceSampler:
    def __init__(self, repository: LocalRepository, max_files: int = 12, max_lines: int = 80):
        if type(max_files) is not int or type(max_lines) is not int or min(max_files, max_lines) <= 0:
            raise ValueError("source sampling limits must be positive integers")
        self._repository = repository
        self._max_files = max_files
        self._max_lines = max_lines

    def sample(self, inspection: CodebaseInspection) -> SourceSample:
        excerpts: list[SourceExcerpt] = []
        omissions: list[Omission] = []
        for candidate in _ordered_candidates(inspection.candidates):
            if len(excerpts) >= self._max_files:
                omissions.append(Omission(candidate.path, "file_limit"))
                continue
            excerpt = self._read_candidate(inspection, candidate)
            if isinstance(excerpt, Omission):
                omissions.append(excerpt)
            else:
                excerpts.append(excerpt)
        return SourceSample(tuple(excerpts), tuple(omissions))

    def _read_candidate(self, inspection: CodebaseInspection,
                        candidate: SourceCandidate) -> SourceExcerpt | Omission:
        try:
            content, truncated = self._repository.read_excerpt(
                inspection.root, candidate, self._max_lines,
            )
        except UnicodeError:
            return Omission(candidate.path, "binary_or_non_utf8")
        except RepositoryError as exc:
            return Omission(candidate.path, str(exc))
        if not content.strip():
            return Omission(candidate.path, "empty_or_no_complete_lines")
        return SourceExcerpt(candidate.path, candidate.language, content, truncated, candidate.kind)
