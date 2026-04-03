from __future__ import annotations

import argparse
import base64
import mimetypes
import re
import sys
import time
import threading
from importlib.metadata import PackageNotFoundError, version as package_version
from datetime import datetime
from pathlib import Path

from prompt_toolkit.application import Application as PTApp
from prompt_toolkit.application.current import get_app
from prompt_toolkit.buffer import Buffer
from prompt_toolkit.completion import Completer, Completion
from prompt_toolkit.document import Document
from prompt_toolkit.history import FileHistory
from prompt_toolkit.key_binding import KeyBindings
from prompt_toolkit.layout import Layout
from prompt_toolkit.layout.containers import HSplit, Window, FloatContainer, Float
from prompt_toolkit.layout.controls import BufferControl, FormattedTextControl
from prompt_toolkit.layout.dimension import Dimension
from prompt_toolkit.layout.menus import CompletionsMenu
from rich.console import Console
from rich.live import Live
from rich.panel import Panel
from rich.spinner import Spinner
from rich.text import Text

from .config import load_app_config
from .coordinator import (
    current_session_mode,
    get_coordinator_system_prompt,
    get_coordinator_user_context,
    get_worker_system_prompt,
    is_coordinator_mode,
    match_session_mode,
    set_coordinator_mode,
)
from .context import build_system_prompt
from .cost_tracker import CostTracker
from .engine import AbortedError, Engine
from .session import SessionStore
from .compact import CompactService, estimate_tokens, should_compact
from .commands import parse_command, handle_command, CommandContext
from ._keylistener import EscListener
from .permissions import PermissionChecker
from .sandbox.config import load_sandbox_config
from .sandbox.manager import SandboxManager
from .tools.ask_user import AskUserQuestionTool
from .tools.agent import AgentTool, SendMessageTool, TaskStopTool
from .tools.bash import BashTool
from .tools.file_edit import FileEditTool
from .tools.file_read import FileReadTool
from .tools.file_write import FileWriteTool
from .tools.glob_tool import GlobTool
from .tools.grep_tool import GrepTool
from .worker_manager import WorkerManager
from .memory import (
    ensure_memory_dir,
    extract_memory_tags,
    append_to_daily_log,
    build_dream_prompt,
    should_auto_dream,
    try_acquire_lock,
    release_lock,
    record_consolidation,
)
from .i18n import DEFAULT_LOCALE, command_description, normalize_locale, t
from .skills import discover_skills, list_skills, build_skills_prompt_section
from .skills_bundled import register_bundled_skills

console = Console()
_HISTORY_FILE = Path.home() / ".cc_mini_history"

# Match claude-code-main: useDoublePress DOUBLE_PRESS_TIMEOUT_MS = 800
_DOUBLE_PRESS_TIMEOUT_MS = 0.8
_WELCOME_PANEL_WIDTH = 28
_SHORTCUTS_PANEL_WIDTH = 39
_INTRO_PANEL_GAP = 2
_HEADER_EXTRA_WIDTH = 5
_WELCOME_ART_LINES = (
    "",
    "  ▓▓▓▓  ▓▓▓▓  ▓       ▓",
    "  ▓     ▓     ▓ ▓   ▓ ▓",
    "  ▓     ▓     ▓  ▓ ▓  ▓",
    "  ▓▓▓▓  ▓▓▓▓  ▓   ▓   ▓",
    "",
)
_WELCOME_ART_WIDTH = max(len(line) for line in _WELCOME_ART_LINES)


def _app_version() -> str:
    try:
        return package_version("cc-mini")
    except PackageNotFoundError:
        return "0.1.0"


# ---------------------------------------------------------------------------
# Slash command autocomplete — shows suggestions when user types "/"
# Matches claude-code-main's commandSuggestions.ts behavior
# ---------------------------------------------------------------------------

class _SlashCommandCompleter(Completer):
    """Autocomplete for slash commands. Triggers when input starts with "/"."""

    def __init__(self, locale_getter=None):
        self._locale_getter = locale_getter or (lambda: DEFAULT_LOCALE)

    # (name, description) — built-in + buddy
    BUILTIN_COMMANDS: list[tuple[str, str]] = [
        ('help',    'Show available commands'),
        ('language','Switch interface language [locale]'),
        ('compact', 'Compress conversation context'),
        ('resume',  'Resume a past session'),
        ('history', 'List saved sessions'),
        ('clear',   'Clear conversation, start new session'),
        ('cost',    'Show token usage and cost summary'),
        ('model',   'Show or switch model'),
        ('skills',  'List all available skills'),
        ('buddy',            'Companion pet — hatch, pet, stats, mute/unmute, ia'),
        ('buddy pet',        'Pet your companion'),
        ('buddy stats',      'Show companion stats'),
        ('buddy new',        'Hatch a new random companion'),
        ('buddy list',       'View all companions'),
        ('buddy select',     'Switch active companion (e.g. /buddy select 2)'),
        ('buddy mute',       'Mute companion reactions'),
        ('buddy unmute',     'Unmute companion reactions'),
        ('buddy ia',         'Idle Adventure — roguelike world exploration game'),
        ('exit',    'Exit the REPL'),
    ]

    def get_completions(self, document: Document, complete_event):
        text = document.text_before_cursor.lstrip()
        if not text.startswith('/'):
            return

        query = text[1:].lower()
        locale = self._locale_getter()

        # Built-in commands
        for name, desc in self.BUILTIN_COMMANDS:
            if not query or name.startswith(query):
                yield Completion(
                    f'/{name}',
                    start_position=-len(text),
                    display=f'/{name}',
                    display_meta=command_description(name, locale, desc),
                )

        # Dynamic skill commands
        try:
            from .skills import list_skills
            for skill in list_skills(user_invocable_only=True):
                # Skip if already covered by built-in commands
                if any(name == skill.name for name, _ in self.BUILTIN_COMMANDS):
                    continue
                if not query or skill.name.startswith(query):
                    yield Completion(
                        f'/{skill.name}',
                        start_position=-len(text),
                        display=f'/{skill.name}',
                        display_meta=skill.description[:40] if skill.description else 'skill',
                    )
        except Exception:
            pass


