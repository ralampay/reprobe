"""Argument parsing, dependency composition, and user-facing errors."""

import argparse
from pathlib import Path
import sys
from typing import Sequence

from reprobe.chat_types import ModelConfig
from reprobe.model import LlamaCppModel, ModelError
from reprobe.terminal import chat


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="reprobe",
        description="Chat with local GGUF models. Codebase evaluation is not implemented yet.",
    )
    parser.add_argument("repository", nargs="?", type=Path, help="Repository to evaluate (scaffold)")
    parser.add_argument("--chat", action="store_true", help="Start interactive chat without a repository")
    parser.add_argument("--model", type=Path, help="Path to a GGUF chat model")
    parser.add_argument("--n-ctx", type=int, help="Context size (default: 4096)")
    parser.add_argument("--n-gpu-layers", type=int, help="GPU layers; -1 for all (default: 0)")
    parser.add_argument("--max-tokens", type=int, help="Maximum reply tokens (default: 512)")
    parser.add_argument("--temperature", type=float, help="Sampling temperature (default: 0.7)")
    parser.add_argument("--chat-format", help="Override the model's chat template")
    args = parser.parse_args(argv)
    model_options = {
        name: getattr(args, name)
        for name in ("n_ctx", "n_gpu_layers", "max_tokens", "temperature", "chat_format")
        if getattr(args, name) is not None
    }
    if not args.chat:
        if args.model is not None or model_options:
            parser.error("model options require --chat")
        if args.repository is None:
            parser.error("a repository is required unless --chat is used")
        print(f"Repository: {args.repository}")
        print("Reprobe is scaffolded; codebase evaluation is not implemented yet.")
        return 0
    if args.repository is not None:
        parser.error("--chat cannot be combined with a repository")
    if args.model is None:
        parser.error("--chat requires --model")
    try:
        config = ModelConfig(model_path=args.model, **model_options)
    except ValueError as exc:
        parser.error(str(exc))
    try:
        print(f"Loading model: {config.model_path}", flush=True)
        with LlamaCppModel(config) as model:
            chat(model)
    except ModelError as exc:
        print(f"reprobe: {exc}", file=sys.stderr)
        return 1
    except KeyboardInterrupt:
        print("\nChat interrupted.", file=sys.stderr)
        return 130
    return 0
