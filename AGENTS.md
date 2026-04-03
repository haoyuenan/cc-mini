# AGENTS.md - Coding Agent Guidelines for cc-mini

## Project Overview

cc-mini is an ultra-light harness scaffolding for AI agents (~1000 lines Python). It provides an interactive REPL with streaming output, agentic tool loop, built-in tools, permission system, and session persistence. Compatible with Anthropic and OpenAI APIs.

## Build Commands

### Setup Development Environment

```bash
# Create virtual environment and install in editable mode
python -m venv .venv
.venv/bin/python -m pip install --upgrade pip
.venv/bin/python -m pip install -e ".[dev]"
```

On Windows (PowerShell):
```powershell
py -3.11 -m venv .venv
.\.venv\Scripts\python.exe -m pip install --upgrade pip
.\.venv\Scripts\python.exe -m pip install -e ".[dev]"
```

### Run the Application

```bash
.venv/bin/cc-mini              # Interactive REPL
.venv/bin/cc-mini "prompt"     # One-shot prompt
.venv/bin/cc-mini --help       # Show CLI options
```

### Build Distributable Packages

```bash
.venv/bin/python -m build      # Creates .whl and .tar.gz in dist/
```

## Test Commands

### Run All Tests

```bash
pytest tests/ -v
```

### Run Tests (Skip Integration/Sandbox Tests)

```bash
pytest tests/ -v -k "not integration"
```

### Run a Single Test File

```bash
pytest tests/test_engine.py -v
```

### Run a Single Test Function

```bash
pytest tests/test_engine.py::test_engine_returns_text_events -v
```

### Run Tests Matching a Pattern

```bash
pytest tests/ -v -k "bash"     # Run all tests with "bash" in name
```

## Lint/Typecheck Commands

**Note:** This project does not currently have a configured linter or type checker. If you add one, update this section.

Recommended (if installed):
```bash
ruff check src/                # Lint with ruff
mypy src/                      # Type check with mypy
```

## Code Style Guidelines

### Imports

Imports are ordered in three groups, separated by blank lines:

1. **Standard library** (alphabetical)
2. **External packages** (alphabetical)
3. **Internal modules** (relative imports, alphabetical)

Example:
```python
from __future__ import annotations

import os
import sys
from pathlib import Path
from typing import Any

import anthropic
from rich.console import Console

from .config import load_app_config
from .engine import Engine
```

**Rules:**
- Always use `from __future__ import annotations` at the top for modern type hints
- Use `from typing import TYPE_CHECKING` and place forward-reference imports inside that block
- Use relative imports for internal modules (`from .module import ...`)

### Type Annotations

Use modern Python 3.11+ type syntax:
- `list[dict]` not `List[Dict]`
- `str | None` not `Optional[str]`
- `dict[str, Any]` not `Dict[str, Any]`

Example:
```python
def submit(self, user_input: str | list) -> Iterator[tuple]:
    ...
    
def get_messages(self) -> list[dict]:
    return list(self._messages)
```

### Naming Conventions

- **Module-level constants:** `_UPPER_CASE` with underscore prefix for private
- **Private methods/attributes:** `_lower_case` with underscore prefix
- **Classes:** `PascalCase`
- **Functions/methods:** `snake_case`
- **Type aliases:** `PascalCase` (e.g., `ProviderName = str`)

Example:
```python
_MAX_RETRIES = 3
_RETRY_BACKOFF = (1, 3, 10)

class Engine:
    def __init__(self, ...):
        self._messages: list[dict] = []
        self._aborted = False
    
    def get_messages(self) -> list[dict]:
        ...
    
    def _execute_tool(self, tool_use) -> ToolResult:
        ...
```

### Dataclasses

Use `@dataclass` for simple data structures:
```python
from dataclasses import dataclass

@dataclass
class ToolResult:
    content: str
    is_error: bool = False

@dataclass(frozen=True)
class AppConfig:
    provider: str
    model: str
    max_tokens: int
```

### Abstract Base Classes

Use `ABC` and `@abstractmethod` for interfaces:
```python
from abc import ABC, abstractmethod

class Tool(ABC):
    @property
    @abstractmethod
    def name(self) -> str: ...
    
    @abstractmethod
    def execute(self, **kwargs) -> ToolResult: ...
```

### Error Handling

- Catch specific exceptions, not bare `Exception` unless necessary
- For non-critical failures, use silent `pass` to avoid breaking the main flow
- Return error results via `ToolResult(is_error=True)` for tool failures
- Raise custom exceptions for control flow (e.g., `AbortedError`)

Example:
```python
try:
    self._session_store.append_message(message)
except Exception:
    pass  # don't break the conversation on I/O errors

try:
    result = tool.execute(**tool_input)
except Exception as e:
    return ToolResult(content=f"Tool error: {e}", is_error=True)
```

### Function/Method Organization

Within a class, organize methods in this order:
1. Properties (getters/setters)
2. Public methods
3. Private helper methods

Use section comments with `--` separators for large classes:
```python
# -- message accessors (for compact / resume / commands) ----------------

def get_messages(self) -> list[dict]:
    ...
```

### Docstrings

Docstrings are optional for helper functions. Use them for:
- Public API methods
- Complex functions that need explanation
- Classes with non-obvious behavior

Format: concise description of purpose, not implementation details.

### Code Formatting

- Maximum line length: ~100 characters (flexible)
- Use trailing commas in multi-line collections for cleaner diffs
- Prefer early returns over nested conditions

### Tests

- Use pytest fixtures for test setup
- Test file naming: `test_<module>.py`
- Test function naming: `test_<description>`
- Use descriptive assert messages when helpful

Example:
```python
@pytest.fixture
def tmp_file(tmp_path):
    f = tmp_path / "sample.txt"
    f.write_text("line one\nline two\n")
    return str(f)

def test_file_read_returns_numbered_content(tmp_file):
    result = FileReadTool().execute(file_path=tmp_file)
    assert not result.is_error
    assert "1\tline one" in result.content
```

## Project Structure

```
src/core/
├── main.py           # CLI entry point + REPL
├── engine.py         # Streaming API loop + tool execution
├── llm.py            # LLM client (Anthropic + OpenAI)
├── config.py         # Configuration (CLI, env, TOML)
├── context.py        # System prompt builder
├── commands.py       # Slash command system
├── session.py        # Session persistence
├── compact.py        # Context compression
├── tools/            # Tool implementations
├── buddy/            # AI companion pet system
└── sandbox/          # Bubblewrap sandbox subsystem

tests/                # pytest test files
docs/                 # Documentation
```

## Important Notes

- Python 3.11+ is required (uses modern type syntax, `tomllib`)
- The package is installed via `pip install -e ".[dev]"` for development
- Editable install means source changes are picked up without reinstall
- Only reinstall when changing `pyproject.toml` or dependencies