# Oracle Database Agent

Interactive CLI agent for Oracle database administration tasks. You give it a prompt, it gathers missing details, reads current database state, shows the command or report action it intends to run, and asks for final approval before making changes.

## What It Supports

- Check Oracle user status.
- Lock or unlock an Oracle user after showing current account status.
- Kill a session after showing session details.
- Show blocking sessions.
- Show long-running SQL operations.
- Show tablespace usage.
- Show invalid database objects, optionally by schema.
- Generate AWR report context for the past N days and produce an analysis.
- Dry-run mode for change requests.
- Explicit approval gate before any mutating SQL.

## Install

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -e .
```

Copy `.env.example` to `.env` or set the variables in your shell.

```powershell
$env:ORACLE_DSN="host:1521/service"
$env:ORACLE_USER="system"
$env:ORACLE_PASSWORD="..."
```

## Run

```powershell
python -m oracle_db_agent "unlock user SCOTT"
python -m oracle_db_agent "check user SCOTT status"
python -m oracle_db_agent "show blocking sessions"
python -m oracle_db_agent "show long running sql"
python -m oracle_db_agent "show tablespace usage"
python -m oracle_db_agent "show invalid objects in schema HR"
python -m oracle_db_agent "kill session sid 123 serial 456"
python -m oracle_db_agent "analyze past 4 days database report"
oracle-db-agent "unlock user SCOTT"
```

Use dry-run when validating flows:

```powershell
python -m oracle_db_agent --dry-run "unlock user SCOTT"
```

Use OpenAI-backed summarization for AWR text if `OPENAI_API_KEY` is set:

```powershell
python -m oracle_db_agent --llm openai "analyze past 4 days database report"
```

Without `--llm openai`, the agent writes a deterministic summary based on AWR text sections and asks no external service.

## Oracle Privileges

The connected account needs privileges appropriate for the requested work:

- Unlock user: `ALTER USER` plus access to `DBA_USERS`.
- Lock user: `ALTER USER` plus access to `DBA_USERS`.
- Kill session: `ALTER SYSTEM` plus access to `V$SESSION`.
- User/session/health checks: access to the referenced DBA/V$ views.
- AWR analysis: access to `DBA_HIST_SNAPSHOT` and execute access for `DBMS_WORKLOAD_REPOSITORY.AWR_REPORT_TEXT`.

AWR usage may require Oracle Diagnostics Pack licensing. Confirm licensing before generating AWR reports in production.

## Safety Model

The agent never executes mutating SQL directly from a prompt. It maps prompts to a registered tool, reads current state, displays the exact planned SQL or report call, and requires a typed approval (`yes`) before execution.

Each capability lives as an explicit tool under `src/oracle_db_agent/tools/`. A tool declares its name, description, examples, match logic, discovery queries, approval text, planned command, execution, and post-check behavior. This keeps the agent general-purpose without allowing arbitrary natural-language SQL execution.
