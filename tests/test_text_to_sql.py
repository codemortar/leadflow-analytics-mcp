"""Pipeline tests with a stand-in client, so they run without an API key."""

import json
import os
from types import SimpleNamespace

import pytest

from leadflow_mcp import text_to_sql
from leadflow_mcp.config import _load_dotenv, get_settings

_load_dotenv()
pytestmark = pytest.mark.skipif(not os.environ.get("READONLY_DATABASE_URL"), reason="needs the database")


class FakeClient:
    """Returns queued replies and records each request."""

    def __init__(self, *replies):
        self.replies = list(replies)
        self.requests = []
        self.beta = SimpleNamespace(messages=SimpleNamespace(create=self._create))

    def _create(self, **kwargs):
        self.requests.append(kwargs)
        stop_reason, payload = self.replies.pop(0)
        content = [] if payload is None else [SimpleNamespace(type="text", text=json.dumps(payload))]
        usage = SimpleNamespace(input_tokens=1000, output_tokens=100,
                                cache_read_input_tokens=0, cache_creation_input_tokens=0)
        return SimpleNamespace(stop_reason=stop_reason, content=content, usage=usage)


def test_answers_a_question():
    client = FakeClient(("end_turn", {"sql": "SELECT count(*) FROM affiliates", "explanation": "Counts affiliates."}))
    result = text_to_sql.ask("How many affiliates?", get_settings(), client)
    assert result.error is None
    assert result.rows == [[30]]
    assert result.attempts == 1
    assert result.cost_usd and result.cost_usd > 0


def test_retries_with_the_error_after_a_rejected_query():
    client = FakeClient(
        ("end_turn", {"sql": "SELECT * FROM staff_accounts", "explanation": "Wrong table."}),
        ("end_turn", {"sql": "SELECT count(*) FROM buyers", "explanation": "Counts buyers."}),
    )
    result = text_to_sql.ask("How many buyers?", get_settings(), client)
    assert result.error is None
    assert result.rows == [[11]]
    assert result.attempts == 2
    feedback = client.requests[1]["messages"][-1]["content"]
    assert "Table not allowed: staff_accounts" in feedback


def test_gives_up_after_max_retries():
    bad = ("end_turn", {"sql": "DELETE FROM sales", "explanation": "No."})
    settings = get_settings()
    client = FakeClient(*[bad] * (settings.max_retries + 1))
    result = text_to_sql.ask("Delete everything", settings, client)
    assert result.error and "Only SELECT" in result.error
    assert result.attempts == settings.max_retries + 1


def test_unanswerable_question():
    client = FakeClient(("end_turn", {"sql": None, "explanation": "There is no salary data."}))
    result = text_to_sql.ask("What are staff salaries?", get_settings(), client)
    assert result.error == "There is no salary data."
    assert result.rows == []


def test_refusal_is_reported():
    client = FakeClient(("refusal", None))
    result = text_to_sql.ask("...", get_settings(), client)
    assert result.error == "The model declined this question."


def test_request_uses_structured_output_and_caching():
    client = FakeClient(("end_turn", {"sql": "SELECT 1", "explanation": "x"}))
    text_to_sql.ask("q", get_settings(), client)
    request = client.requests[0]
    assert request["output_config"]["format"]["type"] == "json_schema"
    assert request["system"][0]["cache_control"] == {"type": "ephemeral"}
