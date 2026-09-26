import os
from pathlib import Path

from reprobe.review.types import SourceCandidate

LANGUAGE_SUFFIXES = {
    "python": frozenset({".py", ".pyw"}),
    "cpp": frozenset({".cpp", ".cc", ".cxx", ".h", ".hpp", ".hh", ".hxx"}),
    "ruby": frozenset({".rb", ".rake"}),
    "go": frozenset({".go"}),
    "javascript": frozenset({".js", ".jsx", ".mjs", ".cjs"}),
    "typescript": frozenset({".ts", ".tsx", ".mts", ".cts"}),
}

RUBY_FILENAMES = frozenset({"Rakefile", "Gemfile", "config.ru"})

EXCLUDED_DIRECTORIES = frozenset({
    "node_modules", ".cache", ".pytest_cache", ".mypy_cache", ".next", ".git", ".venv", "venv", "__pycache__", "build", "dist", "vendor", ".bundle",
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
            raise RepositoryError(f"Repository cannot be accessed: {path}: {exc}") from exc

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

    def read_excerpt(self, root: Path, candidate: SourceCandidate, max_lines: int) -> tuple[str, bool]:
        """Bound bytes as well as lines; never read a linked or escaped file."""
        path = root / candidate.path
        try:
            if path.is_symlink() or not path.resolve(strict=True).is_relative_to(root):
                raise RepositoryError(f"Source is linked or outside repository: {candidate.path}")
            with path.open("rb") as source:
                raw = source.read(65537)
            limited = len(raw) > 65536
            raw = raw[:65536]
            if limited:
                raw = raw[:raw.rfind(b"\n") + 1]
            if b"\0" in raw:
                raise UnicodeError("binary source")
            text = raw.decode("utf-8")
            lines = text.splitlines()
            return "\n".join(lines[:max_lines]), limited or len(lines) > max_lines
        except (OSError, RuntimeError) as exc:
            raise RepositoryError(f"Cannot read {candidate.path}: {exc}") from exc
