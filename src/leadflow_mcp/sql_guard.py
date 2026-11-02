"""Application-level check on model-written SQL. The read-only database role is the backstop."""

from dataclasses import dataclass

import sqlglot
from sqlglot import exp

from .schema_docs import TABLES

ALLOWED_TABLES = frozenset(TABLES)
ALLOWED_SCHEMAS = frozenset({"leadflow"})
SENSITIVE_COLUMNS = frozenset({"password_hash"})
# pg_* covers pg_sleep, pg_read_file and the catalogue helpers.
BLOCKED_FUNCTIONS = frozenset({
    "dblink", "lo_import", "lo_export", "set_config", "current_setting",
    "query_to_xml", "query_to_xml_and_xmlschema", "copy",
})
WRITE_NODES = (
    exp.Insert, exp.Update, exp.Delete, exp.Merge, exp.Create, exp.Drop, exp.Alter,
    exp.Command, exp.Into, exp.Lock, exp.Grant, exp.Set, exp.TruncateTable,
)


@dataclass(frozen=True)
class GuardResult:
    ok: bool
    reason: str = ""
    sql: str = ""  # normalised SQL, safe to wrap in a subquery


def _reject(reason: str) -> GuardResult:
    return GuardResult(ok=False, reason=reason)


def check(sql: str) -> GuardResult:
    try:
        statements = [s for s in sqlglot.parse(sql, read="postgres") if s is not None]
    except sqlglot.errors.ParseError as e:
        return _reject(f"Could not parse the query: {str(e).splitlines()[0]}")
    if len(statements) != 1:
        return _reject("Exactly one statement is allowed.")
    stmt = statements[0]
    if not isinstance(stmt, exp.Query):
        return _reject("Only SELECT queries are allowed.")

    for node in stmt.walk():
        if isinstance(node, WRITE_NODES):
            return _reject(f"Statement type not allowed: {node.key.upper()}.")

    cte_names = {cte.alias_or_name.lower() for cte in stmt.find_all(exp.CTE)}
    for table in stmt.find_all(exp.Table):
        name, schema = table.name.lower(), table.db.lower()
        if not schema and name in cte_names:
            continue
        if schema and schema not in ALLOWED_SCHEMAS:
            return _reject(f"Schema not allowed: {schema}.")
        if name not in ALLOWED_TABLES:
            return _reject(f"Table not allowed: {name}.")

    for func in stmt.find_all(exp.Func):
        name = (func.name if isinstance(func, exp.Anonymous) else func.sql_name()).lower()
        if name.startswith("pg_") or name in BLOCKED_FUNCTIONS:
            return _reject(f"Function not allowed: {name}.")

    for column in stmt.find_all(exp.Column):
        if column.name.lower() in SENSITIVE_COLUMNS:
            return _reject(f"Column not allowed: {column.name}.")

    return GuardResult(ok=True, sql=stmt.sql(dialect="postgres"))