_slash_completer = _SlashCommandCompleter()


def _bottom_toolbar_hint(is_terminal: bool, locale: str) -> str:
    return "-"


def _exit_hint(locale: str) -> str:
    return t(locale, "repl.exit_hint")


def _resume_success_message(title: str, message_count: int, locale: str) -> str:
    return t(locale, "repl.resume.success", title=title, message_count=message_count)


def _resume_not_found_message(value: str, locale: str) -> str:
    return t(locale, "repl.resume.not_found", value=value)


def _background_workers_notice(locale: str) -> str:
    return t(locale, "repl.background_workers_running")


def _worker_update_message(locale: str) -> str:
    return t(locale, "repl.worker_update")


def _shell_exit_message(code: int, locale: str) -> str:
    return t(locale, "repl.shell.exit", code=code)


def _shell_error_message(error: str, locale: str) -> str:
    return t(locale, "repl.shell.error", error=error)


def _auto_compacting_message(locale: str) -> str:
    return t(locale, "repl.auto_compacting")


def _context_compressed_message(token_count: int, locale: str) -> str:
    return t(locale, "repl.context_compressed", token_count=f"{token_count:,}")


def _auto_compact_failed_message(error: str, locale: str) -> str:
    return t(locale, "repl.auto_compact_failed", error=error)


def _dream_start_message(locale: str) -> str:
    return t(locale, "repl.dream.start")


def _dream_complete_message(locale: str) -> str:
    return t(locale, "repl.dream.complete")


def _auto_dream_triggered_message(locale: str) -> str:
    return t(locale, "repl.auto_dream_triggered")


def _yes_no_label(value: bool, locale: str) -> str:
    return t(locale, "repl.value.yes" if value else "repl.value.no")


def _sandbox_status_title(locale: str) -> str:
    return t(locale, "repl.sandbox.status")


def _sandbox_mode_line(mode: str, locale: str) -> str:
    return t(locale, "repl.sandbox.mode", value=mode)


def _sandbox_enabled_line(enabled: bool, locale: str) -> str:
    return t(locale, "repl.sandbox.enabled", value=_yes_no_label(enabled, locale))


def _sandbox_network_isolation_line(enabled: bool, locale: str) -> str:
    return t(locale, "repl.sandbox.network_isolation", value=_yes_no_label(enabled, locale))


def _sandbox_dependency_errors_title(locale: str) -> str:
    return t(locale, "repl.sandbox.dependency_errors")


def _sandbox_excluded_commands_title(locale: str) -> str:
    return t(locale, "repl.sandbox.excluded_commands")


def _sandbox_configure_title(locale: str) -> str:
    return t(locale, "repl.sandbox.configure")


def _sandbox_option_auto_allow(locale: str) -> str:
    return t(locale, "repl.sandbox.option.auto_allow")


def _sandbox_option_regular(locale: str) -> str:
    return t(locale, "repl.sandbox.option.regular")


def _sandbox_option_disabled(locale: str) -> str:
    return t(locale, "repl.sandbox.option.disabled")


def _sandbox_select_prompt(locale: str) -> str:
    return t(locale, "repl.sandbox.select_prompt")


def _sandbox_cannot_enable_title(locale: str) -> str:
    return t(locale, "repl.sandbox.cannot_enable")


def _sandbox_cancelled_message(locale: str) -> str:
    return t(locale, "repl.sandbox.cancelled")


def _tool_done_message(locale: str) -> str:
    return t(locale, "repl.tool_done")


def _session_note(session_id: str, locale: str) -> str:
    return t(locale, "repl.session_note", session_id=session_id)


def _build_repl_header(
    provider: str,
    model: str,
    max_tokens: int,
    session_id: str | None,
    coordinator_enabled: bool,
    locale: str = DEFAULT_LOCALE,
):
    title = Text.assemble(
        ("CC-Mini", "bold cyan"),
        (f" [v{_app_version()}]", "bold white"),
    )
    body = Text()
    body.append("🤖 Model: ", style="bold cyan")
    body.append(model, style="bold")
    body.append("   💾 Max: ", style="bold magenta")
    body.append(str(max_tokens), style="bold")
    if session_id:
        body.append("   🆔 Session: ", style="bold green")
        body.append(session_id[:8], style="bold")
    if coordinator_enabled:
        body.append("   ⚙ ", style="bold yellow")
        body.append("coordinator", style="bold yellow")
    return Panel(
        body,
        title=title,
        border_style="cyan",
        padding=(0, 1),
        expand=False,
        width=_WELCOME_PANEL_WIDTH + _SHORTCUTS_PANEL_WIDTH + _HEADER_EXTRA_WIDTH,
    )


def _build_repl_intro_section(
    model: str | None = None,
    max_tokens: int | None = None,
    session_id: str | None = None,
    locale: str = DEFAULT_LOCALE,
):
    left_width = _WELCOME_PANEL_WIDTH - 4
    right_width = _SHORTCUTS_PANEL_WIDTH - 5
    left_lines = [
        "",
        *list(_WELCOME_ART_LINES[1:-1]),
        "",
        f"Model: {model}" if model else "",
        f"Max: {max_tokens}" if max_tokens is not None else "",
        f"Session: {session_id[:8]}" if session_id else "",
    ]
    right_lines = [
        "Quick Shortcuts",
        "",
        "Esc         : Cancel / Quit",
        "Ctrl + C    : Force Exit",
        "Alt + Enter : New Line",
        "/resume     : Load History",
        "/buddy      : Load Buddy",
        "/exit       : Exit",
    ]
    line_count = max(len(left_lines), len(right_lines))
    left_lines.extend([""] * (line_count - len(left_lines)))
    right_lines.extend([""] * (line_count - len(right_lines)))

    body = Text()
    for index, (left, right) in enumerate(zip(left_lines, right_lines)):
        body.append(left.ljust(left_width), style="bold cyan")
        body.append(" │ ", style="dim")
        body.append(right.ljust(right_width), style="bold yellow" if index == 0 else "bold white")
        if index < line_count - 1:
            body.append("\n")

    return Panel(
        body,
        title=Text(f"Welcome to CC-Mini v{_app_version()}", style="bold white"),
        border_style="cyan",
        padding=(0, 1),
        expand=False,
        width=_WELCOME_PANEL_WIDTH + _SHORTCUTS_PANEL_WIDTH,
    )


