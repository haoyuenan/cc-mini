# UI Language Command Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Add a `/language` command that switches the terminal interface language to Chinese while keeping the design extensible for more locales later.

**Architecture:** Introduce a lightweight `i18n` module for message lookup and locale normalization, treat interface language as session-local UI state instead of model behavior, and thread that locale through `main.py`, `commands.py`, and later fixed buddy UI strings. Persist the locale in session metadata so `/resume` restores the same interface language, while `/clear` resets to the default locale for a new session.

**Tech Stack:** Python 3.11+, `rich`, `prompt_toolkit`, JSON session metadata, `pytest`

---

### Task 1: Add a lightweight i18n foundation

**Objective**

Create a single source of truth for supported locales, locale aliases, and fixed UI message strings so the codebase stops hardcoding English UI text inline.

**Preconditions or dependency**

- None

**Exact file path(s)**

- Create: `d:\Work\Projects\cc-mini\src\core\i18n.py`

**Exact edit instructions or full code to insert/replace**

- Create a new module with:
  - `DEFAULT_LOCALE = "en"`
  - canonical locale keys for at least `en` and `zh-CN`
  - alias normalization for `zh`, `zh-cn`, `cn`, `chinese`, `中文`, `简体中文`, plus `en`, `english`
  - `normalize_locale(value: str | None) -> str | None`
  - `is_supported_locale(value: str | None) -> bool`
  - `available_locales() -> list[str]`
  - `t(locale: str, key: str, **kwargs) -> str`
- Implement messages as nested dictionaries keyed by stable message IDs, not ad hoc `if lang == ...` branches.
- Add only the first batch of message keys needed by core REPL and slash commands, for example:
  - `repl.spinner.thinking`
  - `repl.spinner.preparing_tool`
  - `repl.goodbye`
  - `repl.ctrlc_exit_hint`
  - `repl.bottom.chat_hint`
  - `repl.bottom.terminal_hint`
  - `commands.help.title`
  - `commands.history.title`
  - `commands.resume.usage`
  - `commands.session.not_found`
  - `commands.unknown`
  - `commands.language.current`
  - `commands.language.updated`
  - `commands.language.unsupported`
- Use format placeholders like `{name}`, `{locale}`, `{count}` instead of concatenating localized fragments in calling code.
- Keep the public API small; do not add a heavyweight class hierarchy.

**Verification command(s) or manual checks**

- Manual: read `src/core/i18n.py` and confirm all first-phase keys live in one place.
- Manual: confirm no message text is embedded in helper function names or locale conditionals.

**Done condition**

- A new `i18n.py` exists and can translate core UI keys for English and Chinese.
- Locale alias normalization is centralized and reusable.

**Estimated size**

- 2-5 minutes

---

### Task 2: Write focused tests for locale normalization and translation lookup

**Objective**

Lock down the new i18n behavior before wiring it through the UI.

**Preconditions or dependency**

- Task 1 completed

**Exact file path(s)**

- Create: `d:\Work\Projects\cc-mini\tests\test_i18n.py`

**Exact edit instructions or full code to insert/replace**

- Add pytest tests for:
  - `normalize_locale("zh") == "zh-CN"`
  - `normalize_locale("中文") == "zh-CN"`
  - `normalize_locale("en") == "en"`
  - unsupported values return `None`
  - `t("zh-CN", "repl.goodbye")` returns Chinese text
  - `t("en", "repl.goodbye")` returns English text
  - missing locale falls back to English if you decide to support fallback behavior
  - missing key raises a clear exception or returns a clearly deliberate fallback; choose one behavior and test it explicitly
- Keep the test file small and self-contained; do not involve the engine or terminal rendering.

**Verification command(s) or manual checks**

```powershell
Set-Location D:\Work\Projects\cc-mini
.\.venv\Scripts\python.exe -m pytest tests\test_i18n.py -v
```

**Done condition**

- `tests/test_i18n.py` passes.
- Locale aliases and message lookup behavior are pinned by tests.

**Estimated size**

- 2-5 minutes

---

### Task 3: Persist interface locale in session metadata

**Objective**

