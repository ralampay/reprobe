"""Compatibility exports; implementation lives in :mod:`reprobe.review.types`."""
from reprobe.review.types import (
    CodebaseInspection as CodebaseInspection,
    Evidence as Evidence,
    Omission as Omission,
    Recommendation as Recommendation,
    ReviewError as ReviewError,
    ReviewResult as ReviewResult,
    SourceCandidate as SourceCandidate,
    SourceExcerpt as SourceExcerpt,
    SourceSample as SourceSample,
)

__all__ = ['CodebaseInspection', 'Evidence', 'Omission', 'Recommendation', 'ReviewError', 'ReviewResult', 'SourceCandidate', 'SourceExcerpt', 'SourceSample']
