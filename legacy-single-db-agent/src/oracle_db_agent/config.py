from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


def load_dotenv(path: str | Path = ".env") -> None:
    env_path = Path(path)
    if not env_path.exists():
        return

    for raw_line in env_path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        os.environ.setdefault(key, value)


@dataclass(frozen=True)
class OracleConfig:
    dsn: str
    user: str
    password: str
    mode: str | None = None

    @classmethod
    def from_env(cls) -> "OracleConfig":
        load_dotenv()
        missing = [
            name
            for name in ("ORACLE_DSN", "ORACLE_USER", "ORACLE_PASSWORD")
            if not os.getenv(name)
        ]
        if missing:
            joined = ", ".join(missing)
            raise RuntimeError(f"Missing required environment variable(s): {joined}")

        mode = os.getenv("ORACLE_MODE") or None
        return cls(
            dsn=os.environ["ORACLE_DSN"],
            user=os.environ["ORACLE_USER"],
            password=os.environ["ORACLE_PASSWORD"],
            mode=mode,
        )


@dataclass(frozen=True)
class LlmConfig:
    provider: str
    model: str

    @classmethod
    def from_env(cls, provider: str) -> "LlmConfig":
        load_dotenv()
        return cls(provider=provider, model=os.getenv("OPENAI_MODEL", "gpt-4.1-mini"))
