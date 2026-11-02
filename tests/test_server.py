import asyncio
import os

import pytest

from mcp.server.mcpserver.exceptions import ToolError

from leadflow_mcp import server
from leadflow_mcp.config import _load_dotenv

_load_dotenv()


def test_tools_are_registered_read_only():
    tools = {t.name: t for t in asyncio.run(server.server.list_tools())}
    assert set(tools) == {"list_tables", "describe_table", "run_query", "ask"}
    assert all(t.annotations.read_only_hint for t in tools.values())


def test_describe_unknown_table():
    with pytest.raises(ToolError, match="Unknown table"):
        server.describe_table("staff_accounts")


@pytest.mark.skipif(not os.environ.get("READONLY_DATABASE_URL"), reason="needs the database")
def test_run_query_rejects_writes():
    with pytest.raises(ToolError, match="Query rejected"):
        server.run_query("DELETE FROM sales")
