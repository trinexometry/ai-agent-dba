"""Tests for the LLM system prompt builder."""

from __future__ import annotations

from oracle_db_agent.config import DatabaseTarget
from oracle_db_agent.llm import ToolSpec, build_system_prompt


def make_target(**overrides) -> DatabaseTarget:
    base = dict(
        name="t1",
        database_name="FREE",
        hostname="localhost",
        dsn="localhost:1521/FREE",
        username_env="U",
        password_env="P",
        mode=None,
        environment="prod",
        require_start_confirmation=True,
        require_mutation_approval=True,
        require_typed_scope_confirmation=True,
        diagnostics_pack_enabled=False,
        tuning_pack_enabled=True,
        runbook_dir="./runbooks",
        ollama_url="http://localhost:11434",
        ollama_model="llama3.1:8b",
    )
    base.update(overrides)
    return DatabaseTarget(**base)


def test_prompt_contains_safety_preamble() -> None:
    prompt = build_system_prompt(
        make_target(),
        tool_specs=[],
        runbook_index="(none)",
        max_steps=4,
    )
    assert "NEVER construct or execute free-form SQL" in prompt
    assert "LicenseNotAllowedError" in prompt


def test_prompt_includes_target_metadata() -> None:
    target = make_target(diagnostics_pack_enabled=True, tuning_pack_enabled=False)
    prompt = build_system_prompt(
        target,
        tool_specs=[],
        runbook_index="(none)",
        max_steps=8,
    )
    assert "FREE@localhost" in prompt
    assert "Environment: prod" in prompt
    assert "Diagnostics Pack licensed: True" in prompt
    assert "Tuning Pack licensed: False" in prompt
    assert "Step budget: 8" in prompt


def test_prompt_includes_tool_catalog_with_schemas() -> None:
    target = make_target()
    specs = [
        ToolSpec(
            name="unlock_user",
            description="Unlock an account",
            parameters={
                "type": "object",
                "properties": {"username": {"type": "string", "description": "name"}},
                "required": ["username"],
            },
        )
    ]
    prompt = build_system_prompt(target, specs, runbook_index="(none)", max_steps=4)
    assert "unlock_user" in prompt
    assert "Unlock an account" in prompt
    assert "username" in prompt
    assert "string" in prompt


def test_prompt_includes_runbook_index() -> None:
    prompt = build_system_prompt(
        make_target(),
        tool_specs=[],
        runbook_index="- kill_blocker — Kill a blocking session (params: sid, serial)",
        max_steps=4,
    )
    assert "kill_blocker" in prompt
    assert "list_runbooks" in prompt
    assert "get_runbook" in prompt