def _build_tool_call_panel(tool_name: str, preview: str, locale: str = DEFAULT_LOCALE):
    body = Text()
    body.append(preview or "…", style="dim")
    return Panel(
        body,
        title=Text(f"↳ {tool_name}", style="bold cyan"),
        border_style="bright_black",
        padding=(0, 1),
        expand=False,
    )


# ---------------------------------------------------------------------------
# Bordered input prompt — matches claude-code-main PromptInput.tsx
# borderStyle="round", borderLeft=false, borderRight=false
# Uses a custom prompt_toolkit Application so the bottom border sits
# directly below the input content (not at the screen bottom).
# ---------------------------------------------------------------------------

def _bordered_prompt(
    con: Console,
    history: FileHistory | None = None,
    completer: Completer | None = None,
    animator_toolbar=None,
    refresh_interval: float | None = None,
    terminal_mode_ref: list | None = None,
    locale: str = DEFAULT_LOCALE,
) -> str:
    """Prompt with bordered input box that adapts to content height.

    terminal_mode_ref is a mutable [bool] list so '!' can toggle it in-place.

    Raises KeyboardInterrupt on Ctrl+C, EOFError on Ctrl+D with empty buffer.
    """
    import os

    if terminal_mode_ref is None:
        terminal_mode_ref = [False]

    def _is_terminal():
        return terminal_mode_ref[0]

    def _accept(b):
        get_app().exit(result=b.text)
        return True  # keep text in buffer so final render preserves input

    buf = Buffer(
        history=history,
        completer=completer,
        complete_while_typing=False,
        accept_handler=_accept,
    )

    def _trigger_completion_next_tick():
        """Schedule start_completion on the next event-loop tick.

        This avoids the race with prompt_toolkit's internal completion reset
        that happens synchronously during text insertion.
        """
        import asyncio
        try:
            loop = asyncio.get_event_loop()
            loop.call_soon(lambda: buf.start_completion(select_first=False))
        except RuntimeError:
            pass

    def _on_text_changed(_buf):
        """Trigger completion popup when input starts with '/'."""
        if _buf.text.lstrip().startswith('/'):
            _trigger_completion_next_tick()

    buf.on_text_changed += _on_text_changed

    def _top():
        try:
            w = os.get_terminal_size().columns
        except OSError:
            w = 80
        fill = "\u2500" * max(0, w - 1)
        if _is_terminal():
            return [('bold fg:ansiyellow', f'\u256d{fill}')]
        return [('bold fg:ansicyan', f'\u256d{fill}')]

    def _bot():
        try:
            w = os.get_terminal_size().columns
        except OSError:
            w = 80
        hints = _bottom_toolbar_hint(_is_terminal(), locale)
        fill = "\u2500" * max(0, w - 1 - len(hints))
        style = 'fg:ansiyellow' if _is_terminal() else 'fg:ansicyan'
        parts: list[tuple[str, str]] = [(style, f'\u2570{hints}{fill}')]

        if animator_toolbar:
            extra = animator_toolbar()
            if extra:
                parts.append(('', '\n'))
                parts.extend(extra)
        return parts

    def _line_prefix(lineno, wrap_count):
        """First visual line gets '> ' or '$ ', all others get '  ' padding."""
        if lineno == 0 and wrap_count == 0:
            if _is_terminal():
                return [('bold fg:ansiyellow', '$ ')]
            return [('bold fg:ansicyan', '> ')]
        return [('', '  ')]

    body = HSplit([
        Window(FormattedTextControl(_top), height=1, dont_extend_height=True),
        Window(
            BufferControl(buffer=buf),
            get_line_prefix=_line_prefix,
            height=Dimension(min=1),
            dont_extend_height=True,
            wrap_lines=True,
        ),
        Window(FormattedTextControl(_bot), dont_extend_height=True),
    ])

    root = FloatContainer(
        content=body,
        floats=[
            Float(
                xcursor=True, ycursor=True,
                content=CompletionsMenu(max_height=8, scroll_offset=1),
            ),
        ],
    )

    kb = KeyBindings()

    @kb.add('!')
    def _(event):
        if not buf.text:
            # Toggle terminal mode in-place, no submit
            terminal_mode_ref[0] = not terminal_mode_ref[0]
            event.app.invalidate()  # force UI refresh for color change
        else:
            buf.insert_text('!')

    @kb.add('enter')
    def _(event):
        # Feature: backslash + Enter = newline continuation
        # Check at key-binding level to avoid buffer.reset() clearing text
        if buf.text.endswith('\\'):
            buf.delete_before_cursor(1)
            buf.insert_text('\n')
        else:
            buf.validate_and_handle()

    @kb.add('escape', 'enter')
    def _(event):
        buf.insert_text('\n')

    @kb.add('c-c')
    def _(event):
        event.app.exit(exception=KeyboardInterrupt())

    @kb.add('c-d')
    def _(event):
        if not buf.text:
            event.app.exit(exception=EOFError())

    app = PTApp(
        layout=Layout(root),
        key_bindings=kb,
        full_screen=False,
        refresh_interval=refresh_interval,
    )
    app.layout.focus(buf)
    return app.run()


