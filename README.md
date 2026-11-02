# leadflow-analytics-mcp

An MCP server that lets AI clients answer plain-English questions over a lead-generation business's data, with checked, read-only database access. It comes with an evaluation suite that scores the answers against reference queries.

The data is generated: a fictional US consumer-finance lead-generation business, with 30 affiliates and 11 buyers, plus about 50,000 leads, 123,000 buyer pings and 40,000 sales between January 2025 and October 2026. Each lead is offered to buyers in turn, highest bid first, until one accepts. Sold leads can be returned for a refund.

Three patterns are planted in the data for the kind of "why did this number move" questions an analyst gets asked:

- Summit Lending stops accepting leads in mid-August 2026.
- BrightPath Media's lead quality drops from September 2026, with more duplicates and returns.
- RateBridge Exchange cuts its auto-loan bids by 20% from June 2026.

## Tools

| Tool | What it does |
|---|---|
| `list_tables` | Tables available, with a description of each |
| `describe_table` | Columns in business terms, plus the rules for revenue, margin, acceptance and returns |
| `run_query` | Runs a client-written SELECT through the guard and the read-only role |
| `ask` | Answers a plain-English question end to end: Claude writes the SQL, the server checks and runs it, and feeds any error back for a retry |

All four are annotated read-only. A capable client can use the first three to write its own queries; `ask` is for clients that just want answers, and it's what the evals measure.

## Keeping generated SQL safe

Two independent layers, so a mistake in one is caught by the other:

1. **SQL guard** (`sql_guard.py`). Parses each query with sqlglot rather than matching text, then requires: exactly one statement, a query (no writes anywhere, including `DELETE` inside a `WITH`, `SELECT … INTO` and `FOR UPDATE`), tables from an allow-list, no `pg_*` or other system functions, no sensitive columns.
2. **Read-only database role** (`db/readonly_role.sql`). `SELECT` on the business tables only, no access to `staff_accounts`, read-only transactions by default and a statement timeout. Queries also run in an explicitly read-only transaction with a row limit.

The tests check the role directly with the guard bypassed, so each layer is tested on its own.

## Getting good answers cheaply

- The model sees a hand-written description of the data (`schema_docs.py`) with the business rules spelled out (net revenue, margin, acceptance, sell-through, return rate) rather than raw DDL.
- Structured output (JSON schema) for the query and explanation, so there's no parsing of free text.
- The system prompt is cached, so repeated questions pay for it once.
- Failed queries go back to the model with the database or guard error, up to two retries.
- If a question can't be answered from the data, the model says so instead of guessing.
- Token usage and cost are tracked per question.

## Evaluation

`evals/questions.yaml` holds 25 questions:

- volumes, sell-through, net revenue and margin
- buyer acceptance and response times
- the planted patterns: which buyer stopped buying, which affiliate's returns spiked, how a buyer's price changed
- two that can't be answered from the data
- two adversarial requests: deleting data, and reading password hashes

Each answerable question has a reference query. An answer passes if its rows match the reference's rows, regardless of SQL text, column names, extra columns or row order (unless order matters). Unanswerable and adversarial questions pass only if the model declines or the guard blocks them.

```bash
python evals/run.py                                   # full run
python evals/run.py --model claude-sonnet-5-5 --effort low
python evals/run.py --reference-only                  # no API calls; checks the references still run
```

Each run writes per-question results, token use, cost and timing to `evals/results/`. CI runs the evals on `main` and fails below 85% accuracy.

### Results

| Model | Effort | Accuracy | Cost per run | Mean time per question |
|---|---|---|---|---|
| Claude Opus 5.5 | medium | 25/25 | $0.21 | 4.5s |
| Claude Sonnet 5.5 | low | 25/25 | $0.08 | 2.8s |

Both answered every question correctly, with Sonnet at low effort costing about 37% as much and answering faster, so it's the better default for this workload. Since both score 100%, these questions don't yet separate the models; harder questions are the next step (see below).

## Running it

Requirements: Python 3.11+, PostgreSQL.

```bash
python -m venv .venv && .venv/bin/pip install -e ".[dev]"
cp .env.example .env                       # set READONLY_DATABASE_URL's password and ANTHROPIC_API_KEY
createdb leadflow_mcp
DATABASE_URL=postgresql:///leadflow_mcp .venv/bin/python scripts/seed.py
psql -d leadflow_mcp -v readonly_password="'your-password'" -f db/readonly_role.sql
.venv/bin/pytest
```

Or with Docker: `READONLY_PASSWORD=... ANTHROPIC_API_KEY=... docker compose up` serves it over HTTP at `http://localhost:8000/mcp`.

### Connecting a client

Claude Code:

```bash
claude mcp add leadflow-analytics -- /path/to/leadflow-analytics-mcp/.venv/bin/leadflow-mcp
```

Claude Desktop (`claude_desktop_config.json`):

```json
{
  "mcpServers": {
    "leadflow-analytics": {
      "command": "/path/to/leadflow-analytics-mcp/.venv/bin/leadflow-mcp"
    }
  }
}
```

## Layout

```
src/leadflow_mcp/
  server.py         MCP tools
  text_to_sql.py    question -> SQL -> rows, with retries, cost tracking
  sql_guard.py      AST-based query checks
  db.py             read-only execution with row limit
  schema_docs.py    the data described in business terms
  eval_compare.py   result matching for evals
db/                 schema and read-only role
scripts/seed.py     deterministic data generator, including the planted patterns
evals/              questions, reference queries, runner
tests/              guard, role, pipeline (with a stand-in client), server
```

## Next

- Deploy to AWS with Terraform, behind authentication (the HTTP mode has none yet, so it should only run locally or behind a gateway).
- Anomaly alerts: flag material week-on-week moves in volume, acceptance, price, returns and margin, with a generated summary of the likely cause.
- Harder eval questions (ambiguous wording, multi-step "why" questions) to separate models that currently score the same.
