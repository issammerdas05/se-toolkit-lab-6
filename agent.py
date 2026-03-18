#!/usr/bin/env python3
"""LLM-powered CLI agent with tools and agentic loop.

Usage:
    uv run agent.py "Your question here"

Output:
    JSON with 'answer', 'source', and 'tool_calls' fields to stdout.
    All debug output goes to stderr.
"""

import json
import os
import subprocess
import sys
from pathlib import Path

import httpx
from dotenv import load_dotenv

# Constants
MAX_TOOL_CALLS = 10
PROJECT_ROOT = Path(__file__).parent


def load_env() -> None:
    """Load environment variables from .env.agent.secret."""
    env_file = Path(__file__).parent / ".env.agent.secret"
    if not env_file.exists():
        print("Error: .env.agent.secret not found", file=sys.stderr)
        print("Run: cp .env.agent.example .env.agent.secret", file=sys.stderr)
        sys.exit(1)
    load_dotenv(env_file)


def get_llm_config() -> dict[str, str]:
    """Get LLM configuration from environment."""
    api_key = os.getenv("LLM_API_KEY")
    api_base = os.getenv("LLM_API_BASE")
    model = os.getenv("LLM_MODEL")

    if not api_key:
        print("Error: LLM_API_KEY not set in .env.agent.secret", file=sys.stderr)
        sys.exit(1)
    if not api_base:
        print("Error: LLM_API_BASE not set in .env.agent.secret", file=sys.stderr)
        sys.exit(1)
    if not model:
        print("Error: LLM_MODEL not set in .env.agent.secret", file=sys.stderr)
        sys.exit(1)

    return {"api_key": api_key, "api_base": api_base, "model": model}


# ---------------------------------------------------------------------------
# Tools
# ---------------------------------------------------------------------------


def validate_path(path: str) -> Path | None:
    """Validate that path is within project root. Returns resolved path or None."""
    try:
        # Reject absolute paths
        if os.path.isabs(path):
            print(f"Security: Absolute paths not allowed: {path}", file=sys.stderr)
            return None

        # Reject path traversal
        if ".." in path:
            print(f"Security: Path traversal not allowed: {path}", file=sys.stderr)
            return None

        # Resolve the path
        resolved = (PROJECT_ROOT / path).resolve()

        # Check it's within project root
        if not str(resolved).startswith(str(PROJECT_ROOT.resolve())):
            print(f"Security: Path outside project root: {path}", file=sys.stderr)
            return None

        return resolved
    except Exception as e:
        print(f"Security: Invalid path: {e}", file=sys.stderr)
        return None


def read_file(path: str) -> dict:
    """Read contents of a file.

    Args:
        path: Relative path from project root

    Returns:
        Dict with 'success' and 'content' or 'error'
    """
    validated = validate_path(path)
    if validated is None:
        return {"success": False, "error": f"Invalid path: {path}"}

    if not validated.exists():
        return {"success": False, "error": f"File not found: {path}"}

    if not validated.is_file():
        return {"success": False, "error": f"Not a file: {path}"}

    try:
        content = validated.read_text()
        return {"success": True, "content": content}
    except Exception as e:
        return {"success": False, "error": f"Error reading file: {e}"}


def list_files(path: str) -> dict:
    """List files and directories at a path.

    Args:
        path: Relative directory path from project root

    Returns:
        Dict with 'success' and 'files' (newline-separated) or 'error'
    """
    validated = validate_path(path)
    if validated is None:
        return {"success": False, "error": f"Invalid path: {path}"}

    if not validated.exists():
        return {"success": False, "error": f"Path not found: {path}"}

    if not validated.is_dir():
        return {"success": False, "error": f"Not a directory: {path}"}

    try:
        entries = []
        for entry in validated.iterdir():
            suffix = "/" if entry.is_dir() else ""
            entries.append(f"{entry.name}{suffix}")
        return {"success": True, "files": "\n".join(sorted(entries))}
    except Exception as e:
        return {"success": False, "error": f"Error listing directory: {e}"}


# ---------------------------------------------------------------------------
# Tool Schemas for LLM
# ---------------------------------------------------------------------------

TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "read_file",
            "description": "Read the contents of a file from the project repository",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {
                        "type": "string",
                        "description": "Relative path from project root (e.g., 'wiki/git.md')",
                    }
                },
                "required": ["path"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "list_files",
            "description": "List files and directories at a given path in the project",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {
                        "type": "string",
                        "description": "Relative directory path from project root (e.g., 'wiki/')",
                    }
                },
                "required": ["path"],
            },
        },
    },
]

SYSTEM_PROMPT = """You are a documentation assistant for a software engineering lab.

You have access to two tools:
1. list_files - List files and directories at a given path
2. read_file - Read the contents of a file

To answer questions about the project:
1. Use list_files to discover relevant files, especially in the wiki/ directory
2. Use read_file to read the contents of relevant files
3. Extract the answer from the file contents
4. Include a source reference in the format: path/to/file.md#section-name

When citing sources, try to identify the relevant section anchor from the markdown headings.

Always be concise and accurate. If you cannot find the answer in the available files, say so.
"""


# ---------------------------------------------------------------------------
# LLM API
# ---------------------------------------------------------------------------


async def call_llm_api(
    messages: list[dict], config: dict[str, str], tools: list | None = None
) -> dict | None:
    """Call the LLM API. Returns response dict or None on failure."""
    import asyncio

    # config['api_base'] already includes /v1 (e.g., https://openrouter.ai/api/v1)
    url = f"{config['api_base']}/chat/completions"
    headers = {
        "Authorization": f"Bearer {config['api_key']}",
        "Content-Type": "application/json",
    }

    payload = {
        "model": config["model"],
        "messages": messages,
    }

    if tools:
        payload["tools"] = tools

    max_retries = 3
    retry_delay = 3.0

    for attempt in range(max_retries):
        try:
            print(
                f"Calling LLM API... (attempt {attempt + 1}/{max_retries})",
                file=sys.stderr,
            )

            async with httpx.AsyncClient(timeout=60.0) as client:
                response = await client.post(url, headers=headers, json=payload)

                if response.status_code == 429:
                    if attempt < max_retries - 1:
                        print(
                            f"Rate limited. Retrying in {retry_delay}s...",
                            file=sys.stderr,
                        )
                        await asyncio.sleep(retry_delay)
                        retry_delay *= 2
                        continue
                    else:
                        print("API rate limited.", file=sys.stderr)
                        return None

                response.raise_for_status()
                return response.json()

        except httpx.RequestError as e:
            if attempt < max_retries - 1:
                print(f"Request error: {e}. Retrying...", file=sys.stderr)
                await asyncio.sleep(retry_delay)
                retry_delay *= 2
            else:
                print(f"Request failed: {e}", file=sys.stderr)
                return None

    return None


def call_qwen_cli(messages: list[dict]) -> str | None:
    """Fallback: Call Qwen Code CLI directly."""
    print("Using Qwen Code CLI as fallback...", file=sys.stderr)
    try:
        env = os.environ.copy()
        env["PNPM_HOME"] = "/root/.local/share/pnpm"
        env["PATH"] = f"{env['PNPM_HOME']}:{env['PATH']}"

        # Build prompt from messages
        prompt = messages[-1]["content"]  # Use last user message
        for msg in messages:
            if msg["role"] == "system":
                prompt = msg["content"] + "\n\n" + prompt

        result = subprocess.run(
            ["qwen", prompt, "--prompt"],
            capture_output=True,
            text=True,
            timeout=60,
            env=env,
        )

        if result.returncode != 0:
            print(f"Qwen CLI error: {result.stderr}", file=sys.stderr)
            return None

        return result.stdout.strip()

    except subprocess.TimeoutExpired:
        print("Error: Qwen CLI timed out", file=sys.stderr)
        return None
    except FileNotFoundError:
        print("Error: Qwen CLI not found", file=sys.stderr)
        return None


# ---------------------------------------------------------------------------
# Agentic Loop
# ---------------------------------------------------------------------------


