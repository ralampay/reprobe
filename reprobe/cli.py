"""Argument parsing, dependency composition, and user-facing errors."""
import argparse
import json
from pathlib import Path
import sys
from typing import Sequence

from reprobe.models.types import validate_model_options
from reprobe.models.gguf_metadata import GgufMetadataReader, MetadataError
from reprobe.models.llama_cpp import LlamaCppModel, ModelError
from reprobe.models.settings import ResolveModelSettings
from reprobe.output.json_report import review_report
from reprobe.repositories.local import LocalRepository, RepositoryError
from reprobe.review.commands import EvaluateRepository
from reprobe.review.types import ReviewError
from reprobe.review.source_context import SourceContext
from reprobe.chat.terminal import chat


def _gguf_model_path(value: str) -> Path:
    path = Path(value).expanduser()
    if not path.exists():
        raise argparse.ArgumentTypeError(f"model does not exist: {path}")
    if not path.is_file() or path.suffix.lower() != ".gguf":
        raise argparse.ArgumentTypeError(f"model must be a GGUF file: {path}")
    return path


def _positive(value: str) -> int:
    number = int(value)
    if number <= 0:
        raise argparse.ArgumentTypeError("must be a positive integer")
    return number


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="reprobe", description="Review source code with a local GGUF model; emit a structured JSON report.")
    parser.add_argument("repository", type=Path, help="Repository directory to review")
    parser.add_argument("--model", required=True, type=_gguf_model_path, help="Path to a local GGUF chat/instruction model")
    parser.add_argument("--chat", action="store_true", help="Start interactive chat instead of a repository review")
    parser.add_argument("--n-ctx", type=_positive, help="Context tokens (auto: model context capped at 8192; fallback 4096)")
    parser.add_argument("--max-tokens", type=_positive, help="Output tokens (auto: min(2048, context // 4))")
    parser.add_argument("--n-gpu-layers", type=int, default=0, help="GPU layers; -1 for all (default: CPU)")
    parser.add_argument("--temperature", type=float, help="Sampling temperature (review: 0.2; chat: 0.7)")
    parser.add_argument("--chat-format", help="Override model chat template")
    parser.add_argument("--max-files", type=_positive, default=12, help="Maximum sampled source files (default: 12)")
    parser.add_argument("--max-lines-per-file", type=_positive, default=80, help="Maximum lines sampled per file (default: 80)")
    return parser


def _model_options(args: argparse.Namespace) -> dict:
    return dict(
        n_gpu_layers=args.n_gpu_layers,
        temperature=args.temperature if args.temperature is not None else (0.7 if args.chat else 0.2),
        chat_format=args.chat_format,
    )


def main(argv: Sequence[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)
    options = _model_options(args)
    # Validate explicit scalar options before reading metadata or loading a model.
    try:
        validate_model_options(args.model, n_ctx=args.n_ctx, max_tokens=args.max_tokens, **options)
    except ValueError as exc:
        parser.error(str(exc))
    settings = result = error = None
    status = 0
    repository = LocalRepository()
    root = args.repository
    try:
        if not args.chat:
            root = repository.resolve_root(root)
        try:
            settings = ResolveModelSettings(args.model, GgufMetadataReader(), n_ctx=args.n_ctx,
                                            max_tokens=args.max_tokens, **options).execute()
        except ValueError as exc:
            parser.error(str(exc))
        for diagnostic in settings.diagnostics:
            print(f"reprobe: {diagnostic}", file=sys.stderr)
        print(f"Loading model: {args.model} (context={settings.config.n_ctx}, output={settings.config.max_tokens})", file=sys.stderr)
        with LlamaCppModel(settings.config) as model:
            if args.chat:
                chat(model)
            else:
                context = SourceContext(repository, args.max_files, args.max_lines_per_file)
                result = EvaluateRepository(root, repository, context, model,
                                            settings.review_input_budget).execute()
    except (MetadataError, ModelError, RepositoryError, ReviewError) as exc:
        error, status = exc, 1
        print(f"reprobe: {exc}", file=sys.stderr)
    except KeyboardInterrupt as exc:
        error, status = exc, 130
        print("reprobe: interrupted", file=sys.stderr)
    if not args.chat:
        print(json.dumps(review_report(root, settings, result, error), indent=2, ensure_ascii=False))
    return status
