import os
from pathlib import Path

from reprobe.review_types import SourceCandidate

LANGUAGE_SUFFIXES = {
    "python": frozenset({".py", ".pyw"}),
    "cpp": frozenset({".cpp", ".cc", ".cxx", ".h", ".hpp", ".hh", ".hxx"}),
    "ruby": frozenset({".rb", ".rake"}),
}

RUBY_FILENAMES = frozenset({"Rakefile", "Gemfile", "config.ru"})

EXCLUDED_DIRECTORIES = frozenset({
    ".git", ".venv", "venv", "__pycache__", "build", "dist", "vendor", ".bundle",
})

class RepositoryError(RuntimeError):
    """Repository access failed; not a negative codebase classification."""

def detect_language(path: Path) -> str | None:
    if path.name in RUBY_FILENAMES:
        return "ruby"
    suffix = path.suffix.lower()

    for language, suffixes in LANGUAGE_SUFFIXES.items():
        if suffix in suffixes:
            return language

    return None

def raise_walk_error(error: OSError) -> None:
    # os.walk otherwise ignores directory enumeration errors by default
    raise error

class LocalRepository:
    def resolve_root(self, path: Path) -> Path:
        try:
            root = path.expanduser().resolve(strict=True)
            if not root.is_dir():
                raise RepositoryError(f"Repository must be a directory: {root}")
            return root

        except (OSError, RuntimeError) as exc:
            if isinstance(exc, RepositoryError):
                raise
            raise RepositoryError(f"Repository cannot be accessed: {path}: {exc}")

    def discover(self, root: Path) -> tuple[SourceCandidate, ...]:
        candidates = []

        try:
            for directory, dirs, files in os.walk(
                root, topdown=True, followlinks=False, onerror=raise_walk_error
            ):
                parent = Path(directory)
                dirs[:] = sorted(
                    name for name in dirs
                    if not name in EXCLUDED_DIRECTORIES
                    and not (parent / name).is_symlink()
                )
                
                for name in files:
                    path = parent / name
                    if path.is_symlink() or not path.is_file():
                        continue
                    language = detect_language(path)

                    if language is not None:
                        candidates.append(SourceCandidate(
                            path.relative_to(root).as_posix(), language
                        ))

        except OSError as exc:
            raise RepositoryError(f"Cannot inspect repository {root}: {exc}") from exc
        return tuple(sorted(candidates, key=lambda candidate: candidate.path))
