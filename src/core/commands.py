"""Slash command system — parsing and dispatch.

Modelled after claude-code's ``src/commands.ts``.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING

from rich.console import Console
from rich.table import Table

from .coordinator import current_session_mode, match_session_mode
from .i18n import DEFAULT_LOCALE, available_locales, command_description, locale_label, normalize_locale, t

if TYPE_CHECKING:
    from .compact import CompactService
    from .config import AppConfig
    from .cost_tracker import CostTracker
    from .engine import Engine
    from .permissions import PermissionChecker
    from .session import SessionStore


# ---------------------------------------------------------------------------
# Context bundle passed to every command handler
# ---------------------------------------------------------------------------

@dataclass
class CommandContext:
    engine: Engine
    session_store: SessionStore | None
    compact_service: CompactService
    console: Console
    app_config: AppConfig
    locale: str = DEFAULT_LOCALE
    memory_dir: Path | None = None
    permissions: PermissionChecker | None = None
    run_dream: object = None
    cost_tracker: CostTracker | None = None
    new_session_store: object = None
    reconfigure_mode: object = None
    translate: object = None
    set_locale: object = None


# ---------------------------------------------------------------------------
# Parsing
# ---------------------------------------------------------------------------

def parse_command(text: str) -> tuple[str, str] | None:
    """If *text* starts with ``/``, return ``(command_name, args)``."""
    text = text.strip()
    if not text.startswith("/"):
        return None
    parts = text.split(None, 1)
    name = parts[0][1:].lower()  # strip leading /
    args = parts[1] if len(parts) > 1 else ""
    return name, args


# ---------------------------------------------------------------------------
# Handlers
# ---------------------------------------------------------------------------

def _tr(ctx: CommandContext, key: str, **kwargs) -> str:
    if callable(ctx.translate):
        return ctx.translate(key, **kwargs)  # type: ignore[misc]
    return t(ctx.locale, key, **kwargs)

def _cmd_help(ctx: CommandContext, args: str) -> None:
    table = Table(title=_tr(ctx, "commands.help.title"), show_header=True, header_style="bold cyan")
    table.add_column(_tr(ctx, "commands.help.column_command"), style="green")
    table.add_column(_tr(ctx, "commands.help.column_description"))
    for name, desc, _ in _COMMAND_TABLE:
        table.add_row(f"/{name}", command_description(name, ctx.locale, desc))
    ctx.console.print(table)


def _cmd_compact(ctx: CommandContext, args: str) -> None:
    from .compact import estimate_tokens

    messages = ctx.engine.get_messages()
    if len(messages) < 4:
        ctx.console.print(f"[dim]{_tr(ctx, 'commands.compact.too_few')}[/dim]")
        return

    pre_tokens = estimate_tokens(messages)
    ctx.console.print(
        f"[dim]{_tr(ctx, 'commands.compact.running', message_count=len(messages), pre_tokens=f'{pre_tokens:,}')}[/dim]"
    )

    new_msgs, summary = ctx.compact_service.compact(
        messages, ctx.engine.get_system_prompt(), custom_instructions=args,
    )
    ctx.engine.set_messages(new_msgs)

    # Persist compacted state to a fresh session store if available
    if ctx.session_store is not None:
        _persist_compacted(ctx, new_msgs)

    post_tokens = estimate_tokens(new_msgs)
    ctx.console.print(
        f"[green]✓[/green] "
        f"{_tr(ctx, 'commands.compact.done', pre_tokens=f'{pre_tokens:,}', post_tokens=f'{post_tokens:,}', before_count=len(messages), after_count=len(new_msgs))}"
    )


def _persist_compacted(ctx: CommandContext, new_msgs: list[dict]) -> None:
    """Re-write the current session with compacted messages."""
    if ctx.session_store is None:
        return
    # Create a new session store pointing to the same session id,
    # overwrite the JSONL with the compacted messages.
    import json
    from .session import _serialize_message, _now_iso
    path = ctx.session_store._jsonl_path
    with open(path, "w", encoding="utf-8") as fh:
        for msg in new_msgs:
            safe = _serialize_message(msg)
            safe["_ts"] = _now_iso()
            fh.write(json.dumps(safe, ensure_ascii=False) + "\n")
    ctx.session_store._message_count = len(new_msgs)
    ctx.session_store._save_meta()


def _cmd_history(ctx: CommandContext, args: str) -> None:
    from .session import SessionStore

    cwd = str(os.getcwd())
    sessions = SessionStore.list_sessions(cwd)
    if not sessions:
        ctx.console.print(f"[dim]{_tr(ctx, 'commands.history.empty')}[/dim]")
        return

    table = Table(title=_tr(ctx, "commands.history.title"), show_header=True, header_style="bold cyan")
    table.add_column(_tr(ctx, "commands.history.column_index"), style="dim", width=4)
    table.add_column(_tr(ctx, "commands.history.column_id"), style="dim", width=10)
    table.add_column(_tr(ctx, "commands.history.column_title"))
    table.add_column(_tr(ctx, "commands.history.column_messages"), justify="right", width=8)
    table.add_column(_tr(ctx, "commands.history.column_updated"), width=20)

    for i, meta in enumerate(sessions, 1):
        table.add_row(
            str(i),
            meta.session_id[:8],
            meta.title[:50],
            str(meta.message_count),
            meta.updated_at[:19].replace("T", " "),
        )
    ctx.console.print(table)


def _cmd_resume(ctx: CommandContext, args: str) -> None:
    from .session import SessionStore

    cwd = str(os.getcwd())
    sessions = SessionStore.list_sessions(cwd)

    if not sessions:
        ctx.console.print(f"[dim]{_tr(ctx, 'commands.resume.empty')}[/dim]")
        return

    if not args:
        # Show list and ask user to pick
        _cmd_history(ctx, "")
        ctx.console.print(f"\n[dim]{_tr(ctx, 'commands.resume.usage')}[/dim]")
        return

    # Try as numeric index
    target_meta = None
    try:
        idx = int(args.strip()) - 1
        if 0 <= idx < len(sessions):
            target_meta = sessions[idx]
    except ValueError:
        pass

    # Try as session-id prefix
    if target_meta is None:
        needle = args.strip().lower()
        for meta in sessions:
            if meta.session_id.lower().startswith(needle):
                target_meta = meta
                break

    if target_meta is None:
        ctx.console.print(f"[red]{_tr(ctx, 'commands.resume.not_found', value=args)}[/red]")
        return

    # Skip if resuming the current session
    if ctx.session_store and target_meta.session_id == ctx.session_store.session_id:
        ctx.console.print(f"[dim]{_tr(ctx, 'commands.resume.already_current')}[/dim]")
        return

    # Load messages
    meta, messages = SessionStore.load_session(target_meta.session_id, cwd)
    if not messages:
        ctx.console.print(f"[red]{_tr(ctx, 'commands.resume.no_messages')}[/red]")
        return

    restored_locale = meta.locale if meta is not None and meta.locale else DEFAULT_LOCALE
    if callable(ctx.set_locale):
        ctx.set_locale(restored_locale)  # type: ignore[misc]
    ctx.locale = restored_locale

    warning = None
    session_mode = meta.mode if meta is not None else None
    if callable(ctx.reconfigure_mode):
        warning = ctx.reconfigure_mode(session_mode)
    else:
        warning = match_session_mode(session_mode)

    # Create new session store pointing to the resumed session
    new_store = ctx.new_session_store  # type: ignore[call-arg]
    resumed_store = type(ctx.session_store)(  # type: ignore[arg-type]
        cwd=cwd,
        model=ctx.app_config.model,
        session_id=target_meta.session_id,
        mode=current_session_mode(),
        locale=restored_locale,
    ) if ctx.session_store else None

    ctx.engine.set_messages(messages)
    if resumed_store is not None:
        ctx.engine.set_session_store(resumed_store)
        ctx.session_store = resumed_store  # type: ignore[assignment]

    ctx.console.print(
        f"[green]✓[/green] "
        f"{_tr(ctx, 'commands.resume.success', session_id=target_meta.session_id[:8], title=target_meta.title[:50], message_count=len(messages))}"
    )
    if warning:
        ctx.console.print(f"[yellow]{warning}[/yellow]")


def _cmd_clear(ctx: CommandContext, args: str) -> None:
    confirmation = t(ctx.locale or DEFAULT_LOCALE, "commands.clear.done")
    ctx.engine.set_messages([])
    if callable(ctx.set_locale):
        ctx.set_locale(DEFAULT_LOCALE)  # type: ignore[misc]
    ctx.locale = DEFAULT_LOCALE
    if callable(ctx.new_session_store):
        new_store = ctx.new_session_store()
        ctx.engine.set_session_store(new_store)
        ctx.session_store = new_store  # type: ignore[assignment]
        if hasattr(new_store, "persist_metadata"):
            new_store.persist_metadata()
    ctx.console.print(f"[green]✓[/green] {confirmation}")


def _cmd_language(ctx: CommandContext, args: str) -> None:
    current_locale = ctx.locale or DEFAULT_LOCALE
    supported = ", ".join(available_locales())

    if not args.strip():
        ctx.console.print(
            _tr(
                ctx,
                "commands.language.current",
                locale_code=current_locale,
                supported=supported,
            )
        )
        return

    requested = normalize_locale(args.strip())
    if requested is None:
        ctx.console.print(
            _tr(
                ctx,
                "commands.language.unsupported",
                input=args.strip(),
                supported=supported,
            )
        )
        return

    if callable(ctx.set_locale):
        ctx.set_locale(requested)  # type: ignore[misc]
    ctx.locale = requested
    if ctx.session_store is not None:
        ctx.session_store.locale = requested
        if hasattr(ctx.session_store, "persist_metadata"):
            ctx.session_store.persist_metadata()

    ctx.console.print(
        _tr(
            ctx,
            "commands.language.updated",
            locale_code=requested,
            name=locale_label(requested, display_locale=requested),
        )
    )


def _cmd_memory(ctx: CommandContext, args: str) -> None:
    from .memory import load_memory_index

    if ctx.memory_dir is None:
        ctx.console.print(f"[dim]{_tr(ctx, 'commands.memory.not_configured')}[/dim]")
        return
    index = load_memory_index(ctx.memory_dir)
    if index:
        ctx.console.print(index)
    else:
        ctx.console.print(f"[dim]{_tr(ctx, 'commands.memory.empty')}[/dim]")


def _cmd_remember(ctx: CommandContext, args: str) -> None:
    from .memory import append_to_daily_log

    if ctx.memory_dir is None:
        ctx.console.print(f"[dim]{_tr(ctx, 'commands.memory.not_configured')}[/dim]")
        return
    if not args.strip():
        ctx.console.print(f"[dim]{_tr(ctx, 'commands.remember.usage')}[/dim]")
        return
    append_to_daily_log(ctx.memory_dir, args.strip())
    ctx.console.print(f"[dim]{_tr(ctx, 'commands.remember.saved')}[/dim]")


def _cmd_dream(ctx: CommandContext, args: str) -> None:
    if ctx.run_dream is None or not callable(ctx.run_dream):
        ctx.console.print(f"[dim]{_tr(ctx, 'commands.dream.unavailable')}[/dim]")
        return
    ctx.run_dream()


def _cmd_skills(ctx: CommandContext, args: str) -> None:
    """List all available skills."""
    from .skills import list_skills

    skills = list_skills(user_invocable_only=True)
    if not skills:
        ctx.console.print(f"[dim]{_tr(ctx, 'commands.skills.empty')}[/dim]")
        return

    table = Table(title=_tr(ctx, "commands.skills.title"), show_header=True, header_style="bold cyan")
    table.add_column(_tr(ctx, "commands.skills.column_command"), style="green")
    table.add_column(_tr(ctx, "commands.skills.column_source"), style="dim", width=8)
    table.add_column(_tr(ctx, "commands.skills.column_description"))
    for s in skills:
        hint = f" [{s.argument_hint}]" if s.argument_hint else ""
        table.add_row(f"/{s.name}{hint}", s.source, s.description)
    ctx.console.print(table)
def _cmd_cost(ctx: CommandContext, args: str) -> None:
    if ctx.cost_tracker is None:
        ctx.console.print(f"[dim]{_tr(ctx, 'commands.cost.unavailable')}[/dim]")
        return
    ctx.console.print(ctx.cost_tracker.format_cost())


def _cmd_model(ctx: CommandContext, args: str) -> None:
    from .config import resolve_model, default_max_tokens_for_model, DEFAULT_MODEL

    provider = ctx.app_config.provider

    if args:
        ctx.engine.set_model(args.strip())
        actual = ctx.engine.get_model()
        ctx.console.print(
            f"[green]✓[/green] "
            f"{_tr(ctx, 'commands.model.set', actual=actual, max_tokens=default_max_tokens_for_model(actual, provider=provider))}")
        return

    if provider != "anthropic":
        current = ctx.engine.get_model()
        ctx.console.print(
            f"[dim]{_tr(ctx, 'commands.model.current', current=current)}[/dim]\n"
            f"[dim]{_tr(ctx, 'commands.model.usage', provider=provider)}[/dim]"
        )
        return

    from prompt_toolkit import Application
    from prompt_toolkit.key_binding import KeyBindings
    from prompt_toolkit.layout import Layout
    from prompt_toolkit.layout.containers import Window
    from prompt_toolkit.layout.controls import FormattedTextControl

    current = ctx.engine.get_model()

    # Marketing name lookup
    _NAMES = {
        "claude-sonnet-4-6": "Sonnet 4.6", "claude-sonnet-4-5": "Sonnet 4.5",
        "claude-sonnet-4": "Sonnet 4", "claude-opus-4-6": "Opus 4.6",
        "claude-opus-4-5": "Opus 4.5", "claude-opus-4-1": "Opus 4.1",
        "claude-opus-4": "Opus 4", "claude-haiku-4-5": "Haiku 4.5",
        "claude-3-5-haiku": "Haiku 3.5",
    }
    display = next((n for p, n in _NAMES.items() if p in current), "Sonnet 4.6")

    # (alias, label, description) — from modelOptions.ts PAYG 1P path
    # 1M context variants omitted: require SDK betas not available in cc-mini
    options = [
        (
            DEFAULT_MODEL,
            _tr(ctx, "commands.model.picker.default_label"),
            _tr(ctx, "commands.model.picker.default_desc", display=display),
        ),
        ("sonnet", "Sonnet", _tr(ctx, "commands.model.picker.sonnet_desc")),
        ("opus", "Opus", _tr(ctx, "commands.model.picker.opus_desc")),
        ("haiku", "Haiku", _tr(ctx, "commands.model.picker.haiku_desc")),
    ]

    effort_levels = ["low", "medium", "high"]
    effort_sym = {"low": "◑", "medium": "◕", "high": "●"}

    cursor = [0]
    for i, (alias, _, _) in enumerate(options):
        if resolve_model(alias) == current:
            cursor[0] = i
            break

    effort_idx = [2]
    result: list[str | None] = [None]
    max_label = max(len(l) for _, l, _ in options)

    kb = KeyBindings()

    @kb.add("up")
    def _(e): cursor.__setitem__(0, (cursor[0] - 1) % len(options))
    @kb.add("down")
    def _(e): cursor.__setitem__(0, (cursor[0] + 1) % len(options))
    @kb.add("left")
    def _(e): effort_idx.__setitem__(0, (effort_idx[0] - 1) % len(effort_levels))
    @kb.add("right")
    def _(e): effort_idx.__setitem__(0, (effort_idx[0] + 1) % len(effort_levels))

    @kb.add("enter")
    def _(e):
        result[0] = options[cursor[0]][0]
        e.app.exit()

    for i in range(min(len(options), 9)):
        @kb.add(str(i + 1))
        def _(e, idx=i):
            cursor[0] = idx
            result[0] = options[idx][0]
            e.app.exit()

    @kb.add("escape")
    @kb.add("c-c")
    def _(e): e.app.exit()

    def _tokens():
        t = [
            ("bold ansibrightcyan", f"  {_tr(ctx, 'commands.model.picker.select')}\n"),
            ("ansigray", f"  {_tr(ctx, 'commands.model.picker.intro').replace(chr(10), chr(10) + '  ')}\n\n"),
        ]
        for i, (alias, label, desc) in enumerate(options):
            is_cur = i == cursor[0]
            is_active = resolve_model(alias) == current
            ptr = "❯" if is_cur else " "
            sty = "ansibrightcyan" if is_cur else ""
            chk = " ✔" if is_active else ""
            t.append((sty, f"  {ptr} {i+1}. {(label + chk).ljust(max_label + 3)}"))
            t.append(("ansigray", desc))
            t.append(("", "\n"))

        eff = effort_levels[effort_idx[0]]
        t.append(("", "\n"))
        t.append(("ansigray", f"  {_tr(ctx, 'commands.model.picker.effort')} "))
        for lvl in effort_levels:
            s = "bold ansibrightcyan" if lvl == eff else "ansigray"
            t.append((s, f" {effort_sym[lvl]} {lvl} "))
        t.append(("", "\n"))
        t.append(("ansigray", f"  {_tr(ctx, 'commands.model.picker.footer')}"))
        return t

    app: Application = Application(
        layout=Layout(Window(FormattedTextControl(_tokens))),
        key_bindings=kb, full_screen=False)

    try:
        app.run()
    except (EOFError, KeyboardInterrupt):
        pass

    if result[0] is None:
        ctx.console.print(f"[dim]{_tr(ctx, 'commands.model.kept', current=current)}[/dim]")
        return

    ctx.engine.set_model(result[0])
    actual = ctx.engine.get_model()
    eff = effort_levels[effort_idx[0]]
    ctx.console.print(
        f"[green]✓[/green] Set model to [bold]{actual}[/bold]  "
        f"(max_tokens={default_max_tokens_for_model(actual, provider=provider)}, effort={eff})"
    )


# ---------------------------------------------------------------------------
# Command registry
# ---------------------------------------------------------------------------

# (name, description, handler)
_COMMAND_TABLE: list[tuple[str, str, object]] = [
    ("help",     "Show available commands",                         _cmd_help),
    ("language", "Switch interface language [locale]",              _cmd_language),
    ("compact",  "Compress conversation context [instructions]",    _cmd_compact),
    ("resume",   "Resume a past session [number|session-id]",       _cmd_resume),
    ("history",  "List saved sessions for this directory",          _cmd_history),
    ("clear",    "Clear conversation, start new session",           _cmd_clear),
    ("memory",   "Show current memory index",                       _cmd_memory),
    ("remember", "Save a note to the daily log [text]",             _cmd_remember),
    ("dream",    "Consolidate daily logs into topic files",          _cmd_dream),
    ("skills",   "List all available skills",                       _cmd_skills),
    ("cost",    "Show token usage and cost summary",               _cmd_cost),
    ("model",   "Show or switch model [model-name]",               _cmd_model),
]

_HANDLERS: dict[str, object] = {name: handler for name, _, handler in _COMMAND_TABLE}


def handle_command(name: str, args: str, ctx: CommandContext) -> bool:
    """Dispatch slash command. Returns True if handled, False otherwise.

    If *name* does not match a built-in command, checks the skill registry
    and executes the skill inline (prompt injection) or forked (isolated turn).
    """
    handler = _HANDLERS.get(name)
    if handler is not None:
        handler(ctx, args)  # type: ignore[operator]
        return True

    # Try as a skill invocation
    from .skills import get_skill
    skill = get_skill(name)
    if skill is not None:
        return _execute_skill(skill, args, ctx)

    ctx.console.print(f"[red]{_tr(ctx, 'commands.unknown', name=name)}[/red]")
    return False


def _execute_skill(skill, args: str, ctx: CommandContext) -> bool:
    """Execute a skill — inline or forked.

    Inline (default): inject the skill prompt as a user message into the
    current conversation and let the engine process it.

    Forked: run the skill in an isolated turn (save messages, clear, run,
    restore original messages).  Matches claude-code's ``context: 'fork'``.
    """
    from .main import run_query

    prompt = skill.get_prompt(args)
    if not prompt:
        ctx.console.print(f"[dim]{_tr(ctx, 'commands.skills.no_prompt', name=skill.name)}[/dim]")
        return True

    ctx.console.print(f"[dim]{_tr(ctx, 'commands.skills.running', name=skill.name)}[/dim]")

    if skill.context == "fork":
        # Forked execution: isolated turn
        saved = list(ctx.engine.get_messages())
        ctx.engine.set_messages([])
        try:
            permissions = ctx.permissions
            run_query(ctx.engine, prompt, print_mode=False, permissions=permissions)
        finally:
            # Restore original messages (forked result is ephemeral)
            ctx.engine.set_messages(saved)
    else:
        # Inline execution: inject prompt into ongoing conversation
        permissions = ctx.permissions
        run_query(ctx.engine, prompt, print_mode=False, permissions=permissions)

    return True
