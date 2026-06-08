"""Tests for the generic LLM explainer."""

from __future__ import annotations

from dataclasses import dataclass

from oracle_db_agent.explain import explain_with_llm, trim_for_llm
from oracle_db_agent.llm import ChatMessage, LlmClient, LlmResponse


@dataclass
class FakeLlm(LlmClient):
    last_prompt: str = ""
    response: str = "the user has no active sessions"

    def chat(self, messages, tools=None):
        self.last_prompt = messages[-1].content
        return LlmResponse(text=self.response)


def test_explain_passes_through() -> None:
    llm = FakeLlm()
    out = explain_with_llm(
        llm=llm,
        user_question="is scott active?",
        tool_name="active_sessions",
        tool_output="<table>...</table>",
    )
    assert out == "the user has no active sessions"
    assert "active_sessions" in llm.last_prompt
    assert "is scott active?" in llm.last_prompt
    assert "<table>...</table>" in llm.last_prompt


def test_trim_short_text_unchanged() -> None:
    assert trim_for_llm("hello") == "hello"


def test_trim_long_text_trims_both_ends() -> None:
    long = "x" * 200_000
    out = trim_for_llm(long, max_chars=1000)
    assert len(out) < 2000  # head + tail + boilerplate
    assert "trimmed" in out
    assert out.startswith("x")
    assert out.endswith("x")
