from __future__ import annotations

from app.catalog.matcher import match_products


def test_requirement_matching_returns_pipe_candidates():
    matches = match_products({"kind": "PIPE", "size": "1/2", "max_results": 5})
    assert matches
    assert all("product_kind" in row for row in matches)
    assert any(row.get("product_kind") == "PIPE" for row in matches)


def test_requirement_matching_handles_category_and_size():
    matches = match_products({"kind": "FITTING", "category": "CPVC fittings and accessories", "size": "3/4 x 1/2", "max_results": 10})
    assert matches
    assert all(row.get("match_score", 0) > 0 for row in matches)


def test_requirement_matching_ignores_invalid_rows():
    matches = match_products({"kind": "PIPE", "size": "9999", "max_results": 3})
    assert matches == []
