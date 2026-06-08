# Central Oracle Agent

Target-aware Oracle DBA agent intended for a central server running local inference, for example Ollama with a strong local model. The central server owns tool selection, approvals, audit boundaries, and Oracle connectivity to remote database targets.

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
```

Set credentials through environment variables. Credentials are not sent to any LLM.

```powershell
$env:ORACLE_LOCAL_USER="system"
$env:ORACLE_LOCAL_PASSWORD="..."
```

## Run

```powershell
central-oracle-agent --target local_free "check user SCOTT status"
central-oracle-agent --target local_free "unlock user SCOTT"
central-oracle-agent --target local_free "show blocking sessions"
central-oracle-agent --target local_free "analyze past 4 days awr"
```

You can also let the prompt specify the target:

```powershell
central-oracle-agent "unlock user SCOTT on local_free"
```

Dry-run still requires target scope confirmation, but it does not execute mutating SQL:

```powershell
central-oracle-agent --target local_free --dry-run "kill session sid 123 serial 456"
```

## Architecture

```text
DBA prompt
   |
   v
Central Oracle Agent
   - target inventory
   - scope confirmation
   - deterministic tool registry
   - optional local/LLM report analysis
   - approval gates
   |
   v
OracleClient for selected target only
   |
   v
Remote Oracle database
```

The agent does not execute arbitrary SQL from natural language. Prompts are routed to registered tools under `src/oracle_db_agent/tools/`.

## Supported Tools

- Check user status
- Lock/unlock user
- Kill session
- Show blocking sessions
- Show long-running SQL
- Show tablespace usage
- Show invalid objects
- Generate and analyze AWR text

## Ollama Direction

This project is structured so Ollama can be added as the planner/summarizer on the central server. The execution layer should remain tool-based:

```text
LLM chooses or explains. Python tools validate, ask approval, and execute.
```
