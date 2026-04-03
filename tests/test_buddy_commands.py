from unittest.mock import MagicMock, patch


@patch("core.buddy.commands.get_companion", return_value=None)
def test_buddy_pet_without_companion_is_localized_to_chinese(_mock_get_companion):
    from core.buddy.commands import handle_buddy_command

    console = MagicMock()
    client = MagicMock()

    handle_buddy_command("pet", client, console, "test-model", locale="zh-CN")

    rendered = "\n".join(str(call.args[0]) for call in console.print.call_args_list)
    assert "还没有伙伴" in rendered


@patch("core.buddy.commands.save_companion_muted")
def test_buddy_mute_message_is_localized_to_chinese(_mock_save_muted):
    from core.buddy.commands import handle_buddy_command

    console = MagicMock()
    client = MagicMock()

    handle_buddy_command("mute", client, console, "test-model", locale="zh-CN")

    rendered = "\n".join(str(call.args[0]) for call in console.print.call_args_list)
    assert "伙伴反应已静音" in rendered


def test_buddy_help_title_is_localized_to_chinese():
    from core.buddy.commands import handle_buddy_command

    console = MagicMock()
    client = MagicMock()

    handle_buddy_command("help", client, console, "test-model", locale="zh-CN")

    panel = console.print.call_args.args[0]
    assert "伙伴宠物" in str(panel.title)


def test_buddy_hatch_messages_are_localized_to_chinese():
    from core.buddy.commands import _buddy_hatch_start_message, _buddy_hatch_failed_message

    assert "正在孵化你的伙伴" in _buddy_hatch_start_message(False, "zh-CN")
    assert "正在孵化一个新伙伴" in _buddy_hatch_start_message(True, "zh-CN")
    assert "生成伙伴灵魂失败：boom" in _buddy_hatch_failed_message("boom", "zh-CN")


def test_buddy_select_messages_are_localized_to_chinese():
    from core.buddy.commands import (
        _buddy_select_usage_message,
        _buddy_select_invalid_number_message,
        _buddy_select_switched_message,
        _buddy_usage_message,
    )

    assert "用法：/buddy select <number>" in _buddy_select_usage_message("zh-CN")
    assert "无效编号" in _buddy_select_invalid_number_message(3, "zh-CN")
    assert "已切换到 #2：团子（Cat）" in _buddy_select_switched_message(2, "团子", "Cat", "zh-CN")
    assert "用法：/buddy [help|pet|stats|mood|new|list|select N|mute|unmute|ia]" in _buddy_usage_message("zh-CN")


def test_buddy_pet_and_mood_messages_are_localized_to_chinese():
    from core.buddy.commands import (
        _buddy_pet_reaction_message,
        _buddy_mood_title,
        _buddy_mood_level_label,
        _buddy_dominant_mood_message,
    )

    assert "开心地扭了扭" in _buddy_pet_reaction_message("团子", "zh-CN")
    assert "团子的心情" in _buddy_mood_title("团子", "zh-CN")
    assert _buddy_mood_level_label("neutral", "zh-CN") == "平稳"
    assert _buddy_mood_level_label("high", "zh-CN") == "偏高"
    assert _buddy_mood_level_label("low", "zh-CN") == "偏低"
    assert "主导心情：curious" in _buddy_dominant_mood_message("curious", "zh-CN")


def test_buddy_render_messages_are_localized_to_chinese():
    from core.buddy.render import (
        _buddy_card_title,
        _buddy_card_identity_line,
        _buddy_card_mood_heading,
        _buddy_card_feeling_line,
        _buddy_card_hatched_line,
        _buddy_compact_status_line,
    )

    assert "伙伴" in _buddy_card_title("zh-CN")
    assert "团子（Cat）" in _buddy_card_identity_line("团子", "Cat", True, "zh-CN")
    assert "心情：" in _buddy_card_mood_heading("zh-CN")
    assert "当前感觉：curious" in _buddy_card_feeling_line("curious", "zh-CN")
    assert "孵化日期：2026-04-03" in _buddy_card_hatched_line("2026-04-03", "zh-CN")
    assert "团子（Cat）" in _buddy_compact_status_line(":)", "团子", "Cat", "curious", True, "zh-CN")


def test_buddy_list_messages_are_localized_to_chinese():
    from core.buddy.render import (
        _buddy_list_empty_message,
        _buddy_list_column_face,
        _buddy_list_title,
        _buddy_list_column_name,
        _buddy_list_column_species,
        _buddy_list_column_rarity,
        _buddy_list_column_shiny,
    )

    assert "还没有伙伴" in _buddy_list_empty_message("zh-CN")
    assert "伙伴收藏" in _buddy_list_title("zh-CN")
    assert _buddy_list_column_name("zh-CN") == "名称"
    assert _buddy_list_column_species("zh-CN") == "物种"
    assert _buddy_list_column_rarity("zh-CN") == "稀有度"
    assert _buddy_list_column_face("zh-CN") == "形象"
    assert _buddy_list_column_shiny("zh-CN") == "闪光"


def test_buddy_rarity_and_hatch_reveal_messages_are_localized_to_chinese():
    from core.buddy.render import _buddy_rarity_label, _buddy_hatch_reveal_line

    assert _buddy_rarity_label("legendary", "zh-CN") == "传说"
    assert _buddy_rarity_label("common", "zh-CN") == "普通"
    assert "团子 已孵化！" in _buddy_hatch_reveal_line("团子", "★★", True, "zh-CN")
