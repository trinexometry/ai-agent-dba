import pytest

from oracle_db_agent.db import UnsafeIdentifierError, normalize_username, quote_identifier


def test_normalize_username_uppercases_simple_identifier() -> None:
    assert normalize_username("scott_01") == "SCOTT_01"


def test_quote_identifier_quotes_normalized_username() -> None:
    assert quote_identifier("scott") == '"SCOTT"'


@pytest.mark.parametrize(
    "username",
    [
        "SCOTT account unlock",
        "SCOTT; drop user HR",
        "1SCOTT",
        "SCOTT.ADMIN",
        'SCOTT"',
    ],
)
def test_normalize_username_rejects_unsafe_values(username: str) -> None:
    with pytest.raises(UnsafeIdentifierError):
        normalize_username(username)
