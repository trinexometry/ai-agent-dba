from __future__ import annotations

import re
from dataclasses import dataclass


@dataclass(frozen=True)
class UnlockUserIntent:
    username: str | None


@dataclass(frozen=True)
class AnalyzeAwrIntent:
    days: int


Intent = UnlockUserIntent | AnalyzeAwrIntent


USERNAME_PATTERNS = (
    re.compile(r"\bunlock\s+user\s+([A-Za-z][A-Za-z0-9_$#]{0,127})\b", re.I),
    re.compile(r"\bunlock\s+(?:the\s+)?(?:oracle\s+|database\s+)?user\s+([A-Za-z][A-Za-z0-9_$#]{0,127})\b", re.I),
    re.compile(r"\bunlock\s+([A-Za-z][A-Za-z0-9_$#]{0,127})\b", re.I),
    re.compile(r"\buser\s+([A-Za-z][A-Za-z0-9_$#]{0,127})\b.*\bunlock\b", re.I),
)

USERNAME_STOPWORDS = {"a", "an", "the", "user", "database", "oracle", "account"}


def parse_intent(prompt: str) -> Intent | None:
    text = prompt.strip()
    lowered = text.lower()

    if "unlock" in lowered:
        for pattern in USERNAME_PATTERNS:
            match = pattern.search(text)
            if match and match.group(1).lower() not in USERNAME_STOPWORDS:
                return UnlockUserIntent(username=match.group(1))
        return UnlockUserIntent(username=None)

    if "awr" in lowered or ("report" in lowered and "analy" in lowered):
        days_match = re.search(r"\bpast\s+(\d{1,3})\s+days?\b", lowered)
        if not days_match:
            days_match = re.search(r"\blast\s+(\d{1,3})\s+days?\b", lowered)
        days = int(days_match.group(1)) if days_match else 1
        return AnalyzeAwrIntent(days=max(1, min(days, 31)))

    return None
