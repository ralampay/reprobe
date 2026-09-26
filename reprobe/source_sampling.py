"""Compatibility exports; implementation lives in :mod:`reprobe.repositories.sampling`."""
from reprobe.repositories.sampling import (
    CodebaseInspection as CodebaseInspection,
    LocalRepository as LocalRepository,
    Omission as Omission,
    RepositoryError as RepositoryError,
    SourceCandidate as SourceCandidate,
    SourceExcerpt as SourceExcerpt,
    SourceSample as SourceSample,
    SourceSampler as SourceSampler,
)

__all__ = ['CodebaseInspection', 'LocalRepository', 'Omission', 'RepositoryError', 'SourceCandidate', 'SourceExcerpt', 'SourceSample', 'SourceSampler']
