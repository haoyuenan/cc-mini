from types import SimpleNamespace
from unittest.mock import MagicMock

from core.commands import CommandContext, handle_command
from core.i18n import t
from core.session import SessionMeta


class _LocaleState:
    def __init__(self, locale: str = "en"):
        self.value = locale


def _make_context(initial_locale: str = "en") -> tuple[CommandContext, _LocaleState, SimpleNamespace]:
    locale_state = _LocaleState(initial_locale)
    session_store = SimpleNamespace(locale=initial_locale)

    ctx = CommandContext(
        engine=MagicMock(),
        session_store=session_store,
        compact_service=MagicMock(),
        console=MagicMock(),
        app_config=SimpleNamespace(provider="anthropic", model="test-model"),
        locale=initial_locale,
        translate=lambda key, **kwargs: t(locale_state.value, key, **kwargs),
        set_locale=lambda value: _set_locale(ctx, locale_state, session_store, value),
    )
    return ctx, locale_state, session_store



def _set_locale(ctx: CommandContext, locale_state: _LocaleState, session_store: SimpleNamespace, value: str) -> None:
    locale_state.value = value
    session_store.locale = value
    ctx.locale = value



def test_language_command_reports_current_locale():
    ctx, _, _ = _make_context("en")

    handled = handle_command("language", "", ctx)

    assert handled is True
    rendered = "\n".join(str(call.args[0]) for call in ctx.console.print.call_args_list)
    assert "Current interface language" in rendered
    assert "en" in rendered



def test_language_command_switches_to_chinese():
    ctx, locale_state, session_store = _make_context("en")

    handled = handle_command("language", "zh", ctx)

    assert handled is True
    assert locale_state.value == "zh-CN"
    assert session_store.locale == "zh-CN"
    assert ctx.locale == "zh-CN"
    rendered = "\n".join(str(call.args[0]) for call in ctx.console.print.call_args_list)
    assert "界面语言已切换为 中文" in rendered



def test_language_command_accepts_chinese_alias():
    ctx, locale_state, session_store = _make_context("en")

    handled = handle_command("language", "中文", ctx)

    assert handled is True
    assert locale_state.value == "zh-CN"
    assert session_store.locale == "zh-CN"


def test_language_command_persists_locale_immediately():
    ctx, _, session_store = _make_context("en")
    session_store.persist_metadata = MagicMock()

    handled = handle_command("language", "zh", ctx)

    assert handled is True
    session_store.persist_metadata.assert_called_once_with()



def test_language_command_rejects_unsupported_locale():
    ctx, locale_state, session_store = _make_context("en")

    handled = handle_command("language", "fr", ctx)

    assert handled is True
    assert locale_state.value == "en"
    assert session_store.locale == "en"
    rendered = "\n".join(str(call.args[0]) for call in ctx.console.print.call_args_list)
    assert "Unsupported interface language" in rendered


def test_help_command_prints_chinese_title_when_locale_is_zh():
    ctx, _, _ = _make_context("zh-CN")

    handled = handle_command("help", "", ctx)

    assert handled is True
    rendered_table = ctx.console.print.call_args.args[0]
    assert rendered_table.title == "可用命令"


def test_unknown_command_is_localized_when_locale_is_zh():
    ctx, _, _ = _make_context("zh-CN")

    handled = handle_command("unknown", "", ctx)

    assert handled is False
    rendered = "\n".join(str(call.args[0]) for call in ctx.console.print.call_args_list)
    assert "未知命令" in rendered


def test_history_command_prints_chinese_title_when_locale_is_zh(monkeypatch):
    ctx, _, _ = _make_context("zh-CN")
    sessions = [
        SessionMeta(
            session_id="abc12345",
            title="示例会话",
            cwd="D:/repo",
            model="test-model",
            created_at="2026-04-03T00:00:00+00:00",
            updated_at="2026-04-03T00:00:01+00:00",
            message_count=3,
        )
    ]

    monkeypatch.setattr("core.session.SessionStore.list_sessions", lambda cwd: sessions)

    handled = handle_command("history", "", ctx)

    assert handled is True
    rendered_table = ctx.console.print.call_args.args[0]
    assert rendered_table.title == "会话历史"


