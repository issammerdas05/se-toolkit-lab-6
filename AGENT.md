# Agent Architecture

## Overview

`agent.py` is a CLI tool that connects to an LLM (Large Language Model) and returns structured JSON responses. It uses a dual-approach:

1. **Primary:** OpenRouter API (OpenAI-compatible)
2. **Fallback:** Qwen Code CLI (direct invocation)

## LLM Provider

### Primary: OpenRouter

**Provider:** OpenRouter  
**Model:** `meta-llama/llama-3.3-70b-instruct:free`  
**Why:** Free tier (50 requests/day), no credit card required

### Fallback: Qwen Code CLI

**Provider:** Qwen Code (via CLI)  
**Model:** `coder-model` (Qwen 3.5 Plus)  
**Why:** 1000 free requests/day, already authenticated on VM

The agent automatically falls back to Qwen Code CLI when OpenRouter rate limits are hit.

## Configuration

The agent reads configuration from `.env.agent.secret` in the project root:

```bash
LLM_API_KEY=sk-or-v1-...        # Your OpenRouter API key
LLM_API_BASE=https://openrouter.ai/api/v1  # API base URL
LLM_MODEL=meta-llama/llama-3.3-70b-instruct:free  # Model name
```

### Getting OpenRouter API Key (Free)

1. Go to <https://openrouter.ai/>
2. Sign in with GitHub or Google
3. Go to "Keys" tab
4. Click "Create Key"
5. Copy the key to `.env.agent.secret`

## Usage

```bash
# Run with a question
uv run agent.py "What does REST stand for?"

# Output (JSON to stdout)
{"answer": "Representational State Transfer.", "tool_calls": []}
```

## Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                      agent.py                               │
│                                                             │
│  ┌─────────────┐    ┌──────────────┐    ┌───────────────┐  │
│  │ CLI Parser  │───▶│ Env Loader   │───▶│ HTTP Client   │  │
│  │ (argparse)  │    │ (dotenv)     │    │ (httpx)       │  │
│  └─────────────┘    └──────────────┘    └───────────────┘  │
│                            │                    │           │
│                            ▼                    ▼           │
│                     .env.agent.secret    OpenRouter API     │
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

## Data Flow

1. **Input:** User provides a question as a command-line argument
2. **Environment:** Agent loads API credentials from `.env.agent.secret`
3. **API Call (Primary):** Agent sends POST request to OpenRouter API
4. **Rate Limit Handling:** If rate limited (429), retries with exponential backoff
5. **Fallback:** After all retries, falls back to Qwen Code CLI
6. **Response:** Agent parses the LLM response and extracts the answer
7. **Output:** Agent prints JSON with `answer` and `tool_calls` to stdout

## Output Format

```json
{
  "answer": "The assistant's response text",
  "tool_calls": []
}
```

- `answer`: The LLM's response to the question
- `tool_calls`: Empty array (will be populated in Task 2 when tools are added)

## Error Handling

| Error | Behavior |
|-------|----------|
| Missing `.env.agent.secret` | Error to stderr, exit 1 |
| Missing `LLM_API_KEY` | Error to stderr, exit 1 |
| Network timeout (>60s) | Error to stderr, exit 1 |
| Invalid API response | Fallback to Qwen CLI |
| Empty question | Error to stderr, exit 1 |
| Qwen CLI not found | Error to stderr, exit 1 |

## Testing

Run the regression test:

```bash
uv run pytest backend/tests/unit/test_agent.py -v
```

The test verifies:

- Agent outputs valid JSON
- JSON contains `answer` field (non-empty string)
- JSON contains `tool_calls` field (array, empty for Task 1)

## Future Work (Tasks 2-3)

- **Task 2:** Add tool support (file system, API queries)
- **Task 3:** Add agentic loop (plan → act → observe → repeat)
