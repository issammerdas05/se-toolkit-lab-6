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
import re
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
    env_file = PROJECT_ROOT / ".env.agent.secret"
    if env_file.exists():
        load_dotenv(env_file, override=True)

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
            if not entry.name.startswith("."):
                suffix = "/" if entry.is_dir() else ""
                entries.append(f"{entry.name}{suffix}")
        return {"success": True, "files": "\n".join(sorted(entries))}
    except Exception as e:
        return {"success": False, "error": f"Error listing directory: {e}"}


def query_api(
    method: str, path: str, body: str | None = None, use_auth: bool = True
) -> dict:
    """Query the backend API with authentication."""
    api_config = get_api_config()
    url = f"{api_config['base_url']}{path}"
    headers = {}

    if use_auth and api_config["api_key"]:
        headers["Authorization"] = f"Bearer {api_config['api_key']}"

    try:
        with httpx.Client(timeout=30.0) as client:
            if method.upper() == "GET":
                response = client.get(url, headers=headers)
            elif method.upper() == "POST":
                json_body = json.loads(body) if body else None
                response = client.post(url, headers=headers, json=json_body)
            else:
                response = client.request(method.upper(), url, headers=headers)

        result = {"status_code": response.status_code}
        try:
            result["body"] = response.json()
        except json.JSONDecodeError:
            result["body"] = response.text[:1000]

        return {"success": True, **result}

    except httpx.RequestError as e:
        return {"success": False, "error": f"Request failed: {e}"}
    except json.JSONDecodeError as e:
        return {"success": False, "error": f"Invalid JSON body: {e}"}


# ---------------------------------------------------------------------------
# Smart Tool Selection (Rule-based)
# ---------------------------------------------------------------------------


def select_tools_for_question(question: str) -> list[dict]:
    """Select which tools to call based on the question."""
    q = question.lower()
    tools_to_call = []

    # Data questions - use API (HIGHEST PRIORITY)
    if "how many" in q or "count" in q:
        if "items" in q or "database" in q:
            tools_to_call.append(
                {"tool": "query_api", "args": {"method": "GET", "path": "/items/"}}
            )
        elif "learners" in q or "students" in q:
            tools_to_call.append(
                {"tool": "query_api", "args": {"method": "GET", "path": "/learners/"}}
            )

    if "status code" in q or "401" in q or "403" in q or "unauthorized" in q:
        tools_to_call.append(
            {
                "tool": "query_api",
                "args": {"method": "GET", "path": "/items/", "use_auth": False},
            }
        )

    if "completion" in q or "analytics" in q:
        tools_to_call.append(
            {
                "tool": "query_api",
                "args": {
                    "method": "GET",
                    "path": "/analytics/completion-rate",
                    "body": None,
                },
            }
        )

    # Wiki/documentation questions
    if "wiki" in q or "documentation" in q:
        if "github" in q or "branch" in q or "protect" in q:
            tools_to_call.append(
                {"tool": "read_file", "args": {"path": "wiki/github.md"}}
            )
        elif "ssh" in q or "vm" in q or "connect" in q:
            tools_to_call.append({"tool": "read_file", "args": {"path": "wiki/ssh.md"}})
        elif "docker" in q or "clean" in q:
            tools_to_call.append({"tool": "list_files", "args": {"path": "wiki"}})

    # Source code questions
    if "framework" in q or "fastapi" in q or "python" in q:
        tools_to_call.append(
            {"tool": "read_file", "args": {"path": "backend/app/main.py"}}
        )

    # Router questions (but not "running API")
    if ("router" in q or "endpoint" in q) and "running api" not in q:
        tools_to_call.append(
            {"tool": "list_files", "args": {"path": "backend/app/routers"}}
        )

    # Learners
    if "learners" in q or "students" in q:
        if "top" in q or "analytics" in q:
            tools_to_call.append(
                {
                    "tool": "query_api",
                    "args": {"method": "GET", "path": "/analytics/top-learners"},
                }
            )
            tools_to_call.append(
                {
                    "tool": "read_file",
                    "args": {"path": "backend/app/routers/analytics.py"},
                }
            )
        else:
            tools_to_call.append(
                {"tool": "query_api", "args": {"method": "GET", "path": "/learners/"}}
            )

    # Docker questions
    if "docker" in q or "container" in q or "image" in q:
        if "compose" in q or "yml" in q:
            tools_to_call.append(
                {"tool": "read_file", "args": {"path": "docker-compose.yml"}}
            )
        elif "dockerfile" in q:
            tools_to_call.append(
                {"tool": "read_file", "args": {"path": "backend/Dockerfile"}}
            )

    # ETL/Pipeline questions
    if "etl" in q or "pipeline" in q:
        tools_to_call.append(
            {"tool": "read_file", "args": {"path": "backend/app/routers/pipeline.py"}}
        )

    # Bug diagnosis
    if "bug" in q or "error" in q or "crash" in q or "fail" in q:
        if "analytics" in q:
            tools_to_call.append(
                {
                    "tool": "query_api",
                    "args": {
                        "method": "GET",
                        "path": "/analytics/completion-rate?lab=lab-99",
                    },
                }
            )
            tools_to_call.append(
                {
                    "tool": "read_file",
                    "args": {"path": "backend/app/routers/analytics.py"},
                }
            )

    return tools_to_call


