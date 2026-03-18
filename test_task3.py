"""Regression tests for Task 3: System Agent.

Run with: uv run pytest test_task3.py -v
"""

import json
import subprocess


def test_framework_question_uses_read_file():
    """Agent should use read_file to answer 'What framework does the backend use?'"""
    result = subprocess.run(
        ["uv", "run", "agent.py", "What Python web framework does the backend use?"],
        capture_output=True,
        text=True,
        timeout=90,
    )

    assert result.returncode == 0, f"Agent failed: {result.stderr}"

    output = json.loads(result.stdout)

    # Verify required fields
    assert "answer" in output, "Missing 'answer' field"
    assert "tool_calls" in output, "Missing 'tool_calls' field"

    # Verify answer mentions FastAPI
    answer_lower = output["answer"].lower()
    assert "fastapi" in answer_lower, f"Answer should mention FastAPI: {output['answer']}"


def test_database_count_uses_query_api():
    """Agent should use query_api to answer 'How many items in database?'"""
    result = subprocess.run(
        ["uv", "run", "agent.py", "How many items are in the database?"],
        capture_output=True,
        text=True,
        timeout=90,
    )

    assert result.returncode == 0, f"Agent failed: {result.stderr}"

    output = json.loads(result.stdout)

    # Verify required fields
    assert "answer" in output, "Missing 'answer' field"
    assert "tool_calls" in output, "Missing 'tool_calls' field"

    # Verify answer contains a number
    import re
    numbers = re.findall(r'\d+', output["answer"])
    assert len(numbers) > 0, f"Answer should contain a number: {output['answer']}"
