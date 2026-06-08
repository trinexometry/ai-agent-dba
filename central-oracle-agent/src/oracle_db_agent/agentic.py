"""The agentic loop.

This is where the LLM becomes the decision-maker. The loop:

  1. Builds a system prompt describing the target, the tool catalog, and
     the safety rules.
  2. Calls the LLM with the current conversation.
  3. For each tool call the LLM requests:
       - resolves the tool by name
       - if the tool requires approval, asks the human
       - invokes the tool with parsed arguments
       - records the observation back into the conversation
  4. Repeats until the LLM produces a final answer or the budget is hit.

The loop is `LlmClient`-agnostic; tests pass a fake client that returns
scripted responses.
"""

from __future__ import annotations

import datetime as _dt
import io
import json
import logging
import sys
import time
import uuid
from contextlib import redirect_stdout
from dataclasses import dataclass
from typing import Any

from .approval import ApprovalRequest, ask_approval
from .audit import AuditLog
from .license import LicenseNotAllowedError, require_diagnostics, require_tuning
from .llm import ChatMessage, LlmClient, OllamaClient, ToolSpec, build_system_prompt
from .loop_control import BudgetExceeded, LoopBudget, remaining_seconds
from .runbooks import RunbookStore
from .tools.base import ToolContext
from .tools.runbook_tools import get_runbook_for_loop, list_runbooks_for_loop
from .tools.registry import ToolRegistry

log = logging.getLogger(__name__)


# A short prefix the LLM can use to indicate "I am done, this is the
# final answer". We accept plain assistant messages without tool calls as
# final answers too, so this is optional.
FINAL_ANSWER_TAG = "FINAL_ANSWER:"


@dataclass(frozen=True)
class LoopResult:
    answer: str
    steps_used: int
    final: bool
    budget_exceeded: bool