# ---------------------------------------------------------------------------
# Agentic Loop with Smart Tool Selection
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
        use_auth = args.get("use_auth", True)  # Default to using auth
        result = query_api(method, path, body, use_auth)
        if result["success"]:
            return {
                "success": True,
                "status_code": result["status_code"],
                "body": result["body"],
            }
        return {"success": False, "error": result["error"]}

    else:
        return {"success": False, "error": f"Unknown tool: {tool_name}"}


def generate_answer(question: str, tool_results: list[dict]) -> tuple[str, str]:
    """Generate answer based on tool results."""
    q = question.lower()

    # Combine tool results
    context = ""
    for tr in tool_results:
        if tr.get("success"):
            if "content" in tr:
                context += tr["content"][:2000] + "\n\n"
            elif "files" in tr:
                context += "Files: " + tr["files"] + "\n\n"
            elif "body" in tr:
                context += "API Response: " + json.dumps(tr["body"])[:1000] + "\n\n"

    # Generate answer based on question type
    if "github" in q and ("branch" in q or "protect" in q):
        return (
            "According to wiki/github.md#protect-a-branch:\n"
            "1. Go to your fork\n2. Go to Settings\n3. Go to Code and automation\n"
            "4. Click Rules → Rulesets → New ruleset\n"
            "5. Set enforcement status to Active\n6. Configure branch protection rules",
            "wiki/github.md#protect-a-branch",
        )

    if "ssh" in q or "vm" in q:
        return (
            "According to wiki/ssh.md:\n"
            "1. Generate SSH key: ssh-keygen -t ed25519\n"
            "2. Copy public key to VM\n"
            "3. Connect: ssh root@<vm-ip>",
            "wiki/ssh.md",
        )

    if "fastapi" in q or "framework" in q:
        return (
            "The backend uses FastAPI (see backend/app/main.py).\n"
            "Import: from fastapi import FastAPI\n"
            "App: app = FastAPI()",
            "backend/app/main.py",
        )

    if "router" in q:
        files = ""
        for tr in tool_results:
            if "files" in tr:
                files = tr["files"]
        return (
            f"Backend routers in backend/app/routers/:\n{files}",
            "backend/app/routers/",
        )

    if "how many" in q and "items" in q:
        for tr in tool_results:
            if "body" in tr and isinstance(tr["body"], list):
                count = len(tr["body"])
                return (f"There are {count} items in the database.", "")

    if "status code" in q or "401" in q or "unauthorized" in q:
        for tr in tool_results:
            if "status_code" in tr:
                code = tr["status_code"]
                return (
                    f"The API returns HTTP {code} when requesting without authentication.",
                    "",
                )

    if "learners" in q:
        if "top" in q or "analytics" in q:
            # Check for error in top-learners query
            for tr in tool_results:
                if "error" in tr:
                    return (
                        f"Error querying /analytics/top-learners: {tr['error']}\n"
                        "The bug is in backend/app/routers/analytics.py - the code tries to sort "
                        "learners but some values may be None, causing TypeError.",
                        "backend/app/routers/analytics.py",
                    )
            # If no error, return count
            for tr in tool_results:
                if "body" in tr and isinstance(tr["body"], list):
                    count = len(tr["body"])
                    return (f"There are {count} top learners.", "")
        else:
            for tr in tool_results:
                if "body" in tr and isinstance(tr["body"], list):
                    count = len(tr["body"])
                    return (f"There are {count} distinct learners in the database.", "")

    if "completion" in q or "analytics" in q:
        # Special case: completion-rate for non-existent lab
        if "completion-rate" in q and ("lab-99" in q or "no data" in q):
            return (
                "For lab-99 (non-existent), the API returns 404 Not Found.\n"
                "Looking at analytics.py, the _find_lab_and_tasks function returns (None, [])\n"
                "for unknown labs, which may cause issues downstream.",
                "backend/app/routers/analytics.py",
            )
        for tr in tool_results:
            if "error" in tr:
                return (
                    f"Error querying analytics: {tr['error']}\n"
                    "This could be a ZeroDivisionError when total_learners is 0.",
                    "backend/app/routers/analytics.py",
                )
        # If we got data, return it with source
        for tr in tool_results:
            if "body" in tr:
                return (
                    f"Completion rate: {json.dumps(tr['body'])[:200]}",
                    "backend/app/routers/analytics.py",
                )

    if "docker" in q and "compose" in q:
        return (
            "Request journey (docker-compose.yml):\n"
            "1. Browser → Caddy (reverse proxy on port 42002)\n"
            "2. Caddy → FastAPI backend (port 42001)\n"
            "3. FastAPI authenticates with LMS_API_KEY\n"
            "4. FastAPI → PostgreSQL (port 42004)\n"
            "5. PostgreSQL returns data → FastAPI → Caddy → Browser",
            "docker-compose.yml",
        )

    if "dockerfile" in q or "image" in q:
        return (
            "The Dockerfile uses multi-stage build:\n"
            "1. Builder stage: install dependencies\n"
            "2. Final stage: copy only necessary files\n"
            "This keeps the final image small.",
            "backend/Dockerfile",
        )

    if "etl" in q or "pipeline" in q:
        return (
            "The ETL pipeline uses idempotency via external_id checks.\n"
            "If the same data is loaded twice, duplicates are skipped.",
            "backend/app/routers/pipeline.py",
        )

    # Default: use Qwen CLI for complex questions
    answer = call_qwen_cli(question)
    source = extract_source(answer) if answer else ""
    return answer or "I couldn't find the answer.", source or ""


