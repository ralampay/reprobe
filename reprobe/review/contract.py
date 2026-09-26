"""Review response schema, parsing, and supplied-evidence validation."""
import json
from typing import Any

from reprobe.chat.types import ChatReply
from reprobe.review.types import Evidence, Recommendation, ReviewError, SourceExcerpt


def object_schema(properties: dict[str, Any]) -> dict[str, Any]:
    return {"type": "object", "properties": properties,
            "required": list(properties), "additionalProperties": False}


TEXT = {"type": "string", "minLength": 1}
TEXT_LIST = {"type": "array", "minItems": 1, "items": TEXT}
EVIDENCE_SCHEMA = object_schema({
    "path": TEXT, "start_line": {"type": "integer", "minimum": 1},
    "end_line": {"type": "integer", "minimum": 1}, "explanation": TEXT,
})
RECOMMENDATION_SCHEMA = object_schema({
    "category": {"type": "string", "enum": ["fix", "improvement", "feature"]},
    "priority": {"type": "string", "enum": ["high", "medium", "low"]},
    "title": TEXT,
    "evidence": {"type": "array", "minItems": 1, "items": EVIDENCE_SCHEMA},
    "suggested_changes": TEXT_LIST, "validation_steps": TEXT_LIST,
})
REVIEW_SCHEMA = object_schema({"recommendations": {
    "type": "array", "maxItems": 3, "items": RECOMMENDATION_SCHEMA,
}})


def _validate(value: object, schema: dict[str, Any]) -> None:
    kind = schema["type"]
    if kind == "object":
        if not isinstance(value, dict) or set(value) != set(schema["properties"]):
            raise ValueError("unexpected or missing object fields")
        for key, child in schema["properties"].items():
            _validate(value[key], child)
    elif kind == "array":
        if not isinstance(value, list) or not schema.get("minItems", 0) <= len(value) <= schema.get("maxItems", float("inf")):
            raise ValueError("invalid array length or type")
        for item in value:
            _validate(item, schema["items"])
    elif kind == "string":
        if not isinstance(value, str) or not value.strip():
            raise ValueError("expected nonempty text")
        if "enum" in schema and value not in schema["enum"]:
            raise ValueError("unsupported category or priority")
    elif kind == "integer":
        if type(value) is not int or value < schema["minimum"]:
            raise ValueError("invalid line number")


def parse_recommendations(reply: ChatReply, excerpts: tuple[SourceExcerpt, ...]) -> tuple[Recommendation, ...]:
    if reply.finish_reason != "stop":
        raise ReviewError("Review output was truncated; increase --max-tokens (and --n-ctx if needed).")
    try:
        data = json.loads(reply.content)
        _validate(data, REVIEW_SCHEMA)
        ranges = {e.path: e.end_line for e in excerpts}
        results = []
        for index, item in enumerate(data["recommendations"], 1):
            evidence = []
            for citation in item["evidence"]:
                if citation["path"] not in ranges or not 1 <= citation["start_line"] <= citation["end_line"] <= ranges[citation["path"]]:
                    raise ValueError("evidence refers to source lines not supplied to the model")
                evidence.append(Evidence(**citation))
            results.append(Recommendation(
                f"R{index:03}", item["category"], item["priority"], item["title"],
                tuple(evidence), tuple(item["suggested_changes"]), tuple(item["validation_steps"]),
            ))
        return tuple(results)
    except (ValueError, TypeError, KeyError) as exc:
        raise ReviewError(f"Invalid structured review: {exc}. Check model/chat-template compatibility.") from exc
