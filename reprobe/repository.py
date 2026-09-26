"""Compatibility exports; implementation lives in :mod:`reprobe.repositories.local`."""
from reprobe.repositories.local import (
    EXCLUDED_DIRECTORIES as EXCLUDED_DIRECTORIES,
    LANGUAGE_SUFFIXES as LANGUAGE_SUFFIXES,
    LocalRepository as LocalRepository,
    RUBY_FILENAMES as RUBY_FILENAMES,
    RepositoryError as RepositoryError,
    SourceCandidate as SourceCandidate,
    detect_language as detect_language,
    raise_walk_error as raise_walk_error,
)

__all__ = ['EXCLUDED_DIRECTORIES', 'LANGUAGE_SUFFIXES', 'LocalRepository', 'RUBY_FILENAMES', 'RepositoryError', 'SourceCandidate', 'detect_language', 'raise_walk_error']
