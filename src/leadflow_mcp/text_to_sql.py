"""Plain-English question -> checked SQL -> rows, with errors fed back to the model."""

import json
from dataclasses import asdict, dataclass, field

import anthropic
import psycopg
from pydantic import BaseModel, ValidationError

from . import db, schema_docs
from .config import Settings

SYSTEM = f"""You write one PostgreSQL query that answers a question about a lead-generation business's data.

{schema_docs.render()}

Rules:
- Write a single SELECT (CTEs are fine). Never modify data.
- Use only the tables and columns above; don't guess names.
- Inline literal values; don't use placeholders.
- Give computed columns clear aliases, and round money and percentages to 2 decimal places.
- Include identifying columns (such as names) alongside figures when the question asks "which".
- If the question can't be answered from this data, set sql to null and say why in explanation."""


class SqlAnswer(BaseModel):
    sql: str | None
    explanation: str


ANSWER_SCHEMA = {
    "type": "object",
    "properties": {
        "sql": {"anyOf": [{"type": "string"}, {"type": "null"}]},
        "explanation": {"type": "string"},
    },
    "required": ["sql", "explanation"],
    "additionalProperties": False,
}

# USD per million tokens: input, output, cache read. Cache writes bill at 1.25x input.
PRICES = {
    "claude-opus-5-5": (4.00, 20.00, 0.20),
    "claude-sonnet-5-5": (2.00, 10.00, 0.20),
    "claude-haiku-5-5": (0.10, 0.50, 0.01),
}
# Server-side refusal fallback isn't available for Haiku.
FALLBACK_MODELS = {"claude-opus-5-5", "claude-sonnet-5-5", "claude-fable-5-1"}


@dataclass
class Usage:
    input_tokens: int = 0
    output_tokens: int = 0
    cache_read_tokens: int = 0
    cache_write_tokens: int = 0

    def add(self, u) -> None:
        self.input_tokens += u.input_tokens
        self.output_tokens += u.output_tokens
        self.cache_read_tokens += u.cache_read_input_tokens or 0
        self.cache_write_tokens += u.cache_creation_input_tokens or 0

    def cost_usd(self, model: str) -> float | None:
        if model not in PRICES:
            return None
        inp, out, cache_read = PRICES[model]
        return round((self.input_tokens * inp + self.output_tokens * out
                      + self.cache_read_tokens * cache_read
                      + self.cache_write_tokens * inp * 1.25) / 1_000_000, 6)


@dataclass
class AskResult:
    question: str
    sql: str | None = None
    explanation: str = ""
    columns: list[str] = field(default_factory=list)
    rows: list[list] = field(default_factory=list)
    truncated: bool = False
    error: str | None = None
    attempts: int = 0
    model: str = ""
    usage: Usage = field(default_factory=Usage)
    cost_usd: float | None = None

    def to_dict(self) -> dict:
        return asdict(self)


def _request(client: anthropic.Anthropic, settings: Settings, messages: list):
    kwargs = {}
    if settings.model in FALLBACK_MODELS:
        kwargs = {"betas": ["server-side-fallback-2026-07-01"], "fallbacks": "default"}
    return client.beta.messages.create(
        model=settings.model,
        max_tokens=16000,
        system=[{"type": "text", "text": SYSTEM, "cache_control": {"type": "ephemeral"}}],
        output_config={"effort": settings.effort, "format": {"type": "json_schema", "schema": ANSWER_SCHEMA}},
        messages=messages,
        **kwargs,
    )


def ask(question: str, settings: Settings, client: anthropic.Anthropic | None = None) -> AskResult:
    client = client or anthropic.Anthropic()
    result = AskResult(question=question, model=settings.model)
    messages: list = [{"role": "user", "content": question}]

    for attempt in range(1, settings.max_retries + 2):
        result.attempts = attempt
        response = _request(client, settings, messages)
        result.usage.add(response.usage)

        if response.stop_reason == "refusal":
            result.error = "The model declined this question."
            break
        text = next((b.text for b in response.content if b.type == "text"), "")
        try:
            answer = SqlAnswer.model_validate(json.loads(text))
        except (json.JSONDecodeError, ValidationError):
            result.error = "The model returned malformed output."
            break

        result.sql, result.explanation = answer.sql, answer.explanation
        if answer.sql is None:
            result.error = answer.explanation or "The question can't be answered from this data."
            break

        try:
            qr = db.run_readonly(settings.readonly_database_url, answer.sql, settings.max_rows)
        except (db.QueryRejected, psycopg.Error) as e:
            # Append-only history: the failed attempt stays, and the error goes back to the model.
            result.error = f"{type(e).__name__}: {str(e).strip().splitlines()[0]}"
            messages += [
                {"role": "assistant", "content": response.content},
                {"role": "user", "content": f"That query failed: {result.error}\nFix it and return the corrected query."},
            ]
            continue

        result.sql, result.columns, result.rows, result.truncated = qr.sql, qr.columns, qr.rows, qr.truncated
        result.error = None
        break

    result.cost_usd = result.usage.cost_usd(settings.model)
    return result
