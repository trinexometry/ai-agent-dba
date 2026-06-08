from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class ApprovalRequest:
    title: str
    details: str
    command: str
    mutating: bool = True


def ask_approval(request: ApprovalRequest, assume_yes: bool = False) -> bool:
    print()
    print(f"Approval required: {request.title}")
    if request.details:
        print(request.details)
    print()
    print("Planned command:")
    print(request.command)
    print()

    if assume_yes:
        print("Approved by --yes.")
        return True

    answer = input("Type 'yes' to approve, anything else to cancel: ").strip().lower()
    return answer == "yes"
