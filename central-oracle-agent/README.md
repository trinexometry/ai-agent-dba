# Central Oracle Agent

Target-aware Oracle DBA agent with a **local LLM-backed agentic loop**, designed to run against a central server hosting an Ollama daemon. The central server owns tool selection, approvals, audit boundaries, and Oracle connectivity to remote database targets.

The agent is **local-first**: by default it talks to a local Ollama daemon (`http://localhost:11434`) and runs whatever model you have pulled (recommended: `llama3.1:8b`, `qwen2.5-coder:7b`, `deepseek-coder-v2`). No cloud credentials are required and database contents are never sent to an external LLM.

Every run is scoped to one selected database target. Before any discovery query or action runs, the agent prints the active environment as:

```text
oracle_database@hostname
```

You must explicitly confirm that scope before the agent starts work.

## Install

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -e .
```

For the dev test suite:

```powershell
pip install -e ".[dev]"
```

## Configure Targets

Copy the sample inventory:

```powershell
Copy-Item inventory.example.yml inventory.yml
```

Edit `inventory.yml`:

```yaml
databases:
  local_free:
    database_name: FREEPDB1
    hostname: localhost
    dsn: localhost:1521/FREEPDB1
    username_env: ORACLE_LOCAL_USER
    password_env: ORACLE_LOCAL_PASSWORD
    environment: dev
    require_start_confirmation: true
    require_mutation_approval: true
    diagnostics_pack_enabled: false
    tuning_pack_enabled: false
    runbook_dir: ./runbooks
    ollama_url: http://localhost:11434
    ollama_model: llama3.1:8b
```

Set credentials through environment variables. Credentials are not sent to any LLM.

```powershell
$env:ORACLE_LOCAL_USER="system"
$env:ORACLE_LOCAL_PASSWORD="..."
```

## Run

With Ollama running locally and the model pulled (`ollama pull llama3.1:8b`):

```powershell
central-oracle-agent --target local_free "is SCOTT locked and what is he doing right now?"
central-oracle-agent --target local_free "show me top wait events and any blocking sessions"
central-oracle-agent --target local_free "follow runbook kill_blocker for the blocker on sid 145"
central-oracle-agent --target local_free "unlock SCOTT"
central-oracle-agent --target local_free "analyze past 4 days of AWR data"
```

You can also let the prompt specify the target:

```powershell
central-oracle-agent "unlock user SCOTT on local_free"
```

Dry-run still requires target scope confirmation, but it does not execute mutating SQL:

```powershell
central-oracle-agent --target local_free --dry-run "kill session sid 123 serial 456"
```

### CLI flags

| Flag | Default | Purpose |
| --- | --- | --- |
| `--target NAME` | (inferred) | Inventory target. |
| `--inventory PATH` | `inventory.yml` | Path to the inventory YAML. |
| `--llm {ollama,none}` | `ollama` | LLM backend. `none` falls back to the keyword router (single tool, no chaining). |
| `--ollama-url URL` | `http://localhost:11434` | Where the Ollama daemon listens. |
| `--model NAME` | target's `ollama_model` | The Ollama model to use. |
| `--max-steps N` | `8` | Hard cap on LLM turns per run. |
| `--audit-dir PATH` | `audit/` | Where JSONL audit logs are written. |
| `--explain` | off | After a non-LLM tool run, ask the LLM to summarize. |
| `--dry-run` | off | Mutating tools print their plan but skip execution. |
| `--yes` | off | Pre-approve mutating tools that don't require typed confirmation. |

## How the agent decides

The CLI starts a single `AgenticLoop` per run. The loop:

1. Prints the target scope and asks for confirmation.
2. Builds a system prompt listing the target, the licensed packs, the **full tool catalog** (name, description, JSON Schema for arguments), and the available runbooks.
3. Sends the prompt to the LLM with that catalog as the `tools` field.
4. For every tool the LLM requests:
   - Resolves the tool by name. Unknown names return a clean error observation and the loop continues.
   - Checks Oracle license pack gates. If the target is not licensed, the loop returns a `LicenseNotAllowedError` observation; the model is told not to retry.
   - If the tool is mutating, calls `ask_approval` and shows the planned command. Approval is a hard pre-condition.
   - Invokes the tool with parsed arguments. Tool output is captured and re-attached to the conversation as a tool message.
5. Repeats until the LLM produces a final answer (no tool calls) or the step / wall-time budget is hit.

The loop **never** generates SQL. Every read or write goes through a registered tool that uses bound parameters where possible. There is no free-form SQL tool.

## Architecture

