from __future__ import annotations

import argparse

from .agent import OracleAgent
from .agent_options import AgentOptions
from .config import TargetInventory
from .db import OracleClient
from .scope import confirm_target_scope


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="central-oracle-agent",
        description="Target-aware central Oracle DBA agent with explicit approval gates.",
    )
    parser.add_argument("prompt", nargs="*", help="Natural language request for the agent.")
    parser.add_argument("--target", help="Inventory target name, for example local_free or prod1.")
    parser.add_argument(
        "--inventory",
        default="inventory.yml",
        help="Path to database inventory YAML file.",
    )
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

    inventory = TargetInventory.load(args.inventory)
    target_name = args.target or inventory.infer_target_name(prompt)
    if not target_name:
        parser.error("target is required. Use --target <name> or include 'on <target>' in the prompt.")

    target = inventory.get(target_name)
    if not confirm_target_scope(target, assume_yes=args.yes):
        print("Cancelled before connecting. No database work was started.")
        return 1

    config = target.oracle_config()
    options = AgentOptions(
        target=target,
        dry_run=args.dry_run,
        assume_yes=args.yes,
        llm_provider=args.llm,
    )

    with OracleClient(config) as db:
        agent = OracleAgent(db, options)
        return agent.run(prompt)
