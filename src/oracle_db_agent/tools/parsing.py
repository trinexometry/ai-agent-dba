from __future__ import annotations

import re

from oracle_db_agent.db import normalize_username


USERNAME_STOPWORDS = {"a", "an", "the", "user", "database", "oracle", "account"}


def lowered(prompt: str) -> str:
    return prompt.strip().lower()


def contains_any(prompt: str, terms: tuple[str, ...]) -> bool:
    text = lowered(prompt)
    return any(term in text for term in terms)


def extract_username(prompt: str) -> str | None:
    patterns = (
        r"\b(?:unlock|lock|expire|show|check|status\s+of)\s+(?:the\s+)?(?:oracle\s+|database\s+)?user\s+([A-Za-z][A-Za-z0-9_$#]{0,127})\b",
        r"\buser\s+([A-Za-z][A-Za-z0-9_$#]{0,127})\b",
        r"\b(?:unlock|lock)\s+([A-Za-z][A-Za-z0-9_$#]{0,127})\b",
    )
    for pattern in patterns:
        match = re.search(pattern, prompt, re.I)
        if match and match.group(1).lower() not in USERNAME_STOPWORDS:
            return normalize_username(match.group(1))
    return None


def extract_days(prompt: str, default: int = 1, max_days: int = 31) -> int:
    text = lowered(prompt)
    match = re.search(r"\b(?:past|last)\s+(\d{1,3})\s+days?\b", text)
    if not match:
        return default
    return max(1, min(int(match.group(1)), max_days))


def extract_sid_serial(prompt: str) -> tuple[int, int] | None:
    patterns = (
        r"\bsid\s*[:=]?\s*(\d+)\D+serial#?\s*[:=]?\s*(\d+)\b",
        r"\bsession\s+(\d+)\s*,\s*(\d+)\b",
        r"\bkill\s+(\d+)\s*,\s*(\d+)\b",
    )
    for pattern in patterns:
        match = re.search(pattern, prompt, re.I)
        if match:
            return int(match.group(1)), int(match.group(2))
    return None


def extract_owner(prompt: str) -> str | None:
    match = re.search(r"\b(?:schema|owner)\s+([A-Za-z][A-Za-z0-9_$#]{0,127})\b", prompt, re.I)
    if not match:
        return None
    return normalize_username(match.group(1))
