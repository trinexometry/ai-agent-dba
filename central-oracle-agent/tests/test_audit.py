"""Tests for the audit log."""

from __future__ import annotations

from pathlib import Path

from oracle_db_agent.audit import AuditLog, recent


def test_record_appends_jsonl(tmp_path: Path) -> None:
    audit = AuditLog(tmp_path, run_id="r1")
    audit.record(1, "tool_ok", {"tool": "echo", "rc": 0})
    audit.record(2, "tool_ok", {"tool": "echo", "rc": 0})
    text = audit.path.read_text(encoding="utf-8")
    assert text.count("\n") == 2
    assert '"event": "tool_ok"' in text
    assert '"run_id": "r1"' in text


def test_finish_writes_run_finished(tmp_path: Path) -> None:
    audit = AuditLog(tmp_path, run_id="r2")
    audit.finish("all good")
    text = audit.path.read_text(encoding="utf-8")
    assert "run_finished" in text
    assert "all good" in text


def test_recent_returns_newest_first(tmp_path: Path) -> None:
    import time

    a = AuditLog(tmp_path, run_id="r1")
    a.record(1, "first", {})
    # Force the mtime difference so file-ordering is deterministic on
    # filesystems with low mtime resolution (Windows FAT/NTFS).
    time.sleep(0.05)
    b = AuditLog(tmp_path, run_id="r2")
    b.record(1, "second", {})
    out = recent(tmp_path, limit=10)
    # r2 is written second so should be first
    assert out[0].event == "second"
    assert out[1].event == "first"


def test_creates_directory(tmp_path: Path) -> None:
    nested = tmp_path / "sub" / "audit"
    AuditLog(nested, run_id="r3")
    assert nested.exists()
