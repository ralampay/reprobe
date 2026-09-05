"""CLI bootstrap; evaluation workflows are not implemented yet."""

import argparse
from pathlib import Path
from typing import Sequence


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="reprobe",
        description=(
            "Evaluate codebases through harnesses using local GGUF models. "
            "Currently a scaffold only; no evaluation is performed."
        ),
    )
    parser.add_argument("repository", type=Path, help="Path to the repository to evaluate")
    args = parser.parse_args(argv)
    print(f"Repository: {args.repository}")
    print("Reprobe is scaffolded; codebase evaluation is not implemented yet.")
    return 0