```text
DBA prompt
   |
   v
AgenticLoop  (src/oracle_db_agent/agentic.py)
   |
   |--- build_system_prompt: target, license, tool catalog, runbook index
   |
   v
OllamaClient  (src/oracle_db_agent/llm/ollama.py)
   |  POST /api/chat
   v
Local Ollama daemon
   |  tool_calls[]
   v
ToolRegistry  (src/oracle_db_agent/tools/registry.py)
   |  -> approval gate (mutating tools)
   |  -> license gate (Diagnostics / Tuning pack)
   |  -> Tool.run_with_arguments(...)
   v
OracleClient  (src/oracle_db_agent/db.py)
   |
   v
Remote Oracle database
```

The audit log is written at every step:

```text
audit/audit-YYYYMMDDTHHMMSS-xxxxxx.jsonl
```

Each line is one JSON record with `ts`, `run_id`, `step`, `event`, and `payload`. Useful events: `llm_call`, `tool_unknown`, `license_blocked`, `approval_denied`, `tool_ok`, `tool_error`, `final_answer`, `step_limit_reached`, `wall_time_exceeded`.

## Supported Tools

User and session management:
- `show_user`, `unlock_user`, `lock_user`
- `kill_session`

Health and observability (no license required):
- `blocking_sessions`
- `long_running_sql`
- `tablespace_usage`
- `invalid_objects`
- `active_sessions` (from V$SESSION)
- `top_sql` (from V$SQL, by elapsed / cpu / gets / reads)
- `redo_switches` (hourly buckets from V$LOG_HISTORY)
- `wait_events` (from V$SYSTEM_EVENT)
- `user_activity` (active sessions + current SQL for a user)
- `explain_sql` (EXPLAIN PLAN with a strict single-statement safety check)

Diagnostics and Tuning pack tools (license-gated):
- `analyze_awr` (requires the Diagnostics Pack)

Runbook tools:
- `list_runbooks`
- `get_runbook`

## Runbooks

A runbook is a small markdown file under `target.runbook_dir` (default `./runbooks`). The first `#` heading is the title; `<!-- param: name, type, default, description -->` lines at the top declare parameters; the rest is the body. Example:

```markdown
# Kill a blocking session

<!-- param: sid, integer, 0, SID of the wait-for session -->
<!-- param: serial, integer, 0, Serial number of the wait-for session -->

Steps:

1. Look up the blocker in V$SESSION.
2. Confirm with the operator that killing it is safe.
3. Run `alter system kill session '<sid>,<serial>' immediate`.
```

The agent can list runbooks and load one by name. Tell it `"follow runbook kill_blocker for the blocker on sid 145"` and it will load the runbook, extract the parameters, and execute the steps through the registered tools (each with its own approval gate).

## Safety

The agent preserves the safety properties of the original router:

- **Target scope confirmation** at startup. The agent prints `database@hostname` and asks the operator to type `start` (or typed-scope string on targets that require it). Nothing connects until that succeeds.
- **Approval gate** for every mutating tool. The operator sees the planned command and types `yes` to proceed. `--yes` only pre-approves if the target's `require_mutation_approval` is false.
- **License pack gates** for AWR-style tools. The loop catches `LicenseNotAllowedError` at the tool boundary and returns it as an observation so the LLM can switch tools.
- **No free-form SQL**. There is no "execute arbitrary SQL" tool. Every database read and write goes through a method on `OracleClient` that uses bound parameters.
- **Step and wall-time budgets**. `--max-steps` and an internal `max_wall_seconds` prevent runaway loops.
- **Append-only audit log**. Every LLM call, every tool invocation, every approval decision is written to `audit/`.

## Fallback: keyword router

If Ollama is unavailable or you pass `--llm none`, the agent falls back to the original keyword-based single-tool router. The same inventory, scope, approval, and license gates apply. This is the same behavior the v0.x series provided and is useful as a degraded mode for offline or air-gapped environments.

## Tests

```powershell
PYTHONPATH=src pytest -q
```

70 tests cover the loop, the Ollama HTTP client, the audit log, runbook parsing, the SQL safety helper, the LLM explainer, the inventory loader, and the keyword router.

## Layout

```text
src/oracle_db_agent/
   agentic.py         # the loop
   agent.py           # backwards-compatible shim
   agent_options.py   # AgentOptions dataclass
   audit.py           # JSONL append-only log
   cli.py             # argparse entry point
   config.py          # inventory, DatabaseTarget, LicensePolicy
   db.py              # OracleClient + safety helpers
   explain.py         # generic LLM explainer
   intent.py          # legacy intent parser (kept for tests)
   license.py         # Diagnostics / Tuning pack gates
   llm/               # provider interface + Ollama client + prompt builder
      base.py
      ollama.py
      prompts.py
   loop_control.py    # step and wall-time budget
   reporting.py       # AWR report writer (deterministic summary)
   runbooks.py        # markdown runbook parser
   scope.py           # target scope confirmation
   tools/             # tool classes (each registers parameters + mutating)
      awr.py
      health.py
      observability.py
      runbook_tools.py
      sessions.py
      users.py
      ...
tests/                # 70 tests, runnable without Ollama
```
