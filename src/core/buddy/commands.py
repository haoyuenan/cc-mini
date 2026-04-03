"""/buddy command handler — AI companion pet.

Subcommands:
  /buddy          — hatch (first time) or show companion card
  /buddy help     — show all commands and gameplay guide
  /buddy pet      — pet your companion (heart animation)
  /buddy stats    — show detailed stats
  /buddy mood     — show current mood
  /buddy new      — hatch a new random companion
  /buddy list     — view all companions (仓库)
  /buddy select N  — switch active companion to #N
  /buddy mute     — mute companion reactions
  /buddy unmute   — unmute companion reactions
"""
from __future__ import annotations

import time
import uuid

from rich.console import Console
from rich.live import Live
from rich.text import Text
from ..llm import LLMClient
from ..i18n import DEFAULT_LOCALE, t

from .companion import companion_user_id, get_companion, get_all_companions, roll, roll_with_seed
from .render import render_companion_card, render_hatch_animation, render_compact_status, render_companion_list
from .storage import (
    load_active_index,
    load_companion_muted,
    save_active_index,
    save_companion_muted,
    save_new_companion,
    save_stored_companion,
)
from .types import CompanionBones, CompanionSoul


def _buddy_hatch_start_message(is_new: bool, locale: str = DEFAULT_LOCALE) -> str:
    key = 'buddy.hatch.start.new' if is_new else 'buddy.hatch.start.existing'
    return t(locale, key)


def _buddy_hatch_failed_message(error: str, locale: str = DEFAULT_LOCALE) -> str:
    return t(locale, 'buddy.hatch.failed', error=error)


def _buddy_select_usage_message(locale: str = DEFAULT_LOCALE) -> str:
    return t(locale, 'buddy.select.usage')


def _buddy_select_invalid_number_message(count: int, locale: str = DEFAULT_LOCALE) -> str:
    return t(locale, 'buddy.select.invalid', count=count)


def _buddy_select_switched_message(index: int, name: str, species: str, locale: str = DEFAULT_LOCALE) -> str:
    return t(locale, 'buddy.select.switched', index=index, name=name, species=species)


def _buddy_usage_message(locale: str = DEFAULT_LOCALE) -> str:
    return t(locale, 'buddy.usage')


def _buddy_pet_reaction_message(name: str, locale: str = DEFAULT_LOCALE) -> str:
    return t(locale, 'buddy.pet.reaction', name=name)


def _buddy_mood_title(name: str, locale: str = DEFAULT_LOCALE) -> str:
    return t(locale, 'buddy.mood.title', name=name)


def _buddy_mood_level_label(level: str, locale: str = DEFAULT_LOCALE) -> str:
    return t(locale, f'buddy.mood.level.{level}')


def _buddy_dominant_mood_message(mood: str, locale: str = DEFAULT_LOCALE) -> str:
    return t(locale, 'buddy.mood.dominant', mood=mood)

def _generate_soul(
    bones: CompanionBones,
    client: LLMClient,
    model: str,
) -> CompanionSoul:
    """Call the configured LLM to generate a name and personality."""
    stats_desc = ', '.join(f'{k}={v}' for k, v in bones.stats.items())
    shiny_note = ' This is an extremely rare SHINY companion!' if bones.shiny else ''

    prompt = (
        f'You are naming a new companion pet. It is a {bones.rarity} {bones.species} '
        f'with these stats: {stats_desc}. Its eye style is {bones.eye} and '
        f'it wears a {bones.hat} hat.{shiny_note}\n\n'
        f'Generate:\n'
        f'1. A short, creative name (1-2 words, no quotes)\n'
        f'2. A one-sentence personality description (under 80 chars)\n\n'
        f'Format your response EXACTLY as:\n'
        f'NAME: <name>\n'
        f'PERSONALITY: <personality>'
    )

    response = client.create_message(
        model=model,
        max_tokens=100,
        messages=[{'role': 'user', 'content': prompt}],
    )

    text = ""
    for block in response.content:
        if isinstance(block, dict) and block.get("type") == "text":
            text += block.get("text", "")
    text = text.strip()
    name = 'Buddy'
    personality = f'A mysterious {bones.species}.'

    for line in text.split('\n'):
        line = line.strip()
        if line.upper().startswith('NAME:'):
            name = line.split(':', 1)[1].strip()
        elif line.upper().startswith('PERSONALITY:'):
            personality = line.split(':', 1)[1].strip()

    return CompanionSoul(name=name, personality=personality)


