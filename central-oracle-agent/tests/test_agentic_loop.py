"""Tests for the agentic loop.

Uses a fake `LlmClient` that returns scripted `LlmResponse` objects. No
network, no real LLM, no real Oracle connection.

Assertion strategy: the loop's job is to drive a conversation. The
"user-visible" stdout is just the final answer; the rest of the action
is in the `messages` list passed back to the LLM. The tests assert
against the messages recorded in the fake LLM.
"""

from __future__ import annotations

import io
import re
from contextlib import redirect_stdout
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import pytest

from oracle_db_agent.agent_options import AgentOptions
from oracle_db_agent.agentic import AgenticLoop
from oracle_db_agent.audit import AuditLog
from oracle_db_agent.config import DatabaseTarget
from oracle_db_agent.llm import ChatMessage, LlmClient, LlmResponse, ToolCall
from oracle_db_agent.loop_control import LoopBudget
from oracle_db_agent.tools._compat import BaseDbTool
from oracle_db_agent.tools.registry import ToolRegistry


# --------------------------------------------------------------- fakes


@dataclass
class FakeLlm(LlmClient):
    """Returns scripted responses in order; raises if asked for more.

    Records every `chat()` call so tests can assert on the conversation.
    """

    responses: list[LlmResponse]
    calls: list[dict[str, Any]] = field(default_factory=list)

    def chat(self, messages, tools=None):
        self.calls.append(
            {
                "messages": list(messages),
                "tools": [t.name for t in (tools or [])],
            }
        )
        if not self.responses:
            raise AssertionError("FakeLlm asked for more responses than scripted")
        return self.responses.pop(0)


class FakeDb:
    """Stub that records calls; satisfies the methods our test tools use."""

    def __init__(self) -> None:
        self.calls: list[tuple[str, dict]] = []

    def get_user_status(self, username: str):
        self.calls.append(("get_user_status", {"username": username}))
        return None


# --------------------------------------------------------------- tools


class EchoTool(BaseDbTool):
    name = "echo"
    description = "Echo the given message."
    examples = ("echo hello",)
    mutating = False
    requires_approval = False
    parameters = {
        "type": "object",
        "properties": {"message": {"type": "string"}},
        "required": ["message"],
    }

    def match(self, prompt: str):
        return None

    def run(self, prompt, context):
        return 0

    def run_with_arguments(self, arguments, context):
        print(arguments.get("message", ""))
        return 0


class MutatingTool(BaseDbTool):
    name = "do_mutation"
    description = "Pretend to mutate something."
    examples = ("do mutation",)
    mutating = True
    requires_approval = True
    parameters = {
        "type": "object",
        "properties": {"target": {"type": "string"}},
        "required": ["target"],
    }

    def __init__(self) -> None:
        self.invocations: list[dict] = []

    def match(self, prompt: str):
        return None

    def run(self, prompt, context):
        return 0

    def run_with_arguments(self, arguments, context):
        self.invocations.append(dict(arguments))
        print(f"mutated {arguments.get('target')}")
        return 0


# --------------------------------------------------------------- helpers


def make_target(**overrides) -> DatabaseTarget:
    base = dict(
        name="t1",
        database_name="FREE",
        hostname="localhost",
        dsn="localhost:1521/FREE",
        username_env="U",
        password_env="P",
        mode=None,
        environment="dev",
        require_start_confirmation=True,
        require_mutation_approval=True,
        require_typed_scope_confirmation=False,
        diagnostics_pack_enabled=True,
        tuning_pack_enabled=False,
        runbook_dir="./runbooks",
        ollama_url="http://localhost:11434",
        ollama_model="llama3.1:8b",
    )
    base.update(overrides)
    return DatabaseTarget(**base)


def make_options(target=None, **overrides) -> AgentOptions:
    # Allow overriding assume_yes or any other field
    target = target if target is not None else make_target()
    return AgentOptions(target=target, **overrides)


def make_loop(
    llm: LlmClient | None,
    db: Any = None,
    registry: ToolRegistry | None = None,
    options: AgentOptions | None = None,
    audit_dir: Path | None = None,
    budget: LoopBudget | None = None,
) -> tuple[AgenticLoop, AuditLog, FakeDb]:
    audit_dir = audit_dir or Path("audit-test")
    audit_dir.mkdir(parents=True, exist_ok=True)
    audit = AuditLog(audit_dir=audit_dir, run_id="test")
    options = options or make_options(audit_dir=audit_dir)
    registry = registry or ToolRegistry([EchoTool()])
    db = db or FakeDb()
    loop = AgenticLoop(
        db=db,
        options=options,
        registry=registry,
        llm=llm,
        audit=audit,
        budget=budget,
    )
    return loop, audit, db


