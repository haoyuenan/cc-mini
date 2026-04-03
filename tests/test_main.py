from unittest.mock import MagicMock, patch, PropertyMock
from core.engine import Engine, AbortedError
from core.tools.base import Tool, ToolResult
from core.permissions import PermissionChecker
from core.session import SessionMeta
from prompt_toolkit.document import Document
from rich.console import Console


class DummyTool(Tool):
    name = "Dummy"
    description = "A dummy tool for testing"
    input_schema = {
        "type": "object",
        "properties": {"msg": {"type": "string"}},
        "required": ["msg"],
    }

    def execute(self, msg: str) -> ToolResult:
        return ToolResult(content=f"got: {msg}")


def _make_text_stream(text: str):
    block = MagicMock()
    block.type = "text"
    block.text = text

    final_msg = MagicMock()
    final_msg.content = [block]

    stream = MagicMock()
    stream.__enter__ = MagicMock(return_value=stream)
    stream.__exit__ = MagicMock(return_value=False)
    stream.text_stream = iter([text])
    stream.get_final_message = MagicMock(return_value=final_msg)
    return stream


def _make_engine():
    return Engine(
        tools=[DummyTool()],
        system_prompt="test",
        permission_checker=PermissionChecker(auto_approve=True),
    )


class _FakeEscListener:
    """A no-op replacement for EscListener that doesn't touch the terminal."""
    pressed = False

    def __init__(self, **kwargs):
        pass

    def __enter__(self):
        return self

    def __exit__(self, *_):
        pass

    def pause(self):
        pass

    def resume(self):
        pass

    def check_esc_nonblocking(self):
        return False


@patch("core.main.EscListener", _FakeEscListener)
def test_run_query_prints_text(capsys):
    """run_query should print text events to stdout in print_mode."""
    from core.main import run_query

    engine = _make_engine()
    with patch.object(engine._client, "stream_messages", return_value=_make_text_stream("hello world")):
        run_query(engine, "hi", print_mode=True)

    captured = capsys.readouterr()
    assert "hello world" in captured.out


@patch("core.main.EscListener", _FakeEscListener)
def test_run_query_handles_tool_call_event():
    """run_query should display tool call info via rich console."""
    from core.main import run_query

    engine = _make_engine()

    tool_block = MagicMock()
    tool_block.type = "tool_use"
    tool_block.id = "tu_1"
    tool_block.name = "Dummy"
    tool_block.input = {"msg": "test"}

    first_final = MagicMock()
    first_final.content = [tool_block]
    first_stream = MagicMock()
    first_stream.__enter__ = MagicMock(return_value=first_stream)
    first_stream.__exit__ = MagicMock(return_value=False)
    first_stream.text_stream = iter([])
    first_stream.get_final_message = MagicMock(return_value=first_final)

    second_stream = _make_text_stream("done")

    with patch.object(engine._client, "stream_messages", side_effect=[first_stream, second_stream]):
        run_query(engine, "use tool", print_mode=True)


@patch("core.main.EscListener", _FakeEscListener)
def test_run_query_handles_keyboard_interrupt():
    """run_query should gracefully handle KeyboardInterrupt."""
    from core.main import run_query

    engine = _make_engine()

    def raise_interrupt(*a, **kw):
        raise KeyboardInterrupt()

    with patch.object(engine._client, "stream_messages", side_effect=raise_interrupt):
        run_query(engine, "hi", print_mode=True)
    # Should not propagate the exception


def test_localized_builtin_commands_show_chinese_descriptions():
    from core.main import _SlashCommandCompleter

    completer = _SlashCommandCompleter(locale_getter=lambda: "zh-CN")
    document = Document("/he")

    completions = list(completer.get_completions(document, None))

    assert completions
    assert completions[0].display_text == "/help"
    assert "显示可用命令" in str(completions[0].display_meta)


def test_bottom_toolbar_hint_is_localized_to_chinese():
    from core.main import _bottom_toolbar_hint

    assert _bottom_toolbar_hint(False, "zh-CN") == "-"
    assert _bottom_toolbar_hint(True, "zh-CN") == "-"


def test_load_startup_locale_restores_latest_session_locale():
    from core.main import _load_startup_locale

    sessions = [
        SessionMeta(
            session_id="session-1",
            title="latest",
            cwd="D:/repo",
            model="test-model",
            created_at="2026-04-03T00:00:00+00:00",
            updated_at="2026-04-03T00:00:01+00:00",
            locale="zh-CN",
        ),
    ]

    with patch("core.main.SessionStore.list_sessions", return_value=sessions):
        assert _load_startup_locale("D:/repo") == "zh-CN"


