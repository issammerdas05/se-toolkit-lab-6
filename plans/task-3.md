# Task 3: The System Agent

## Overview

Add `query_api` tool to allow the agent to query the deployed backend API. This enables answering data-dependent questions (database counts, status codes, analytics).

## Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                      agent.py                               │
│                                                             │
│  ┌─────────────┐    ┌──────────────┐    ┌───────────────┐  │
│  │ CLI Parser  │───▶│ Agentic Loop │───▶│ Tool Executor │  │
│  │             │    │  (max 10)    │    │               │  │
│  └─────────────┘    └──────────────┘    │ - read_file   │  │
│                            │            │ - list_files  │  │
│                            ▼            │ - query_api   │  │
│                     ┌──────────────┐    └───────────────┘  │
│                     │ LLM (Qwen)   │            │           │
│                     │ + Tools      │            │           │
│                     └──────────────┘            ▼           │
│                            │            ┌───────────────┐   │
│                            │            │ Backend API   │   │
│                            │            │ (LMS_API_KEY) │   │
│                            │            └───────────────┘   │
│                            ▼                                │
│  ┌─────────────┐    ┌──────────────┐    ┌───────────────┐  │
│  │ JSON Output │◀───│ Source       │◀───│ LLM Answer    │  │
│  │ (stdout)    │    │ Extractor    │    │               │  │
│  └─────────────┘    └──────────────┘    └───────────────┘  │
└─────────────────────────────────────────────────────────────┘
```

## New Tool: query_api

### Schema

```python
{
    "name": "query_api",
    "description": "Query the backend LMS API. Use for data questions (counts, status codes, analytics).",
    "parameters": {
        "type": "object",
        "properties": {
            "method": {
                "type": "string",
                "description": "HTTP method (GET, POST, etc.)",
                "enum": ["GET", "POST", "PUT", "DELETE"]
            },
            "path": {
                "type": "string",
                "description": "API path (e.g., '/items/', '/analytics/scores')"
            },
            "body": {
                "type": "string",
                "description": "Optional JSON request body (for POST/PUT)"
            }
        },
        "required": ["method", "path"]
    }
}
```

### Implementation

```python
def query_api(method: str, path: str, body: str | None = None) -> dict:
    """Query the backend API with LMS_API_KEY authentication."""
    base_url = os.getenv("AGENT_API_BASE_URL", "http://localhost:42002")
    api_key = os.getenv("LMS_API_KEY")
    
    url = f"{base_url}{path}"
    headers = {"Authorization": f"Bearer {api_key}"}
    
    response = httpx.request(method, url, headers=headers, json=body)
    
    return {
        "status_code": response.status_code,
        "body": response.json()
    }
```

## Environment Variables

| Variable | Purpose | Source |
|----------|---------|--------|
| `LLM_API_KEY` | LLM provider API key | `.env.agent.secret` |
| `LLM_API_BASE` | LLM API endpoint | `.env.agent.secret` |
| `LLM_MODEL` | Model name | `.env.agent.secret` |
| `LMS_API_KEY` | Backend API key | `.env.docker.secret` |
| `AGENT_API_BASE_URL` | Backend URL (default: `http://localhost:42002`) | Optional |

## System Prompt Update

```
You are a documentation and system assistant. You have three tools:

1. list_files - Discover files in the project
2. read_file - Read file contents (use for wiki, source code, configs)
3. query_api - Query the backend API (use for data questions: counts, status codes, analytics)

Decision guide:
- Wiki/documentation questions → use list_files, then read_file
- Source code questions → use read_file on backend/ files
- Data questions (how many, what status code) → use query_api
- Bug diagnosis → use query_api to reproduce error, then read_file to find bug

Always cite sources when using read_file (format: path/to/file.md#section).
```

## Benchmark Questions

| # | Question | Tool | Expected Answer |
|---|----------|------|-----------------|
| 0 | Branch protection steps (wiki) | read_file | branch, protect |
| 1 | SSH connection steps (wiki) | read_file | ssh, key, connect |
| 2 | Python web framework | read_file | FastAPI |
| 3 | API router modules | list_files | items, interactions, analytics, pipeline |
| 4 | Items in database | query_api | number > 0 |
| 5 | Status code without auth | query_api | 401/403 |
| 6 | /analytics/completion-rate error | query_api + read_file | ZeroDivisionError |
| 7 | /analytics/top-learners crash | query_api + read_file | TypeError/None |
| 8 | Request lifecycle (LLM judge) | read_file | 4+ hops |
| 9 | ETL idempotency (LLM judge) | read_file | external_id check |

## Iteration Strategy

1. Run `uv run run_eval.py`
2. Fix first failing question
3. Re-run until all 10 pass
4. Document lessons learned in AGENT.md

## Security

- Validate API paths (no path traversal)
- Use LMS_API_KEY from environment (not hardcoded)
- Timeout HTTP requests (30s max)
