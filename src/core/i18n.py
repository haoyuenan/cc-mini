from __future__ import annotations

DEFAULT_LOCALE = "en"

_LOCALE_ALIASES: dict[str, str] = {
    "en": "en",
    "english": "en",
    "zh": "zh-CN",
    "zh-cn": "zh-CN",
    "cn": "zh-CN",
    "chinese": "zh-CN",
    "中文": "zh-CN",
    "简体中文": "zh-CN",
}

_MESSAGES: dict[str, dict[str, str]] = {
    "en": {
        "buddy.help.title": "[bold]Buddy — AI Companion Pet[/bold]",
        "buddy.help.text": "[bold]Commands[/bold]\n\n  [cyan]/buddy[/cyan]              Hatch your first companion, or show its card\n  [cyan]/buddy help[/cyan]          Show this help\n  [cyan]/buddy pet[/cyan]           Pet your companion (heart animation, boosts happy)\n  [cyan]/buddy stats[/cyan]         Show companion card with stats and mood\n  [cyan]/buddy mood[/cyan]          Show current mood details\n  [cyan]/buddy new[/cyan]           Hatch an additional random companion\n  [cyan]/buddy list[/cyan]          View all companions in your collection\n  [cyan]/buddy select N[/cyan]      Switch active companion to #N\n  [cyan]/buddy mute[/cyan]          Mute companion speech bubbles\n  [cyan]/buddy unmute[/cyan]        Unmute companion speech bubbles\n  [cyan]/buddy ia[/cyan]            Start the Poke Game adventure\n\n[bold]Gameplay Guide[/bold]\n\n  [yellow]Hatching[/yellow]  Your first companion is determined by your username.\n            Use [cyan]/buddy new[/cyan] to hatch more with random seeds.\n            18 species, 5 rarities (Common to Legendary), 1% shiny chance.\n\n  [yellow]Stats[/yellow]    Each companion has 5 permanent stats (0-100):\n            DEBUGGING, PATIENCE, CHAOS, WISDOM, SNARK.\n            These shape how your companion talks and reacts.\n\n  [yellow]Mood[/yellow]     6 dynamic mood dimensions that change over time:\n            Happy, Bored, Excited, Tired, Grumpy, Curious.\n            Mood is affected by your coding activity:\n            - Task success / bug fixes  ->  happy, excited\n            - Errors / failures         ->  grumpy, tired\n            - Reading / exploring code  ->  curious\n            - Petting ([cyan]/buddy pet[/cyan])     ->  happy, excited\n            - Long idle time            ->  bored\n            Mood gradually decays back to neutral over time.\n\n  [yellow]Talking[/yellow]  Your companion reacts after each Claude response.\n            Address it by name to chat directly (20-turn memory).\n            Its tone adapts to both stats and current mood.\n\n  [yellow]Pikachu[/yellow]  Set CC_MINI_BUDDY_SEED=pikachu-3361 before hatching\n            to unlock the secret Legendary Pikachu species.",
        "buddy.no_companion": "No companion yet. Type /buddy to hatch one!",
        "buddy.muted": "Companion reactions muted.",
        "buddy.unmuted": "Companion reactions unmuted.",
        "commands.desc.buddy": "Companion pet — hatch, pet, stats, mute/unmute, ia",
        "commands.desc.buddy_ia": "Idle Adventure — roguelike world exploration game",
        "commands.desc.buddy_list": "View all companions",
        "commands.desc.buddy_mute": "Mute companion reactions",
        "commands.desc.buddy_new": "Hatch a new random companion",
        "commands.desc.buddy_pet": "Pet your companion",
        "commands.desc.buddy_select": "Switch active companion (e.g. /buddy select 2)",
        "commands.desc.buddy_stats": "Show companion stats",
        "commands.desc.buddy_unmute": "Unmute companion reactions",
        "commands.desc.clear": "Clear conversation, start new session",
        "commands.desc.compact": "Compress conversation context [instructions]",
        "commands.desc.cost": "Show token usage and cost summary",
        "commands.desc.exit": "Exit the REPL",
        "commands.desc.help": "Show available commands",
        "commands.desc.history": "List saved sessions for this directory",
        "commands.desc.language": "Switch interface language [locale]",
        "commands.desc.memory": "Show current memory index",
        "commands.desc.model": "Show or switch model [model-name]",
        "commands.desc.remember": "Save a note to the daily log [text]",
        "commands.desc.resume": "Resume a past session [number|session-id]",
        "commands.desc.skills": "List all available skills",
        "commands.desc.dream": "Consolidate daily logs into topic files",
        "commands.help.column_command": "Command",
        "commands.help.column_description": "Description",
        "commands.help.title": "Available Commands",
        "commands.language.current": "Current interface language: {locale_code}\nSupported: {supported}",
        "commands.language.updated": "Interface language switched to {name} ({locale_code}).",
        "commands.language.unsupported": "Unsupported interface language: {input}. Supported: {supported}",
        "commands.unknown": "Unknown command: /{name}  (try /help or /skills)",
        "repl.bottom.chat_hint": "─ Enter send · Alt+Enter newline · ! shell · / commands ",
        "repl.bottom.terminal_hint": "─ TERMINAL MODE · ! to exit · Enter run ",
        "repl.goodbye": "Goodbye.",
        "repl.press_ctrlc_again": "Press Ctrl+C again to exit",
        "repl.spinner.preparing_tool": "Preparing tool call…",
        "repl.spinner.thinking": "Thinking…",
        "repl.turn_cancelled": "⏹ Turn cancelled",
        "repl.turn_cancelled_esc": "⏹ Turn cancelled (Esc)",
    },
    "zh-CN": {
        "buddy.help.title": "[bold]伙伴——AI 伙伴宠物[/bold]",
        "buddy.help.text": "[bold]命令[/bold]\n\n  [cyan]/buddy[/cyan]              孵化你的第一个伙伴，或显示它的卡片\n  [cyan]/buddy help[/cyan]         显示本帮助\n  [cyan]/buddy pet[/cyan]          摸摸你的伙伴（爱心动画，提升开心）\n  [cyan]/buddy stats[/cyan]        显示伙伴卡片、属性和心情\n  [cyan]/buddy mood[/cyan]         显示当前心情详情\n  [cyan]/buddy new[/cyan]          孵化一个额外的随机伙伴\n  [cyan]/buddy list[/cyan]         查看你收集的所有伙伴\n  [cyan]/buddy select N[/cyan]     切换当前伙伴到第 N 个\n  [cyan]/buddy mute[/cyan]         静音伙伴气泡反应\n  [cyan]/buddy unmute[/cyan]       取消静音伙伴气泡反应\n  [cyan]/buddy ia[/cyan]           开始 Poke Game 冒险\n\n[bold]玩法指南[/bold]\n\n  [yellow]孵化[/yellow]  你的第一个伙伴由用户名决定。\n            使用 [cyan]/buddy new[/cyan] 可用随机种子继续孵化。\n            共有 18 个物种、5 种稀有度（普通到传说），闪光概率 1%。\n\n  [yellow]属性[/yellow]  每个伙伴有 5 个永久属性（0-100）：\n            DEBUGGING、PATIENCE、CHAOS、WISDOM、SNARK。\n            这些属性会影响它说话和反应的方式。\n\n  [yellow]心情[/yellow]  有 6 个会随时间变化的动态维度：\n            Happy、Bored、Excited、Tired、Grumpy、Curious。\n            你的编码行为会影响心情：\n            - 完成任务 / 修复 bug      ->  happy, excited\n            - 错误 / 失败              ->  grumpy, tired\n            - 阅读 / 探索代码          ->  curious\n            - 抚摸（[cyan]/buddy pet[/cyan]） ->  happy, excited\n            - 长时间空闲              ->  bored\n            心情会随着时间逐渐回到中性。\n\n  [yellow]交流[/yellow]  你的伙伴会在每次 Claude 回复后作出反应。\n            直接叫它名字可以和它聊天（保留 20 轮记忆）。\n            它的语气会同时受属性和当前心情影响。\n\n  [yellow]皮卡丘[/yellow]  在孵化前设置 CC_MINI_BUDDY_SEED=pikachu-3361\n            即可解锁隐藏的传说皮卡丘物种。",
        "buddy.no_companion": "还没有伙伴。输入 /buddy 来孵化一个吧！",
        "buddy.muted": "伙伴反应已静音。",
        "buddy.unmuted": "伙伴反应已取消静音。",
        "commands.desc.buddy": "伙伴宠物——孵化、抚摸、状态、静音/取消静音、冒险",
        "commands.desc.buddy_ia": "闲置冒险——轻度肉鸽世界探索游戏",
        "commands.desc.buddy_list": "查看所有伙伴",
        "commands.desc.buddy_mute": "静音伙伴反应",
        "commands.desc.buddy_new": "孵化新的随机伙伴",
        "commands.desc.buddy_pet": "摸摸你的伙伴",
        "commands.desc.buddy_select": "切换当前伙伴（例如 /buddy select 2）",
        "commands.desc.buddy_stats": "显示伙伴状态",
        "commands.desc.buddy_unmute": "取消静音伙伴反应",
        "commands.desc.clear": "清空对话并开始新会话",
        "commands.desc.compact": "压缩对话上下文 [instructions]",
        "commands.desc.cost": "显示 token 用量和成本摘要",
        "commands.desc.exit": "退出 REPL",
        "commands.desc.help": "显示可用命令",
        "commands.desc.history": "列出当前目录的已保存会话",
        "commands.desc.language": "切换界面语言 [locale]",
        "commands.desc.memory": "显示当前记忆索引",
        "commands.desc.model": "显示或切换模型 [model-name]",
        "commands.desc.remember": "保存一条笔记到每日日志 [text]",
        "commands.desc.resume": "恢复过去的会话 [number|session-id]",
        "commands.desc.skills": "列出所有可用技能",
        "commands.desc.dream": "把每日日志整合成主题文件",
        "commands.help.column_command": "命令",
        "commands.help.column_description": "说明",
        "commands.help.title": "可用命令",
        "commands.language.current": "当前界面语言：{locale_code}\n支持：{supported}",
        "commands.language.updated": "界面语言已切换为 {name}（{locale_code}）。",
        "commands.language.unsupported": "不支持的界面语言：{input}。支持：{supported}",
        "commands.unknown": "未知命令：/{name}（试试 /help 或 /skills）",
        "repl.bottom.chat_hint": "─ 回车发送 · Alt+Enter 换行 · ! shell · / 命令 ",
        "repl.bottom.terminal_hint": "─ 终端模式 · ! 退出 · 回车运行 ",
        "repl.goodbye": "再见。",
        "repl.press_ctrlc_again": "再次按 Ctrl+C 退出",
        "repl.spinner.preparing_tool": "准备调用工具…",
        "repl.spinner.thinking": "思考中…",
        "repl.turn_cancelled": "⏹ 已取消本轮",
        "repl.turn_cancelled_esc": "⏹ 已取消本轮（Esc）",
    },
}

