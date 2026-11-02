"""Execution-based answer matching: compare result rows, not SQL text."""
import re
from collections import Counter
from datetime import date, datetime
from decimal import Decimal
from itertools import product

MAX_COLUMN_MAPPINGS = 1000


def _norm(value):
    if isinstance(value, bool) or value is None:
        return value
    if isinstance(value, (int, float, Decimal)):
        return round(float(value), 2)
    if isinstance(value, (date, datetime)):
        return value.isoformat()[:10]
    if isinstance(value, str):
        v = value.strip()
        if re.fullmatch(r"\d{4}-\d{2}", v):  # '2026-01' and '2026-01-01' are the same month bucket
            return v + "-01"
        try:
            return round(float(v), 2)
        except ValueError:
            return v[:10] if len(v) >= 10 and v[4] == "-" and v[7] == "-" else v.lower()
    return value


def rows_match(reference: list[list], candidate: list[list], ordered: bool = False) -> bool:
    """True if some choice of candidate columns reproduces the reference rows.

    Extra candidate columns (ids, names alongside figures) are allowed; column names are ignored.
    """
    if len(reference) != len(candidate):
        return False
    if not reference:
        return True
    ref = [[_norm(v) for v in row] for row in reference]
    cand = [[_norm(v) for v in row] for row in candidate]

    ref_cols = list(zip(*ref))
    cand_cols = list(zip(*cand))
    options = [[k for k, cc in enumerate(cand_cols) if Counter(cc) == Counter(rc)] for rc in ref_cols]
    if any(not o for o in options):
        return False

    for i, mapping in enumerate(product(*options)):
        if i >= MAX_COLUMN_MAPPINGS:
            return False
        projected = [tuple(row[k] for k in mapping) for row in cand]
        expected = [tuple(row) for row in ref]
        if (projected == expected) if ordered else (Counter(projected) == Counter(expected)):
            return True
    return False
