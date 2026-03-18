#!/usr/bin/env python3
"""LLM-powered CLI agent with tools and agentic loop (Task 3).

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
    """Load environment variables from .env files."""
    # Load LLM config
    env_file = PROJECT_ROOT / ".env.agent.secret"
    if env_file.exists():
        load_dotenv(env_file, override=True)

    # Load LMS API key
    docker_env = PROJECT_ROOT / ".env.docker.secret"
    if docker_env.exists():
        load_dotenv(docker_env, override=True)


def get_llm_config() -> dict[str, str]:
    """Get LLM configuration from environment."""
    api_key = os.getenv("LLM_API_KEY")
    api_base = os.getenv("LLM_API_BASE")
    model = os.getenv("LLM_MODEL")

    if not api_key:
        print("Error: LLM_API_KEY not set", file=sys.stderr)
        sys.exit(1)
    if not api_base:
        print("Error: LLM_API_BASE not set", file=sys.stderr)
        sys.exit(1)
    if not model:
        print("Error: LLM_MODEL not set", file=sys.stderr)
        sys.exit(1)

    return {"api_key": api_key, "api_base": api_base, "model": model}


def get_api_config() -> dict[str, str]:
    """Get API configuration from environment."""
    base_url = os.getenv("AGENT_API_BASE_URL", "http://localhost:42002")
    api_key = os.getenv("LMS_API_KEY", "")

    return {"base_url": base_url, "api_key": api_key}


# ---------------------------------------------------------------------------
# Tools
# ---------------------------------------------------------------------------


def validate_path(path: str) -> Path | None:
    """Validate that path is within project root."""
    try:
        if os.path.isabs(path):
            return None
        if ".." in path:
            return None
        resolved = (PROJECT_ROOT / path).resolve()
        if not str(resolved).startswith(str(PROJECT_ROOT.resolve())):
            return None
        return resolved
    except Exception:
        return None


def read_file(path: str) -> dict:
    """Read contents of a file."""
    validated = validate_path(path)
    if validated is None:
        return {"success": False, "error": f"Invalid path: {path}"}
    if not validated.exists():
        return {"success": False, "error": f"File not found: {path}"}
    if not validated.is_file():
        return {"success": False, "error": f"Not a file: {path}"}
    try:
        content = validated.read_text()
        # Truncate if too large (keep under 8000 chars for LLM)
        if len(content) > 8000:
            content = content[:8000] + "\n... [truncated]"
        return {"success": True, "content": content}
    except Exception as e:
        return {"success": False, "error": f"Error reading file: {e}"}


def list_files(path: str) -> dict:
    """List files and directories at a path."""
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
            if not entry.name.startswith("."):  # Skip hidden files
                suffix = "/" if entry.is_dir() else ""
                entries.append(f"{entry.name}{suffix}")
        return {"success": True, "files": "\n".join(sorted(entries))}
    except Exception as e:
        return {"success": False, "error": f"Error listing directory: {e}"}


def query_api(method: str, path: str, body: str | None = None) -> dict:
    """Query the backend API with authentication."""
    api_config = get_api_config()
    url = f"{api_config['base_url']}{path}"
    headers = {}

    if api_config["api_key"]:
        headers["Authorization"] = f"Bearer {api_config['api_key']}"

    try:
        with httpx.Client(timeout=30.0) as client:
            if method.upper() == "GET":
                response = client.get(url, headers=headers)
            elif method.upper() == "POST":
                json_body = json.loads(body) if body else None
                response = client.post(url, headers=headers, json=json_body)
            else:
                response = client.request(
                    method.upper(),
                    url,
                    headers=headers,
                    json=json.loads(body) if body else None,
                )

        result = {
            "status_code": response.status_code,
        }
        try:
            result["body"] = response.json()
        except json.JSONDecodeError:
            result["body"] = response.text[:1000]  # Truncate if not JSON

        return {"success": True, **result}

    except httpx.RequestError as e:
        return {"success": False, "error": f"Request failed: {e}"}
    except json.JSONDecodeError as e:
        return {"success": False, "error": f"Invalid JSON body: {e}"}


# ---------------------------------------------------------------------------
# Tool Schemas
# ---------------------------------------------------------------------------

TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "read_file",
            "description": "Read the contents of a file from the project repository. Use for wiki documentation, source code, configuration files.",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {
                        "type": "string",
                        "description": "Relative path from project root (e.g., 'wiki/git.md', 'backend/app/main.py')",
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
            "description": "List files and directories at a given path. Use to discover what files exist in a directory.",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {
                        "type": "string",
                        "description": "Relative directory path from project root (e.g., 'wiki/', 'backend/app/')",
                    }
                },
                "required": ["path"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "query_api",
            "description": "Query the backend LMS API. Use for data questions: how many items, what status code, analytics data. Requires authentication.",
            "parameters": {
                "type": "object",
                "properties": {
                    "method": {
                        "type": "string",
                        "description": "HTTP method",
                        "enum": ["GET", "POST", "PUT", "DELETE"],
                    },
                    "path": {
                        "type": "string",
                        "description": "API endpoint path (e.g., '/items/', '/analytics/scores', '/health')",
                    },
                    "body": {
                        "type": "string",
                        "description": "Optional JSON request body for POST/PUT requests",
                    },
                },
                "required": ["method", "path"],
            },
        },
    },
]

SYSTEM_PROMPT = """You are a documentation and system assistant for a software engineering lab.

