from __future__ import annotations

from .config import DatabaseTarget


def confirm_target_scope(target: DatabaseTarget, assume_yes: bool = False) -> bool:
    print()
    print("Target scope")
    print(f"Environment: {target.environment}")
    print(f"Database scope: {target.scope_label}")
    print(f"Inventory target: {target.name}")
    print()
    print("The agent will only work against this selected Oracle database target.")

    if assume_yes or not target.require_start_confirmation:
        print("Scope confirmed.")
        return True

    expected = "start"
    answer = input("Type 'start' to begin work on this target, anything else to cancel: ")
    return answer.strip().lower() == expected
