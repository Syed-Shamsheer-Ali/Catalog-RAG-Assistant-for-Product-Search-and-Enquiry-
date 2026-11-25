from __future__ import annotations

from app.graph import run_requirement_graph


def test_requirement_graph_returns_matches():
    result = run_requirement_graph({"kind": "PIPE", "size": "1/2", "max_results": 5})
    assert "matches" in result
    assert isinstance(result["matches"], list)
    assert result["count"] >= 0