Allow `/resume` to restore the same interface language by saving locale in `SessionMeta`.

**Preconditions or dependency**

- Task 1 completed

**Exact file path(s)**

- Modify: `d:\Work\Projects\cc-mini\src\core\session.py`
- Create: `d:\Work\Projects\cc-mini\tests\test_session.py`

**Exact edit instructions or full code to insert/replace**

- In `src/core/session.py`:
  - add `locale: str | None = None` to `SessionMeta`
  - update `SessionStore.__init__` to accept `locale: str | None = None`
  - store `self.locale`
  - include `locale=self.locale` when writing metadata in `_save_meta()`
- Preserve backward compatibility:
  - `SessionMeta(**data)` must still work for old metadata files without `locale`
  - if needed, load JSON into a dict and inject `locale=None` when missing before constructing `SessionMeta`
- In `tests/test_session.py`:
  - add a round-trip test that writes session metadata with locale `zh-CN` and reloads it
  - add a compatibility test that loads an older `.meta.json` without `locale` and confirms it defaults to `None`

**Verification command(s) or manual checks**

```powershell
Set-Location D:\Work\Projects\cc-mini
.\.venv\Scripts\python.exe -m pytest tests\test_session.py -v
```

**Done condition**

- Session metadata can save and restore locale.
- Older saved sessions without locale still load successfully.

**Estimated size**

- 2-5 minutes

---

### Task 4: Thread locale through the REPL runtime state in `main.py`

**Objective**

Create one authoritative current-locale value for the active session and make it available wherever the REPL renders UI text.

**Preconditions or dependency**

- Tasks 1 and 3 completed

**Exact file path(s)**

- Modify: `d:\Work\Projects\cc-mini\src\core\main.py`

**Exact edit instructions or full code to insert/replace**

- Introduce a `session_locale` variable near session initialization.
  - Default it to `DEFAULT_LOCALE` from `core.i18n`
  - When resuming a session, if `meta.locale` exists, restore it into `session_locale`
- Update `SessionStore(...)` constructions to pass `locale=session_locale`
- Add a small helper function inside `main()` for locale-aware string lookup, for example a closure that calls `t(session_locale, key, **kwargs)`.
- Update `_build_system_prompt_for_mode()` **not at all** for locale; this feature is UI-only.
- Update `_apply_session_mode()` so it does not overwrite locale.
- When `/clear` creates a new session store, reset locale to the default locale before creating that new session.
- When `/resume` reconstructs `SessionStore`, include the restored locale value.
- Extend `CommandContext` creation so commands can read and mutate the active locale through fields like:
  - `locale`
  - `set_locale`
  - optional `translate`
- Keep locale state local to the interactive session; do not couple it to `AppConfig` yet.

**Verification command(s) or manual checks**

- Manual: inspect `main.py` and confirm locale is treated separately from model/provider state.
- Manual: verify `/clear` path resets locale state when it builds a fresh session.

**Done condition**

- `main.py` has one active locale source of truth.
- Commands have a safe way to read/update the UI locale.

**Estimated size**

- 2-5 minutes

---

### Task 5: Add the `/language` slash command and localize core command text

**Objective**

Introduce the user-facing locale switch command and convert the most important slash-command UI strings to use i18n keys.

**Preconditions or dependency**

- Tasks 1 and 4 completed

**Exact file path(s)**

- Modify: `d:\Work\Projects\cc-mini\src\core\commands.py`
- Create: `d:\Work\Projects\cc-mini\tests\test_commands.py`

**Exact edit instructions or full code to insert/replace**

- In `src/core/commands.py`:
  - extend `CommandContext` with locale-related fields needed by commands, for example:
    - `locale: str`
    - `translate: object` or a callable translator
    - `set_locale: object` or a callable setter
  - add a new `_cmd_language(ctx, args)` handler
  - command behavior:
    - `/language` shows current interface language and supported options
    - `/language zh` / `/language 中文` normalize to `zh-CN`
    - `/language en` switches back to English
    - unsupported input prints a localized error and does not change state
  - update `_COMMAND_TABLE` to register `language`
  - replace hardcoded text in the highest-traffic command paths with i18n lookups:
    - help table title
    - history table title
    - resume usage
    - session not found
    - unknown command
    - clear confirmation
    - cost/model informational text where practical in first phase
