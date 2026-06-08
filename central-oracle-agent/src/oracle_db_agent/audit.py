"""Append-only JSONL audit log.

Every step of an agent run is recorded as one JSON object per line. The
log is human-readable (`tail -f` is useful while debugging) and easy to
post-process with `jq`. The directory is created on first write.
"""

from __future__ import annotations

import datetime as _dt
import json
import threading
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any


def _now_iso() -> str:
    return _dt.datetime.now(_dt.timezone.utc).isoformat(timespec="seconds")


@dataclass
class AuditRecord:
    ts: str
    run_id: str
    step: int
    event: str
    payload: dict[str, Any] = field(default_factory=dict)

    def to_jsonl(self) -> str:
        return json.dumps(asdict(self), ensure_ascii=False, sort_keys=True)


class AuditLog:
    """Append-only writer for one run.

    A single `AuditLog` is created per `AgenticLoop.run()` and writes to a
    file under `audit_dir/audit-<run_id>.jsonl`. The lock is held only for
    the disk write; readers should not hold the file open.
    """

    def __init__(self, audit_dir: Path, run_id: str) -> None:
        self.audit_dir = audit_dir
        self.run_id = run_id
        self.path = audit_dir / f"audit-{run_id}.jsonl"
        self._lock = threading.Lock()
        self.audit_dir.mkdir(parents=True, exist_ok=True)

    def record(self, step: int, event: str, payload: dict[str, Any] | None = None) -> None:
        rec = AuditRecord(
            ts=_now_iso(),
            run_id=self.run_id,
            step=step,
            event=event,
            payload=payload or {},
        )
        line = rec.to_jsonl()
        with self._lock:
            with self.path.open("a", encoding="utf-8") as fh:
                fh.write(line + "\n")

    def finish(self, summary: str) -> None:
        self.record(step=-1, event="run_finished", payload={"summary": summary})


def recent(audit_dir: Path, limit: int = 50) -> list[AuditRecord]:
    """Read the most recent records across all audit files in `audit_dir`.

    Used by the CLI's `audit tail` command and by tests. Newest first.
    """

    if not audit_dir.exists():
        return []
    files = sorted(audit_dir.glob("audit-*.jsonl"), key=lambda p: p.stat().st_mtime, reverse=True)
    out: list[AuditRecord] = []
    for path in files:
        for raw in path.read_text(encoding="utf-8").splitlines():
            if not raw.strip():
                continue
            data = json.loads(raw)
            out.append(
                AuditRecord(
                    ts=str(data.get("ts", "")),
                    run_id=str(data.get("run_id", "")),
                    step=int(data.get("step", -1)),
                    event=str(data.get("event", "")),
                    payload=dict(data.get("payload") or {}),
                )
            )
            if len(out) >= limit:
                return out
    return out
