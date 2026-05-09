# Discord Web E2E Smoke Tests

This suite uses Playwright to exercise the bot through Discord Web. Treat it as a live smoke test, not a replacement for cheaper Python-level validation.

## One-time setup

Install Node dependencies and the Chromium browser:

```powershell
npm.cmd --prefix tests/e2e install
npm.cmd --prefix tests/e2e run e2e:install
```

Create a dedicated Discord test server, add the bot, and create one test channel. Configure the bot for fast guild command sync:

```powershell
DEV_MODE=true
DEV_GUILD_ID=<test guild id>
MONGO_DB=productivity_bot_e2e
```

Then start the bot:

```powershell
python main.py
```

Copy the E2E env template and fill in the Discord test target:

```powershell
Copy-Item tests/e2e/.env.example tests/e2e/.env
```

## Save Discord browser auth

Use a dedicated test Discord user account. Do not store or use a Discord user token.

```powershell
npm.cmd --prefix tests/e2e run e2e:auth
```

Log in in the opened browser window. Playwright saves browser cookies and local storage to `tests/e2e/.auth/discord-user.json`, which is ignored by git.

## Run smoke tests

Set the target guild and channel in `tests/e2e/.env`, then run:

```powershell
npm.cmd --prefix tests/e2e run e2e
```

`DISCORD_E2E_ASSERT_LOG=true` makes tests check this repo's bot log for the received command. Some tests create todo, habit, reminder, jobs, and pomodoro data in the configured test server/database.

Optional feature flags:

- `DISCORD_E2E_JOBS_ENABLED=true` when `JOBS_COMMANDS_DISABLED=false`
- `DISCORD_E2E_TOGGL_MUTATING=true` only with a dedicated Toggl test account
- `DISCORD_E2E_TOGGL_SAVED_ENABLED=true` when `TOGGL_SAVED_DISABLED=false`
- `DISCORD_E2E_ALIAS_ENABLED=true` when `ALIAS_DISABLED=false`

## Current coverage

Command smoke specs are grouped under `specs/commands` by bot feature:

- `settings.spec.ts`
- `todo.spec.ts`
- `reminder.spec.ts`
- `habit.spec.ts`
- `pomodoro.spec.ts`
- `toggl.spec.ts`
- `jobs.spec.ts`
- `assistant.spec.ts`
- `bug-report.spec.ts`
- `feature-request.spec.ts`