def run_loop(loop: AgenticLoop, prompt: str = "hi") -> tuple[str, int]:
    buf = io.StringIO()
    with redirect_stdout(buf):
        rc = loop.run(prompt)
    return buf.getvalue(), rc


def _last_conversation(llm: FakeLlm) -> list[ChatMessage]:
    if not llm.calls:
        return []
    return llm.calls[-1]["messages"]


def _tool_messages(messages: list[ChatMessage]) -> list[ChatMessage]:
    return [m for m in messages if m.role == "tool"]


# --------------------------------------------------------------- tests


def test_final_answer_path() -> None:
    llm = FakeLlm(responses=[LlmResponse(text="hello user", tool_calls=())])
    loop, audit, _ = make_loop(llm)
    out, rc = run_loop(loop)
    assert rc == 0
    assert "hello user" in out
    assert audit.path.exists()


def test_tool_call_chain() -> None:
    llm = FakeLlm(
        responses=[
            LlmResponse(
                text="thinking",
                tool_calls=(ToolCall(name="echo", arguments={"message": "first"}),),
            ),
            LlmResponse(
                text="thinking more",
                tool_calls=(ToolCall(name="echo", arguments={"message": "second"}),),
            ),
            LlmResponse(text="done", tool_calls=()),
        ]
    )
    loop, _, _ = make_loop(llm)
    out, rc = run_loop(loop)
    assert rc == 0
    # Final answer reaches the user.
    assert "done" in out
    # The tool messages in the final conversation contain the tool output.
    tool_msgs = _tool_messages(_last_conversation(llm))
    assert any("first" in m.content for m in tool_msgs)
    assert any("second" in m.content for m in tool_msgs)


def test_unknown_tool_returns_observation() -> None:
    llm = FakeLlm(
        responses=[
            LlmResponse(
                text="trying",
                tool_calls=(ToolCall(name="no_such_tool", arguments={}),),
            ),
            LlmResponse(text="ok", tool_calls=()),
        ]
    )
    loop, _, _ = make_loop(llm)
    out, rc = run_loop(loop)
    assert rc == 0
    tool_msgs = _tool_messages(_last_conversation(llm))
    assert any("Unknown tool" in m.content for m in tool_msgs)


def test_approval_gate_called_for_mutating_tool(monkeypatch) -> None:
    """When the model asks for a mutating tool, the loop must call
    `ask_approval` before invoking it."""
    approval_calls: list[bool] = []

    def fake_ask_approval(request, assume_yes=False):
        approval_calls.append(assume_yes)
        return True

    monkeypatch.setattr("oracle_db_agent.agentic.ask_approval", fake_ask_approval)

    mt = MutatingTool()
    llm = FakeLlm(
        responses=[
            LlmResponse(
                text="ok",
                tool_calls=(ToolCall(name="do_mutation", arguments={"target": "X"}),),
            ),
            LlmResponse(text="done", tool_calls=()),
        ]
    )
    loop, _, _ = make_loop(llm, registry=ToolRegistry([mt]))
    out, rc = run_loop(loop)
    assert rc == 0
    assert len(approval_calls) == 1
    assert mt.invocations == [{"target": "X"}]


def test_approval_denied_does_not_invoke_tool(monkeypatch) -> None:
    monkeypatch.setattr("oracle_db_agent.agentic.ask_approval", lambda *a, **k: False)

    mt = MutatingTool()
    llm = FakeLlm(
        responses=[
            LlmResponse(
                text="",
                tool_calls=(ToolCall(name="do_mutation", arguments={"target": "X"}),),
            ),
            LlmResponse(text="ok", tool_calls=()),
        ]
    )
    loop, _, _ = make_loop(llm, registry=ToolRegistry([mt]))
    out, rc = run_loop(loop)
    assert rc == 0
    assert mt.invocations == []
    tool_msgs = _tool_messages(_last_conversation(llm))
    assert any("did not approve" in m.content for m in tool_msgs)


def test_license_gate_blocks_awr_when_diagnostics_disabled() -> None:
    target = make_target(diagnostics_pack_enabled=False)
    options = make_options(target=target)
    llm = FakeLlm(
        responses=[
            LlmResponse(
                text="",
                tool_calls=(ToolCall(name="analyze_awr", arguments={"days": 1}),),
            ),
            LlmResponse(text="ok", tool_calls=()),
        ]
    )

    class AwrRecorder(BaseDbTool):
        name = "analyze_awr"
        description = "x"
        examples = ()
        mutating = False
        requires_approval = False
        parameters = {"type": "object", "properties": {"days": {"type": "integer"}}}

        def match(self, p):
            return None

        def run(self, p, ctx):
            return 0

        def run_with_arguments(self, args, ctx):
            raise AssertionError("AWR tool should not have been called")

    loop, _, _ = make_loop(llm, registry=ToolRegistry([AwrRecorder()]), options=options)
    out, rc = run_loop(loop)
    assert rc == 0
    tool_msgs = _tool_messages(_last_conversation(llm))
    assert any("Diagnostics Pack" in m.content for m in tool_msgs)


