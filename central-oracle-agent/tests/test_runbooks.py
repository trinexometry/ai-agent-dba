"""Tests for the runbook store."""

from __future__ import annotations

from pathlib import Path

from oracle_db_agent.runbooks import RunbookStore


SAMPLE_RUNBOOK = """# Kill a blocking session

<!-- param: sid, integer, 0, SID of the wait-for session -->
<!-- param: serial, integer, 0, Serial number of the wait-for session -->

Steps:

1. Look up the blocker in V$SESSION.
2. Confirm with the operator that killing it is safe.
3. Run `alter system kill session '<sid>,<serial>' immediate`.
"""


def test_parse_full_runbook(tmp_path: Path) -> None:
    (tmp_path / "kill_blocker.md").write_text(SAMPLE_RUNBOOK, encoding="utf-8")
    store = RunbookStore(tmp_path)
    books = store.list()
    assert len(books) == 1
    book = books[0]
    assert book.name == "kill_blocker"
    assert book.title == "Kill a blocking session"
    assert {p.name for p in book.parameters} == {"sid", "serial"}
    assert any("alter system kill session" in book.body for _ in [0])
    assert "Steps:" in book.body
    # The param comments should NOT appear in the rendered body
    assert "<!--" not in book.body


def test_get_by_name_with_and_without_suffix(tmp_path: Path) -> None:
    (tmp_path / "kill_blocker.md").write_text(SAMPLE_RUNBOOK, encoding="utf-8")
    store = RunbookStore(tmp_path)
    assert store.get("kill_blocker") is not None
    assert store.get("kill_blocker.md") is not None
    assert store.get("nope") is None


def test_path_traversal_rejected(tmp_path: Path) -> None:
    store = RunbookStore(tmp_path)
    assert store.get("../etc/passwd") is None
    assert store.get("..\\windows\\system32") is None
    assert store.get("sub/evil") is None


def test_index_text_lists_runs(tmp_path: Path) -> None:
    (tmp_path / "kill_blocker.md").write_text(SAMPLE_RUNBOOK, encoding="utf-8")
    (tmp_path / "reclaim_temp.md").write_text("# Reclaim temp\nbody", encoding="utf-8")
    store = RunbookStore(tmp_path)
    text = store.index_text()
    assert "kill_blocker" in text
    assert "reclaim_temp" in text
    assert "sid, serial" in text or "serial" in text


def test_empty_dir_returns_empty_index(tmp_path: Path) -> None:
    store = RunbookStore(tmp_path)
    assert store.list() == []
    assert "no runbooks" in store.index_text()