def _tool_preview(tool_name: str, tool_input: dict) -> str:
    if tool_name == "Bash":
        cmd = tool_input.get("command", "")
        return cmd[:80] + ("…" if len(cmd) > 80 else "")
    if tool_name in ("Read", "Edit", "Write"):
        fp = tool_input.get("file_path", "")
        return fp[-60:] if len(fp) > 60 else fp
    if tool_name in ("Glob", "Grep"):
        return tool_input.get("pattern", "")
    return ""


_IMAGE_EXTS = {".png", ".jpg", ".jpeg", ".gif", ".webp"}
_IMG_PATH_RE = re.compile(r"@(\S+)")


def _parse_input(text: str) -> str | list:
    """Parse user input, extracting @path image references into content blocks.

    Returns plain string if no images, or a list of content blocks if images found.
    """
    matches = list(_IMG_PATH_RE.finditer(text))
    if not matches:
        return text

    image_blocks = []
    for m in matches:
        fpath = Path(m.group(1))
        if not fpath.suffix.lower() in _IMAGE_EXTS:
            continue
        if not fpath.exists():
            continue
        media_type = mimetypes.guess_type(str(fpath))[0] or "image/png"
        data = base64.standard_b64encode(fpath.read_bytes()).decode("ascii")
        image_blocks.append({
            "type": "image",
            "source": {"type": "base64", "media_type": media_type, "data": data},
        })

    if not image_blocks:
        return text

    # Remove @path tokens from text
    cleaned = _IMG_PATH_RE.sub("", text).strip()
    content: list[dict] = list(image_blocks)
    if cleaned:
        content.append({"type": "text", "text": cleaned})
    return content


class _SpinnerManager:
    """Manages a Rich Live spinner that shows while waiting for API/tool responses.

    Matches claude-code-main's spinner behavior: show a spinning indicator
    with contextual text while the model is thinking or tools are executing.
    """

    def __init__(self, console: Console, locale: str = DEFAULT_LOCALE):
        self._console = console
        self._live: Live | None = None
        self._locale = locale
        self._spinner_text = t(locale, "repl.spinner.thinking")

    def start(self, text: str | None = None):
        if text is None:
            text = t(self._locale, "repl.spinner.thinking")
        self._spinner_text = text
        self._live = Live(
            Spinner("dots", text=Text(self._spinner_text, style="dim")),
            console=self._console,
            refresh_per_second=12,
        )
        self._live.start()

    def update(self, text: str):
        self._spinner_text = text
        if self._live is not None:
            self._live.update(
                Spinner("dots", text=Text(self._spinner_text, style="dim"))
            )

    def stop(self):
        if self._live is not None:
            # Clear spinner line: update to empty then stop
            self._live.update("")
            self._live.stop()
            self._live = None


def run_query(engine: Engine, user_input: str | list, print_mode: bool,
              permissions: PermissionChecker | None = None,
              locale: str = DEFAULT_LOCALE) -> None:
    """Run a single turn. Ctrl+C or Esc cancels the active turn."""
    listener = EscListener(on_cancel=engine.abort)
    if permissions:
        permissions.set_esc_listener(listener)

    spinner = _SpinnerManager(console, locale=locale)
    first_text = True
    streaming = False

    try:
        with listener:
            spinner.start(t(locale, "repl.spinner.thinking"))

            for event in engine.submit(user_input):
                if streaming and listener.check_esc_nonblocking():
                    spinner.stop()
                    engine.cancel_turn()
                    console.print(f"\n[dim yellow]{t(locale, 'repl.turn_cancelled_esc')}[/dim yellow]")
                    return

                if event[0] == "text":
                    if first_text:
                        spinner.stop()
                        listener.pause()
                        streaming = True
                        first_text = False
                    if print_mode:
                        print(event[1], end="", flush=True)
                    else:
                        console.print(event[1], end="", markup=False)

                elif event[0] == "waiting":
                    streaming = False
                    listener.resume()
                    spinner.start(t(locale, "repl.spinner.preparing_tool"))

                elif event[0] == "tool_call":
                    spinner.stop()
                    streaming = False
                    listener.pause()
                    _, tool_name, tool_input = event
                    preview = _tool_preview(tool_name, tool_input)
                    console.print()
                    console.print(_build_tool_call_panel(tool_name, preview, locale))

                elif event[0] == "tool_result":
                    _, tool_name, tool_input, result = event
                    status = "[red]✗[/red]" if result.is_error else "[green]✓[/green]"
                    console.print(f"[dim]  {status} {_tool_done_message(locale)}[/dim]")
                    if result.is_error:
                        console.print(f"  [red]{result.content[:300]}[/red]")
                    streaming = False
                    listener.resume()
                    spinner.start(t(locale, "repl.spinner.thinking"))
                    first_text = True

                elif event[0] == "error":
                    spinner.stop()
                    console.print(f"\n[bold red]{event[1]}[/bold red]")

            spinner.stop()
    except (AbortedError, KeyboardInterrupt):
        spinner.stop()
        if not isinstance(sys.exc_info()[1], AbortedError):
            engine.cancel_turn()
        console.print(f"\n[dim yellow]{t(locale, 'repl.turn_cancelled')}[/dim yellow]")
        return
    finally:
        spinner.stop()
        if permissions:
            permissions.set_esc_listener(None)

    if not print_mode:
        console.print()


def _run_dream(engine: Engine, memory_dir: Path,
               permissions: PermissionChecker,
               locale: str = DEFAULT_LOCALE) -> None:
    """Run dream consolidation: snapshot messages, submit dream prompt, restore."""
    console.print(f"[dim]{_dream_start_message(locale)}[/dim]")
    saved_messages = list(engine.messages)
    engine.messages = []
    dream_prompt = build_dream_prompt(memory_dir)
    run_query(engine, dream_prompt, print_mode=False, permissions=permissions, locale=locale)
    engine.messages = saved_messages
    # Rebuild system prompt to pick up updated MEMORY.md
    engine.system_prompt = build_system_prompt(memory_dir=memory_dir)
    record_consolidation(memory_dir)
    console.print(f"[dim]{_dream_complete_message(locale)}[/dim]")