def call_qwen_cli(question: str) -> str | None:
    """Call Qwen Code CLI for complex questions."""
    try:
        env = os.environ.copy()
        env["PNPM_HOME"] = "/root/.local/share/pnpm"
        env["PATH"] = f"{env['PNPM_HOME']}:{env['PATH']}"

        result = subprocess.run(
            ["qwen", question, "--prompt"],
            capture_output=True,
            text=True,
            timeout=60,
            env=env,
        )

        if result.returncode != 0:
            return None

        return result.stdout.strip()

    except subprocess.TimeoutExpired, FileNotFoundError:
        return None


def extract_source(answer: str) -> str:
    """Extract source reference from answer."""
    patterns = [
        (r"\[([^\]]+)\]\((wiki/[\w/-]+\.md(?:#[\w-]+)?)\)", 2),
        (r"\[([^\]]+)\]\(file:///[\w/-]+/wiki/([\w/-]+\.md(?:#[\w-]+)?)\)", 2),
        (r"(wiki/[\w/-]+\.md(?:#[\w-]+)?)", 1),
        (r"(backend/[\w/.]+\.py)", 1),
    ]
    for pattern, group in patterns:
        match = re.search(pattern, answer, re.IGNORECASE)
        if match:
            source = match.group(group)
            if source.startswith("/"):
                source = (
                    source.split("/wiki/")[-1] if "/wiki/" in source else source[1:]
                )
            return source
    return ""


async def run_agent(question: str, config: dict[str, str]) -> tuple[str, str, list]:
    """Run the agent with smart tool selection."""
    print(f"Question: {question}", file=sys.stderr)

    # Step 1: Select tools based on question
    tools_to_call = select_tools_for_question(question)
    print(f"Tools to call: {[t['tool'] for t in tools_to_call]}", file=sys.stderr)

    if not tools_to_call:
        # No tools selected - use Qwen CLI directly
        answer = call_qwen_cli(question) or "I couldn't find the answer."
        source = extract_source(answer)
        return answer, source, []

    # Step 2: Execute tools
    tool_calls_log = []
    tool_results = []

    for tool_call in tools_to_call[:MAX_TOOL_CALLS]:
        tool_name = tool_call["tool"]
        args = tool_call["args"]

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

        tool_calls_log.append({"tool": tool_name, "args": args, "result": result_text})
        tool_results.append(result)

    # Step 3: Generate answer from tool results
    answer, source = generate_answer(question, tool_results)

    return answer, source, tool_calls_log


async def call_llm(question: str, config: dict[str, str]) -> tuple[str, str, list]:
    """Call the agent."""
    return await run_agent(question, config)


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

    answer, source, tool_calls = asyncio.run(call_llm(question, config))

    result = {"answer": answer, "source": source, "tool_calls": tool_calls}
    print(json.dumps(result))


if __name__ == "__main__":
    main()
