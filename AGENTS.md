# AGENTS.md

## Project Summary

This repository contains a self-hosted Discord productivity bot. The main runtime is `main.py`, and the preferred local development loop is `dev.py`, which restarts the bot when Python source files or `.env` change.

## Environment And Setup

- Shell in this workspace is PowerShell. Activate the virtual environment with:
  - `.\\.venv\\Scripts\\Activate.ps1`
- Install dependencies with:
  - `pip install -r packages.pip`
- The app reads configuration from the root `.env` via `config/env.py`.
- Do not commit or print secrets from `.env`, `credentials.json`, `token.json`, or similar auth files.

## Important Run Commands

- Start the bot once:
  - `python main.py`
- Start the autoreload dev loop:
  - `python dev.py`
- Audit or clean Discord application commands:
  - `python scripts/cleanup_app_commands.py`
  - `python scripts/cleanup_app_commands.py --apply`

## Code Layout

- `main.py`: bot bootstrap, extension loading, command sync behavior.
- `cogs/`: Discord cogs and slash-command registration.
- `classes/`: higher-level feature logic used by cogs.
- `services/`: shared helper logic and integration support.
- `views/`: Discord UI views and modals.
- `embeds/`: embed builders and presentation helpers.
- `config/`: environment, logging, and database setup.
- `cli_args/`: argument parsing helpers for command-style inputs.
- `docs/`: research notes and implementation planning docs.

## Code Style

- Write simple, readable code. Prefer straightforward control flow over clever abstractions.
- Do not overengineer. Add new helpers, classes, or indirection only when they clearly improve readability, reuse, or separation of concerns.
- Prefer established libraries for non-trivial functionality instead of building custom implementations from scratch, unless the requirement is simple enough that a small local implementation is clearly the cleaner option.
- Match the style of the surrounding file before introducing a new local pattern.
- Keep command handlers and cogs relatively thin when possible; place reusable business logic in `classes/` or `services/`.
- Keep functions focused, but do not split logic into many tiny helpers unless that clearly improves comprehension.
- Prefer explicit, descriptive names over short or ambiguous names.
- Add comments sparingly and only when they explain intent, constraints, or non-obvious behavior.
- Preserve existing user-facing command behavior unless the task explicitly requires changing it.

## Discord UX Guidelines

- Treat embeds and views as complementary, not interchangeable: use embeds for structured display and add views when the message represents an actionable state.
- Default to public responses when choosing between public and ephemeral replies. Use ephemeral only when the content is user-specific, sensitive, transient, or would create unnecessary channel noise.
- Keep Discord view code modular. Prefer one view or one closely related view family per Python file rather than growing a single mega-file for many unrelated views.
- When a user is likely to take a next step from a message, prefer buttons, selects, or modals over forcing them to run another command manually.
- For user input flows, prefer pop-up modals over ad hoc inline prompt messages when the interaction fits naturally into a modal.
- Before adding a new button or select, ask whether the action is truly common, safe, and useful enough to deserve persistent UI.
- Every interactive message should answer: what can the user do next without typing another command?
- Prefer low-noise interaction flows. Avoid ephemeral "success" or "done" confirmations when the same result can be shown by updating the original message, refreshing the view, or otherwise keeping the interaction self-contained.
- Avoid channel spam. Prefer editing an existing bot message or using a compact follow-up only when a visible state change is actually useful.
- Keep component layouts easy to scan: group related actions together and avoid overcrowding a message with too many controls at once.
- Prefer one clear primary action row over multiple crowded rows.
- Do not add buttons for rarely used or admin-only actions unless there is a strong UX reason.
- For destructive or high-impact actions, require a clearer confirmation path than for routine actions.
- If an interaction changes the state shown in a message, prefer updating that message so the embed and view stay in sync.
- Keep interactive messages stateful and self-refreshing where practical; avoid leaving stale buttons or views attached to outdated embeds.
- Disable, replace, or remove controls when the underlying action is no longer valid.
- For list or detail views, include refresh, back, or navigation actions when users are likely to iterate through the UI.
- If a modal is used, keep fields minimal and ask only for the information needed to complete the action.

## Restricted Areas

- `classes/CalendarFunctionsOLD.py` is legacy code. It is read-only by default and should not be modified unless the task explicitly targets that file or a legacy calendar migration.
- `cogs/DailyCronExampleCog.py` is example code and is not part of the normal runtime loaded by `main.py`. Do not modify it unless the task explicitly asks for that example flow.
- `cli_args/` is unused legacy parsing code in the current runtime. Treat it as read-only by default and do not modify it unless the task explicitly targets legacy calendar or parser behavior.
- The TickTick surface is currently dormant in this checkout:
  - `cogs/TickTickCog.py`
  - `classes/TickTickFunctions.py`
  - `embeds/TickTickEmbeds.py`
  These are read-only by default because `TICK_DISABLED` is enabled in the current environment and the repo review notes call this surface legacy or dormant. Only edit them when the task is explicitly about TickTick support, revival, removal, or migration.
- The alias surface is also currently dormant in this checkout:
  - `cogs/AliasCog.py`
  - `embeds/AliasEmbeds.py`
  - alias-specific paths in `cogs/TogglCog.py`
  Treat these as read-only unless the task is explicitly about aliases.
- `config/run_context.txt` is known to be stale relative to the live command tree. Do not use it as the source of truth for product behavior. Verify live command surfaces against `main.py` and the active cogs first, and only edit `run_context.txt` when the task is specifically about assistant routing or command documentation.

## Working Rules For Agents

- Keep changes surgical. Preserve existing command names, extension names, and startup behavior unless the task explicitly requires changing them.
- Prefer editing the smallest layer that owns the behavior:
  - command wiring in `cogs/`
  - business logic in `classes/` or `services/`
  - Discord UI behavior in `views/`
  - output formatting in `embeds/`
- When working on Discord components, modals, buttons, selects, or message layout, prefer the official Discord Component Reference first:
  - https://docs.discord.com/developers/components/reference
- Use that reference to verify component structure, field requirements, and current platform constraints before implementing or changing Discord UI behavior.
- Avoid reading or editing generated or noisy files unless the task is specifically about them:
  - `discord.log*`
  - `discord.deps.log`
  - `__pycache__/`
  - `assets/`
  - `tmp/`
- Treat `.env.example` as the template when adding new environment variables.
- If a change affects command registration or scope behavior, review `main.py` and `scripts/cleanup_app_commands.py` together.

## Validation

- There is no established unit test suite in this repo yet.
- For safe validation after Python edits, run:
  - `python -m compileall main.py cogs classes services views embeds config cli_args`
- If the change affects startup or command sync logic, also run the relevant startup or cleanup command when credentials are available.
- Do not claim tests passed unless you actually ran them.

## Notes

- This is a Windows checkout. Bash-style activation such as `source /c/.../activate` is not the native command here; use PowerShell activation instead.
- The repo may contain user-authored docs and in-progress notes in `docs/`, `ideas-to-do.md`, and `mvp.md`. Do not treat them as implementation unless the task calls for it.
