from unittest.mock import MagicMock, patch, PropertyMock
from core.engine import Engine, AbortedError
from core.tools.base import Tool, ToolResult
from core.permissions import PermissionChecker
from core.session import SessionMeta
from prompt_toolkit.document import Document


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

    assert "回车发送" in _bottom_toolbar_hint(False, "zh-CN")
    assert "终端模式" in _bottom_toolbar_hint(True, "zh-CN")


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