- In `tests/test_commands.py`:
  - create small unit tests around `_cmd_language` or `handle_command`
  - use a fake context with a mutable locale holder and mock console
  - verify:
    - `/language` reports current locale
    - `/language zh` updates locale to `zh-CN`
    - `/language 中文` also updates locale to `zh-CN`
    - unsupported locale prints an error and leaves locale unchanged

**Verification command(s) or manual checks**

```powershell
Set-Location D:\Work\Projects\cc-mini
.\.venv\Scripts\python.exe -m pytest tests\test_commands.py -v
```

**Done condition**

- `/language` exists and works for Chinese.
- Core slash-command UI strings no longer rely on English hardcoding in the edited paths.

**Estimated size**

- 2-5 minutes

---

### Task 6: Localize REPL chrome in `main.py`

**Objective**

Translate the visible REPL shell around the conversation: spinner text, bottom hints, startup lines, exit/cancel messages, and slash autocomplete descriptions.

**Preconditions or dependency**

- Tasks 1, 4, and 5 completed

**Exact file path(s)**

- Modify: `d:\Work\Projects\cc-mini\src\core\main.py`
- Modify: `d:\Work\Projects\cc-mini\tests\test_main.py`

**Exact edit instructions or full code to insert/replace**

- In `src/core/main.py`:
  - update `_SlashCommandCompleter.BUILTIN_COMMANDS` descriptions to come from i18n-aware data instead of fixed English literals
  - localize `_SpinnerManager` default text and updates:
    - `Thinking…`
    - `Preparing tool call…`
  - localize bottom toolbar hints inside `_bordered_prompt()`
  - localize visible status strings such as:
    - goodbye text
    - cancel text
    - worker update text if included in phase one
    - `Session not found` in resume path
  - localize REPL startup banner notes where practical
- In `tests/test_main.py`:
  - add or extend tests so `run_query()` still prints streamed text correctly after spinner strings are localized
  - add a focused test for the slash completer descriptions or a helper you extract for localized built-in command metadata
- Keep the rendering API stable; do not rewrite the prompt_toolkit layout just to localize strings.

**Verification command(s) or manual checks**

```powershell
Set-Location D:\Work\Projects\cc-mini
.\.venv\Scripts\python.exe -m pytest tests\test_main.py -v
```

**Done condition**

- Core REPL UI text is locale-aware.
- Existing `run_query()` behavior remains intact.

**Estimated size**

- 2-5 minutes

---

### Task 7: Localize fixed `/buddy` command UI text as phase-two surface within the same feature

**Objective**

Make the most obvious buddy UI strings follow the same locale without changing buddy gameplay logic or generated pet names/personalities.

**Preconditions or dependency**

- Tasks 1 and 4 completed
- Preferably after Tasks 5 and 6 so the i18n pattern is established

**Exact file path(s)**

- Modify: `d:\Work\Projects\cc-mini\src\core\buddy\commands.py`
- Create: `d:\Work\Projects\cc-mini\tests\test_buddy_commands.py`

**Exact edit instructions or full code to insert/replace**

- Update `handle_buddy_command(...)` to accept locale access in the least invasive way.
  - Preferred: add a `locale: str = DEFAULT_LOCALE` parameter and pass it from `main.py`
  - Avoid reading global mutable state from inside buddy code
- Replace only fixed UI strings with i18n lookups, including:
  - `Hatching your companion...`
  - `Failed to generate companion soul`
  - `No companion yet. Type /buddy to hatch one!`
  - `Companion reactions muted/unmuted`
  - usage and invalid-number messages
  - mood header labels (`neutral`, `high`, `low`, `Dominant mood`)
  - help panel title and static help text
- Do **not** localize generated LLM companion names/personalities in this task.
- In `tests/test_buddy_commands.py`:
  - add targeted tests for no-companion and usage output under Chinese locale
  - add one help-render smoke test if practical, asserting Chinese help text appears

