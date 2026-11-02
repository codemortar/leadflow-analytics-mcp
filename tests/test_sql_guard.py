import pytest

from leadflow_mcp.sql_guard import check

ALLOWED = [
    "SELECT name FROM affiliates",
    "SELECT count(*) FROM leadflow.pings WHERE accepted",
    "WITH t AS (SELECT * FROM sales) SELECT count(*) FROM t",
    "SELECT a.name FROM affiliates a JOIN campaigns c USING (affiliate_id) UNION SELECT name FROM buyers",
    "SELECT date_trunc('month', sold_at), sum(price) FROM sales GROUP BY 1",
    "SELECT * FROM buyers -- trailing comment",
]

REJECTED = [
    ("SELECT 1; DROP TABLE leads", "one statement"),
    ("DELETE FROM leads", "Only SELECT"),
    ("UPDATE campaigns SET payout = 0", "Only SELECT"),
    ("WITH x AS (DELETE FROM returns RETURNING *) SELECT * FROM x", "DELETE"),
    ("SELECT * INTO copy_of_sales FROM sales", "INTO"),
    ("SELECT * FROM sales FOR UPDATE", "LOCK"),
    ("SELECT * FROM staff_accounts", "staff_accounts"),
    ('SELECT * FROM "staff_accounts"', "staff_accounts"),
    ("SELECT * FROM leadflow.staff_accounts", "staff_accounts"),
    ("SELECT * FROM pg_catalog.pg_tables", "pg_catalog"),
    ("SELECT * FROM information_schema.columns", "information_schema"),
    ("SELECT pg_sleep(10)", "pg_sleep"),
    ("SELECT current_setting('is_superuser')", "current_setting"),
    ("SELECT password_hash FROM affiliates", "password_hash"),
    ("COPY sales TO '/tmp/out'", "Only SELECT"),
    ("SELECT FROM WHERE", "parse"),
]


@pytest.mark.parametrize("sql", ALLOWED)
def test_allows_read_queries(sql):
    result = check(sql)
    assert result.ok, result.reason
    assert result.sql


@pytest.mark.parametrize("sql,reason", REJECTED)
def test_rejects_unsafe_queries(sql, reason):
    result = check(sql)
    assert not result.ok
    assert reason.lower() in result.reason.lower()
