"""Regression tests for Task 2: Documentation Agent.

These tests verify that the agent can answer questions about the wiki.
Run with: uv run pytest test_agent_task2.py -v
"""

import json
import subprocess


def test_agent_answers_merge_conflict_question():
    """Agent should answer 'How do you resolve a merge conflict?'"""
    result = subprocess.run(
        ["uv", "run", "agent.py", "How do you resolve a merge conflict?"],
        capture_output=True,
        text=True,
        timeout=120,
    )

    assert result.returncode == 0, f"Agent failed: {result.stderr}"

    output = json.loads(result.stdout)

    # Verify required fields
    assert "answer" in output, "Missing 'answer' field"
    assert "source" in output, "Missing 'source' field"
    assert "tool_calls" in output, "Missing 'tool_calls' field"

    # Verify answer is non-empty
    assert len(output["answer"].strip()) > 0, "'answer' should not be empty"

    # Verify answer mentions git/merge concepts
    answer_lower = output["answer"].lower()
    assert any(
        word in answer_lower for word in ["merge", "conflict", "git", "commit", "stage"]
    ), f"Answer should mention merge/conflict resolution: {output['answer']}"


def test_agent_answers_wiki_files_question():
    """Agent should answer 'What files are in the wiki?'"""
    result = subprocess.run(
        ["uv", "run", "agent.py", "What files are in the wiki directory?"],
        capture_output=True,
        text=True,
        timeout=120,
    )

    assert result.returncode == 0, f"Agent failed: {result.stderr}"

    output = json.loads(result.stdout)

    # Verify required fields
    assert "answer" in output, "Missing 'answer' field"
    assert "source" in output, "Missing 'source' field"
    assert "tool_calls" in output, "Missing 'tool_calls' field"

    # Verify answer is non-empty
    assert len(output["answer"].strip()) > 0, "'answer' should not be empty"

    # Verify answer mentions wiki files
    answer_lower = output["answer"].lower()
    assert any(word in answer_lower for word in ["wiki", "file", "directory", "md"]), (
        f"Answer should mention wiki/files: {output['answer']}"
    )
