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
                "omissions": [], "partial": False, "input_tokens": None,
                "input_budget": None, "generation_attempts": 0}
    return {
        "discovered_files": len(result.inspection.candidates),
        "reviewed_files": len(result.excerpts),
        "supplied_ranges": [{"path": e.path, "start_line": 1, "end_line": e.end_line,
                            "truncated": e.truncated} for e in result.excerpts],
        "omissions": [asdict(o) for o in result.omissions],
        "partial": bool(result.omissions) or any(e.truncated for e in result.excerpts),
        "input_tokens": result.input_tokens, "input_budget": result.input_budget,
        "generation_attempts": result.generation_attempts,
    }


def _token_usage_report(result: ReviewResult | None) -> dict[str, object]:
    usages = result.token_usage if result is not None else ()
    count = result.generation_attempts if result is not None else 0
    attempts = [None if usage is None else {
        "input_tokens": usage.input_tokens, "output_tokens": usage.output_tokens,
        "total_tokens": usage.total_tokens,
    } for usage in usages]
    # Older Python callers can construct results without usage information.
    attempts.extend([None] * max(0, count - len(attempts)))
    complete = all(usage is not None for usage in attempts)
    return {
        "input_tokens": sum(u["input_tokens"] for u in attempts) if complete else None,
        "output_tokens": sum(u["output_tokens"] for u in attempts) if complete else None,
        "total_tokens": sum(u["total_tokens"] for u in attempts) if complete else None,
        "complete": complete, "attempts": attempts,
    }


def _context_usage_report(settings: ResolvedModelSettings | None,
                          usage: dict[str, object]) -> dict[str, object]:
    configured = settings.config.n_ctx if settings is not None else None
    model_max = settings.model_context_length if settings is not None else None
    attempts = []
    for number, attempt in enumerate(usage["attempts"], 1):
        used = attempt["total_tokens"] if attempt is not None else None
        attempts.append({
            "attempt": number, "used_tokens": used,
            "configured_context_percent": round(100 * used / configured, 2)
                if used is not None and configured is not None else None,
            "model_context_percent": round(100 * used / model_max, 2)
                if used is not None and model_max is not None else None,
            "remaining_context_tokens": max(0, configured - used)
                if used is not None and configured is not None else None,
        })
    return {"configured_context_tokens": configured,
            "model_context_tokens": model_max, "attempts": attempts}


def review_report(repository: Path | str, settings: ResolvedModelSettings | None = None,
                  result: ReviewResult | None = None,
                  error: BaseException | None = None) -> dict[str, object]:
    status = "completed"
    if result is not None and not result.inspection.is_codebase:
        status = "no_supported_source"
    if error is not None:
        status = "error"
    usage = _token_usage_report(result)
    return {
        "schema_version": "1.0", "status": status,
        "repository": str(result.inspection.root if result is not None else repository),
        "languages": list(result.inspection.languages) if result is not None else [],
        "model": _model_report(settings), "coverage": _coverage_report(result),
        "token_usage": usage,
        "context_usage": _context_usage_report(settings, usage),
        "recommendations": [asdict(r) for r in result.recommendations] if result is not None and error is None else [],
        "errors": [{"code": type(error).__name__, "message": str(error) or type(error).__name__}] if error is not None else [],
    }
