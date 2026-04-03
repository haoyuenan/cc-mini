from __future__ import annotations

import locale
import subprocess
from typing import TYPE_CHECKING

from .base import Tool, ToolResult

if TYPE_CHECKING:
    from ..sandbox.manager import SandboxManager

_DEFAULT_TIMEOUT = 120


def _decode_process_output(data: bytes | str | None) -> str:
    if data is None:
        return ""
    if isinstance(data, str):
        return data

    raw = bytes(data)

    preferred = locale.getpreferredencoding(False) or "utf-8"
    candidates: list[str] = []
    for encoding in ("utf-8", "utf-8-sig"):
        if encoding not in candidates:
            candidates.append(encoding)

    for encoding in candidates:
        try:
            return raw.decode(encoding)
        except UnicodeDecodeError:
            continue

    non_ascii_bytes = sum(1 for byte in raw if byte >= 0x80)
    if non_ascii_bytes and non_ascii_bytes <= max(3, len(raw) // 8):
        return raw.decode("utf-8", errors="replace")

    if preferred not in candidates:
        candidates.append(preferred)

    for encoding in candidates[2:]:
        try:
            return raw.decode(encoding)
        except UnicodeDecodeError:
            continue

    return raw.decode(preferred, errors="replace")


class BashTool(Tool):
    name = "Bash"
    description = (
        "Execute a bash command. Returns stdout + stderr. "
        "Timeout defaults to 120s. Avoid interactive commands."
    )
    input_schema = {
        "type": "object",
        "properties": {
            "command": {"type": "string", "description": "The bash command to execute"},
            "timeout": {"type": "integer", "description": "Timeout in seconds", "default": 120},
            "dangerously_disable_sandbox": {
                "type": "boolean",
                "description": "If true and allowed by config, run outside sandbox",
            },
        },
        "required": ["command"],
    }

    def __init__(self, sandbox_manager: SandboxManager | None = None):
        self._sandbox = sandbox_manager

    def execute(
        self,
        command: str,
        timeout: int = _DEFAULT_TIMEOUT,
        dangerously_disable_sandbox: bool = False,
    ) -> ToolResult:
        # Sandbox decision
        use_sandbox = (
            self._sandbox is not None
            and self._sandbox.should_sandbox(command, dangerously_disable_sandbox)
        )

        actual_command = self._sandbox.wrap(command) if use_sandbox else command

        try:
            result = subprocess.run(
                actual_command, shell=True, capture_output=True, timeout=timeout
            )
            parts = []
            stdout = _decode_process_output(result.stdout).rstrip()
            stderr = _decode_process_output(result.stderr).rstrip()
            if stdout:
                parts.append(stdout)
            if stderr:
                parts.append(f"[stderr]\n{stderr}")
            if result.returncode != 0:
                parts.append(f"[exit code: {result.returncode}]")
            return ToolResult(content="\n".join(parts) if parts else "(no output)")
        except subprocess.TimeoutExpired:
            return ToolResult(content=f"Error: Command timed out after {timeout}s", is_error=True)
        except Exception as e:
            return ToolResult(content=f"Error: {e}", is_error=True)
