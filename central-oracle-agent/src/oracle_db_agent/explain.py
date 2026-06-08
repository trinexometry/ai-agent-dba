"""Optional LLM explanation of any tool output.

A tool's `run()` returns an integer exit code and prints to stdout. To get
a natural-language summary of a tool run, wrap the call with
`explain_with_llm()` and feed the captured output back to the loop.

This is intentionally separate from the loop itself: a tool can opt into
explanation via the `--explain` CLI flag without changing its code.
"""

from __future__ import annotations

import os
import textwrap
from typing import Sequence

from .llm.base import ChatMessage, LlmClient


def trim_for_llm(text: str, max_chars: int = 120_000) -> str:
    if len(text) <= max_chars:
        return text
    head = text[: max_chars // 2]
    tail = text[-max_chars // 2 :]
    return f"{head}\n\n[... output trimmed ...]\n\n{tail}"


def explain_with_llm(
    *,
    llm: LlmClient,
    user_question: str,
    tool_name: str,
    tool_output: str,
) -> str:
    """Ask the LLM to summarize `tool_output` in the context of `user_question`.

    Used by the CLI's `--explain` flag and by the AWR tool's analysis path.
    """

    if os.getenv("ORACLE_AGENT_DISABLE_LLM") == "1":
        return tool_output

    prompt = textwrap.dedent(
        f"""
        You are a careful Oracle DBA. The user asked: "{user_question}".

        The tool `{tool_name}` produced the output below. Summarize it in
        plain English, focusing on what the user asked for. Be concise.
        Do not invent metrics not present in the output. If the output is
        empty or errored, say so plainly.

        ----- {tool_name} output -----
        {trim_for_llm(tool_output)}
        ----- end output -----
        """
    ).strip()

    response = llm.chat([ChatMessage(role="user", content=prompt)])
    return response.text or tool_output


def explain_many_with_llm(
    *,
    llm: LlmClient,
    user_question: str,
    sections: Sequence[tuple[str, str]],
) -> str:
    """Like `explain_with_llm` but combines multiple tool outputs."""

    joined = "\n\n".join(
        f"----- {name} -----\n{trim_for_llm(output)}" for name, output in sections
    )
    prompt = textwrap.dedent(
        f"""
        You are a careful Oracle DBA. The user asked: "{user_question}".

        Several tools were run. Synthesize the results into a single
        short answer. Do not invent metrics not present in the outputs.

        {joined}
        """
    ).strip()
    response = llm.chat([ChatMessage(role="user", content=prompt)])
    return response.text or joined
