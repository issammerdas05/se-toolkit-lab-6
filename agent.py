#!/usr/bin/env python3
"""LLM-powered CLI agent.

Usage:
    uv run agent.py "Your question here"

Output:
    JSON with 'answer' and 'tool_calls' fields to stdout.
    All debug output goes to stderr.
"""

import json
import os
import subprocess
import sys
from pathlib import Path

import httpx
from dotenv import load_dotenv


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


async def call_llm_api(question: str, config: dict[str, str]) -> str | None:
    """Call the LLM API. Returns None if rate limited."""
    import asyncio

    url = f"{config['api_base']}/chat/completions"
    headers = {
        "Authorization": f"Bearer {config['api_key']}",
        "Content-Type": "application/json",
    }
    payload = {
        "model": config["model"],
        "messages": [
            {"role": "system", "content": "You are a helpful assistant."},
            {"role": "user", "content": question},
        ],
    }

    max_retries = 3
    retry_delay = 3.0

    for attempt in range(max_retries):
        try:
            print(
                f"Calling LLM API at {url}... (attempt {attempt + 1}/{max_retries})",
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
                data = response.json()

                try:
                    answer = data["choices"][0]["message"]["content"]
                    return answer
                except (KeyError, IndexError) as e:
                    print(
                        f"Error: Unexpected API response format: {e}", file=sys.stderr
                    )
                    return None

        except httpx.RequestError as e:
            if attempt < max_retries - 1:
                print(f"Request error: {e}. Retrying...", file=sys.stderr)
                await asyncio.sleep(retry_delay)
                retry_delay *= 2
            else:
                print(f"Request failed: {e}", file=sys.stderr)
                return None

    return None


def call_qwen_cli(question: str) -> str:
    """Fallback: Call Qwen Code CLI directly."""
    print("Using Qwen Code CLI as fallback...", file=sys.stderr)
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
            print(f"Qwen CLI error: {result.stderr}", file=sys.stderr)
            sys.exit(1)

        return result.stdout.strip()

    except subprocess.TimeoutExpired:
        print("Error: Qwen CLI timed out", file=sys.stderr)
        sys.exit(1)
    except FileNotFoundError:
        print("Error: Qwen CLI not found", file=sys.stderr)
        sys.exit(1)


async def call_llm(question: str, config: dict[str, str]) -> str:
    """Call the LLM with API fallback to CLI."""
    answer = await call_llm_api(question, config)
    if answer is not None:
        return answer
    return call_qwen_cli(question)


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

    # Call LLM
    answer = asyncio.run(call_llm(question, config))

    # Output JSON result
    result = {"answer": answer, "tool_calls": []}
    print(json.dumps(result))


if __name__ == "__main__":
    main()