_LOCALE_LABELS: dict[str, dict[str, str]] = {
    "en": {
        "en": "English",
        "zh-CN": "Chinese",
    },
    "zh-CN": {
        "en": "English",
        "zh-CN": "中文",
    },
}


def normalize_locale(value: str | None) -> str | None:
    if value is None:
        return None
    normalized = value.strip().lower()
    if not normalized:
        return None
    return _LOCALE_ALIASES.get(normalized)



def available_locales() -> list[str]:
    return list(_MESSAGES.keys())



def is_supported_locale(value: str | None) -> bool:
    normalized = normalize_locale(value)
    return normalized in _MESSAGES if normalized else False


def locale_label(locale: str, display_locale: str | None = None) -> str:
    normalized = normalize_locale(locale) or DEFAULT_LOCALE
    display = normalize_locale(display_locale) or DEFAULT_LOCALE
    labels = _LOCALE_LABELS.get(display, _LOCALE_LABELS[DEFAULT_LOCALE])
    return labels.get(normalized, normalized)


def command_description(name: str, locale: str, fallback: str) -> str:
    key = f"commands.desc.{name.replace(' ', '_')}"
    try:
        return t(locale, key)
    except KeyError:
        return fallback


def t(locale: str, key: str, **kwargs) -> str:
    normalized = normalize_locale(locale) or DEFAULT_LOCALE
    messages = _MESSAGES.get(normalized, _MESSAGES[DEFAULT_LOCALE])
    template = messages.get(key)
    if template is None:
        template = _MESSAGES[DEFAULT_LOCALE].get(key)
    if template is None:
        raise KeyError(key)
    return template.format(**kwargs)
