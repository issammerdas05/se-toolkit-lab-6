"""Regression tests for agent.py CLI."""

import json
import subprocess


def test_agent_returns_valid_json():
    """Agent should output valid JSON with 'answer' and 'tool_calls' fields."""
    result = subprocess.run(
        ["uv", "run", "agent.py", "What is 2+2?"],
        capture_output=True,
        text=True,
        timeout=120,
    )
    
    assert result.returncode == 0, f"Agent failed: {result.stderr}"
    
    output = json.loads(result.stdout)
    
    assert "answer" in output, "Missing 'answer' field"
    assert "tool_calls" in output, "Missing 'tool_calls' field"
    assert isinstance(output["answer"], str), "'answer' should be string"
    assert isinstance(output["tool_calls"], list), "'tool_calls' should be array"
    assert len(output["answer"].strip()) > 0, "'answer' should not be empty"
