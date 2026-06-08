from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any


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
class LicensePolicy:
    """Oracle license gates that determine which agent features are allowed.

    A target with `diagnostics=False` cannot run AWR, ASH, or ADDM (those
    features require the Oracle Diagnostics Pack). A target with
    `tuning=False` cannot run SQL Tuning Advisor or accept SQL Profiles
    (those require the Oracle Tuning Pack).
    """

    diagnostics: bool = False
    tuning: bool = False


@dataclass(frozen=True)
class DatabaseTarget:
    name: str
    database_name: str
    hostname: str
    dsn: str
    username_env: str
    password_env: str
    mode: str | None
    environment: str
    require_start_confirmation: bool = True
    require_mutation_approval: bool = True
    require_typed_scope_confirmation: bool = True
    diagnostics_pack_enabled: bool = False
    tuning_pack_enabled: bool = False
    runbook_dir: str = "./runbooks"
    ollama_url: str = "http://localhost:11434"
    ollama_model: str = "llama3.1:8b"

    @property
    def scope_label(self) -> str:
        return f"{self.database_name}@{self.hostname}"

    @property
    def license_policy(self) -> LicensePolicy:
        return LicensePolicy(
            diagnostics=self.diagnostics_pack_enabled,
            tuning=self.tuning_pack_enabled,
        )

    def oracle_config(self) -> OracleConfig:
        load_dotenv()
        missing = [name for name in (self.username_env, self.password_env) if not os.getenv(name)]
        if missing:
            joined = ", ".join(missing)
            raise RuntimeError(
                f"Missing credential environment variable(s) for target {self.name}: {joined}"
            )
        return OracleConfig(
            dsn=self.dsn,
            user=os.environ[self.username_env],
            password=os.environ[self.password_env],
            mode=self.mode,
        )


class TargetInventory:
    def __init__(self, targets: dict[str, DatabaseTarget]):
        self.targets = targets

    @classmethod
    def load(cls, path: str | Path = "inventory.yml") -> "TargetInventory":
        load_dotenv()
        inventory_path = Path(path)
        if not inventory_path.exists():
            raise RuntimeError(
                f"Inventory file not found: {inventory_path}. Copy inventory.example.yml to inventory.yml."
            )

        try:
            import yaml
        except ImportError as exc:
            raise RuntimeError("PyYAML is required to load inventory.yml. Run: pip install -e .") from exc

        raw = yaml.safe_load(inventory_path.read_text(encoding="utf-8")) or {}
        databases = raw.get("databases")
        if not isinstance(databases, dict) or not databases:
            raise RuntimeError("inventory.yml must contain a non-empty 'databases' mapping.")

        targets: dict[str, DatabaseTarget] = {}
        for name, value in databases.items():
            if not isinstance(value, dict):
                raise RuntimeError(f"Invalid inventory entry for target {name}.")
            targets[name] = _target_from_mapping(str(name), value)
        return cls(targets)

    def get(self, name: str) -> DatabaseTarget:
        if name not in self.targets:
            available = ", ".join(sorted(self.targets))
            raise RuntimeError(f"Unknown target '{name}'. Available targets: {available}")
        return self.targets[name]

    def infer_target_name(self, prompt: str) -> str | None:
        lowered = prompt.lower()
        for name in sorted(self.targets, key=len, reverse=True):
            if f" on {name.lower()}" in lowered or f" target {name.lower()}" in lowered:
                return name
        return None


def _target_from_mapping(name: str, value: dict[str, Any]) -> DatabaseTarget:
    required = ("database_name", "hostname", "dsn", "username_env", "password_env")
    missing = [field for field in required if not value.get(field)]
    if missing:
        joined = ", ".join(missing)
        raise RuntimeError(f"Target {name} is missing required field(s): {joined}")

    return DatabaseTarget(
        name=name,
        database_name=str(value["database_name"]),
        hostname=str(value["hostname"]),
        dsn=str(value["dsn"]),
        username_env=str(value["username_env"]),
        password_env=str(value["password_env"]),
        mode=value.get("mode") or None,
        environment=str(value.get("environment") or "unknown"),
        require_start_confirmation=bool(value.get("require_start_confirmation", True)),
        require_mutation_approval=bool(value.get("require_mutation_approval", True)),
        require_typed_scope_confirmation=bool(
            value.get("require_typed_scope_confirmation", True)
        ),
        diagnostics_pack_enabled=bool(value.get("diagnostics_pack_enabled", False)),
        tuning_pack_enabled=bool(value.get("tuning_pack_enabled", False)),
        runbook_dir=str(value.get("runbook_dir") or "./runbooks"),
        ollama_url=str(value.get("ollama_url") or "http://localhost:11434"),
        ollama_model=str(value.get("ollama_model") or "llama3.1:8b"),
    )


@dataclass(frozen=True)
class LlmConfig:
    provider: str
    model: str

    @classmethod
    def from_env(cls, provider: str) -> "LlmConfig":
        load_dotenv()
        return cls(provider=provider, model=os.getenv("OPENAI_MODEL", "gpt-4.1-mini"))
