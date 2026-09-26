"""Readable terminal presentation derived only from the structured report."""
import re
import textwrap
from typing import Any


def _text(value: object) -> str:
    # Model text and filenames must not inject terminal control sequences.
    return " ".join(re.sub(r"[\x00-\x1f\x7f-\x9f]", " ", str(value)).split())


def format_report(report: dict[str, Any], *, width: int = 88, color: bool = False) -> str:
    width = max(32, min(width, 120))
    lines: list[str] = []

    def add(text: str = "", indent: str = "", continuation: str | None = None) -> None:
        lines.extend(textwrap.wrap(_text(text), width=width, initial_indent=indent,
                                   subsequent_indent=continuation if continuation is not None else indent) or [""])

    def heading(text: str) -> None:
        lines.append("")
        lines.append(f"\x1b[1;36m{text}\x1b[0m" if color else text)

    title = "REPROBE / PRIORITY REVIEW"
    lines.append(f"\x1b[1;36m{title}\x1b[0m" if color else title)
    lines.append("=" * width)
    add(report["repository"], indent="Repository  ", continuation="            ")
    languages = ", ".join(report["languages"]) or "none detected"
    add(languages, indent="Languages   ", continuation="            ")
    coverage = report["coverage"]
    scope = "sampled / partial" if coverage["partial"] else "all discovered source included"
    if report["status"] == "error":
        scope = "attempted review; see error below"
    add(f"{coverage['reviewed_files']} / {coverage['discovered_files']} source files ({scope})",
        indent="Coverage    ", continuation="            ")
    if coverage["input_tokens"] is not None:
        add(f"{coverage['input_tokens']} / {coverage['input_budget']} available tokens",
            indent="Input       ", continuation="            ")
    if coverage["generation_attempts"]:
        add(str(coverage["generation_attempts"]), indent="Attempts    ")

    if report["status"] == "error":
        heading("REVIEW FAILED")
        for error in report["errors"]:
            add(f"{error['code']}: {error['message']}")
    elif report["status"] == "no_supported_source":
        heading("NO SUPPORTED SOURCE")
        add("No supported source files were found in this directory.")
    elif not report["recommendations"]:
        heading("NO ACTIONABLE RECOMMENDATION")
        add("The sampled source did not provide enough evidence for a useful recommendation.")
    else:
        finding = report["recommendations"][0]
        heading("TOP RECOMMENDATION")
        add(f"[{finding['priority'].upper()}] [{finding['category'].upper()}] {finding['id']}")
        add(finding["title"])
        heading("WHY THIS MATTERS / EVIDENCE")
        for item in finding["evidence"]:
            location = f"{item['path']}:{item['start_line']}"
            if item["end_line"] != item["start_line"]:
                location += f"-{item['end_line']}"
            add(location, indent="  ")
            add(item["explanation"], indent="    ")
        heading("SUGGESTED CHANGE")
        for number, step in enumerate(finding["suggested_changes"], 1):
            add(step, indent=f"  {number}. ", continuation="     ")
        heading("HOW TO VALIDATE")
        for number, step in enumerate(finding["validation_steps"], 1):
            add(step, indent=f"  {number}. ", continuation="     ")
    lines.append("")
    lines.append("-" * width)
    if coverage["partial"]:
        add("Based on a bounded source sample. See the JSON export for file ranges and omissions.")
    add("Repository files were not modified by the review.")
    return "\n".join(lines)
