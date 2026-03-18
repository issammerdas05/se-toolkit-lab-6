"""Task 2 tests."""
import json
import subprocess

def test_merge_conflict_question():
    """Test merge conflict question."""
    result = subprocess.run(
        ["uv", "run", "agent.py", "How to resolve merge conflict?"],
        capture_output=True, text=True, timeout=90)
    assert result.returncode == 0
    output = json.loads(result.stdout)
    assert "answer" in output
    assert "source" in output
    assert "tool_calls" in output

def test_wiki_files_question():
    """Test wiki files question."""
    result = subprocess.run(
        ["uv", "run", "agent.py", "What files in wiki?"],
        capture_output=True, text=True, timeout=90)
    assert result.returncode == 0
    output = json.loads(result.stdout)
    assert "answer" in output
    assert len(output["answer"]) > 0
