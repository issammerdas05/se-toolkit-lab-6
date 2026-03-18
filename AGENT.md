# Agent Architecture (Task 3: The System Agent)

## Overview

`agent.py` is a CLI agent with an **agentic loop** that can use three tools to answer questions:

1. `list_files` - Discover files in the project
2. `read_file` - Read wiki documentation and source code
3. `query_api` - Query the backend LMS API for data

## LLM Provider

**Primary:** OpenRouter API (`meta-llama/llama-3.3-70b-instruct:free`)  
**Fallback:** Qwen Code CLI (`coder-model`)

## Tools

### read_file

Reads contents of a file from the project repository.

**Parameters:**

- `path` (string): Relative path from project root

**Security:**

- Rejects absolute paths and path traversal (`../`)
- Validates resolved path is within project root
- Truncates content to 8000 chars for LLM context

### list_files

Lists files and directories at a given path.

**Parameters:**

- `path` (string): Relative directory path from project root

**Security:**

- Same path validation as `read_file`
- Skips hidden files (starting with `.`)

### query_api

Queries the backend LMS API with authentication.

**Parameters:**

- `method` (string): HTTP method (GET, POST, PUT, DELETE)
- `path` (string): API endpoint path (e.g., `/items/`, `/analytics/scores`)
- `body` (string, optional): JSON request body for POST/PUT

**Authentication:**

- Uses `LMS_API_KEY` from `.env.docker.secret`
- Sends `Authorization: Bearer {LMS_API_KEY}` header

**Returns:**

- `{"success": true, "status_code": 200, "body": {...}}`
- `{"success": false, "error": "..."}`

**Security:**

- 30 second timeout
- Response body truncated to 1000 chars if not JSON

## Agentic Loop

```python
messages = [
    {"role": "system", "content": SYSTEM_PROMPT},
    {"role": "user", "content": question}
]

for i in range(MAX_TOOL_CALLS):  # max 10
    response = call_llm(messages, tools)
    
    if response has tool_calls:
        for each tool_call:
            result = execute_tool(tool_name, args)
            log_tool_call(tool_name, args, result[:500])
            messages.append({"role": "tool", "content": json(result)})
    else:
        answer = response.content
        extract_source(answer)
        break
```

### Decision Guide (from System Prompt)

| Question Type | Tool Strategy |
|---------------|---------------|
| Wiki/documentation | `list_files` → `read_file` |
| Source code | `read_file` on `backend/` files |
| Data (counts, status codes) | `query_api` |
| Bug diagnosis | `query_api` (reproduce) → `read_file` (find bug) |

## Environment Variables

| Variable | Purpose | Source | Default |
|----------|---------|-------|---------|
| `LLM_API_KEY` | LLM provider API key | `.env.agent.secret` | - |
| `LLM_API_BASE` | LLM API endpoint | `.env.agent.secret` | - |
| `LLM_MODEL` | Model name | `.env.agent.secret` | - |
| `LMS_API_KEY` | Backend API key | `.env.docker.secret` | - |
| `AGENT_API_BASE_URL` | Backend URL | Optional | `http://localhost:42002` |

**Important:** The autochecker injects different values for these variables. Never hardcode!

## Output Format

```json
{
    "answer": "There are 42 items in the database.",
    "source": "",
    "tool_calls": [
        {
            "tool": "query_api",
            "args": {"method": "GET", "path": "/items/"},
            "result": "{\"status_code\": 200, \"body\": [...]}"
        }
    ]
}
```

- `answer` (string): The LLM's response
- `source` (string): Wiki section reference (optional for Task 3)
- `tool_calls` (array): All tool calls with args and truncated results

## System Prompt

```
You are a documentation and system assistant for a software engineering lab.

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
```

## Benchmark Results

### Question Coverage

| # | Question | Tool(s) | Status |
|---|----------|---------|--------|
| 0 | Branch protection (wiki) | read_file | ✓ |
| 1 | SSH connection (wiki) | read_file | ✓ |
| 2 | Python web framework | read_file | ✓ |
| 3 | API router modules | list_files | ✓ |
| 4 | Items in database | query_api | ✓ |
| 5 | Status code without auth | query_api | ✓ |
| 6 | /analytics/completion-rate error | query_api + read_file | ✓ |
| 7 | /analytics/top-learners crash | query_api + read_file | ✓ |
| 8 | Request lifecycle (LLM judge) | read_file | ✓ |
| 9 | ETL idempotency (LLM judge) | read_file | ✓ |

## Lessons Learned

1. **Tool descriptions matter**: The LLM needs clear guidance on when to use each tool. Initially, it would call `read_file` for data questions. Adding explicit "Decision guide" to the system prompt fixed this.

2. **Content truncation is critical**: Large files (like `pyproject.toml` with full lock file) would exceed the LLM context. Truncating to 8000 chars and tool results to 500 chars keeps responses manageable.

3. **Error handling for null content**: The LLM sometimes returns `content: null` when making tool calls. Using `(msg.get("content") or "")` instead of `msg.get("content", "")` prevents `AttributeError`.

4. **API authentication**: Two separate keys (`LLM_API_KEY` for the model, `LMS_API_KEY` for the backend) was confusing at first. Clear variable naming and separate config functions helped.

5. **Fallback is essential**: OpenRouter free tier has strict rate limits. The Qwen Code CLI fallback ensures the agent always works.

## Final Eval Score

**Local benchmark:** 10/10 questions passing  
**Autochecker:** Pending

## Testing

Run tests:

```bash
uv run run_eval.py          # Full benchmark (10 questions)
uv run pytest test_*.py -v  # Regression tests
```

### Regression Tests

1. **Framework question**: "What framework does the backend use?" → expects `read_file`, answer contains "FastAPI"
2. **Database count**: "How many items in database?" → expects `query_api`, answer contains number > 0

## Future Improvements

- Add `search_file` tool for finding text across files
- Add conversation history for multi-turn dialogue
- Implement retry logic for failed API calls
- Add caching for repeated file reads
