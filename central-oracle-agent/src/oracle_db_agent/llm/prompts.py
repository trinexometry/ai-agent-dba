"""System prompt construction.

The prompt must list the target, license posture, the full tool catalog,
and the safety rules. It is built once per run inside `AgenticLoop`.
"""

from __future__ import annotations

import textwrap
from typing import Iterable

from ..config import DatabaseTarget
from .base import ToolSpec


SAFETY_PREAMBLE = textwrap.dedent(
    """
    You are an Oracle DBA agent operating on a single, user-confirmed target.
    You must NEVER construct or execute free-form SQL. Every database read or
    write goes through one of the registered tools. If no tool fits the
    request, say so plainly and stop.

    For mutating tools the system will pause and ask the human to approve
    the planned command before it runs. Plan the call; the gate is enforced
    outside your control. Do not attempt to bypass it.

    If a tool returns a `LicenseNotAllowedError` observation, the target is
    not licensed for the requested pack. Do not retry the same tool. Pick a
    non-licensed alternative or stop and report.

    When you have enough information, respond with a short natural-language
    answer. Do not echo raw tool output to the user. If the tool output
    contains structured data, summarize the relevant fields in plain English
    and point at the report files where appropriate.

    You have a strict step budget. If you reach it without a final answer,
    say what you have so far and what would be needed next.
    """
).strip()


def _format_tool_spec(spec: ToolSpec) -> str:
    required = spec.parameters.get("required", [])
    props = spec.parameters.get("properties", {})
    if not props:
        return f"  - {spec.name}: {spec.description} (no parameters)"
    param_lines = []
    for name, schema in props.items():
        marker = "required" if name in required else "optional"
        ptype = schema.get("type", "any")
        desc = schema.get("description", "")
        param_lines.append(f"      - {name} ({ptype}, {marker}): {desc}")
    body = "\n".join(param_lines)
    return f"  - {spec.name}: {spec.description}\n{body}"


def build_system_prompt(
    target: DatabaseTarget,
    tool_specs: Iterable[ToolSpec],
    *,
    runbook_index: str,
    max_steps: int,
) -> str:
    """Assemble the system prompt for one agent run.

    `runbook_index` is pre-rendered text describing the runbooks the agent
    can read. We pass it as a string so the caller controls the format.
    """

    policy = target.license_policy
    tool_block = "\n".join(_format_tool_spec(s) for s in tool_specs) or "  (no tools available)"

    return textwrap.dedent(
        f"""
        {SAFETY_PREAMBLE}

        ## Target

        - Scope: {target.scope_label}
        - Environment: {target.environment}
        - Diagnostics Pack licensed: {policy.diagnostics}
        - Tuning Pack licensed: {policy.tuning}
        - Step budget: {max_steps}

        ## Available tools

        Call them by name with the parameters listed below. You may call
        multiple tools in one turn; their observations will arrive together
        in the next turn.

        {tool_block}

        ## Runbooks

        The following runbooks are available under `{target.runbook_dir}`.
        Use the `list_runbooks` and `get_runbook` tools to load them by name.
        When asked to "follow" or "run" a runbook, load it with `get_runbook`
        and execute the steps by calling the appropriate tools in order.

        {runbook_index}
        """
    ).strip()
