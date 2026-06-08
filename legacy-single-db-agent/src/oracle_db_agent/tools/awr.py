from __future__ import annotations

from oracle_db_agent.approval import ApprovalRequest, ask_approval
from oracle_db_agent.config import LlmConfig
from oracle_db_agent.db import group_snapshots_by_instance
from oracle_db_agent.reporting import (
    AwrAnalysis,
    analyze_with_openai,
    deterministic_awr_summary,
    save_analysis,
    write_report,
)

from .base import ToolContext, ToolMatch
from .parsing import extract_days


class AnalyzeAwrTool:
    name = "analyze_awr"
    description = "Generate AWR report text for the past N days and produce a DBA analysis."
    examples = ("analyze past 4 days database report",)
    mutating = False

    def match(self, prompt: str) -> ToolMatch | None:
        text = prompt.lower()
        if "awr" in text:
            return ToolMatch(confidence=95)
        if "report" in text and "analy" in text:
            return ToolMatch(confidence=85)
        return None

    def run(self, prompt: str, context: ToolContext) -> int:
        days = extract_days(prompt)
        snapshots = context.db.get_recent_snapshots(days)
        grouped = group_snapshots_by_instance(snapshots)
        usable_ranges = [
            (dbid, inst, items[0].snap_id, items[-1].snap_id, len(items))
            for (dbid, inst), items in grouped.items()
            if len(items) >= 2
        ]

        if not usable_ranges:
            print(f"No usable AWR snapshot range found for the past {days} day(s).")
            return 1

        details = [
            f"DBID {dbid}, instance {inst}, snapshots {begin_snap}-{end_snap} ({count} snapshots)"
            for dbid, inst, begin_snap, end_snap, count in usable_ranges
        ]
        command = "\n".join(
            "select output from table(dbms_workload_repository.awr_report_text("
            f"{dbid}, {inst}, {begin_snap}, {end_snap}));"
            for dbid, inst, begin_snap, end_snap, _ in usable_ranges
        )

        approved = ask_approval(
            ApprovalRequest(
                title=f"Generate and analyze AWR reports for past {days} day(s)",
                details="\n".join(details),
                command=command,
                mutating=False,
            ),
            assume_yes=context.options.assume_yes,
        )
        if not approved:
            print("Cancelled. No AWR reports were generated.")
            return 1
        if context.options.dry_run:
            print("Dry run enabled. No AWR reports were generated.")
            return 0

        analysis = self._generate_awr_analysis(context, days, usable_ranges)
        print()
        print("AWR analysis complete.")
        print("Report files:")
        for path in analysis.report_paths:
            print(f"- {path}")
        analysis_path = save_analysis(analysis.summary, days)
        print(f"Analysis file: {analysis_path}")
        print()
        print(analysis.summary)
        return 0

    def _generate_awr_analysis(
        self,
        context: ToolContext,
        days: int,
        ranges: list[tuple[int, int, int, int, int]],
    ) -> AwrAnalysis:
        reports: list[str] = []
        paths = []
        for dbid, inst, begin_snap, end_snap, _ in ranges:
            text = context.db.generate_awr_report_text(dbid, inst, begin_snap, end_snap)
            reports.append(text)
            paths.append(write_report(text, dbid, inst, begin_snap, end_snap))

        if context.options.llm_provider == "openai":
            summary = analyze_with_openai(reports, LlmConfig.from_env("openai"))
        else:
            summary = deterministic_awr_summary(reports)

        heading = f"# AWR Analysis - Past {days} Day(s)\n\n"
        return AwrAnalysis(report_paths=paths, summary=heading + summary)