**Verification command(s) or manual checks**

```powershell
Set-Location D:\Work\Projects\cc-mini
.\.venv\Scripts\python.exe -m pytest tests\test_buddy_commands.py -v
```

**Done condition**

- Buddy fixed UI strings can render in Chinese.
- Buddy logic still works without changing model behavior.

**Estimated size**

- 2-5 minutes

---

### Task 8: Document the feature and usage expectations

**Objective**

Explain what `/language` changes, what it does not change, and how locale persistence works.

**Preconditions or dependency**

- Tasks 5 and 6 completed

**Exact file path(s)**

- Modify: `d:\Work\Projects\cc-mini\README.md`
- Modify: `d:\Work\Projects\cc-mini\docs\configuration.md`

**Exact edit instructions or full code to insert/replace**

- In `README.md`:
  - add `/language` to the slash command table with wording like “Switch interface language”
  - add one short example such as `/language zh`
- In `docs/configuration.md`:
  - add a short section clarifying:
    - `/language` changes interface language only
    - model reply language still follows user input / model behavior unless a separate feature is added later
    - session resume restores locale if saved
    - `/clear` starts a new session with the default locale
- Do not document a config/env default locale yet unless that feature is implemented in this same branch.

**Verification command(s) or manual checks**

- Manual: confirm docs never claim `/language` changes model output language.
- Manual: confirm examples use `/language zh` and not an unimplemented alias command.

**Done condition**

- User-facing docs accurately describe the feature scope.

**Estimated size**

- 2-5 minutes

---

### Task 9: End-to-end interactive verification pass

**Objective**

Verify the feature behaves correctly across REPL startup, command switching, session clear, and resume.

**Preconditions or dependency**

- Tasks 1 through 8 completed

**Exact file path(s)**

- No new files required
- Use the already modified files from previous tasks

**Exact edit instructions or full code to insert/replace**

- No code changes; this is a verification-only task.
- Perform this sequence manually in the REPL:
  1. start `cc-mini`
  2. run `/language zh`
  3. open `/help` and confirm Chinese interface text appears
  4. run `/history` or `/clear` and confirm localized feedback
  5. switch back with `/language en`
  6. set `/language zh`, exit, resume the same session, and confirm locale is restored
  7. run `/buddy help` after the buddy phase is implemented and confirm Chinese fixed strings render
- If tests expose unrelated existing repository failures, keep verification focused on the new targeted test files and manual REPL checks.

**Verification command(s) or manual checks**

```powershell
Set-Location D:\Work\Projects\cc-mini
.\.venv\Scripts\python.exe -m pytest tests\test_i18n.py tests\test_session.py tests\test_commands.py tests\test_main.py tests\test_buddy_commands.py -v
.\.venv\Scripts\cc-mini.exe
```

**Done condition**

- Interface language switching works in the REPL.
- Locale survives `/resume` and resets on `/clear`.
- The feature scope matches documentation.

**Estimated size**

- 2-5 minutes

---

## Final verification

Run these checks after all tasks are complete:

```powershell
Set-Location D:\Work\Projects\cc-mini
.\.venv\Scripts\python.exe -m pytest tests\test_i18n.py tests\test_session.py tests\test_commands.py tests\test_main.py tests\test_buddy_commands.py -v
.\.venv\Scripts\cc-mini.exe --help
```

Manual end-to-end checks:

1. Start `cc-mini` in interactive mode.
2. Confirm default UI is English in a fresh session.
3. Run `/language zh` and confirm:
   - spinner text is Chinese
   - `/help` title and descriptions are Chinese
   - bottom toolbar hints are Chinese
   - common status messages are Chinese
4. Run `/clear` and confirm locale resets to default for the new session.
5. Start another session, switch to Chinese, exit, resume it, and confirm locale restoration.
6. If buddy localization is included in the implementation scope, run `/buddy help` and `/buddy mood` to confirm fixed UI text is Chinese.

Repository note:

- Do not use the full unfiltered Windows test suite as the only success signal; this repository already has unrelated Windows failures.
- Treat the targeted tests above and manual REPL verification as the acceptance gate for this feature.
