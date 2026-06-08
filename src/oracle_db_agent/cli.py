from __future__ import annotations

import argparse

from .agent import OracleAgent
from .agent_options import AgentOptions
from .config import OracleConfig
from .db import OracleClient


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="oracle-db-agent",
        description="Interactive Oracle DBA agent with explicit approval gates.",
    )
    parser.add_argument("prompt", nargs="*", help="Natural language request for the agent.")
    parser.add_argument("--dry-run", action="store_true", help="Show planned work but do not execute it.")
    parser.add_argument("--yes", action="store_true", help="Approve planned actions without prompting.")
    parser.add_argument(
        "--llm",
        choices=("none", "openai"),
        default="none",
        help="Analysis provider for generated reports.",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    prompt = " ".join(args.prompt).strip() or input("What do you want the database agent to do? ").strip()
    if not prompt:
        parser.error("prompt is required")

    config = OracleConfig.from_env()
    options = AgentOptions(dry_run=args.dry_run, assume_yes=args.yes, llm_provider=args.llm)

    with OracleClient(config) as db:
        agent = OracleAgent(db, options)
        return agent.run(prompt)
