"""Compatibility exports; implementation lives in :mod:`reprobe.output.json_report`."""
from reprobe.output.json_report import (
    ResolvedModelSettings as ResolvedModelSettings,
    ReviewResult as ReviewResult,
    review_report as review_report,
)

__all__ = ['ResolvedModelSettings', 'ReviewResult', 'review_report']
