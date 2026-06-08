from __future__ import annotations

import os
import re
import textwrap
from dataclasses import dataclass
from pathlib import Path

from .config import LlmConfig


REPORT_DIR = Path("reports")


@dataclass(frozen=True)
class AwrAnalysis:
    report_paths: list[Path]
    summary: str


IMPORTANT_SECTIONS = (
    "Load Profile",
    "Instance Efficiency Percentages",
    "Top 10 Foreground Events",
    "Top Timed Foreground Events",
    "SQL ordered by Elapsed Time",
    "SQL ordered by CPU Time",
    "SQL ordered by Gets",
    "Segments by Logical Reads",
    "Tablespace IO Stats",
)


def write_report(text: str, dbid: int, instance_number: int, begin_snap: int, end_snap: int) -> Path:
    REPORT_DIR.mkdir(exist_ok=True)
    path = REPORT_DIR / f"awr_db{dbid}_inst{instance_number}_{begin_snap}_{end_snap}.txt"
    path.write_text(text, encoding="utf-8", errors="replace")
    return path


def deterministic_awr_summary(reports: list[str]) -> str:
    combined = "\n".join(reports)
    lines = combined.splitlines()
    extracted: list[str] = []

    for section in IMPORTANT_SECTIONS:
        idx = next((i for i, line in enumerate(lines) if section.lower() in line.lower()), None)
        if idx is None:
            continue
        snippet = "\n".join(lines[idx : idx + 18]).strip()
        extracted.append(f"## {section}\n{snippet}")

    if not extracted:
        return (
            "AWR text was generated, but no known summary sections were found. "
            "Open the report files under reports/ and review wait events, load profile, "
            "top SQL, and IO sections manually."
        )

    return "\n\n".join(extracted)


def trim_for_llm(text: str, max_chars: int = 120_000) -> str:
    if len(text) <= max_chars:
        return text
    head = text[: max_chars // 2]
    tail = text[-max_chars // 2 :]
    return f"{head}\n\n[... middle of AWR text trimmed ...]\n\n{tail}"


def analyze_with_openai(reports: list[str], config: LlmConfig) -> str:
    if not os.getenv("OPENAI_API_KEY"):
        raise RuntimeError("OPENAI_API_KEY is required for --llm openai.")

    from openai import OpenAI

    client = OpenAI()
    awr_context = trim_for_llm("\n\n".join(reports))
    prompt = textwrap.dedent(
        """
        Analyze these Oracle AWR reports for a DBA. Focus on:
        - workload changes and pressure points
        - top wait events and likely causes
        - top SQL candidates to tune
        - IO, CPU, parsing, memory, and concurrency symptoms
        - concrete next checks and actions

        Be precise and do not invent metrics not present in the report.
        """
    ).strip()

    response = client.responses.create(
        model=config.model,
        input=[
            {"role": "system", "content": "You are a careful Oracle performance DBA."},
            {"role": "user", "content": f"{prompt}\n\nAWR context:\n{awr_context}"},
        ],
    )
    return response.output_text


def save_analysis(summary: str, days: int) -> Path:
    REPORT_DIR.mkdir(exist_ok=True)
    slug = re.sub(r"[^a-z0-9]+", "_", f"awr_analysis_{days}_days".lower()).strip("_")
    path = REPORT_DIR / f"{slug}.md"
    path.write_text(summary + "\n", encoding="utf-8")
    return path
