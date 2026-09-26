"""Argument parsing, dependency composition, and user-facing errors."""
import argparse
import os
import shutil
from pathlib import Path
import sys
from typing import Sequence

from reprobe.models.types import validate_model_options
from reprobe.models.gguf_metadata import GgufMetadataReader, MetadataError
from reprobe.models.llama_cpp import LlamaCppModel, ModelError
from reprobe.models.settings import ResolveModelSettings
from reprobe.output.json_report import review_report
from reprobe.output.files import ReportWriteError, WriteJsonReport, serialize_report
from reprobe.output.terminal_report import format_report
from reprobe.output.progress import ProgressReporter
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
    parser = argparse.ArgumentParser(prog="reprobe", description="Review source code with a local GGUF model; show prioritized recommendations.")
    parser.add_argument("repository", type=Path, help="Repository directory to review")
    parser.add_argument("--model", required=True, type=_gguf_model_path, help="Path to a local GGUF chat/instruction model")
    parser.add_argument("--output-json", type=Path, metavar="PATH", help="Also save structured JSON to PATH; use - for JSON-only stdout")
    parser.add_argument("-n", type=_positive, metavar="COUNT", help="Number of top recommendations (default: 1)")
    parser.add_argument("--query", help="Focus the review on this request (quote multiword queries)")
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
    if args.chat and args.n is not None:
        parser.error("-n is available for repository reviews, not --chat")
    if args.query is not None:
        args.query = args.query.strip()
        if not args.query:
            parser.error("--query must not be empty")
        if args.chat:
            parser.error("--query is available for repository reviews, not --chat")
    if args.chat and args.output_json is not None:
        parser.error("--output-json is available for repository reviews, not --chat")
    if args.output_json is not None and args.output_json != Path("-"):
        if args.output_json.expanduser().resolve() == args.model.resolve():
            parser.error("--output-json must not overwrite the model file")
    options = _model_options(args)
    # Validate explicit scalar options before reading metadata or loading a model.
    try:
        validate_model_options(args.model, n_ctx=args.n_ctx, max_tokens=args.max_tokens, **options)
    except ValueError as exc:
        parser.error(str(exc))
    settings = result = error = None
    review_command = None
    status = 0
    repository = LocalRepository()
    root = args.repository
    try:
        with ProgressReporter() as progress:
            if not args.chat:
                root = repository.resolve_root(root)
            progress.update("metadata")
            try:
                settings = ResolveModelSettings(args.model, GgufMetadataReader(), n_ctx=args.n_ctx,
                                                max_tokens=args.max_tokens, **options).execute()
            except ValueError as exc:
                parser.error(str(exc))
            progress.stop()
            for diagnostic in settings.diagnostics:
                print(f"reprobe: {diagnostic}", file=sys.stderr)
            progress.message(f"Loading local model: {args.model} (context={settings.config.n_ctx}, output={settings.config.max_tokens})")
            with LlamaCppModel(settings.config) as model:
                if args.chat:
                    progress.update("chat_ready")
                    chat(model)
                else:
                    context = SourceContext(repository, args.max_files, args.max_lines_per_file)
                    review_command = EvaluateRepository(root, repository, context, model,
                                                settings.review_input_budget,
                                                on_progress=progress.update, query=args.query,
                                                max_recommendations=args.n if args.n is not None else 1)
                    result = review_command.execute()
                progress.update("close")
            if not args.chat:
                progress.update("complete")
    except (MetadataError, ModelError, RepositoryError, ReviewError) as exc:
        error, status = exc, 1
        print(f"reprobe: {exc}", file=sys.stderr)
    except KeyboardInterrupt as exc:
        error, status = exc, 130
        print("reprobe: interrupted", file=sys.stderr)
    if not args.chat:
        if result is None and review_command is not None:
            result = review_command.result
        report = review_report(root, settings, result, error)
        if args.output_json == Path("-"):
            print(serialize_report(report), end="")
        else:
            color = sys.stdout.isatty() and "NO_COLOR" not in os.environ and os.environ.get("TERM") != "dumb"
            print(format_report(report, width=shutil.get_terminal_size((88, 24)).columns, color=color))
            if args.output_json is not None:
                try:
                    saved = WriteJsonReport(args.output_json, report).execute()
                except ReportWriteError as exc:
                    print(f"reprobe: {exc}", file=sys.stderr)
                    return 1
                print(f"reprobe: JSON report saved to {saved}", file=sys.stderr)
    return status
