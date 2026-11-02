"""MCP server exposing a lead-generation business's data through checked, read-only tools."""

import os

from mcp.server import MCPServer
from mcp.server.mcpserver.exceptions import ToolError
from mcp.types import ToolAnnotations
from pydantic import BaseModel

from . import db, schema_docs, text_to_sql
from .config import get_settings

server = MCPServer(
    "leadflow-analytics",
    instructions=(
        "Read-only access to a lead-generation business's data: affiliates, campaigns, leads, buyer pings, sales and returns. "
        "Use list_tables and describe_table to learn the data, then run_query for your own SELECT queries, "
        "or ask to have a plain-English question answered end to end."
    ),
)
READ_ONLY = ToolAnnotations(read_only_hint=True, idempotent_hint=True, open_world_hint=False)


class QueryOutput(BaseModel):
    sql: str
    columns: list[str]
    rows: list[list]
    truncated: bool


class AskOutput(QueryOutput):
    explanation: str
    attempts: int
    model: str
    cost_usd: float | None


@server.tool(annotations=READ_ONLY)
def list_tables() -> list[dict]:
    """List the tables available, with a one-line description of each."""
    return [{"table": name, "description": info["description"]} for name, info in schema_docs.TABLES.items()]


@server.tool(annotations=READ_ONLY)
def describe_table(table: str) -> dict:
    """Describe a table's columns, plus the business rules for revenue, margin, acceptance and returns."""
    info = schema_docs.TABLES.get(table.lower())
    if info is None:
        raise ToolError(f"Unknown table '{table}'. Use list_tables to see what's available.")
    return {"table": table.lower(), **info, "rules": schema_docs.RULES}


@server.tool(annotations=READ_ONLY)
def run_query(sql: str, max_rows: int = 200) -> QueryOutput:
    """Run one read-only SELECT query (CTEs allowed) and return the rows.

    Queries are checked before running and execute as a read-only database role,
    so writes, system tables and sensitive columns are rejected.
    """
    settings = get_settings()
    try:
        result = db.run_readonly(settings.readonly_database_url, sql, min(max_rows, settings.max_rows))
    except db.QueryRejected as e:
        raise ToolError(f"Query rejected: {e}") from e
    return QueryOutput(sql=result.sql, columns=result.columns, rows=result.rows, truncated=result.truncated)


@server.tool(annotations=READ_ONLY)
def ask(question: str) -> AskOutput:
    """Answer a plain-English question about the data: writes the SQL, checks and runs it,
    retrying with the error if it fails. Returns the SQL used alongside the rows."""
    result = text_to_sql.ask(question, get_settings())
    if result.error:
        raise ToolError(result.error)
    return AskOutput(
        sql=result.sql, columns=result.columns, rows=result.rows, truncated=result.truncated,
        explanation=result.explanation, attempts=result.attempts, model=result.model, cost_usd=result.cost_usd,
    )


def main() -> None:
    # stdio for local clients (Claude Desktop, Claude Code); streamable-http for a hosted deployment.
    if os.environ.get("MCP_TRANSPORT") == "streamable-http":
        server.run("streamable-http", host=os.environ.get("HOST", "127.0.0.1"), port=int(os.environ.get("PORT", "8000")))
    else:
        server.run()


if __name__ == "__main__":
    main()
