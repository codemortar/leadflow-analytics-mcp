from dataclasses import dataclass, field
from datetime import date, datetime
from decimal import Decimal

import psycopg

from . import sql_guard


class QueryRejected(Exception):
    pass


@dataclass
class QueryResult:
    sql: str
    columns: list[str]
    rows: list[list] = field(default_factory=list)
    truncated: bool = False


def _jsonable(value):
    if isinstance(value, Decimal):
        return float(value)
    if isinstance(value, (date, datetime)):
        return value.isoformat()
    return value


def run_readonly(database_url: str, sql: str, max_rows: int) -> QueryResult:
    """Guard, then run as the read-only role. Raises QueryRejected or psycopg.Error."""
    verdict = sql_guard.check(sql)
    if not verdict.ok:
        raise QueryRejected(verdict.reason)

    # Fetch one extra row to know whether the result was cut off.
    wrapped = f"SELECT * FROM ({verdict.sql}) AS q LIMIT {max_rows + 1}"
    with psycopg.connect(database_url) as conn:
        conn.read_only = True
        with conn.cursor() as cur:
            cur.execute("SET LOCAL statement_timeout = '5s'")
            cur.execute(wrapped)
            columns = [d.name for d in cur.description]
            rows = cur.fetchall()
    return QueryResult(
        sql=verdict.sql,
        columns=columns,
        rows=[[_jsonable(v) for v in row] for row in rows[:max_rows]],
        truncated=len(rows) > max_rows,
    )
