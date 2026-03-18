# Task 2: The Documentation Agent

## Overview

Build an agentic loop that allows the LLM to use tools (`read_file`, `list_files`) to navigate the project wiki and answer questions with sources.

## Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                      agent.py                               │
│                                                             │
│  ┌─────────────┐    ┌──────────────┐    ┌───────────────┐  │
│  │ CLI Parser  │───▶│ Agentic Loop │───▶│ Tool Executor │  │
│  └─────────────┘    │  (max 10)    │    │               │  │
│                     └──────────────┘    │ - read_file   │  │
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

## Tool Schemas

### read_file

```python
{
    "name": "read_file",
    "description": "Read contents of a file from the project",
    "parameters": {
        "type": "object",
        "properties": {
            "path": {"type": "string", "description": "Relative path from project root"}
        },
        "required": ["path"]
    }
}
```

**Security:** Reject paths with `../` or absolute paths outside project root.

### list_files

```python
{
    "name": "list_files",
    "description": "List files and directories at a given path",
    "parameters": {
        "type": "object",
        "properties": {
            "path": {"type": "string", "description": "Relative directory path from project root"}
        },
        "required": ["path"]
    }
}
```

**Security:** Reject paths that escape project root.

## Agentic Loop

```python
messages = [
    {"role": "system", "content": SYSTEM_PROMPT},
    {"role": "user", "content": question}
]

for i in range(MAX_TOOL_CALLS):  # max 10
    response = call_llm(messages, tools)
    
    if response has tool_calls:
        execute each tool
        append tool results to messages
    else:
        answer = response.content
        break
```

## System Prompt

```
You are a documentation assistant. You have access to two tools:
- list_files: List files in a directory
- read_file: Read contents of a file

To answer questions about the project:
1. First use list_files to discover relevant files in wiki/
2. Then use read_file to read the relevant files
3. Extract the answer and include the source as file_path#section_anchor

Always cite your sources using the format: wiki/filename.md#section-name
```

## Output Format

```json
{
    "answer": "The answer text",
    "source": "wiki/git-workflow.md#resolving-merge-conflicts",
    "tool_calls": [
        {"tool": "list_files", "args": {"path": "wiki"}, "result": "..."},
        {"tool": "read_file", "args": {"path": "wiki/git-workflow.md"}, "result": "..."}
    ]
}
```

## Security

- Validate all paths: reject `../`, absolute paths, paths outside project root
- Use `os.path.realpath` to resolve symlinks and check final path

## Testing

1. Test `read_file`: Ask "How do you resolve a merge conflict?" → should call `read_file` on `wiki/git-workflow.md`
2. Test `list_files`: Ask "What files are in the wiki?" → should call `list_files` on `wiki/`
