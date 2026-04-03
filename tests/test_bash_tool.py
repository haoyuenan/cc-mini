from __future__ import annotations

from subprocess import CompletedProcess
from unittest.mock import patch

from core.tools.bash import BashTool


def test_bash_tool_decodes_invalid_bytes_without_crashing() -> None:
    tool = BashTool()
    completed = CompletedProcess(
        args="git diff",
        returncode=0,
        stdout=b"before\x94after",
        stderr=b"",
    )

    with patch("core.tools.bash.subprocess.run", return_value=completed):
        result = tool.execute("git diff")

    assert result.is_error is False
    assert "before" in result.content
    assert "after" in result.content


def test_bash_tool_decodes_utf8_bytes_output() -> None:
    tool = BashTool()
    completed = CompletedProcess(
        args="git diff",
        returncode=0,
        stdout="中文输出".encode("utf-8"),
        stderr=b"",
    )

    with patch("core.tools.bash.subprocess.run", return_value=completed):
        result = tool.execute("git diff")

    assert result.content == "中文输出"
