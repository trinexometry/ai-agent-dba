"""Tests for `extract_single_statement` (the SQL safety helper)."""

from __future__ import annotations

import pytest

from oracle_db_agent.db import UnsafeIdentifierError, extract_single_statement


def test_accepts_select() -> None:
    assert extract_single_statement("select 1 from dual") == "select 1 from dual"


def test_accepts_with_clause() -> None:
    s = "with t as (select 1 a from dual) select a from t"
    assert extract_single_statement(s) == s


def test_strips_trailing_semicolon() -> None:
    out = extract_single_statement("select 1 from dual;")
    assert ";" not in out
    assert out.startswith("select")


def test_rejects_stacked_statements() -> None:
    with pytest.raises(UnsafeIdentifierError):
        extract_single_statement("select 1 from dual; drop table x")


def test_rejects_ddl_keywords() -> None:
    for bad in ("drop ", "truncate ", "alter ", "create ", "grant ", "revoke "):
        with pytest.raises(UnsafeIdentifierError):
            extract_single_statement(f"{bad}table x")


def test_rejects_dml_keywords() -> None:
    for bad in ("insert ", "update ", "delete ", "merge "):
        with pytest.raises(UnsafeIdentifierError):
            extract_single_statement(f"{bad}table x values (1)")


def test_rejects_txn_keywords_anywhere() -> None:
    for bad in ("commit", "rollback"):
        with pytest.raises(UnsafeIdentifierError):
            extract_single_statement(f"select 1 from {bad}")


def test_rejects_unbalanced_parens() -> None:
    with pytest.raises(UnsafeIdentifierError):
        extract_single_statement("select 1 from (dual")


def test_rejects_empty() -> None:
    with pytest.raises(UnsafeIdentifierError):
        extract_single_statement("")


def test_rejects_wrong_first_token() -> None:
    with pytest.raises(UnsafeIdentifierError):
        extract_single_statement("show tables")


def test_accepts_explain() -> None:
    s = "explain plan for select 1 from dual"
    assert extract_single_statement(s) == s


def test_rejects_exec() -> None:
    with pytest.raises(UnsafeIdentifierError):
        extract_single_statement("exec dbms_output.put_line('hi')")
