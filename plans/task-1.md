# Task 1: Call an LLM from Code

## LLM Provider

**Primary Provider:** OpenRouter  
**Primary Model:** `meta-llama/llama-3.3-70b-instruct:free`  
**Fallback Provider:** Qwen Code CLI  
**Fallback Model:** `coder-model` (Qwen 3.5 Plus)

**Why dual approach:**

- OpenRouter free tier has strict rate limits (50 requests/day, often lower)
- Qwen Code CLI provides 1000 free requests/day and is already authenticated
- Agent tries OpenRouter first, falls back to Qwen CLI on rate limits

## Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                      agent.py                               │
│                                                             │
│  ┌─────────────┐    ┌──────────────┐    ┌───────────────┐  │
│  │ CLI Parser  │───▶│ Env Loader   │───▶│ HTTP Client   │──┼──▶ OpenRouter API
│  │ (argparse)  │    │ (dotenv)     │    │ (httpx)       │  │
│  └─────────────┘    └──────────────┘    └───────────────┘  │
│                            │                    │           │
│                            │         ┌──────────┘           │
│                            │         │ 429 Rate Limited     │
│                            ▼         ▼                      │
│                     ┌──────────────────────┐                │
│                     │  Fallback: Qwen CLI  │                │
│                     │  (subprocess call)   │                │
│                     └──────────────────────┘                │
│                            │                                │
│                            ▼                                │
│  ┌─────────────┐    ┌──────────────┐    ┌───────────────┐  │
│  │ JSON Output │◀───│ Response     │◀───│ LLM Response  │  │
│  │ (stdout)    │    │ Parser       │    │               │  │
│  └─────────────┘    └──────────────┘    └───────────────┘  │
└─────────────────────────────────────────────────────────────┘
```

## Implementation Details

### 1. Environment Setup

- Read `.env.agent.secret` for `LLM_API_KEY`, `LLM_API_BASE`, `LLM_MODEL`
- Use `python-dotenv` to load environment variables

### 2. CLI Interface

- Parse command-line argument (the question)
- Validate input (non-empty question)

### 3. LLM API Call (Primary)

- Use `httpx` for async HTTP requests
- POST to `{LLM_API_BASE}/chat/completions`
- Headers: `Authorization: Bearer {LLM_API_KEY}`, `Content-Type: application/json`
- Body: `{"model": LLM_MODEL, "messages": [{"role": "user", "content": question}]}`
- Retry with exponential backoff on 429 rate limits (3 retries)

### 4. Fallback: Qwen Code CLI

- If API fails after all retries, invoke `qwen "<question>" --prompt`
- Set `PNPM_HOME` and `PATH` environment variables
- Capture stdout as the answer

### 5. Response Parsing

- Extract `choices[0].message.content` from API response
- Or use CLI stdout directly
- Format as JSON: `{"answer": "...", "tool_calls": []}`

### 6. Output

- Print JSON to stdout (single line)
- All debug/logging to stderr
- Exit code 0 on success

## Error Handling

- Missing API key → error to stderr, exit 1
- Network error → retry, then fallback to CLI
- Invalid response → fallback to CLI
- Timeout (>60s) → error to stderr, exit 1
- Qwen CLI not found → error to stderr, exit 1

## Testing

- 1 regression test: run `agent.py "test question"`, parse JSON, verify `answer` and `tool_calls` fields exist
- Test passes with both API and CLI fallback

## Files Created

| File | Purpose |
|------|---------|
| `plans/task-1.md` | Implementation plan |
| `agent.py` | CLI agent with API + fallback |
| `AGENT.md` | Architecture documentation |
| `backend/tests/unit/test_agent.py` | Regression test |
| `.env.agent.secret` | Configuration (API key) |
| `pyproject.toml` | Added `python-dotenv` dependency |
