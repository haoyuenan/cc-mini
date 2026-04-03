from types import SimpleNamespace
from unittest.mock import MagicMock

from core.commands import CommandContext, handle_command
from core.i18n import t


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