class AgenticLoop:
    """The ReAct-style loop.

    Construct once per run, call `run(prompt)`. The constructor takes
    everything the loop needs so the CLI can wire it up in one place.
    """

    def __init__(
        self,
        *,
        db,  # oracle_db_agent.db.OracleClient
        options,  # oracle_db_agent.agent_options.AgentOptions
        registry: ToolRegistry,
        llm: LlmClient | None,
        audit: AuditLog,
        budget: LoopBudget | None = None,
    ) -> None:
        self.db = db
        self.options = options
        self.registry = registry
        self.llm = llm
        self.audit = audit
        self.budget = budget or LoopBudget()

    # ------------------------------------------------------------------ run

    def run(self, prompt: str) -> int:
        self.audit.record(0, "run_started", {"prompt": prompt[:500]})
        if self.llm is None:
            # LLM disabled at the CLI level. Fall back to the keyword router
            # so the operator can still get something useful out of v1.
            self.audit.record(0, "fallback_keyword_router", {})
            return self._fallback_keyword_router(prompt)

        runbook_index = RunbookStore(self.options.target.runbook_dir).index_text()
        tool_specs = self._build_tool_specs()
        system_prompt = build_system_prompt(
            self.options.target,
            tool_specs,
            runbook_index=runbook_index,
            max_steps=self.budget.max_steps,
        )
        messages: list[ChatMessage] = [
            ChatMessage(role="system", content=system_prompt),
            ChatMessage(role="user", content=prompt),
        ]

        started = time.monotonic()
        for step in range(1, self.budget.max_steps + 1):
            if remaining_seconds(self.budget, started) <= 0:
                self.audit.record(step, "wall_time_exceeded", {})
                print("Step wall-time budget exceeded. Stopping.")
                return 4

            self.audit.record(step, "llm_call", {})
            try:
                response = self.llm.chat(messages, tools=tool_specs)
            except Exception as exc:  # noqa: BLE001 — broad on purpose
                self.audit.record(step, "llm_error", {"error": str(exc)})
                if self.budget.max_retries_per_step < 1:
                    print(f"LLM call failed: {exc}")
                    return 4
                self.budget = LoopBudget(
                    max_steps=self.budget.max_steps,
                    max_wall_seconds=self.budget.max_wall_seconds,
                    max_retries_per_step=self.budget.max_retries_per_step - 1,
                )
                continue

            # Wall-time check after the chat returns. A slow chat on the
            # last step must still result in a clean exit.
            if remaining_seconds(self.budget, started) <= 0:
                self.audit.record(step, "wall_time_exceeded", {})
                print("Step wall-time budget exceeded. Stopping.")
                return 4

            if response.is_final_answer:
                self.audit.record(step, "final_answer", {"text": response.text})
                self.audit.finish(response.text)
                print(response.text)
                return 0

            # The model produced tool calls. Execute them, append observations.
            assistant = ChatMessage(
                role="assistant",
                content=response.text,
                tool_calls=response.tool_calls,
            )
            messages.append(assistant)

            for call in response.tool_calls:
                observation = self._invoke_tool(step, call)
                messages.append(observation)

        self.audit.record(self.budget.max_steps + 1, "step_limit_reached", {})
        print(
            "Step limit reached without a final answer. "
            "Raise --max-steps or simplify the request."
        )
        return 3

    # --------------------------------------------------------------- helpers

    def _build_tool_specs(self) -> list[ToolSpec]:
        return [
            ToolSpec(
                name=tool.name,
                description=tool.description,
                parameters=tool.parameters,
            )
            for tool in self.registry.tools
        ]

    def _invoke_tool(self, step: int, call) -> ChatMessage:
        tool = self.registry.get(call.name)
        if tool is None:
            self.audit.record(step, "tool_unknown", {"name": call.name})
            return self._observation_message(
                call,
                error=f"Unknown tool '{call.name}'. Use one of: {', '.join(self.registry.names())}.",
            )

        # License pack gate. We check by name against a small map of
        # tool -> (gate, feature). Adding a new gated tool means adding
        # to the map, not editing the loop.
        gate = _LICENSE_GATES.get(tool.name)
        if gate is not None:
            gate_name, feature = gate
            try:
                if gate_name == "diagnostics":
                    require_diagnostics(self.options.target, feature)
                elif gate_name == "tuning":
                    require_tuning(self.options.target, feature)
            except LicenseNotAllowedError as exc:
                self.audit.record(step, "license_blocked", {"tool": tool.name, "error": str(exc)})
                return self._observation_message(call, error=str(exc))

        # Approval gate.
        if tool.requires_approval:
            command_preview = self._preview_command(tool, call.arguments)
            ok = ask_approval(
                ApprovalRequest(
                    title=f"Run tool '{tool.name}'",
                    details=f"Tool: {tool.name}\nArguments: {json.dumps(call.arguments)}",
                    command=command_preview,
                    mutating=True,
                ),
                assume_yes=self.options.assume_yes
                and not self.options.target.require_mutation_approval,
            )
            if not ok:
                self.audit.record(step, "approval_denied", {"tool": tool.name})
                return self._observation_message(call, error="User did not approve; tool not executed.")

        # Run the tool, capturing stdout so the agentic loop can re-attach
        # the printed rows to the conversation as an observation.
        buffer = io.StringIO()
        context = ToolContext(db=self.db, options=self.options, run_id=self.audit.run_id)
        try:
            with redirect_stdout(buffer):
                rc = tool.run_with_arguments(call.arguments, context)
        except Exception as exc:  # noqa: BLE001
            self.audit.record(
                step,
                "tool_error",
                {"tool": tool.name, "error": str(exc)},
            )
            return self._observation_message(call, error=f"Tool '{tool.name}' raised: {exc}")

        output = buffer.getvalue().strip()
        self.audit.record(
            step,
            "tool_ok",
            {"tool": tool.name, "rc": rc, "output_chars": len(output)},
        )
        if not output:
            output = f"(tool {tool.name} returned no output, exit code {rc})"
        return self._observation_message(call, content=output[:8000])

    def _observation_message(self, call, *, content: str = "", error: str = "") -> ChatMessage:
        text = content if not error else f"ERROR: {error}"
        return ChatMessage(
            role="tool",
            content=text,
            tool_call_id=call.name,  # Ollama uses the function name as id
        )

    def _preview_command(self, tool, arguments: dict[str, Any]) -> str:
        # Best-effort, human-readable preview. We don't claim it's the
        # exact SQL the tool will run; the operator can always say no.
        try:
            if tool.name == "unlock_user" and arguments.get("username"):
                return f"alter user {arguments['username']} account unlock"
            if tool.name == "lock_user" and arguments.get("username"):
                return f"alter user {arguments['username']} account lock"
            if tool.name == "kill_session" and arguments.get("sid") is not None:
                return f"alter system kill session '{arguments['sid']},{arguments['serial']}' immediate"
        except Exception:
            pass
        return json.dumps(arguments, sort_keys=True)

    def _fallback_keyword_router(self, prompt: str) -> int:
        selection = self.registry.select(prompt)
        if selection is None:
            print("I could not map that prompt to a supported operation.")
            self.registry.print_supported_tools()
            return 2
        context = ToolContext(db=self.db, options=self.options, run_id=self.audit.run_id)
        return selection.tool.run(prompt, context)


# --------------------------------------------------------------- run helper

# Map of tool name -> (gate, feature string for the error message)
_LICENSE_GATES: dict[str, tuple[str, str]] = {
    "analyze_awr": ("diagnostics", "AWR report generation"),
}


def build_ollama_loop(
    *,
    db,
    options,
    registry: ToolRegistry,
    audit_dir,
) -> AgenticLoop:
    """Construct the loop with the Ollama client wired in.

    Convenience for the CLI. `options` is the same dataclass as before,
    extended with `llm_provider`, `ollama_url`, `ollama_model`, `max_steps`.
    """

    if options.llm_provider == "ollama":
        llm: LlmClient | None = OllamaClient(
            base_url=options.ollama_url,
            model=options.ollama_model,
        )
    else:
        llm = None
    run_id = _dt.datetime.now(_dt.timezone.utc).strftime("%Y%m%dT%H%M%S") + "-" + uuid.uuid4().hex[:6]
    audit = AuditLog(audit_dir=audit_dir, run_id=run_id)
    budget = LoopBudget(max_steps=options.max_steps)
    return AgenticLoop(
        db=db,
        options=options,
        registry=registry,
        llm=llm,
        audit=audit,
        budget=budget,
    )


__all__ = ["AgenticLoop", "LoopResult", "build_ollama_loop"]
