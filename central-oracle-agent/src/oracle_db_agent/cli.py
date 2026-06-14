from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from .agentic import build_ollama_loop
from .config import TargetInventory
from .db import OracleClient
from .scope import confirm_target_scope
from .tools.registry import default_registry


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="central-oracle-agent",
        description=(
            "Target-aware central Oracle DBA agent with explicit approval gates "
            "and a local Ollama-backed agentic loop."
        ),
    )
    # Positional prompt words — these are the natural-language request.
    # The original v0.1 design used these directly; we keep it.
    parser.add_argument("prompt", nargs="*", help="Natural language request for the agent.")
    # `--models` is a flag (not a subcommand) so it never collides with
    # a prompt that happens to start with a verb like "show" or "lock".
    parser.add_argument(
        "--models",
        action="store_true",
        help="List Ollama models available locally and exit. Does not require a target or DB.",
    )
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
        choices=("none", "ollama"),
        default="ollama",
        help="LLM backend. Default: ollama. Use 'none' to fall back to the keyword router.",
    )
    parser.add_argument(
        "--ollama-url",
        default="http://localhost:11434",
        help="Ollama daemon URL. Override for remote Ollama.",
    )
    parser.add_argument(
        "--model",
        default=None,
        help="Ollama model name (e.g. phi3:mini, llama3.1:8b). Defaults to the target's ollama_model.",
    )
    parser.add_argument(
        "--max-steps",
        type=int,
        default=8,
        help="Maximum LLM steps per run. Default 8.",
    )
    parser.add_argument(
        "--audit-dir",
        type=Path,
        default=Path("audit"),
        help="Directory for append-only JSONL audit logs. Default ./audit.",
    )
    parser.add_argument(
        "--explain",
        action="store_true",
        help="After a non-LLM tool run, ask the LLM to summarize the output in plain English.",
    )
    return parser


def _print_models(url: str) -> int:
    import requests

    try:
        r = requests.get(f"{url.rstrip('/')}/api/tags", timeout=3)
    except requests.RequestException as exc:
        print(f"Cannot reach Ollama at {url}: {exc}", file=sys.stderr)
        return 4
    if r.status_code != 200:
        print(f"Ollama returned HTTP {r.status_code}: {r.text[:200]}", file=sys.stderr)
        return 4
    try:
        data = r.json()
    except json.JSONDecodeError:
        print(f"Ollama returned non-JSON body: {r.text[:200]}", file=sys.stderr)
        return 4

    models = data.get("models") or []
    if not models:
        print("No models installed. Run: ollama pull phi3:mini")
        return 0
    print(f"Local Ollama models at {url}:")
    for m in models:
        size_bytes = int(m.get("size") or 0)
        size_gb = size_bytes / (1024 ** 3)
        name = m.get("name", "?")
        det = m.get("details") or {}
        family = det.get("family") or "?"
        param_size = det.get("parameter_size") or "?"
        quant = det.get("quantization_level") or "?"
        print(
            f"  - {name:<30} {size_gb:5.2f} GB   {family} {param_size} {quant}"
        )
    print()
    print("For 8 GB RAM, recommended: phi3:mini (~2.2 GB) or qwen2.5:3b (~1.9 GB).")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    if args.models:
        return _print_models(args.ollama_url)

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

    from .agent_options import AgentOptions

    model = args.model or target.ollama_model
    options = AgentOptions(
        target=target,
        dry_run=args.dry_run,
        assume_yes=args.yes,
        llm_provider=args.llm,
        ollama_url=args.ollama_url,
        ollama_model=model,
        max_steps=args.max_steps,
        explain=args.explain,
        audit_dir=args.audit_dir,
    )

    config = target.oracle_config()
    with OracleClient(config) as db:
        registry = default_registry()
        loop = build_ollama_loop(
            db=db,
            options=options,
            registry=registry,
            audit_dir=args.audit_dir,
        )
        return loop.run(prompt)
