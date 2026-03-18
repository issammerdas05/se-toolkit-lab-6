# Agent Architecture (Task 2)

## Overview

`agent.py` is a CLI tool with an **agentic loop** that can use tools to navigate the project wiki and answer questions with cited sources.

## LLM Provider

**Primary:** OpenRouter API (`meta-llama/llama-3.3-70b-instruct:free`)  
**Fallback:** Qwen Code CLI (`coder-model`)

## Tools

### read_file

Reads contents of a file from the project repository.

**Parameters:**

- `path` (string): Relative path from project root (e.g., `wiki/git.md`)

**Returns:**

- `{"success": true, "content": "..."}` on success
- `{"success": false, "error": "..."}` on failure

**Security:**

- Rejects absolute paths
- Rejects paths with `../` (path traversal)
- Validates resolved path is within project root

### list_files

Lists files and directories at a given path.

**Parameters:**

- `path` (string): Relative directory path from project root (e.g., `wiki/`)

**Returns:**

- `{"success": true, "files": "file1.md\ndir2/"}` on success
- `{"success": false, "error": "..."}` on failure

**Security:**

- Same path validation as `read_file`

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
            log_tool_call(tool_name, args, result)
            messages.append({"role": "tool", "content": result})
    else:
        answer = response.content
        extract_source(answer)
        break
```

### Flow

1. Send user question + tool schemas to LLM
2. If LLM returns `tool_calls`:
   - Execute each tool
   - Append results to messages as `tool` role
   - Continue loop
3. If LLM returns text answer:
   - Extract source reference (e.g., `wiki/git.md#merge-conflicts`)
   - Return JSON and exit
4. If max 10 tool calls reached:
   - Return whatever answer we have

## System Prompt

```
You are a documentation assistant for a software engineering lab.

You have access to two tools:
1. list_files - List files and directories at a given path
2. read_file - Read the contents of a file

To answer questions about the project:
1. Use list_files to discover relevant files, especially in the wiki/ directory
2. Use read_file to read the contents of relevant files
3. Extract the answer from the file contents
4. Include a source reference in the format: path/to/file.md#section-name
```

## Output Format

```json
{
    "answer": "Edit the conflicting file, choose which changes to keep, then stage and commit.",
    "source": "wiki/git-workflow.md#resolving-merge-conflicts",
    "tool_calls": [
        {
            "tool": "list_files",
            "args": {"path": "wiki"},
            "result": "git-workflow.md\n..."
        },
        {
            "tool": "read_file",
            "args": {"path": "wiki/git-workflow.md"},
            "result": "..."
        }
    ]
}
```

- `answer` (string): The LLM's response
- `source` (string): Wiki section reference (e.g., `wiki/file.md#section`)
- `tool_calls` (array): All tool calls made during the agentic loop

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
│                            ▼            └───────────────┘  │
│                     ┌──────────────┐            │           │
│                     │ LLM (Qwen)   │◀───────────┘           │
│                     │ + Tools      │                        │
│                     └──────────────┘                        │
│                            │                                │
│                            ▼                                │
│  ┌─────────────┐    ┌──────────────┐    ┌───────────────┐  │
│  │ JSON Output │◀───│ Source       │◀───│ LLM Answer    │  │
│  │ (stdout)    │    │ Extractor    │    │               │  │
│  └─────────────┘    └──────────────┘    └───────────────┘  │
└─────────────────────────────────────────────────────────────┘
```

## Security

Path validation prevents directory traversal:

```python
def validate_path(path: str) -> Path | None:
    # Reject absolute paths
    if os.path.isabs(path):
        return None
    
    # Reject path traversal
    if ".." in path:
        return None
    
    # Resolve and check within project root
    resolved = (PROJECT_ROOT / path).resolve()
    if not str(resolved).startswith(str(PROJECT_ROOT)):
        return None
    
    return resolved
```

## Testing

Run tests:

```bash
uv run pytest test_agent.py tests/test_agent.py -v
```

### Test Cases

1. **read_file test**: Ask "How do you resolve a merge conflict?"
   - Expected: `read_file` in tool_calls
   - Expected: `wiki/git-workflow.md` in source

2. **list_files test**: Ask "What files are in the wiki?"
   - Expected: `list_files` in tool_calls

## Future Work (Task 3)

- Add more tools (search, API queries)
- Improve source extraction
- Add conversation history support
