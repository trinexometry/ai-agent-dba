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


def group_snapshots_by_instance(snapshots: Iterable[Snapshot]) -> dict[tuple[int, int], list[Snapshot]]:
    grouped: dict[tuple[int, int], list[Snapshot]] = {}
    for snapshot in snapshots:
        grouped.setdefault((snapshot.dbid, snapshot.instance_number), []).append(snapshot)
    return grouped
