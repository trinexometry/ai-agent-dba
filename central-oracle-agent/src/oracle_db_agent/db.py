from __future__ import annotations

import re
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from .config import OracleConfig


IDENTIFIER_RE = re.compile(r"^[A-Za-z][A-Za-z0-9_$#]{0,127}$")


class UnsafeIdentifierError(ValueError):
    pass


def normalize_username(username: str) -> str:
    candidate = username.strip()
    if not IDENTIFIER_RE.fullmatch(candidate):
        raise UnsafeIdentifierError(
            "Only simple Oracle usernames are supported: letters, numbers, _, $, #."
        )
    return candidate.upper()


def quote_identifier(identifier: str) -> str:
    normalized = normalize_username(identifier)
    return f'"{normalized}"'


@dataclass(frozen=True)
class UserStatus:
    username: str
    account_status: str
    lock_date: datetime | None
    expiry_date: datetime | None
    profile: str


@dataclass(frozen=True)
class SessionInfo:
    sid: int
    serial: int
    username: str | None
    status: str
    machine: str | None
    program: str | None
    sql_id: str | None
    event: str | None
    blocking_session: int | None = None


@dataclass(frozen=True)
class TablespaceUsage:
    tablespace_name: str
    used_mb: float
    free_mb: float
    total_mb: float
    used_pct: float


@dataclass(frozen=True)
class InvalidObject:
    owner: str
    object_name: str
    object_type: str
    status: str


@dataclass(frozen=True)
class Snapshot:
    dbid: int
    instance_number: int
    snap_id: int
    begin_interval_time: datetime
    end_interval_time: datetime


@dataclass(frozen=True)
class ActiveSession:
    sid: int
    serial: int
    username: str | None
    status: str
    machine: str | None
    program: str | None
    sql_id: str | None
    prev_sql_id: str | None
    event: str | None
    seconds_in_wait: int | None
    logon_time: datetime | None


@dataclass(frozen=True)
class TopSql:
    sql_id: str
    plan_hash_value: int | None
    executions: int | None
    elapsed_seconds: float | None
    cpu_seconds: float | None
    buffer_gets: int | None
    disk_reads: int | None
    sql_text: str


@dataclass(frozen=True)
class RedoSwitch:
    day: datetime
    switches: int


@dataclass(frozen=True)
class WaitEvent:
    event: str
    total_waits: int
    time_waited_seconds: float
    average_wait_ms: float


@dataclass(frozen=True)
class ExplainPlan:
    statement: str
    plan_lines: tuple[str, ...]