def execute_tool(tool_name: str, args: dict) -> dict:
    """Execute a tool and return the result."""
    print(f"Executing tool: {tool_name}({args})", file=sys.stderr)

    if tool_name == "read_file":
        path = args.get("path", "")
        result = read_file(path)
        if result["success"]:
            return {"success": True, "content": result["content"]}
        return {"success": False, "error": result["error"]}

    elif tool_name == "list_files":
        path = args.get("path", "")
        result = list_files(path)
        if result["success"]:
            return {"success": True, "files": result["files"]}
        return {"success": False, "error": result["error"]}

    else:
        return {"success": False, "error": f"Unknown tool: {tool_name}"}


async def run_agentic_loop(
    question: str, config: dict[str, str]
) -> tuple[str, str, list]:
    """Run the agentic loop. Returns (answer, source, tool_calls)."""
    import asyncio

    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": question},
    ]

    tool_calls_log = []

    for i in range(MAX_TOOL_CALLS):
        print(f"\n--- Iteration {i + 1}/{MAX_TOOL_CALLS} ---", file=sys.stderr)

        # Call LLM
        response = await call_llm_api(messages, config, TOOLS)

        if response is None:
            # API failed, try CLI fallback (simplified - just get answer)
            answer = call_qwen_cli(messages) or "Could not get answer"
            return answer, "", tool_calls_log

        # Parse response
        try:
            choice = response["choices"][0]["message"]
        except (KeyError, IndexError) as e:
            print(f"Error parsing response: {e}", file=sys.stderr)
            return "Error parsing LLM response", "", tool_calls_log

        # Check for tool calls
        tool_calls = choice.get("tool_calls", [])

        if tool_calls:
            # Execute tools
            for tc in tool_calls:
                func = tc.get("function", {})
                tool_name = func.get("name", "unknown")
                args_str = func.get("arguments", "{}")

                try:
                    args = (
                        json.loads(args_str) if isinstance(args_str, str) else args_str
                    )
                except json.JSONDecodeError:
                    args = {}

                print(f"Tool call: {tool_name}({args})", file=sys.stderr)

                # Execute tool
                result = execute_tool(tool_name, args)

                # Log the tool call
                tool_calls_log.append(
                    {
                        "tool": tool_name,
                        "args": args,
                        "result": result.get("content")
                        or result.get("files")
                        or result.get("error", "Unknown error"),
                    }
                )

                # Add tool result to messages
                messages.append(
                    {
                        "role": "tool",
                        "tool_call_id": tc.get("id", "unknown"),
                        "content": json.dumps(result),
                    }
                )

            # Continue loop - LLM will process tool results
            continue

        else:
            # No tool calls - we have the final answer
            answer = choice.get("content", "")
            print(f"Final answer: {answer[:100]}...", file=sys.stderr)

            # Extract source from answer (look for wiki/...md#... pattern)
            source = ""
            import re

            source_match = re.search(r"(wiki/[\w-]+\.md(?:#[\w-]+)?)", answer)
            if source_match:
                source = source_match.group(1)

            return answer, source, tool_calls_log

    # Max iterations reached
    print("Max tool calls reached", file=sys.stderr)
    return "Max tool calls reached", "", tool_calls_log


async def call_llm(question: str, config: dict[str, str]) -> tuple[str, str, list]:
    """Call the LLM with agentic loop."""
    return await run_agentic_loop(question, config)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def main() -> None:
    """Main entry point."""
    import asyncio

    # Validate command-line arguments
    if len(sys.argv) < 2:
        print("Usage: uv run agent.py <question>", file=sys.stderr)
        sys.exit(1)

    question = sys.argv[1]
    if not question.strip():
        print("Error: Question cannot be empty", file=sys.stderr)
        sys.exit(1)

    # Load configuration
    load_env()
    config = get_llm_config()

    print(f"Question: {question}", file=sys.stderr)

    # Run agentic loop
    answer, source, tool_calls = asyncio.run(call_llm(question, config))

    # Output JSON result
    result = {"answer": answer, "source": source, "tool_calls": tool_calls}
    print(json.dumps(result))


if __name__ == "__main__":
    main()