def test_resume_command_prints_chinese_usage_when_missing_args(monkeypatch):
    ctx, _, _ = _make_context("zh-CN")
    sessions = [
        SessionMeta(
            session_id="abc12345",
            title="示例会话",
            cwd="D:/repo",
            model="test-model",
            created_at="2026-04-03T00:00:00+00:00",
            updated_at="2026-04-03T00:00:01+00:00",
            message_count=3,
        )
    ]

    monkeypatch.setattr("core.session.SessionStore.list_sessions", lambda cwd: sessions)

    handled = handle_command("resume", "", ctx)

    assert handled is True
    rendered = "\n".join(str(call.args[0]) for call in ctx.console.print.call_args_list)
    assert "用法：/resume <编号> 或 /resume <session-id>" in rendered


def test_clear_command_prints_chinese_confirmation():
    ctx, _, _ = _make_context("zh-CN")
    ctx.new_session_store = lambda: SimpleNamespace(persist_metadata=lambda: None)

    handled = handle_command("clear", "", ctx)

    assert handled is True
    rendered = "\n".join(str(call.args[0]) for call in ctx.console.print.call_args_list)
    assert "对话已清空，已开始新会话" in rendered


def test_memory_command_prints_chinese_empty_message_when_index_missing(monkeypatch):
    ctx, _, _ = _make_context("zh-CN")
    ctx.memory_dir = MagicMock()

    monkeypatch.setattr("core.memory.load_memory_index", lambda _: "")

    handled = handle_command("memory", "", ctx)

    assert handled is True
    rendered = "\n".join(str(call.args[0]) for call in ctx.console.print.call_args_list)
    assert "还没有记忆" in rendered


def test_remember_command_prints_chinese_usage_when_text_missing():
    ctx, _, _ = _make_context("zh-CN")
    ctx.memory_dir = MagicMock()

    handled = handle_command("remember", "", ctx)

    assert handled is True
    rendered = "\n".join(str(call.args[0]) for call in ctx.console.print.call_args_list)
    assert "用法：/remember <text>" in rendered


def test_dream_command_prints_chinese_unavailable_message():
    ctx, _, _ = _make_context("zh-CN")
    ctx.run_dream = None

    handled = handle_command("dream", "", ctx)

    assert handled is True
    rendered = "\n".join(str(call.args[0]) for call in ctx.console.print.call_args_list)
    assert "Dream 功能当前不可用" in rendered


def test_skills_command_prints_chinese_title_when_locale_is_zh(monkeypatch):
    ctx, _, _ = _make_context("zh-CN")
    skills = [SimpleNamespace(name="review", source="repo", description="审查代码", argument_hint=None)]

    monkeypatch.setattr("core.skills.list_skills", lambda user_invocable_only=True: skills)

    handled = handle_command("skills", "", ctx)

    assert handled is True
    rendered_table = ctx.console.print.call_args.args[0]
    assert rendered_table.title == "可用技能"


def test_compact_command_prints_chinese_too_few_message():
    ctx, _, _ = _make_context("zh-CN")
    ctx.engine.get_messages.return_value = [{"role": "user"}] * 3

    handled = handle_command("compact", "", ctx)

    assert handled is True
    rendered = "\n".join(str(call.args[0]) for call in ctx.console.print.call_args_list)
    assert "消息太少，无法压缩" in rendered


def test_cost_command_prints_chinese_unavailable_message():
    ctx, _, _ = _make_context("zh-CN")
    ctx.cost_tracker = None

    handled = handle_command("cost", "", ctx)

    assert handled is True
    rendered = "\n".join(str(call.args[0]) for call in ctx.console.print.call_args_list)
    assert "成本跟踪当前不可用" in rendered