class OracleClient:
    def __init__(self, config: OracleConfig):
        self.config = config
        self._connection: Any | None = None

    def __enter__(self) -> "OracleClient":
        self.connect()
        return self

    def __exit__(self, *_: object) -> None:
        self.close()

    def connect(self) -> None:
        import oracledb

        kwargs: dict[str, Any] = {
            "user": self.config.user,
            "password": self.config.password,
            "dsn": self.config.dsn,
        }
        if self.config.mode:
            mode_name = self.config.mode.upper()
            if not hasattr(oracledb, mode_name):
                raise RuntimeError(f"Unsupported ORACLE_MODE: {self.config.mode}")
            kwargs["mode"] = getattr(oracledb, mode_name)

        self._connection = oracledb.connect(**kwargs)

    def close(self) -> None:
        if self._connection is not None:
            self._connection.close()
            self._connection = None

    @property
    def connection(self) -> Any:
        if self._connection is None:
            raise RuntimeError("Oracle connection has not been opened.")
        return self._connection

    def fetch_one(self, sql: str, params: dict[str, Any] | None = None) -> dict[str, Any] | None:
        rows = self.fetch_all(sql, params)
        return rows[0] if rows else None

    def fetch_all(self, sql: str, params: dict[str, Any] | None = None) -> list[dict[str, Any]]:
        with self.connection.cursor() as cursor:
            cursor.execute(sql, params or {})
            columns = [col[0].lower() for col in cursor.description]
            return [dict(zip(columns, row)) for row in cursor.fetchall()]

    def execute(self, sql: str, params: dict[str, Any] | None = None) -> None:
        with self.connection.cursor() as cursor:
            cursor.execute(sql, params or {})
        self.connection.commit()

    def get_user_status(self, username: str) -> UserStatus | None:
        normalized = normalize_username(username)
        row = self.fetch_one(
            """
            select username, account_status, lock_date, expiry_date, profile
            from dba_users
            where username = :username
            """,
            {"username": normalized},
        )
        if row is None:
            return None
        return UserStatus(
            username=row["username"],
            account_status=row["account_status"],
            lock_date=row["lock_date"],
            expiry_date=row["expiry_date"],
            profile=row["profile"],
        )

    def unlock_user_sql(self, username: str) -> str:
        return f"alter user {quote_identifier(username)} account unlock"

    def unlock_user(self, username: str) -> None:
        self.execute(self.unlock_user_sql(username))

    def lock_user_sql(self, username: str) -> str:
        return f"alter user {quote_identifier(username)} account lock"

    def lock_user(self, username: str) -> None:
        self.execute(self.lock_user_sql(username))

    def get_session(self, sid: int, serial: int) -> SessionInfo | None:
        row = self.fetch_one(
            """
            select sid, serial#, username, status, machine, program, sql_id, event,
                   blocking_session
            from v$session
            where sid = :sid and serial# = :serial
            """,
            {"sid": sid, "serial": serial},
        )
        if row is None:
            return None
        return SessionInfo(
            sid=int(row["sid"]),
            serial=int(row["serial#"]),
            username=row["username"],
            status=row["status"],
            machine=row["machine"],
            program=row["program"],
            sql_id=row["sql_id"],
            event=row["event"],
            blocking_session=row["blocking_session"],
        )

    def kill_session_sql(self, sid: int, serial: int, immediate: bool = True) -> str:
        suffix = " immediate" if immediate else ""
        return f"alter system kill session '{int(sid)},{int(serial)}'{suffix}"

    def kill_session(self, sid: int, serial: int, immediate: bool = True) -> None:
        self.execute(self.kill_session_sql(sid, serial, immediate=immediate))

    def get_blocking_sessions(self) -> list[dict[str, Any]]:
        return self.fetch_all(
            """
            select
                s.sid,
                s.serial#,
                s.username,
                s.status,
                s.machine,
                s.program,
                s.sql_id,
                s.event,
                s.blocking_session,
                b.username as blocker_username,
                b.machine as blocker_machine,
                b.program as blocker_program,
                b.sql_id as blocker_sql_id
            from v$session s
            left join v$session b on b.sid = s.blocking_session
            where s.blocking_session is not null
            order by s.blocking_session, s.sid
            """
        )

    def get_long_running_sql(self, min_minutes: int = 10) -> list[dict[str, Any]]:
        return self.fetch_all(
            """
            select
                sid,
                serial#,
                username,
                sql_id,
                opname,
                sofar,
                totalwork,
                elapsed_seconds,
                time_remaining,
                round(elapsed_seconds / 60, 1) as elapsed_minutes
            from v$session_longops
            where totalwork > 0
              and sofar < totalwork
              and elapsed_seconds >= :min_seconds
            order by elapsed_seconds desc
            fetch first 20 rows only
            """,
            {"min_seconds": min_minutes * 60},
        )

    def get_tablespace_usage(self) -> list[TablespaceUsage]:
        rows = self.fetch_all(
            """
            select
                df.tablespace_name,
                round((df.total_bytes - nvl(fs.free_bytes, 0)) / 1024 / 1024, 2) used_mb,
                round(nvl(fs.free_bytes, 0) / 1024 / 1024, 2) free_mb,
                round(df.total_bytes / 1024 / 1024, 2) total_mb,
                round((df.total_bytes - nvl(fs.free_bytes, 0)) / df.total_bytes * 100, 2) used_pct
            from (
                select tablespace_name, sum(bytes) total_bytes
                from dba_data_files
                group by tablespace_name
            ) df
            left join (
                select tablespace_name, sum(bytes) free_bytes
                from dba_free_space
                group by tablespace_name
            ) fs on fs.tablespace_name = df.tablespace_name
            order by used_pct desc
            """
        )
        return [
            TablespaceUsage(
                tablespace_name=row["tablespace_name"],
                used_mb=float(row["used_mb"]),
                free_mb=float(row["free_mb"]),
                total_mb=float(row["total_mb"]),
                used_pct=float(row["used_pct"]),
            )
            for row in rows
        ]

    def get_invalid_objects(self, owner: str | None = None) -> list[InvalidObject]:
        params: dict[str, Any] = {}
        owner_clause = ""
        if owner:
            params["owner"] = normalize_username(owner)
            owner_clause = "and owner = :owner"
        rows = self.fetch_all(
            f"""
            select owner, object_name, object_type, status
            from dba_objects
            where status <> 'VALID'
            {owner_clause}
            order by owner, object_type, object_name
            fetch first 100 rows only
            """,
            params,
        )
        return [
            InvalidObject(
                owner=row["owner"],
                object_name=row["object_name"],
                object_type=row["object_type"],
                status=row["status"],
            )
            for row in rows
        ]

    def get_recent_snapshots(self, days: int) -> list[Snapshot]:
        rows = self.fetch_all(
            """
            select dbid, instance_number, snap_id, begin_interval_time, end_interval_time
            from dba_hist_snapshot
            where begin_interval_time >= systimestamp - numtodsinterval(:days, 'DAY')
            order by instance_number, snap_id
            """,
            {"days": days},
        )
        return [
            Snapshot(
                dbid=int(row["dbid"]),
                instance_number=int(row["instance_number"]),
                snap_id=int(row["snap_id"]),
                begin_interval_time=row["begin_interval_time"],
                end_interval_time=row["end_interval_time"],
            )
            for row in rows
        ]

    def generate_awr_report_text(
        self,
        dbid: int,
        instance_number: int,
        begin_snap: int,
        end_snap: int,
    ) -> str:
        rows = self.fetch_all(
            """
            select output
            from table(dbms_workload_repository.awr_report_text(
                :dbid,
                :instance_number,
                :begin_snap,
                :end_snap
            ))
            """,
            {
                "dbid": dbid,
                "instance_number": instance_number,
                "begin_snap": begin_snap,
                "end_snap": end_snap,
            },
        )
        return "\n".join(str(row["output"]) for row in rows)

    # -------------------------------------------------- new read-only methods

    def get_active_sessions(
        self,
        username: str | None = None,
        min_seconds_in_wait: int = 0,
    ) -> list[ActiveSession]:
        """Return currently active sessions, optionally filtered by username.

        Reads from V$SESSION. No license pack required.
        """

        params: dict[str, Any] = {"min_wait": min_seconds_in_wait}
        user_clause = ""
        if username:
            params["username"] = normalize_username(username)
            user_clause = "and s.username = :username"
        rows = self.fetch_all(
            f"""
            select s.sid, s.serial#, s.username, s.status, s.machine, s.program,
                   s.sql_id, s.prev_sql_id, s.event, s.seconds_in_wait, s.logon_time
            from v$session s
            where s.type = 'USER'
              and s.status = 'ACTIVE'
              and nvl(s.seconds_in_wait, 0) >= :min_wait
              {user_clause}
            order by nvl(s.seconds_in_wait, 0) desc, s.sid
            fetch first 50 rows only
            """,
            params,
        )
        return [
            ActiveSession(
                sid=int(row["sid"]),
                serial=int(row["serial#"]),
                username=row["username"],
                status=row["status"],
                machine=row["machine"],
                program=row["program"],
                sql_id=row["sql_id"],
                prev_sql_id=row["prev_sql_id"],
                event=row["event"],
                seconds_in_wait=int(row["seconds_in_wait"]) if row["seconds_in_wait"] is not None else None,
                logon_time=row["logon_time"],
            )
            for row in rows
        ]

    def get_top_sql(
        self,
        metric: str = "elapsed",
        limit: int = 10,
    ) -> list[TopSql]:
        """Return the top N SQL by `elapsed`, `cpu`, `gets`, or `reads`.

        Reads from V$SQL. The metric name is matched against a whitelist so
        the loop can never inject a different column. No license pack required.
        """

        order_by = {
            "elapsed": "elapsed_time desc",
            "cpu": "cpu_time desc",
            "gets": "buffer_gets desc",
            "reads": "disk_reads desc",
        }.get(metric.lower())
        if order_by is None:
            raise ValueError(f"unsupported top_sql metric: {metric!r}")

        rows = self.fetch_all(
            f"""
            select sql_id, plan_hash_value, executions, elapsed_time, cpu_time,
                   buffer_gets, disk_reads, sql_fulltext
            from v$sql
            where executions > 0
            order by {order_by}
            fetch first {int(limit)} rows only
            """,
        )
        out: list[TopSql] = []
        for row in rows:
            executions = row["executions"] or 0
            elapsed = (row["elapsed_time"] or 0) / 1_000_000.0
            cpu = (row["cpu_time"] or 0) / 1_000_000.0
            out.append(
                TopSql(
                    sql_id=str(row["sql_id"]),
                    plan_hash_value=int(row["plan_hash_value"]) if row["plan_hash_value"] is not None else None,
                    executions=int(executions),
                    elapsed_seconds=elapsed,
                    cpu_seconds=cpu,
                    buffer_gets=int(row["buffer_gets"] or 0),
                    disk_reads=int(row["disk_reads"] or 0),
                    sql_text=str(row["sql_fulltext"] or "")[:1000],
                )
            )
        return out

    def get_redo_switches(self, hours: int = 24) -> list[RedoSwitch]:
        """Hourly redo log switch counts over the last `hours` hours.

        Reads from V$LOG_HISTORY. No license pack required.
        """

        rows = self.fetch_all(
            """
            select trunc(first_time, 'HH') as day, count(*) as switches
            from v$log_history
            where first_time >= systimestamp - numtodsinterval(:hours, 'HOUR')
            group by trunc(first_time, 'HH')
            order by trunc(first_time, 'HH')
            """,
            {"hours": int(hours)},
        )
        return [
            RedoSwitch(day=row["day"], switches=int(row["switches"]))
            for row in rows
        ]

    def get_top_wait_events(self, limit: int = 10) -> list[WaitEvent]:
        """Top wait events since instance startup from V$SYSTEM_EVENT.

        No license pack required.
        """

        rows = self.fetch_all(
            """
            select event, total_waits, time_waited_micro, average_wait
            from (
                select event, total_waits, time_waited_micro,
                       case when total_waits = 0 then 0
                            else time_waited_micro / total_waits / 1000
                       end as average_wait
                from v$system_event
                where wait_class != 'Idle'
                order by time_waited_micro desc
            )
            fetch first :limit rows only
            """,
            {"limit": int(limit)},
        )
        return [
            WaitEvent(
                event=str(row["event"]),
                total_waits=int(row["total_waits"] or 0),
                time_waited_seconds=float(row["time_waited_micro"] or 0) / 1_000_000.0,
                average_wait_ms=float(row["average_wait"] or 0),
            )
            for row in rows
        ]

    def get_session_sql(self, sid: int) -> str | None:
        """Return the SQL text currently being run by `sid` (v$sql join).

        Returns None if the session has no current SQL.
        """

        row = self.fetch_one(
            """
            select sql_fulltext
            from v$session s
            left join v$sql q on q.sql_id = s.sql_id
            where s.sid = :sid
            """,
            {"sid": int(sid)},
        )
        if row is None or not row.get("sql_fulltext"):
            return None
        return str(row["sql_fulltext"])

    def explain_sql(self, statement: str) -> ExplainPlan:
        """Run EXPLAIN PLAN for `statement` and return the formatted output.

        `statement` must pass `extract_single_statement()`. We run the plan
        in its own statement_id scope and clean up the PLAN_TABLE afterwards
        so successive calls don't leak rows.
        """

        safe = extract_single_statement(statement)
        # Use a fresh statement_id per call. Lowercase + underscore is safe
        # because we control the value.
        import uuid

        stmt_id = f"agentic_{uuid.uuid4().hex[:12]}"
        try:
            self.execute(f"explain plan set statement_id = '{stmt_id}' for {safe}")
            rows = self.fetch_all(
                """
                select plan_line
                from (
                    select rpad(' ', 2 * (depth - 1)) || operation || ' '
                        || options || ' ' || object_name
                        || ' ' || to_char(cost, '999999990.00') as plan_line,
                        depth
                    from plan_table
                    where statement_id = :stmt_id
                    order by id
                )
                """,
                {"stmt_id": stmt_id},
            )
        finally:
            # Best-effort cleanup. Even if the cursor is broken, do not raise.
            try:
                with self.connection.cursor() as cursor:
                    cursor.execute(
                        "delete from plan_table where statement_id = :stmt_id",
                        {"stmt_id": stmt_id},
                    )
                self.connection.commit()
            except Exception:
                pass
        return ExplainPlan(statement=safe, plan_lines=tuple(r["plan_line"] for r in rows))


