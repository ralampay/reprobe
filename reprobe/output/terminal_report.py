"""Readable terminal presentation derived only from the structured report."""
import re
from io import StringIO

from rich import box
from rich.console import Console, Group
from rich.panel import Panel
from rich.table import Table
from rich.text import Text
from typing import Any


def _text(value: object) -> str:
    # Model text and filenames must not inject terminal control sequences.
    return " ".join(re.sub(r"[\x00-\x1f\x7f-\x9f]", " ", str(value)).split())


def _item_card(finding: dict[str, Any], rank: int, total: int) -> Panel:
    accent = {"high": "red", "medium": "yellow", "low": "cyan"}.get(finding["priority"], "cyan")
    body = [Text(_text(finding["title"]), style="bold"),
            Text(f"[{_text(finding['priority']).upper()}] [{_text(finding['category']).upper()}]  "
                 f"{_text(finding['id'])}  |  PROPOSED", style=accent)]

    def section(label: str) -> None:
        body.extend([Text(""), Text(label, style="bold cyan")])

    if finding.get("synopsis"):
        section("SYNOPSIS")
        body.append(Text(_text(finding["synopsis"])))
    section("WHY THIS MATTERS / EVIDENCE")
    for item in finding["evidence"]:
        location = f"{item['path']}:{item['start_line']}"
        if item["end_line"] != item["start_line"]:
            location += f"-{item['end_line']}"
        body.append(Text(_text(location), style="bold"))
        body.append(Text(_text(item["explanation"]), style="dim"))
    for label, key in (("SUGGESTED CHANGE", "suggested_changes"),
                       ("HOW TO VALIDATE", "validation_steps")):
        section(label)
        checklist = Table.grid(padding=(0, 1), expand=True)
        checklist.add_column(width=3, no_wrap=True)
        checklist.add_column(ratio=1, overflow="fold")
        for step in finding[key]:
            checklist.add_row(Text("[ ]", style=accent), Text(_text(step)))
        body.append(checklist)
    return Panel(Group(*body), title=Text(f"ITEM {rank} OF {total}", style="bold"),
                 title_align="left", border_style=accent, box=box.ROUNDED, padding=(1, 2))


def format_report(report: dict[str, Any], *, width: int = 88, color: bool = False) -> str:
    width = max(32, min(width, 120))
    summary = Table.grid(padding=(0, 1), expand=True)
    summary.add_column(style="bold cyan", width=12)
    summary.add_column(ratio=1, overflow="fold")

    def add(text: str = "", indent: str = "") -> None:
        summary.add_row(Text(indent.strip()), Text(_text(text)))

    add(report["repository"], indent="Repository  ")
    languages = ", ".join(report["languages"]) or "none detected"
    add(languages, indent="Languages   ")
    coverage = report["coverage"]
    scope = "sampled / partial" if coverage["partial"] else "all discovered files included"
    if report["status"] == "error":
        scope = "attempted review; see error below"
    add(f"{coverage['reviewed_files']} / {coverage['discovered_files']} code or instruction files ({scope})",
        indent="Coverage    ")
    model = report.get("model")
    if model is not None:
        maximum = model["training_context_tokens"]
        add(f"{maximum:,} tokens (GGUF training context)" if maximum is not None
            else "Unknown (GGUF context metadata absent)",
            indent="Model max   ")
        add(f"{model['context_tokens']:,} tokens configured; "
            f"{model['output_tokens']:,} output token limit",
            indent="Context     ")
    else:
        add("Unavailable (model settings not resolved)", indent="Model max   ")
    if coverage["input_tokens"] is not None:
        add(f"{coverage['input_tokens']} / {coverage['input_budget']} available tokens",
            indent="Preflight   ")
    if coverage["generation_attempts"]:
        add(str(coverage["generation_attempts"]), indent="Attempts    ")

    usage = report.get("token_usage")
    if usage is not None and usage["complete"]:
        add(f"{usage['total_tokens']:,} total ({usage['input_tokens']:,} input + "
            f"{usage['output_tokens']:,} output; all attempts)",
            indent="Tokens used ")
    else:
        add("Unavailable (backend usage missing for one or more attempts)",
            indent="Tokens used ")

    context_usage = report.get("context_usage")
    if context_usage is not None:
        for attempt in context_usage["attempts"]:
            number = attempt["attempt"]
            if attempt["configured_context_percent"] is None:
                detail = f"Attempt {number}: unavailable"
            else:
                detail = (f"Attempt {number}: {attempt['used_tokens']:,} / "
                          f"{context_usage['configured_context_tokens']:,} tokens "
                          f"({attempt['configured_context_percent']:.2f}% configured")
                if attempt["model_context_percent"] is not None:
                    detail += f"; {attempt['model_context_percent']:.2f}% model max"
                detail += ")"
            add(detail, indent="Context used ")
        if not context_usage["attempts"]:
            add("0 tokens (no inference attempts)", indent="Context used ")

    output = StringIO()
    console = Console(file=output, width=width, force_terminal=color,
                      force_jupyter=False, color_system="standard" if color else None,
                      no_color=not color, markup=False, highlight=False, emoji=False)
    console.print(Text("REPROBE / PRIORITY REVIEW", style="bold cyan"))
    console.print(summary)
    console.print()
    if report["status"] == "error":
        message = Text("\n".join(_text(f"{error['code']}: {error['message']}")
                                  for error in report["errors"]))
        console.print(Panel(message, title=Text("REVIEW FAILED"), border_style="red"))
    elif report["status"] == "no_supported_source":
        console.print(Panel(Text("No supported code or instruction files were found in this directory."),
                            title=Text("NO SUPPORTED SOURCE"), border_style="cyan"))
    elif not report["recommendations"]:
        console.print(Panel(Text("The sampled content did not provide enough evidence for a useful recommendation."),
                            title=Text("NO ACTIONABLE RECOMMENDATION"), border_style="cyan"))
    else:
        for rank, finding in enumerate(report["recommendations"], 1):
            console.print(_item_card(finding, rank, len(report["recommendations"])))
            console.print()
    if coverage["partial"]:
        console.print(Text("Based on a bounded repository sample. See the JSON export for file ranges and omissions.", style="dim"))
    console.print(Text("Repository files were not modified by the review.", style="dim"))
    return output.getvalue().rstrip("\n")
