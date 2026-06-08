from __future__ import annotations

from collections.abc import Sequence
from typing import Any


def print_rows(rows: Sequence[dict[str, Any]], limit: int = 20) -> None:
    if not rows:
        print("No rows found.")
        return

    selected = rows[:limit]
    columns = list(selected[0].keys())
    widths = {
        column: min(
            40,
            max(len(column), *(len(str(row.get(column, "") or "")) for row in selected)),
        )
        for column in columns
    }
    header = " | ".join(column.upper().ljust(widths[column]) for column in columns)
    separator = "-+-".join("-" * widths[column] for column in columns)
    print(header)
    print(separator)
    for row in selected:
        print(
            " | ".join(
                str(row.get(column, "") or "")[: widths[column]].ljust(widths[column])
                for column in columns
            )
        )
    if len(rows) > limit:
        print(f"... {len(rows) - limit} more row(s) not shown")