# --------------------------------------------------------------- SQL safety


_STATEMENT_TERMINATOR = ";"


def extract_single_statement(statement: str) -> str:
    """Validate that `statement` is a single read-only SQL statement.

    Rejects anything that contains more than one statement (stacked with `;`),
    has unbalanced parentheses, mentions a write keyword, or has trailing
    comments that could hide a second statement. The returned string is
    the trimmed statement, ready to be passed to EXPLAIN PLAN.
    """

    if statement is None:
        raise UnsafeIdentifierError("statement is required")
    text = statement.strip().rstrip(_STATEMENT_TERMINATOR).strip()
    if not text:
        raise UnsafeIdentifierError("statement is empty")
    if text.count(_STATEMENT_TERMINATOR) > 0:
        raise UnsafeIdentifierError("only a single SQL statement is allowed")

    lower = text.lower()
    forbidden = (
        "insert ", "update ", "delete ", "merge ", "drop ", "truncate ",
        "alter ", "create ", "grant ", "revoke ", "commit", "rollback",
        "exec ", "execute ", "call ", "begin ", "declare ",
    )
    for keyword in forbidden:
        if keyword in lower:
            raise UnsafeIdentifierError(f"statement contains forbidden keyword: {keyword.strip()}")

    # Parenthesis balance: cheap defence against malformed input.
    if text.count("(") != text.count(")"):
        raise UnsafeIdentifierError("statement has unbalanced parentheses")

    # Must start with a read-only keyword (or a WITH ... SELECT).
    first_token = lower.split(None, 1)[0] if lower else ""
    allowed_first = {"select", "with", "explain"}
    if first_token not in allowed_first:
        raise UnsafeIdentifierError(
            f"statement must start with one of: {', '.join(sorted(allowed_first))}"
        )
    return text


def group_snapshots_by_instance(snapshots: Iterable[Snapshot]) -> dict[tuple[int, int], list[Snapshot]]:
    grouped: dict[tuple[int, int], list[Snapshot]] = {}
    for snapshot in snapshots:
        grouped.setdefault((snapshot.dbid, snapshot.instance_number), []).append(snapshot)
    return grouped
