"""Compatibility exports; implementation lives in :mod:`reprobe.review.contract`."""
from reprobe.review.contract import (
    ChatReply as ChatReply,
    EVIDENCE_SCHEMA as EVIDENCE_SCHEMA,
    Evidence as Evidence,
    RECOMMENDATION_SCHEMA as RECOMMENDATION_SCHEMA,
    REVIEW_SCHEMA as REVIEW_SCHEMA,
    Recommendation as Recommendation,
    ReviewError as ReviewError,
    SourceExcerpt as SourceExcerpt,
    TEXT as TEXT,
    TEXT_LIST as TEXT_LIST,
    object_schema as object_schema,
    parse_recommendations as parse_recommendations,
)

__all__ = ['ChatReply', 'EVIDENCE_SCHEMA', 'Evidence', 'RECOMMENDATION_SCHEMA', 'REVIEW_SCHEMA', 'Recommendation', 'ReviewError', 'SourceExcerpt', 'TEXT', 'TEXT_LIST', 'object_schema', 'parse_recommendations']