def test_skill_command_prints_chinese_no_prompt_message(monkeypatch):
    ctx, _, _ = _make_context("zh-CN")
    skill = SimpleNamespace(name="review", get_prompt=lambda args: "", context="inline")

    monkeypatch.setattr("core.skills.get_skill", lambda name: skill)

    handled = handle_command("review", "", ctx)

    assert handled is True
    rendered = "\n".join(str(call.args[0]) for call in ctx.console.print.call_args_list)
    assert "没有生成可执行提示" in rendered


def test_skill_command_prints_chinese_running_message(monkeypatch):
    ctx, _, _ = _make_context("zh-CN")
    ctx.permissions = MagicMock()
    skill = SimpleNamespace(name="review", get_prompt=lambda args: "prompt", context="inline")

    monkeypatch.setattr("core.skills.get_skill", lambda name: skill)
    monkeypatch.setattr("core.main.run_query", lambda *args, **kwargs: None)

    handled = handle_command("review", "", ctx)

    assert handled is True
    rendered = "\n".join(str(call.args[0]) for call in ctx.console.print.call_args_list)
    assert "正在运行技能：/review" in rendered


def test_model_command_prints_chinese_current_model_for_openai_provider():
    ctx, _, _ = _make_context("zh-CN")
    ctx.app_config = SimpleNamespace(provider="openai", model="test-model")
    ctx.engine.get_model.return_value = "gpt-4.1-mini"

    handled = handle_command("model", "", ctx)

    assert handled is True
    rendered = "\n".join(str(call.args[0]) for call in ctx.console.print.call_args_list)
    assert "当前模型" in rendered
    assert "使用 /model <name> 可切换模型" in rendered


def test_model_command_prints_chinese_set_confirmation_when_argument_given():
    ctx, _, _ = _make_context("zh-CN")
    ctx.app_config = SimpleNamespace(provider="openai", model="test-model")
    ctx.engine.get_model.return_value = "gpt-4.1-mini"

    handled = handle_command("model", "gpt-4.1-mini", ctx)

    assert handled is True
    rendered = "\n".join(str(call.args[0]) for call in ctx.console.print.call_args_list)
    assert "已切换模型为" in rendered


def test_model_command_prints_chinese_kept_message_when_picker_cancelled(monkeypatch):
    ctx, _, _ = _make_context("zh-CN")
    ctx.app_config = SimpleNamespace(provider="anthropic", model="test-model")
    ctx.engine.get_model.return_value = "claude-sonnet-4"

    class _FakeApplication:
        def __init__(self, *args, **kwargs):
            pass

        def run(self):
            return None

    monkeypatch.setattr("prompt_toolkit.Application", _FakeApplication)

    handled = handle_command("model", "", ctx)

    assert handled is True
    rendered = "\n".join(str(call.args[0]) for call in ctx.console.print.call_args_list)
    assert "保留当前模型" in rendered


def test_model_picker_tokens_are_localized_when_locale_is_zh(monkeypatch):
    ctx, _, _ = _make_context("zh-CN")
    ctx.app_config = SimpleNamespace(provider="anthropic", model="test-model")
    ctx.engine.get_model.return_value = "claude-sonnet-4"

    class _FakeFormattedTextControl:
        last_text = None

        def __init__(self, text):
            _FakeFormattedTextControl.last_text = text

    class _FakeWindow:
        def __init__(self, content):
            self.content = content

    class _FakeLayout:
        def __init__(self, container):
            self.container = container

    class _FakeApplication:
        def __init__(self, *args, **kwargs):
            pass

        def run(self):
            return None

    monkeypatch.setattr("prompt_toolkit.Application", _FakeApplication)
    monkeypatch.setattr("prompt_toolkit.layout.Layout", _FakeLayout)
    monkeypatch.setattr("prompt_toolkit.layout.containers.Window", _FakeWindow)
    monkeypatch.setattr("prompt_toolkit.layout.controls.FormattedTextControl", _FakeFormattedTextControl)

    handled = handle_command("model", "", ctx)

    assert handled is True
    rendered = "".join(fragment for _, fragment in _FakeFormattedTextControl.last_text())
    assert "选择模型" in rendered
    assert "投入度" in rendered
    assert "确认" in rendered