def _hatch(client: LLMClient, console: Console, model: str, locale: str = DEFAULT_LOCALE) -> None:
    """Hatch a new companion: generate bones, call API for soul, save, animate."""
    roll.cache_clear()  # ensure fresh roll (seed may have changed)
    user_id = companion_user_id()
    r = roll(user_id)
    bones = r.bones

    console.print(f'\n[dim]{_buddy_hatch_start_message(False, locale)}[/dim]')

    try:
        soul = _generate_soul(bones, client, model)
    except Exception as e:
        console.print(f"[red]{_buddy_hatch_failed_message(str(e), locale)}[/red]")
        # Fallback soul
        soul = CompanionSoul(
            name='Buddy',
            personality=f'A quiet {bones.species} who prefers actions over words.',
        )

    save_stored_companion(soul)
    render_hatch_animation(bones, soul, console, locale=locale)

    companion = get_companion()
    if companion:
        render_companion_card(companion, console, locale=locale)


def _hatch_new(client: LLMClient, console: Console, model: str, locale: str = DEFAULT_LOCALE) -> None:
    """Hatch an additional random companion with a unique seed."""
    seed = f'buddy-new-{uuid.uuid4()}'
    r = roll_with_seed(seed)
    bones = r.bones

    console.print(f'\n[dim]{_buddy_hatch_start_message(True, locale)}[/dim]')

    try:
        soul = _generate_soul(bones, client, model)
    except Exception as e:
        console.print(f"[red]{_buddy_hatch_failed_message(str(e), locale)}[/red]")
        soul = CompanionSoul(
            name='Buddy',
            personality=f'A quiet {bones.species} who prefers actions over words.',
        )

    save_new_companion(soul, seed)
    render_hatch_animation(bones, soul, console, locale=locale)

    companion = get_companion()
    if companion:
        render_companion_card(companion, console, locale=locale)


def _pet_animation(console: Console, locale: str = DEFAULT_LOCALE) -> None:
    """Show a heart animation when petting the companion.

    Matches CompanionSprite.tsx PET_HEARTS: 5-frame heart float
    animation over 2.5 seconds with fading dots at the end.
    """
    companion = get_companion()
    if not companion:
        return

    from .sprites import render_sprite
    from .types import RARITY_COLORS

    color = RARITY_COLORS.get(companion.rarity, 'dim')
    bones = CompanionBones(
        rarity=companion.rarity, species=companion.species,
        eye=companion.eye, hat=companion.hat,
        shiny=companion.shiny, stats=companion.stats,
    )

    # Match CompanionSprite.tsx PET_HEARTS — hearts float up and fade to dots
    H = '\u2764'
    pet_hearts = [
        f'   {H}    {H}   ',
        f'  {H}  {H}   {H}  ',
        f' {H}   {H}  {H}   ',
        f'{H}  {H}      {H} ',
        '\u00b7    \u00b7   \u00b7  ',
    ]

    # Excited mode: cycle through all sprite frames fast
    frame_count = len([f for f in [0, 1, 2]])

    with Live(console=console, refresh_per_second=4, transient=True) as live:
        for i, heart_line in enumerate(pet_hearts):
            sprite_lines = render_sprite(bones, frame=i % 3)
            # Build rich Text with proper styling (not markup strings)
            frame_text = Text()
            frame_text.append(f'  {heart_line}\n', style='bold red')
            for sl in sprite_lines:
                frame_text.append(f'  {sl}\n', style=color)
            live.update(frame_text)
            time.sleep(0.5)

    console.print(f"[dim]{_buddy_pet_reaction_message(companion.name, locale)}[/dim]")

    # Pet boosts mood
    try:
        from .mood import apply_events, apply_decay
        from .storage import load_active_mood, save_active_mood
        now_ms = int(time.time() * 1000)
        mood = load_active_mood()
        mood = apply_decay(mood, now_ms)
        mood = apply_events(mood, ['pet'])
        save_active_mood(mood)
    except Exception:
        pass