def test_step_limit_reached() -> None:
    llm = FakeLlm(
        responses=[
            LlmResponse(
                text="",
                tool_calls=(ToolCall(name="echo", arguments={"message": "loop"}),),
            )
        ] * 10
    )
    loop, _, _ = make_loop(llm, budget=LoopBudget(max_steps=2))
    out, rc = run_loop(loop)
    assert rc == 3
    assert "Step limit reached" in out


def test_wall_time_budget() -> None:
    """Wall time budget returns exit code 4."""

    class SlowLlm(LlmClient):
        def chat(self, messages, tools=None):
            import time as _t

            _t.sleep(0.05)
            return LlmResponse(text="slow", tool_calls=())

    loop, _, _ = make_loop(SlowLlm(), budget=LoopBudget(max_steps=10, max_wall_seconds=0.01))
    out, rc = run_loop(loop)
    assert rc == 4


def test_llm_error_returns_code_4(monkeypatch) -> None:
    class BoomLlm(LlmClient):
        def chat(self, messages, tools=None):
            raise RuntimeError("boom")

    loop, _, _ = make_loop(
        BoomLlm(), budget=LoopBudget(max_steps=2, max_retries_per_step=0)
    )
    out, rc = run_loop(loop)
    assert rc == 4
    assert "boom" in out


def test_fallback_keyword_router_when_no_llm() -> None:
    """When `llm` is None, the loop falls back to the keyword router."""

    class Echo:
        name = "echo"
        description = "echo"
        examples = ()
        mutating = False
        requires_approval = False
        parameters = {"type": "object", "properties": {}}

        def match(self, p):
            from oracle_db_agent.tools.base import ToolMatch

            return ToolMatch(confidence=99) if "echo" in p.lower() else None

        def run(self, p, ctx):
            print("routed")
            return 0

        def run_with_arguments(self, args, ctx):
            return self.run("", ctx)

    loop, audit, _ = make_loop(llm=None, registry=ToolRegistry([Echo()]))
    out, rc = run_loop(loop, prompt="echo please")
    assert rc == 0
    assert "routed" in out
    text = audit.path.read_text(encoding="utf-8")
    assert "fallback_keyword_router" in text


def test_assume_yes_skips_approval(monkeypatch) -> None:
    """When `assume_yes` is True and the target does NOT require typed
    approval, ask_approval must still be called (with assume_yes=True) so
    the audit log captures the decision."""
    captured: dict = {}

    def fake_ask_approval(request, assume_yes=False):
        captured["assume_yes"] = assume_yes
        return True

    monkeypatch.setattr("oracle_db_agent.agentic.ask_approval", fake_ask_approval)

    mt = MutatingTool()
    target = make_target(require_mutation_approval=False)
    options = make_options(target=target, assume_yes=True)
    llm = FakeLlm(
        responses=[
            LlmResponse(
                text="",
                tool_calls=(ToolCall(name="do_mutation", arguments={"target": "Y"}),),
            ),
            LlmResponse(text="done", tool_calls=()),
        ]
    )
    loop, _, _ = make_loop(llm, registry=ToolRegistry([mt]), options=options)
    _, rc = run_loop(loop)
    assert rc == 0
    assert captured.get("assume_yes") is True
    assert mt.invocations == [{"target": "Y"}]


def test_dry_run_options_propagate_to_tool() -> None:
    """The loop must pass `options` to the tool, so the tool can read
    `options.dry_run` and short-circuit. We assert that the tool sees the
    AgentOptions instance and that `dry_run` is True on it."""
    seen_options: dict = {}

    class DryRunChecker(BaseDbTool):
        name = "check_dry_run"
        description = "x"
        examples = ()
        mutating = True
        requires_approval = True
        parameters = {"type": "object", "properties": {}}

        def match(self, p):
            return None

        def run(self, p, ctx):
            return 0

        def run_with_arguments(self, args, ctx):
            seen_options["dry_run"] = ctx.options.dry_run
            return 0

    import oracle_db_agent.agentic as _agentic
    _agentic.ask_approval = lambda *a, **k: True  # type: ignore[assignment]
    llm = FakeLlm(
        responses=[
            LlmResponse(text="", tool_calls=(ToolCall(name="check_dry_run", arguments={}),)),
            LlmResponse(text="ok", tool_calls=()),
        ]
    )
    options = make_options(dry_run=True)
    loop, _, _ = make_loop(llm, registry=ToolRegistry([DryRunChecker()]), options=options)
    _, rc = run_loop(loop)
    assert rc == 0
    assert seen_options.get("dry_run") is True
