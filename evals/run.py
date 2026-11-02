"""Run the question set through the text-to-SQL pipeline and score it against reference answers.

  python evals/run.py                       # full run (calls the Claude API)
  python evals/run.py --reference-only      # check every reference query runs; no API calls
  python evals/run.py --model claude-sonnet-5-5 --effort low --only revenue-2025,win-rate-by-type
  python evals/run.py --min-accuracy 0.9    # non-zero exit below the threshold (for CI)
"""

import argparse
import json
import sys
import time
from dataclasses import replace
from datetime import datetime, timezone
from pathlib import Path

import yaml

from leadflow_mcp import db, text_to_sql
from leadflow_mcp.config import get_settings
from leadflow_mcp.eval_compare import rows_match

HERE = Path(__file__).resolve().parent


def load_questions(only: set[str] | None) -> list[dict]:
    questions = yaml.safe_load((HERE / "questions.yaml").read_text())
    return [q for q in questions if not only or q["id"] in only]


def reference_rows(q: dict, settings) -> list[list]:
    return db.run_readonly(settings.readonly_database_url, q["reference_sql"], 10_000).rows


def score(q: dict, result: text_to_sql.AskResult, settings) -> tuple[bool, str]:
    expect = q.get("expect", "rows")
    if expect in ("unanswerable", "rejected"):
        return (result.error is not None, "declined" if result.error else "answered when it should have declined")
    if result.error:
        return False, result.error
    expected = reference_rows(q, settings)
    if rows_match(expected, result.rows, ordered=q.get("ordered", False)):
        return True, "match"
    return False, f"rows differ: expected {expected[:3]}{'...' if len(expected) > 3 else ''}, got {result.rows[:3]}"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--reference-only", action="store_true")
    parser.add_argument("--model")
    parser.add_argument("--effort")
    parser.add_argument("--only", help="comma-separated question ids")
    parser.add_argument("--min-accuracy", type=float, default=0.0)
    args = parser.parse_args()

    settings = get_settings()
    settings = replace(settings, model=args.model or settings.model, effort=args.effort or settings.effort)
    questions = load_questions(set(args.only.split(",")) if args.only else None)

    if args.reference_only:
        failures = 0
        for q in questions:
            if "reference_sql" not in q:
                continue
            try:
                rows = reference_rows(q, settings)
                print(f"ok    {q['id']:<40} {len(rows)} row(s)  {rows[:2]}")
            except Exception as e:  # report every broken reference, not just the first
                failures += 1
                print(f"FAIL  {q['id']:<40} {e}")
        return 1 if failures else 0

    records, passed, total_cost = [], 0, 0.0
    for q in questions:
        started = time.monotonic()
        result = text_to_sql.ask(q["question"], settings)
        ok, detail = score(q, result, settings)
        passed += ok
        total_cost += result.cost_usd or 0
        records.append({
            "id": q["id"], "passed": ok, "detail": detail, "seconds": round(time.monotonic() - started, 2),
            **{k: v for k, v in result.to_dict().items() if k not in ("rows", "question")},
            "row_count": len(result.rows),
        })
        print(f"{'PASS' if ok else 'FAIL'}  {q['id']:<40} attempts={result.attempts} "
              f"cost=${result.cost_usd or 0:.4f}  {'' if ok else detail}")

    accuracy = passed / len(questions) if questions else 0.0
    summary = {
        "model": settings.model, "effort": settings.effort, "questions": len(questions), "passed": passed,
        "accuracy": round(accuracy, 3), "total_cost_usd": round(total_cost, 4),
        "mean_seconds": round(sum(r["seconds"] for r in records) / max(len(records), 1), 2),
    }
    print(json.dumps(summary, indent=2))

    out_dir = HERE / "results"
    out_dir.mkdir(exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    (out_dir / f"{stamp}-{settings.model}-{settings.effort}.json").write_text(
        json.dumps({"summary": summary, "results": records}, indent=2, default=str))
    return 0 if accuracy >= args.min_accuracy else 1


if __name__ == "__main__":
    sys.exit(main())
