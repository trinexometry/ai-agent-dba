from oracle_db_agent.tools.registry import default_registry


def tool_name(prompt: str) -> str | None:
    selection = default_registry().select(prompt)
    return selection.tool.name if selection else None


def test_routes_unlock_user() -> None:
    assert tool_name("unlock user SCOTT") == "unlock_user"


def test_routes_lock_user() -> None:
    assert tool_name("lock user SCOTT") == "lock_user"


def test_routes_user_status() -> None:
    assert tool_name("check user SCOTT status") == "show_user"


def test_routes_kill_session() -> None:
    assert tool_name("kill session sid 123 serial 456") == "kill_session"


def test_routes_blocking_sessions() -> None:
    assert tool_name("show blocking sessions") == "blocking_sessions"


def test_routes_long_running_sql() -> None:
    assert tool_name("show long running sql") == "long_running_sql"


def test_routes_tablespace_usage() -> None:
    assert tool_name("show tablespace usage") == "tablespace_usage"


def test_routes_invalid_objects() -> None:
    assert tool_name("show invalid objects in schema HR") == "invalid_objects"


def test_routes_awr_analysis() -> None:
    assert tool_name("analyze past 4 days database report") == "analyze_awr"