def _render_mood(companion, console: Console, locale: str = DEFAULT_LOCALE) -> None:
    """Show mood detail for a companion."""
    from .types import RARITY_COLORS, MOOD_DIMENSIONS, MOOD_NEUTRAL
    from .render import _stat_bar

    color = RARITY_COLORS.get(companion.rarity, 'dim')
    mood = companion.mood
    console.print(f"\n[{color}]{_buddy_mood_title(companion.name, locale)}[/{color}]")
    for dim in MOOD_DIMENSIONS:
        val = getattr(mood, dim)
        bar = _stat_bar(val)
        if abs(val - MOOD_NEUTRAL) < 10:
            label = _buddy_mood_level_label('neutral', locale)
        elif val > MOOD_NEUTRAL:
            label = _buddy_mood_level_label('high', locale)
        else:
            label = _buddy_mood_level_label('low', locale)
        console.print(f'  {dim.capitalize():<10} {bar} {val:>3} ({label})')
    console.print(f"\n[dim]{_buddy_dominant_mood_message(mood.dominant().lower(), locale)}[/dim]")


def _render_help(console: Console, locale: str = DEFAULT_LOCALE) -> None:
    """Show all buddy commands and gameplay guide."""
    from rich.panel import Panel
    from rich.text import Text

    help_text = t(locale, "buddy.help.text")

    panel = Panel(
        help_text,
        title=t(locale, "buddy.help.title"),
        border_style="cyan",
        padding=(1, 2),
    )
    console.print(panel)


def handle_buddy_command(
    args: str,
    client: LLMClient,
    console: Console,
    model: str,
    locale: str = DEFAULT_LOCALE,
) -> None:
    """Handle /buddy commands."""
    subcmd = args.strip().lower()

    if subcmd == '':
        # Hatch or show card
        companion = get_companion()
        if companion:
            render_companion_card(companion, console, locale=locale)
        else:
            _hatch(client, console, model, locale=locale)

    elif subcmd == 'help':
        _render_help(console, locale=locale)

    elif subcmd == 'pet':
        companion = get_companion()
        if not companion:
            console.print(f"[dim]{t(locale, 'buddy.no_companion')}[/dim]")
        else:
            _pet_animation(console, locale=locale)

    elif subcmd == 'stats':
        companion = get_companion()
        if not companion:
            console.print(f"[dim]{t(locale, 'buddy.no_companion')}[/dim]")
        else:
            render_companion_card(companion, console, locale=locale)

    elif subcmd == 'mute':
        save_companion_muted(True)
        console.print(f"[dim]{t(locale, 'buddy.muted')}[/dim]")

    elif subcmd == 'unmute':
        save_companion_muted(False)
        console.print(f"[dim]{t(locale, 'buddy.unmuted')}[/dim]")

    elif subcmd == 'mood':
        companion = get_companion()
        if not companion:
            console.print(f"[dim]{t(locale, 'buddy.no_companion')}[/dim]")
        else:
            _render_mood(companion, console, locale=locale)

    elif subcmd == 'ia':
        from .poke_game import start_game
        start_game(client, console, model)

    elif subcmd == 'new':
        _hatch_new(client, console, model, locale=locale)

    elif subcmd == 'list':
        companions = get_all_companions()
        active = load_active_index()
        render_companion_list(companions, active, console, locale=locale)

    elif subcmd.startswith('select'):
        parts = subcmd.split()
        if len(parts) != 2 or not parts[1].isdigit():
            console.print(f"[dim]{_buddy_select_usage_message(locale)}[/dim]")
        else:
            n = int(parts[1])
            companions = get_all_companions()
            if n < 1 or n > len(companions):
                console.print(f"[dim]{_buddy_select_invalid_number_message(len(companions), locale)}[/dim]")
            else:
                idx = n - 1
                save_active_index(idx)
                comp = companions[idx]
                console.print(f"[bold]{_buddy_select_switched_message(n, comp.name, comp.species, locale)}[/bold]")
                render_companion_card(comp, console, locale=locale)

    else:
        console.print(f"[dim]{_buddy_usage_message(locale)}[/dim]")
