"""Runs against a seeded database. Skipped when READONLY_DATABASE_URL isn't available."""

import os

import psycopg
import pytest

from leadflow_mcp import db
from leadflow_mcp.config import _load_dotenv

_load_dotenv()
URL = os.environ.get("READONLY_DATABASE_URL")
pytestmark = pytest.mark.skipif(not URL, reason="READONLY_DATABASE_URL not set")


def test_runs_a_guarded_query():
    result = db.run_readonly(URL, "SELECT count(*) AS n FROM affiliates", 10)
    assert result.columns == ["n"]
    assert result.rows == [[30]]


def test_truncates_to_max_rows():
    result = db.run_readonly(URL, "SELECT ping_id FROM pings", 5)
    assert len(result.rows) == 5
    assert result.truncated


def test_guard_rejects_before_the_database_sees_it():
    with pytest.raises(db.QueryRejected):
        db.run_readonly(URL, "DELETE FROM sales", 10)


# The role must hold even if the guard is bypassed, so these go straight to the database.
def test_role_cannot_write():
    with psycopg.connect(URL) as conn, pytest.raises(psycopg.errors.ReadOnlySqlTransaction):
        conn.execute("DELETE FROM sales WHERE sale_id = -1")


def test_role_cannot_read_staff_accounts():
    with psycopg.connect(URL) as conn, pytest.raises(psycopg.errors.InsufficientPrivilege):
        conn.execute("SELECT * FROM staff_accounts")


def test_role_has_statement_timeout():
    with psycopg.connect(URL) as conn, pytest.raises(psycopg.errors.QueryCanceled):
        conn.execute("SET statement_timeout = '200ms'")
        conn.execute("SELECT pg_sleep(1)")
