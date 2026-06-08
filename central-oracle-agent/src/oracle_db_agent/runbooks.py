"""Read runbooks from `target.runbook_dir` and expose them as tools.

A runbook is a small markdown file that names a procedure a DBA might want
to follow: `kill_blocker.md`, `reclaim_temp.md`, etc. We don't try to
parse every style of runbook; we extract just enough structure to be
useful:

  - The first `#` heading becomes the title.
  - Lines of the form `<!-- param: name, type, default, description -->`
    at the top of the file declare parameters.
  - The body is returned verbatim.

If a runbook has no parameter declarations, it is treated as parameterless
and the agent is expected to follow the prose.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path


_PARAM_RE = re.compile(
    r"<!--\s*param:\s*"
    r"([A-Za-z_][A-Za-z0-9_]*)\s*,\s*"  # name
    r"([A-Za-z0-9_]+)\s*,\s*"            # type
    r"([^,]*?)\s*,\s*"                    # default (no commas)
    r"(.*?)\s*"                           # description (anything, lazy)
    r"-->"
)
_TITLE_RE = re.compile(r"^#\s+(.+?)\s*$", re.M)


@dataclass(frozen=True)
class RunbookParameter:
    name: str
    type: str
    default: str
    description: str


@dataclass(frozen=True)
class Runbook:
    name: str
    path: Path
    title: str
    parameters: tuple[RunbookParameter, ...]
    body: str


class RunbookStore:
    """Read runbooks from a directory.

    The directory is created on first read if `create_if_missing` is True,
    which is convenient for first-run operator experience.
    """

    def __init__(self, runbook_dir: str | Path, *, create_if_missing: bool = False) -> None:
        self.runbook_dir = Path(runbook_dir)
        if create_if_missing:
            self.runbook_dir.mkdir(parents=True, exist_ok=True)

    def list(self) -> list[Runbook]:
        if not self.runbook_dir.exists():
            return []
        out: list[Runbook] = []
        for path in sorted(self.runbook_dir.glob("*.md")):
            try:
                out.append(self._parse(path))
            except ValueError:
                # Skip malformed runbooks rather than failing the whole list.
                continue
        return out

    def get(self, name: str) -> Runbook | None:
        # Accept either a bare name or a .md suffix; reject path traversal.
        if "/" in name or "\\" in name or ".." in name:
            return None
        candidate = self.runbook_dir / (name if name.endswith(".md") else f"{name}.md")
        if not candidate.exists():
            return None
        return self._parse(candidate)

    def index_text(self) -> str:
        """Short text block suitable for embedding in the system prompt."""
        books = self.list()
        if not books:
            return "(no runbooks found in this directory)"
        lines = []
        for book in books:
            param_names = ", ".join(p.name for p in book.parameters) or "(no parameters)"
            lines.append(f"  - {book.name} — {book.title} (params: {param_names})")
        return "\n".join(lines)

    # --------------------------------------------------------------- parsing

    def _parse(self, path: Path) -> Runbook:
        text = path.read_text(encoding="utf-8", errors="replace")
        title_match = _TITLE_RE.search(text)
        title = title_match.group(1).strip() if title_match else path.stem
        params: list[RunbookParameter] = []
        body_lines: list[str] = []
        for line in text.splitlines():
            param_match = _PARAM_RE.search(line)
            if param_match:
                params.append(
                    RunbookParameter(
                        name=param_match.group(1).strip(),
                        type=param_match.group(2).strip(),
                        default=param_match.group(3).strip(),
                        description=param_match.group(4).strip(),
                    )
                )
            else:
                body_lines.append(line)
        if not title_match and not params:
            raise ValueError(f"runbook {path} has no title and no parameters")
        return Runbook(
            name=path.stem,
            path=path,
            title=title,
            parameters=tuple(params),
            body="\n".join(body_lines).strip(),
        )
