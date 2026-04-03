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
