"""Stable review JSON contract; never serialize raw backend responses."""
from dataclasses import asdict
from pathlib import Path

from reprobe.models.settings import ResolvedModelSettings
from reprobe.review.types import ReviewResult


def _model_report(settings: ResolvedModelSettings | None) -> dict[str, object] | None:
    if settings is None:
        return None
    return {
        "path": str(settings.config.model_path), "architecture": settings.architecture,
        "training_context_tokens": settings.model_context_length,
        "context_tokens": settings.config.n_ctx, "output_tokens": settings.config.max_tokens,
        "context_source": settings.context_source, "output_source": settings.output_source,
        "diagnostics": list(settings.diagnostics),
    }


def _coverage_report(result: ReviewResult | None) -> dict[str, object]:
    if result is None:
        return {"discovered_files": 0, "reviewed_files": 0, "supplied_ranges": [],
                "omissions": [], "partial": False}
    return {
        "discovered_files": len(result.inspection.candidates),
        "reviewed_files": len(result.excerpts),
        "supplied_ranges": [{"path": e.path, "start_line": 1, "end_line": e.end_line,
                            "truncated": e.truncated} for e in result.excerpts],
        "omissions": [asdict(o) for o in result.omissions],
        "partial": bool(result.omissions) or any(e.truncated for e in result.excerpts),
    }


def review_report(repository: Path | str, settings: ResolvedModelSettings | None = None,
                  result: ReviewResult | None = None,
                  error: BaseException | None = None) -> dict[str, object]:
    status = "completed"
    if result is not None and not result.inspection.is_codebase:
        status = "no_supported_source"
    if error is not None:
        status = "error"
    return {
        "schema_version": "1.0", "status": status,
        "repository": str(result.inspection.root if result is not None else repository),
        "languages": list(result.inspection.languages) if result is not None else [],
        "model": _model_report(settings), "coverage": _coverage_report(result),
        "recommendations": [asdict(r) for r in result.recommendations] if result is not None and error is None else [],
        "errors": [{"code": type(error).__name__, "message": str(error) or type(error).__name__}] if error is not None else [],
    }
