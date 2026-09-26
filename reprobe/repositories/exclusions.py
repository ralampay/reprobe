"""Source-discovery exclusions, applied before descending into directories."""
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from pathspec import GitIgnoreSpec


EXCLUDED_DIRECTORIES = frozenset({
    ".git", ".hg", ".svn", "node_modules", "vendor", "third_party",
    "third-party", "thirdparty", ".bundle", ".yarn", ".pnpm-store",
    "env", ".env", "venv", ".venv", "site-packages", "dist-packages",
    ".tox", ".nox", ".eggs", "__pycache__", ".cache", ".pytest_cache",
    ".mypy_cache", ".ruff_cache", ".next", ".nuxt", ".svelte-kit",
    "build", "dist", "htmlcov", ".ipynb_checkpoints",
})


def is_dependency_directory(path: Path) -> bool:
    """Recognize conventional names and environments with arbitrary names."""
    name = path.name.casefold()
    return (
        name in EXCLUDED_DIRECTORIES
        or name.endswith(".egg-info")
        or name.startswith("cmake-build-")
        or (path / "pyvenv.cfg").is_file()
        or (path / "conda-meta").is_dir()
    )


@dataclass(frozen=True)
class IgnoreRules:
    """An ignore file and its relative base; external matching stays here."""
    directory: Path
    spec: "GitIgnoreSpec"

    def match(self, path: Path, *, directory: bool) -> bool | None:
        relative = path.relative_to(self.directory).as_posix()
        return self.spec.check_file(relative + ("/" if directory else "")).include


def read_ignore_rules(directory: Path, filename: str) -> tuple[IgnoreRules, ...]:
    path = directory / filename
    # Ignore files must obey the same no-symlinks boundary as source files.
    if path.is_symlink():
        return ()
    try:
        text = path.read_text(encoding="utf-8")
    except FileNotFoundError:
        return ()
    except (OSError, UnicodeError) as exc:
        raise OSError(f"Cannot read ignore rules {path}: {exc}") from exc
    try:
        from pathspec import GitIgnoreSpec
    except ImportError as exc:
        raise OSError("Ignore matching requires pathspec; run pip install -e .") from exc

    try:
        return (IgnoreRules(directory, GitIgnoreSpec.from_lines(text.splitlines())),)
    except ValueError as exc:
        raise OSError(f"Invalid ignore rules {path}: {exc}") from exc


def is_ignored(path: Path, rules: tuple[IgnoreRules, ...], *, directory: bool) -> bool:
    ignored = False
    for rule in rules:
        match = rule.match(path, directory=directory)
        if match is not None:
            ignored = match
    return ignored
