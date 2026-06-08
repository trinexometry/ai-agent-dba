"""Backwards-compatible base + adapter for the existing keyword-routed tools.

The original tool classes were written for the keyword router and did not
declare JSON Schema parameters. Rather than rewrite every one of them, we
add a thin shim layer:

  - `BaseDbTool` provides a default `run_with_arguments` that calls `run()`
    after interpolating the arguments into a pseudo-prompt. The keyword
    router path keeps working unchanged.
  - `PARAMETERS` and `REQUIRES_APPROVAL` are declared as class attributes
    on the existing tools (see the imports below) so the loop can build a
    tool catalog without rewriting tool classes.
"""

from __future__ import annotations

from .base import DbTool, ToolContext, ToolMatch

__all__ = ["DbTool", "ToolContext", "ToolMatch"]


class BaseDbTool:
    """Mixin that gives tools a default `run_with_arguments` implementation.

    The default builds a string of the form `name: value, name: value` and
    passes it to `run(prompt, context)`. Tools that need structured argument
    handling override `run_with_arguments` directly.
    """

    name: str
    mutating: bool
    requires_approval: bool
    parameters: dict

    def run_with_arguments(
        self,
        arguments: dict[str, object],
        context: ToolContext,
    ) -> int:
        prompt = self._arguments_to_prompt(arguments)
        return self.run(prompt, context)

    @staticmethod
    def _arguments_to_prompt(arguments: dict[str, object]) -> str:
        if not arguments:
            return ""
        parts: list[str] = []
        for key, value in arguments.items():
            if isinstance(value, (list, tuple)):
                rendered = ", ".join(str(item) for item in value)
                parts.append(f"{key}: {rendered}")
            else:
                parts.append(f"{key}: {value}")
        return " ".join(parts)
