"""Quick tests for Task 2."""
import json
import subprocess

def test_agent_answers_question():
    """Agent should answer a simple question."""
    result = subprocess.run(
        ["uv", "run", "agent.py", "What is REST?"],
        capture_output=True,
        text=True,
        timeout=90,
    )
    
    assert result.returncode == 0, f"Failed: {result.stderr}"
    
    output = json.loads(result.stdout)
    assert "answer" in output
    assert "source" in output
    assert "tool_calls" in output
    assert len(output["answer"].strip()) > 0
