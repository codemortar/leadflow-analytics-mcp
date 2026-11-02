from leadflow_mcp.eval_compare import rows_match


def test_scalar_with_rounding():
    assert rows_match([[1169426.29]], [["1169426.2900"]])


def test_ignores_extra_columns_and_order():
    ref = [["trade", 33], ["retail", 8]]
    cand = [[8, "retail", 4], [33, "trade", 1]]
    assert rows_match(ref, cand)


def test_ordered_comparison():
    ref = [["a", 2], ["b", 1]]
    assert rows_match(ref, [["a", 2], ["b", 1]], ordered=True)
    assert not rows_match(ref, [["b", 1], ["a", 2]], ordered=True)


def test_wrong_values_fail():
    assert not rows_match([["trade", 33]], [["trade", 34]])


def test_row_count_must_match():
    assert not rows_match([["a"]], [["a"], ["b"]])


def test_dates_compare_as_days():
    assert rows_match([["2026-01-01", 161.0]], [["2026-01-01T00:00:00", 161]])


def test_month_labels_match_first_of_month_dates():
    assert rows_match([["2026-01-01", 161.0]], [["2026-01", 161]])