"""Step and time budgets for the agentic loop.

Pulled out of `agentic.py` so the loop is testable in isolation: a test can
hand it a tiny budget (e.g. 2 steps, 1 second) and assert that the loop
exits cleanly when it is reached.
"""

from __future__ import annotations

import time
from dataclasses import dataclass


@dataclass(frozen=True)
class LoopBudget:
    """Hard limits for one agent run.

    `max_steps` is the number of LLM turns, not tool calls. A single turn can
    request multiple tool calls and they all count as one step.

    `max_wall_seconds` is a safety net against a hung model or a runaway
    retry loop. The loop checks it at the top of each iteration.
    """

    max_steps: int = 8
    max_wall_seconds: float = 300.0
    max_retries_per_step: int = 1

    def __post_init__(self) -> None:
        if self.max_steps < 1:
            raise ValueError("max_steps must be >= 1")
        if self.max_wall_seconds <= 0:
            raise ValueError("max_wall_seconds must be > 0")
        if self.max_retries_per_step < 0:
            raise ValueError("max_retries_per_step must be >= 0")


class BudgetExceeded(RuntimeError):
    """Raised internally when a limit is hit; the loop catches and exits."""


def remaining_seconds(budget: LoopBudget, started_at: float) -> float:
    return max(0.0, budget.max_wall_seconds - (time.monotonic() - started_at))
