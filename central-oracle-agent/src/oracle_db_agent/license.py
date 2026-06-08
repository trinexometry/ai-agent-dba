"""License gates for Oracle Diagnostics Pack and Tuning Pack.

Tools that require a licensed feature call the `require_*` helpers at the
top of `run()`. When the gate fails, `LicenseNotAllowedError` is raised with
a message the CLI can print directly. The tool itself is responsible for
catching the error and exiting with a non-zero code so no audit line is
written for an action that never ran.
"""

from __future__ import annotations

from .config import DatabaseTarget, LicensePolicy

__all__ = [
    "LicenseNotAllowedError",
    "LicensePolicy",
    "require_diagnostics",
    "require_tuning",
]


class LicenseNotAllowedError(RuntimeError):
    """Raised when a tool needs an Oracle pack the target is not licensed for."""


def require_diagnostics(target: DatabaseTarget, feature: str) -> None:
    """Raise if `target` is not allowed to use Oracle Diagnostics Pack features."""
    if not target.license_policy.diagnostics:
        raise LicenseNotAllowedError(
            f"{feature} requires the Oracle Diagnostics Pack and is disabled on "
            f"target {target.name}. Set 'diagnostics_pack_enabled: true' in "
            f"inventory.yml if the customer is licensed."
        )


def require_tuning(target: DatabaseTarget, feature: str) -> None:
    """Raise if `target` is not allowed to use Oracle Tuning Pack features."""
    if not target.license_policy.tuning:
        raise LicenseNotAllowedError(
            f"{feature} requires the Oracle Tuning Pack and is disabled on "
            f"target {target.name}. Set 'tuning_pack_enabled: true' in "
            f"inventory.yml if the customer is licensed."
        )
