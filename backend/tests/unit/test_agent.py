"""Regression tests for agent.py CLI.

These tests verify that agent.py outputs valid JSON with the required fields.
Run with: uv run pytest backend/tests/unit/test_agent.py -v
"""

import json
import subprocess
import sys
from pathlib import Path

import pytest

AGENT_PATH = Path(__file__).parent.parent.parent / "agent.py"
PROJECT_ROOT = Path(__file__).parent.parent.parent.parent


class TestAgentOutput:
    """Test that agent.py produces valid JSON output with required fields."""

    def test_agent_returns_valid_json(self):
        """Agent should output valid JSON with 'answer' and 'tool_calls' fields."""
        # Run agent with a simple question
        result = subprocess.run(
            ["uv", "run", "agent.py", "What is 2+2?"],
            capture_output=True,
            text=True,
            timeout=120,
            cwd=PROJECT_ROOT,
        )

        # Check exit code
        assert result.returncode == 0, f"Agent failed: {result.stderr}"

        # Parse stdout as JSON
        output = json.loads(result.stdout)

        # Verify required fields exist
        assert "answer" in output, "Missing 'answer' field in output"
        assert "tool_calls" in output, "Missing 'tool_calls' field in output"

        # Verify field types
        assert isinstance(output["answer"], str), "'answer' should be a string"
        assert isinstance(output["tool_calls"], list), "'tool_calls' should be an array"

        # Verify answer is non-empty
        assert len(output["answer"].strip()) > 0, "'answer' should not be empty"

        # Verify tool_calls is empty for Task 1
        assert len(output["tool_calls"]) == 0, "'tool_calls' should be empty in Task 1"