def test_load_startup_locale_falls_back_to_default_when_missing():
    from core.main import _load_startup_locale

    with patch("core.main.SessionStore.list_sessions", return_value=[]):
        assert _load_startup_locale("D:/repo") == "en"


def test_resume_success_message_is_localized_to_chinese():
    from core.main import _resume_success_message

    rendered = _resume_success_message("示例会话", 5, "zh-CN")

    assert "已恢复" in rendered
    assert "5 条消息" in rendered


def test_resume_not_found_message_is_localized_to_chinese():
    from core.main import _resume_not_found_message

    rendered = _resume_not_found_message("abc123", "zh-CN")

    assert "未找到会话" in rendered
    assert "abc123" in rendered


def test_background_workers_notice_is_localized_to_chinese():
    from core.main import _background_workers_notice

    rendered = _background_workers_notice("zh-CN")

    assert "后台 worker 仍在运行" in rendered


def test_worker_update_message_is_localized_to_chinese():
    from core.main import _worker_update_message

    assert "收到 worker 更新" in _worker_update_message("zh-CN")


def test_exit_hint_is_localized_to_chinese():
    from core.main import _exit_hint

    rendered = _exit_hint("zh-CN")

    assert "按 Esc 或 Ctrl+C 取消" in rendered


def test_shell_exit_message_is_localized_to_chinese():
    from core.main import _shell_exit_message

    assert "退出码 7" in _shell_exit_message(7, "zh-CN")


def test_shell_error_message_is_localized_to_chinese():
    from core.main import _shell_error_message

    assert "错误：boom" in _shell_error_message("boom", "zh-CN")


def test_auto_compact_messages_are_localized_to_chinese():
    from core.main import (
        _auto_compacting_message,
        _context_compressed_message,
        _auto_compact_failed_message,
    )

    assert "正在自动压缩对话" in _auto_compacting_message("zh-CN")
    assert "上下文已压缩到 123 个 token" in _context_compressed_message(123, "zh-CN")
    assert "自动压缩失败：boom" in _auto_compact_failed_message("boom", "zh-CN")


def test_dream_messages_are_localized_to_chinese():
    from core.main import (
        _dream_start_message,
        _dream_complete_message,
        _auto_dream_triggered_message,
    )

    assert "开始执行 dream 整理" in _dream_start_message("zh-CN")
    assert "dream 整理完成" in _dream_complete_message("zh-CN")
    assert "已触发自动 dream" in _auto_dream_triggered_message("zh-CN")


def test_sandbox_status_messages_are_localized_to_chinese():
    from core.main import (
        _sandbox_status_title,
        _sandbox_mode_line,
        _sandbox_enabled_line,
        _sandbox_network_isolation_line,
        _sandbox_dependency_errors_title,
        _sandbox_excluded_commands_title,
    )

    assert "沙箱状态" in _sandbox_status_title("zh-CN")
    assert "模式：" in _sandbox_mode_line("regular", "zh-CN")
    assert "已启用：是" in _sandbox_enabled_line(True, "zh-CN")
    assert "网络隔离：否" in _sandbox_network_isolation_line(False, "zh-CN")
    assert "依赖错误" in _sandbox_dependency_errors_title("zh-CN")
    assert "排除命令" in _sandbox_excluded_commands_title("zh-CN")


def test_yes_no_label_is_localized_without_hardcoding_call_sites():
    from core.main import _yes_no_label

    assert _yes_no_label(True, "zh-CN") == "是"
    assert _yes_no_label(False, "zh-CN") == "否"
    assert _yes_no_label(True, "en") == "yes"
    assert _yes_no_label(False, "en") == "no"


def test_sandbox_setup_messages_are_localized_to_chinese():
    from core.main import (
        _sandbox_configure_title,
        _sandbox_option_auto_allow,
        _sandbox_option_regular,
        _sandbox_option_disabled,
        _sandbox_select_prompt,
        _sandbox_cannot_enable_title,
        _sandbox_cancelled_message,
    )

    assert "配置沙箱模式" in _sandbox_configure_title("zh-CN")
    assert "自动放行" in _sandbox_option_auto_allow("zh-CN")
    assert "仍需确认" in _sandbox_option_regular("zh-CN")
    assert "禁用" in _sandbox_option_disabled("zh-CN")
    assert "请选择 [1/2/3]" in _sandbox_select_prompt("zh-CN")
    assert "无法启用沙箱" in _sandbox_cannot_enable_title("zh-CN")
    assert "已取消" in _sandbox_cancelled_message("zh-CN")