def _load_startup_locale(cwd: str) -> str:
    """Restore the most recent locale for the current workspace, if available."""
    sessions = SessionStore.list_sessions(cwd)
    if not sessions:
        return DEFAULT_LOCALE
    restored = normalize_locale(sessions[0].locale)
    return restored or DEFAULT_LOCALE


def main() -> None:
    parser = argparse.ArgumentParser(prog="cc-mini",
                                     description="Minimal Python Claude Code")
    parser.add_argument("prompt", nargs="?", help="Prompt to send (optional)")
    parser.add_argument("-p", "--print", action="store_true",
                        help="Non-interactive: print response and exit")
    parser.add_argument("--auto-approve", action="store_true",
                        help="Auto-approve all tool permissions (dangerous)")
    parser.add_argument("--config", help="Path to a TOML config file")
    parser.add_argument("--provider", choices=("anthropic", "openai"),
                        help="API provider / wire format")
    parser.add_argument("--api-key", help="API key for the selected provider")
    parser.add_argument("--base-url", help="Custom API base URL for the selected provider")
    parser.add_argument("--model", help="Model name, e.g. claude-sonnet-4")
    parser.add_argument("--max-tokens", type=int,
                        help="Maximum output tokens for each model response")
    parser.add_argument("--effort", choices=("low", "medium", "high"),
                        help="Optional reasoning effort for supported OpenAI models")
    parser.add_argument("--buddy-model",
                        help="Override the model used by buddy / companion side-features")
    parser.add_argument("--resume", metavar="SESSION",
                        help="Resume a previous session (id or index)")
    parser.add_argument("--memory-dir", help="Override memory directory path")
    parser.add_argument("--no-auto-dream", action="store_true",
                        help="Disable automatic dream consolidation")
    parser.add_argument("--dream-interval", type=float,
                        help="Hours between auto-dream runs (default: 24)")
    parser.add_argument("--dream-min-sessions", type=int,
                        help="Minimum new sessions before auto-dream triggers (default: 5)")
    parser.add_argument("--coordinator", action="store_true",
                        help="Enable coordinator mode with background workers")
    args = parser.parse_args()

    try:
        app_config = load_app_config(args)
    except ValueError as exc:
        parser.error(str(exc))

    # Sandbox initialization
    sandbox_config = load_sandbox_config(app_config.config_paths)
    sandbox_mgr = SandboxManager(config=sandbox_config)

    # Memory setup
    memory_dir = app_config.memory_dir
    ensure_memory_dir(memory_dir)
    session_id = datetime.now().strftime("%Y%m%d-%H%M%S")

    # Skill setup — register bundled + discover project/user skills
    register_bundled_skills()
    cwd = str(Path.cwd())
    discover_skills(cwd)
    skills_section = build_skills_prompt_section()

    if args.coordinator:
        set_coordinator_mode(True)

    def _build_base_tools() -> list:
        return [
            FileReadTool(), GlobTool(), GrepTool(),
            FileEditTool(), FileWriteTool(),
            BashTool(sandbox_manager=sandbox_mgr),
        ]

    worker_tool_names = [tool.name for tool in _build_base_tools()]

    def _build_system_prompt_for_mode(coordinator_enabled: bool) -> str:
        prompt = build_system_prompt(cwd=cwd, memory_dir=memory_dir)
        if skills_section:
            prompt += "\n\n" + skills_section
        if coordinator_enabled:
            extra = get_coordinator_user_context(worker_tool_names)
            worker_context = extra.get("workerToolsContext")
            if worker_context:
                prompt += "\n\n# Coordinator Context\n" + worker_context
            prompt += "\n\n" + get_coordinator_system_prompt()
        return prompt

    permissions = PermissionChecker(
        auto_approve=args.auto_approve,
        sandbox_manager=sandbox_mgr,
    )

    def _build_worker_engine() -> Engine:
        worker_permissions = PermissionChecker(
            auto_approve=True,
            sandbox_manager=sandbox_mgr,
        )
        worker_prompt = build_system_prompt(cwd=cwd, memory_dir=memory_dir)
        if skills_section:
            worker_prompt += "\n\n" + skills_section
        worker_prompt += "\n\n" + get_worker_system_prompt()
        return Engine(
            tools=_build_base_tools(),
            system_prompt=worker_prompt,
            permission_checker=worker_permissions,
            provider=app_config.provider,
            api_key=app_config.api_key,
            base_url=app_config.base_url,
            model=app_config.model,
            max_tokens=app_config.max_tokens,
            effort=app_config.effort,
        )

    worker_manager = WorkerManager(build_worker_engine=_build_worker_engine)

    def _build_tools_for_mode(coordinator_enabled: bool) -> list:
        tools = _build_base_tools()
        tools.append(AskUserQuestionTool())
        if coordinator_enabled:
            tools.extend([
                AgentTool(worker_manager),
                SendMessageTool(worker_manager),
                TaskStopTool(worker_manager),
            ])
        return tools

    coordinator_enabled = is_coordinator_mode()

    # Session & compact services
    cost_tracker = CostTracker()
    session_locale = [_load_startup_locale(cwd)]
    session_store: SessionStore | None = None

    def _set_session_locale(value: str | None) -> None:
        normalized = normalize_locale(value) or DEFAULT_LOCALE
        session_locale[0] = normalized
        if session_store is not None:
            session_store.locale = normalized

    def _translate(key: str, **kwargs) -> str:
        return t(session_locale[0], key, **kwargs)

    if not args.print:
        session_store = SessionStore(
            cwd=cwd,
            model=app_config.model,
            mode=current_session_mode(),
            locale=session_locale[0],
        )

    engine = Engine(
        tools=_build_tools_for_mode(coordinator_enabled),
        system_prompt=_build_system_prompt_for_mode(coordinator_enabled),
        permission_checker=permissions,
        provider=app_config.provider,
        api_key=app_config.api_key,
        base_url=app_config.base_url,
        model=app_config.model,
        max_tokens=app_config.max_tokens,
        effort=app_config.effort,
        session_store=session_store,
        cost_tracker=cost_tracker,
    )
    compact_service = CompactService(
        client=engine._client,
        model=app_config.model,
        effort=app_config.effort,
    )

    def _apply_session_mode(session_mode: str | None) -> str | None:
        warning = match_session_mode(session_mode)
        enabled = is_coordinator_mode()
        engine.set_tools(_build_tools_for_mode(enabled))
        engine.system_prompt = _build_system_prompt_for_mode(enabled)
        if session_store is not None:
            session_store.mode = current_session_mode()
        return warning

    # Handle --resume
    if args.resume and session_store is not None:
        sessions = SessionStore.list_sessions(cwd)
        target = None
        try:
            idx = int(args.resume) - 1
            if 0 <= idx < len(sessions):
                target = sessions[idx]
        except ValueError:
            needle = args.resume.lower()
            for m in sessions:
                if m.session_id.lower().startswith(needle):
                    target = m
                    break
        if target:
            meta, msgs = SessionStore.load_session(target.session_id, cwd)
            if msgs:
                warning = _apply_session_mode(meta.mode if meta is not None else None)
                engine.set_messages(msgs)
                _set_session_locale(meta.locale if meta is not None else None)
                session_store = SessionStore(
                    cwd=cwd,
                    model=app_config.model,
                    session_id=target.session_id,
                    mode=current_session_mode(),
                    locale=session_locale[0],
                )
                engine.set_session_store(session_store)
                console.print(
                    f"[green]✓[/green] {_resume_success_message(target.title[:50], len(msgs), session_locale[0])}"
                )
                if warning:
                    console.print(f"[yellow]{warning}[/yellow]")
        else:
            console.print(f"[red]{_resume_not_found_message(args.resume, session_locale[0])}[/red]")

    # Non-interactive / piped
    if args.print or args.prompt:
        prompt_text = args.prompt or sys.stdin.read()
        run_query(engine, _parse_input(prompt_text), print_mode=args.print, permissions=permissions)
        if worker_manager.has_running_tasks():
            console.print(f"\n[dim]{_background_workers_notice(session_locale[0])}[/dim]")
        if cost_tracker.total_cost_usd > 0:
            console.print(f"\n[dim]{cost_tracker.format_cost()}[/dim]")
        return

    # Interactive REPL
    console.print(
        _build_repl_intro_section(
            model=app_config.model,
            max_tokens=app_config.max_tokens,
            session_id=session_store.session_id if session_store else None,
            locale=session_locale[0],
        )
    )

    _file_history = FileHistory(str(_HISTORY_FILE))

    # Track last Ctrl+C time for double-press exit (matches useDoublePress)
    last_ctrlc_time = 0.0

    # Terminal mode state — shared mutable ref toggled by "!" key binding
    _terminal_mode_ref = [False]

    def _run_shell(cmd: str) -> None:
        """Execute a shell command and print output."""
        import subprocess
        console.print(f"[dim]$ {cmd}[/dim]")
        try:
            result = subprocess.run(
                cmd, shell=True, text=True,
                stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
            )
            if result.stdout:
                console.print(result.stdout, end="", markup=False)
            if result.returncode != 0:
                console.print(f"[red][{_shell_exit_message(result.returncode, session_locale[0])}][/red]")
        except Exception as exc:
            console.print(f"[red]{_shell_error_message(str(exc), session_locale[0])}[/red]")

    # Companion animator — drives real-time idle animation in bottom_toolbar
    # Matches CompanionSprite.tsx tick-based animation system
    animator = None
    try:
        from .buddy.companion import get_companion
        from .buddy.storage import load_companion_muted
        from .buddy.animator import CompanionAnimator
        if not load_companion_muted():
            comp = get_companion()
            if comp:
                animator = CompanionAnimator(comp)
    except Exception:
        pass

    def _set_reaction(text: str, print_to_terminal: bool = False) -> None:
        """Observer callback — delivers reaction to animator's toolbar bubble.

        For normal mode (reacting to Claude): only shows in toolbar bubble.
        For direct address mode: also prints to terminal scroll history.
        """
        if animator:
            animator.set_reaction(text)
        if print_to_terminal:
            try:
                from .buddy.companion import get_companion
                from .buddy.types import RARITY_COLORS
                from .buddy.sprites import render_face
                from .buddy.types import CompanionBones
                comp = get_companion()
                if comp:
                    color = RARITY_COLORS.get(comp.rarity, 'dim')
                    bones = CompanionBones(
                        rarity=comp.rarity, species=comp.species,
                        eye=comp.eye, hat=comp.hat, shiny=comp.shiny, stats=comp.stats,
                    )
                    face = render_face(bones)
                    console.print(f'\n[{color}]{face} {comp.name}:[/{color}] [{color} italic]{text}[/{color} italic]')
            except Exception:
                pass

    def _drain_worker_notifications() -> None:
        if not is_coordinator_mode():
            return
        while True:
            notifications = worker_manager.drain_notifications()
            if not notifications:
                return
            for notification in notifications:
                console.print(f"\n[dim]{_worker_update_message(session_locale[0])}[/dim]")
                run_query(engine, notification, print_mode=False, permissions=permissions, locale=session_locale[0])

    while True:
        _drain_worker_notifications()

        # Start/restart animator before each prompt (picks up newly hatched companions)
        if animator is None:
            try:
                from .buddy.companion import get_companion
                from .buddy.storage import load_companion_muted
                from .buddy.animator import CompanionAnimator
                if not load_companion_muted():
                    comp = get_companion()
                    if comp:
                        animator = CompanionAnimator(comp)
            except Exception:
                pass

        try:
            if animator:
                animator.start()
            console.print()
            _terminal_mode_ref[0] = False  # always start in chat mode
            user_input = _bordered_prompt(
                console,
                history=_file_history,
                completer=_SlashCommandCompleter(locale_getter=lambda: session_locale[0]),
                animator_toolbar=animator.toolbar_text if animator else None,
                refresh_interval=0.5 if animator else None,
                terminal_mode_ref=_terminal_mode_ref,
                locale=session_locale[0],
            ).strip()
        except KeyboardInterrupt:
            now = time.monotonic()
            if now - last_ctrlc_time <= _DOUBLE_PRESS_TIMEOUT_MS:
                if animator:
                    animator.stop()
                console.print(f"\n[dim]{t(session_locale[0], 'repl.goodbye')}[/dim]")
                break
            last_ctrlc_time = now
            console.print(f"\n[dim yellow]{t(session_locale[0], 'repl.press_ctrlc_again')}[/dim yellow]")
            continue
        except EOFError:
            if animator:
                animator.stop()
            console.print(f"\n[dim]{t(session_locale[0], 'repl.goodbye')}[/dim]")
            break
        finally:
            if animator:
                animator.stop()

        # Reset double-press timer on any normal input
        last_ctrlc_time = 0.0

        if not user_input:
            continue

        # ---------------------------------------------------------------------------
        # Terminal mode — "!" key toggles mode in-place (no submit needed).
        # In terminal mode every submitted input is a shell command.
        # Outside terminal mode "!cmd" runs a one-off shell command.
        # ---------------------------------------------------------------------------
        if _terminal_mode_ref[0]:
            _run_shell(user_input)
            continue

        if user_input.startswith("!") and len(user_input) > 1:
            _run_shell(user_input[1:].lstrip())
            continue
        if user_input.lower() in ("exit", "quit", "/exit", "/quit"):
            console.print(f"[dim]{t(session_locale[0], 'repl.goodbye')}[/dim]")
            break
        if user_input.startswith("/sandbox"):
            _handle_sandbox_command(user_input, sandbox_mgr, console, locale=session_locale[0])
            continue

        # Slash commands (session, compact, help, etc.)
        cmd = parse_command(user_input)
        if cmd is not None:
            cmd_name, cmd_args = cmd
            if cmd_name in ("exit", "quit"):
                console.print(f"[dim]{t(session_locale[0], 'repl.goodbye')}[/dim]")
                break
            # /buddy is handled separately (companion pet)
            if cmd_name == "buddy":
                from .buddy.commands import handle_buddy_command
                handle_buddy_command(
                    cmd_args,
                    engine._client,
                    console,
                    app_config.buddy_model or app_config.model,
                    locale=session_locale[0],
                )
                # Refresh animator in case companion was just hatched
                try:
                    from .buddy.companion import get_companion
                    from .buddy.animator import CompanionAnimator
                    comp = get_companion()
                    if comp:
                        animator = CompanionAnimator(comp)
                except Exception:
                    pass
                continue
            cmd_ctx = CommandContext(
                engine=engine,
                session_store=session_store,
                compact_service=compact_service,
                console=console,
                app_config=app_config,
                locale=session_locale[0],
                memory_dir=memory_dir,
                permissions=permissions,
                run_dream=lambda: _run_dream(engine, memory_dir, permissions, locale=session_locale[0]),
                cost_tracker=cost_tracker,
                new_session_store=lambda: SessionStore(
                    cwd=cwd,
                    model=app_config.model,
                    mode=current_session_mode(),
                    locale=session_locale[0],
                ),
                reconfigure_mode=_apply_session_mode,
                translate=_translate,
                set_locale=_set_session_locale,
            )
            handle_command(cmd_name, cmd_args, cmd_ctx)
            session_store = cmd_ctx.session_store
            continue

        # Auto-compact when approaching token limits
        if should_compact(engine.get_messages(), model=app_config.model,
                          last_input_tokens=cost_tracker.last_input_tokens):
            console.print(f"[dim]{_auto_compacting_message(session_locale[0])}[/dim]")
            try:
                new_msgs, _ = compact_service.compact(
                    engine.get_messages(), engine.get_system_prompt())
                engine.set_messages(new_msgs)
                console.print(f"[dim]{_context_compressed_message(estimate_tokens(new_msgs), session_locale[0])}[/dim]")
            except Exception as e:
                console.print(f"[dim red]{_auto_compact_failed_message(str(e), session_locale[0])}[/dim red]")

        # Check if user is talking directly to companion — skip Claude, let
        # companion reply directly via observer (no awkward "." response)
        _companion_addressed = False
        try:
            from .buddy.companion import get_companion
            from .buddy.storage import load_companion_muted
            from .buddy.observer import fire_companion_observer, _is_addressed
            if not load_companion_muted():
                comp = get_companion()
                if comp and _is_addressed(user_input, comp.name):
                    _companion_addressed = True
                    import threading
                    reply_event = threading.Event()
                    def _direct_reply(text: str) -> None:
                        _set_reaction(text, print_to_terminal=True)
                        reply_event.set()
                    fire_companion_observer(
                        '', comp, engine._client, _direct_reply,
                        model=app_config.buddy_model or app_config.model,
                        user_msg=user_input,
                    )
                    reply_event.wait(timeout=10)
        except Exception:
            pass

        if _companion_addressed:
            continue

        run_query(engine, _parse_input(user_input), print_mode=False, permissions=permissions, locale=session_locale[0])
        _drain_worker_notifications()

        # Fire companion observer in background after each turn
        try:
            from .buddy.companion import get_companion
            from .buddy.storage import load_companion_muted
            from .buddy.observer import fire_companion_observer
            if not load_companion_muted():
                comp = get_companion()
                if comp and engine._messages:
                    last_msg = engine._messages[-1]
                    if last_msg.get("role") == "assistant":
                        content = last_msg.get("content", "")
                        if isinstance(content, str):
                            assistant_text = content
                        elif isinstance(content, list):
                            parts = []
                            for block in content:
                                if isinstance(block, dict) and block.get("type") == "text":
                                    parts.append(block.get("text", ""))
                                elif hasattr(block, "text"):
                                    parts.append(block.text)
                            assistant_text = ' '.join(parts)
                        else:
                            assistant_text = str(content)
                        if assistant_text.strip():
                            # Update companion mood based on this turn
                            try:
                                import time as _time
                                from .buddy.mood import classify_events, apply_events, apply_decay
                                from .buddy.storage import load_active_mood, save_active_mood
                                now_ms = int(_time.time() * 1000)
                                current_mood = load_active_mood()
                                current_mood = apply_decay(current_mood, now_ms)
                                events = classify_events(assistant_text, user_input)
                                if events:
                                    current_mood = apply_events(current_mood, events)
                                save_active_mood(current_mood)
                                # Refresh companion with updated mood
                                comp = get_companion()
                                if animator and comp:
                                    animator.update_companion(comp)
                            except Exception:
                                pass
                            fire_companion_observer(
                                assistant_text, comp, engine._client, _set_reaction,
                                model=app_config.buddy_model or app_config.model,
                                user_msg=user_input,
                            )
        except Exception:
            pass  # Non-essential

        # Post-turn: extract <memory> tags
        text = engine.last_assistant_text()
        for mem in extract_memory_tags(text):
            append_to_daily_log(memory_dir, mem)

        # Auto-dream gate check
        current_sid = session_store.session_id if session_store else session_id
        sessions_path = session_store._dir if session_store else None
        if app_config.auto_dream and should_auto_dream(
            memory_dir,
            min_hours=app_config.dream_interval_hours,
            min_sessions=app_config.dream_min_sessions,
            current_session_id=current_sid,
            sessions_dir=sessions_path,
        ):
            if try_acquire_lock(memory_dir):
                console.print(f"\n[dim]{_auto_dream_triggered_message(session_locale[0])}[/dim]")
                _run_dream(engine, memory_dir, permissions, locale=session_locale[0])
                release_lock(memory_dir)

    # Print cost summary on exit
    if cost_tracker.total_cost_usd > 0:
        console.print(f"\n[dim]{cost_tracker.format_cost()}[/dim]")


