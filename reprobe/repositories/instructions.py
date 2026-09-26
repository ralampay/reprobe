"""Recognize the documented repository-local agent instruction conventions."""
from pathlib import PurePosixPath


INSTRUCTION_NAMES = frozenset({
    "AGENTS.md", "AGENTS.override.md", "INSTRUCTIONS.md", "CLAUDE.md",
    "GEMINI.md", "SKILL.md",
})
ROOT_FILES = frozenset({
    ".cursorrules", ".windsurfrules", ".github/copilot-instructions.md",
})
RULE_DIRECTORIES = {
    ".cursor/rules": ".mdc",
    ".clinerules": ".md",
    ".github/instructions": ".instructions.md",
}


def is_instruction_file(relative_path: str) -> bool:
    path = PurePosixPath(relative_path)
    suffix = RULE_DIRECTORIES.get(path.parent.as_posix())
    return (
        path.name in INSTRUCTION_NAMES
        or relative_path in ROOT_FILES
        or (suffix is not None and path.name.endswith(suffix))
    )