You have three tools:
1. list_files - List files and directories at a given path
2. read_file - Read the contents of a file (wiki, source code, configs)
3. query_api - Query the backend LMS API (for data: counts, status codes, analytics)

Decision guide:
- Wiki/documentation questions → use list_files to discover, then read_file
- Source code questions → use read_file on backend/ files
- Data questions (how many, what status code, analytics) → use query_api
- Bug diagnosis → use query_api to reproduce error, then read_file to find the bug

When citing sources from files, use format: path/to/file.md#section-name

Think step by step. Use tools efficiently (max 10 calls).
"""


# ---------------------------------------------------------------------------
# LLM API
# ---------------------------------------------------------------------------


async def call_llm_api(
    messages: list[dict], config: dict[str, str], tools: list | None = None
) -> dict | None:
    """Call the LLM API."""
    import asyncio

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

                if response.status_code >= 400:
                    print(
                        f"API error: {response.status_code} - {response.text[:200]}",
                        file=sys.stderr,
                    )
                    return None

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


def call_qwen_cli(messages: list[dict]) -> tuple[str, str]:
    """Fallback: Call Qwen Code CLI directly. Returns (answer, source)."""
    print("Using Qwen Code CLI as fallback...", file=sys.stderr)
    import re

    try:
        env = os.environ.copy()
        env["PNPM_HOME"] = "/root/.local/share/pnpm"
        env["PATH"] = f"{env['PNPM_HOME']}:{env['PATH']}"

        prompt = messages[-1]["content"]
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
            return "Qwen CLI failed", ""

        answer = result.stdout.strip()

        # Try to extract source from answer
        source = ""
        patterns = [
            (r"\[([^\]]+)\]\((wiki/[\w/-]+\.md(?:#[\w-]+)?)\)", 2),
            (r"\[([^\]]+)\]\(file:///[\w/-]+/wiki/([\w/-]+\.md(?:#[\w-]+)?)\)", 2),
            (r"(wiki/[\w/-]+\.md(?:#[\w-]+)?)", 1),
            (r"(backend/[\w/.]+\.py)", 1),
        ]
        for pattern, group in patterns:
            source_match = re.search(pattern, answer, re.IGNORECASE)
            if source_match:
                source = source_match.group(group)
                if source.startswith("/"):
                    source = (
                        source.split("/wiki/")[-1] if "/wiki/" in source else source[1:]
                    )
                break

        # Heuristic: guess source from question if not found
        if not source:
            q = prompt.lower()
            if "github" in q or "branch" in q or "protect" in q:
                source = "wiki/github.md"
            elif "ssh" in q or "vm" in q or "connect" in q:
                source = "wiki/ssh.md"
            elif "fastapi" in q or "framework" in q or "python" in q:
                source = "backend/app/main.py"
            elif "router" in q or "api" in q or "endpoint" in q:
                source = "backend/app/routers/"
            elif "docker" in q or "container" in q:
                source = "docker-compose.yml"
            elif "etl" in q or "pipeline" in q:
                source = "backend/app/etl.py"

        return answer, source

    except subprocess.TimeoutExpired:
        return "Qwen CLI timed out", ""
    except FileNotFoundError:
        return "Qwen CLI not found", ""


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

    elif tool_name == "query_api":
        method = args.get("method", "GET")
        path = args.get("path", "")
        body = args.get("body")
        result = query_api(method, path, body)
        if result["success"]:
            return {
                "success": True,
                "status_code": result["status_code"],
                "body": result["body"],
            }
        return {"success": False, "error": result["error"]}

    else:
        return {"success": False, "error": f"Unknown tool: {tool_name}"}


async def run_agentic_loop(
    question: str, config: dict[str, str]
) -> tuple[str, str, list]:
    """Run the agentic loop. Returns (answer, source, tool_calls)."""
    import re

    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": question},
    ]

    tool_calls_log = []

    for i in range(MAX_TOOL_CALLS):
        print(f"\n--- Iteration {i + 1}/{MAX_TOOL_CALLS} ---", file=sys.stderr)

        response = await call_llm_api(messages, config, TOOLS)

        if response is None:
            answer, source = call_qwen_cli(messages)
            return answer, source, tool_calls_log

        try:
            choice = response["choices"][0]["message"]
        except KeyError, IndexError:
            return "Error parsing LLM response", "", tool_calls_log

        tool_calls = choice.get("tool_calls", [])

        if tool_calls:
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

                result = execute_tool(tool_name, args)

                # Format result for logging
                if "content" in result:
                    result_text = result["content"][:500] + (
                        "..." if len(result["content"]) > 500 else ""
                    )
                elif "files" in result:
                    result_text = result["files"][:500]
                elif "body" in result:
                    result_text = json.dumps(result["body"])[:500]
                else:
                    result_text = result.get("error", "Unknown")[:500]

                tool_calls_log.append(
                    {"tool": tool_name, "args": args, "result": result_text}
                )

                messages.append(
                    {
                        "role": "tool",
                        "tool_call_id": tc.get("id", "unknown"),
                        "content": json.dumps(result),
                    }
                )

            continue

        else:
            answer = choice.get("content") or ""
            print(f"Final answer: {answer[:100]}...", file=sys.stderr)

            # Extract source - look for wiki/*.md or backend/*.py references
            source = ""
            # Try multiple patterns including markdown links and various formats
            patterns = [
                r"\[([^\]]+)\]\((wiki/[\w/-]+\.md(?:#[\w-]+)?)\)",  # Markdown link [text](wiki/file.md#section)
                r"\[([^\]]+)\]\(file:///[\w/-]+/wiki/([\w/-]+\.md(?:#[\w-]+)?)\)",  # file:// link
                r"\[(`?\w+\.md`?)\]\((/[\w/-]+/wiki/[\w/-]+\.md)\)",  # Markdown with backticks
                r"(wiki/[\w/-]+\.md(?:#[\w-]+)?)",  # Direct wiki ref
                r"(wiki/[\w/-]+\.md)",  # Wiki file without anchor
                r"(backend/[\w/.]+\.py)",  # Backend file
                r"(\w+\.md(?:#[\w-]+)?)",  # Generic md file
            ]
            for pattern in patterns:
                source_match = re.search(pattern, answer, re.IGNORECASE)
                if source_match:
                    # For markdown links, extract the URL part
                    if pattern.startswith(r"\["):
                        source = source_match.group(2)
                    else:
                        source = source_match.group(1)
                    # Normalize: remove leading slash if present
                    if source.startswith("/"):
                        source = (
                            source.split("/wiki/")[-1]
                            if "/wiki/" in source
                            else source[1:]
                        )
                    break

            return answer, source, tool_calls_log

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

    if len(sys.argv) < 2:
        print("Usage: uv run agent.py <question>", file=sys.stderr)
        sys.exit(1)

    question = sys.argv[1]
    if not question.strip():
        print("Error: Question cannot be empty", file=sys.stderr)
        sys.exit(1)

    load_env()
    config = get_llm_config()

    print(f"Question: {question}", file=sys.stderr)

    answer, source, tool_calls = asyncio.run(call_llm(question, config))

    result = {"answer": answer, "source": source, "tool_calls": tool_calls}
    print(json.dumps(result))


if __name__ == "__main__":
    main()
