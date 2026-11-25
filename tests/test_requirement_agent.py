from __future__ import annotations

from app.graph import run_requirement_agent


def test_requirement_agent_parses_natural_language():
    result = run_requirement_agent("Need a CPVC pipe 1/2 inch, 5 results")
    assert "matches" in result
    assert isinstance(result["matches"], list)
    assert result["count"] >= 0