def _handle_sandbox_command(
    user_input: str, mgr: SandboxManager, con: Console, locale: str = DEFAULT_LOCALE
) -> None:
    """Handle /sandbox REPL command.

    Corresponds to commands/sandbox-toggle/sandbox-toggle.tsx.

    Sub-commands:
    - /sandbox           -- interactive setup
    - /sandbox status    -- show current status
    - /sandbox exclude <pattern> -- add excluded command
    - /sandbox mode <auto-allow|regular|disabled> -- set mode
    """
    parts = user_input.strip().split(maxsplit=2)
    subcmd = parts[1] if len(parts) > 1 else ""

    if subcmd == "status" or subcmd == "":
        _show_sandbox_status(mgr, con, locale)
    elif subcmd == "exclude" and len(parts) > 2:
        pattern = parts[2].strip("\"'")
        msg = mgr.add_excluded_command(pattern)
        mgr.save()
        con.print(f"[green]{msg}[/green]")
    elif subcmd == "mode" and len(parts) > 2:
        msg = mgr.set_mode(parts[2])
        mgr.save()
        con.print(f"[green]{msg}[/green]")
    else:
        _interactive_sandbox_setup(mgr, con, locale)


def _show_sandbox_status(mgr: SandboxManager, con: Console, locale: str = DEFAULT_LOCALE) -> None:
    """Display sandbox status. Corresponds to SandboxConfigTab + SandboxDependenciesTab."""
    dep = mgr.check_dependencies()
    mode = (
        "auto-allow"
        if mgr.is_auto_allow()
        else ("regular" if mgr.config.enabled else "disabled")
    )
    con.print(f"[bold]{_sandbox_status_title(locale)}[/bold]")
    con.print(f"  {_sandbox_mode_line(mode, locale).replace(mode, f'[cyan]{mode}[/cyan]')}")
    con.print(f"  {_sandbox_enabled_line(mgr.is_enabled(), locale)}")
    con.print(f"  {_sandbox_network_isolation_line(mgr.config.unshare_net, locale)}")
    if dep.errors:
        con.print(f"[bold red]{_sandbox_dependency_errors_title(locale)}[/bold red]")
        for e in dep.errors:
            con.print(f"  [red]{e}[/red]")
    if dep.warnings:
        for w in dep.warnings:
            con.print(f"  [yellow]{w}[/yellow]")
    if mgr.config.excluded_commands:
        con.print(f"[bold]{_sandbox_excluded_commands_title(locale)}[/bold]")
        for cmd in mgr.config.excluded_commands:
            con.print(f"  - {cmd}")


def _interactive_sandbox_setup(mgr: SandboxManager, con: Console, locale: str = DEFAULT_LOCALE) -> None:
    """Interactive three-way mode selection. Corresponds to SandboxModeTab Select."""
    dep = mgr.check_dependencies()
    if dep.errors:
        con.print(f"[bold red]{_sandbox_cannot_enable_title(locale)}[/bold red]")
        for e in dep.errors:
            con.print(f"  [red]{e}[/red]")
        return

    con.print(f"[bold]{_sandbox_configure_title(locale)}[/bold]")
    con.print(f"  {_sandbox_option_auto_allow(locale)}")
    con.print(f"  {_sandbox_option_regular(locale)}")
    con.print(f"  {_sandbox_option_disabled(locale)}")
    choice = input(f"  {_sandbox_select_prompt(locale)}").strip()
    mode_map = {"1": "auto-allow", "2": "regular", "3": "disabled"}
    mode = mode_map.get(choice)
    if mode:
        msg = mgr.set_mode(mode)
        mgr.save()
        con.print(f"[green]{msg}[/green]")
    else:
        con.print(f"[dim]{_sandbox_cancelled_message(locale)}[/dim]")


if __name__ == "__main__":
    main()