def test_tool_done_and_session_note_are_localized_to_chinese():
    from core.main import _tool_done_message, _session_note

    assert "完成" in _tool_done_message("zh-CN")
    assert "会话 abcd1234" in _session_note("abcd1234", "zh-CN")


def test_repl_intro_panel_contains_version_and_runtime_status_details():
    from core.main import _build_repl_intro_section

    recorder = Console(record=True, width=100)
    recorder.print(
        _build_repl_intro_section(
            model="claude-sonnet-4-20250514",
            max_tokens=32000,
            session_id="abcd1234",
        )
    )

    rendered = recorder.export_text()

    assert "Welcome to CC-Mini v0.1.0" in rendered
    assert "Model:" in rendered
    assert "claude-sonnet-4-20250514" in rendered
    assert "Max: 32000" in rendered
    assert "Session: abcd1234" in rendered


def test_tool_call_panel_surfaces_tool_name_and_preview():
    from core.main import _build_tool_call_panel

    recorder = Console(record=True, width=100)
    recorder.print(_build_tool_call_panel("Bash", "git diff --stat", "zh-CN"))

    rendered = recorder.export_text()

    assert "Bash" in rendered
    assert "git diff --stat" in rendered


def test_repl_intro_panel_contains_welcome_art_and_shortcuts_in_one_frame():
    from core.main import _build_repl_intro_section

    panel = _build_repl_intro_section()
    recorder = Console(record=True, width=100)
    recorder.print(panel)

    rendered = recorder.export_text()

    assert "Welcome to CC-Mini" in rendered
    assert "Quick Shortcuts" in rendered
    assert "▓▓▓▓" in rendered
    assert "▓   ▓" in rendered
    assert "Cancel / Quit" in rendered
    assert panel.expand is False


def test_repl_intro_panel_uses_single_outer_panel_width():
    from rich.panel import Panel
    from core.main import (
        _SHORTCUTS_PANEL_WIDTH,
        _WELCOME_PANEL_WIDTH,
        _build_repl_intro_section,
    )

    panel = _build_repl_intro_section()

    assert isinstance(panel, Panel)
    assert panel.width == _WELCOME_PANEL_WIDTH + _SHORTCUTS_PANEL_WIDTH


def test_repl_intro_section_uses_tighter_gap_and_fixed_width():
    from core.main import _build_repl_intro_section

    intro = _build_repl_intro_section()

    assert intro.expand is False
    assert intro.width is not None


def test_repl_header_width_matches_intro_total_width():
    from core.main import (
        _HEADER_EXTRA_WIDTH,
        _SHORTCUTS_PANEL_WIDTH,
        _WELCOME_PANEL_WIDTH,
        _build_repl_header,
    )

    header = _build_repl_header(
        provider="anthropic",
        model="claude-sonnet-4-20250514",
        max_tokens=32000,
        session_id="abcd1234",
        coordinator_enabled=True,
        locale="zh-CN",
    )

    assert header.expand is False
    assert _HEADER_EXTRA_WIDTH == 5
    assert header.width == _WELCOME_PANEL_WIDTH + _SHORTCUTS_PANEL_WIDTH + _HEADER_EXTRA_WIDTH


def test_welcome_panel_is_narrower_to_pull_shortcuts_left():
    from core.main import _SHORTCUTS_PANEL_WIDTH, _WELCOME_PANEL_WIDTH

    assert _WELCOME_PANEL_WIDTH < _SHORTCUTS_PANEL_WIDTH
    assert _WELCOME_PANEL_WIDTH <= 28


@patch("core.main.EscListener", _FakeEscListener)
def test_run_query_uses_localized_spinner_labels():
    from core.main import run_query

    spinner_starts: list[str] = []

    class _FakeSpinnerManager:
        def __init__(self, _console, locale=None):
            pass

        def start(self, text: str = ""):
            spinner_starts.append(text)

        def update(self, text: str):
            pass

        def stop(self):
            pass

    engine = MagicMock()
    engine.submit.return_value = iter([("waiting",)])
    engine.abort = MagicMock()
    engine.cancel_turn = MagicMock()

    with patch("core.main._SpinnerManager", _FakeSpinnerManager):
        run_query(engine, "hi", print_mode=True, locale="zh-CN")

    assert spinner_starts[0] == "思考中…"
    assert "准备调用工具" in spinner_starts[1]
