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

You can still override any value from PowerShell for one run:

```powershell
$env:DISCORD_E2E_MUTATING="true"
npm.cmd --prefix tests/e2e run e2e
```

`DISCORD_E2E_ASSERT_LOG=true` makes tests check this repo's bot log for the received command. `DISCORD_E2E_MUTATING=true` enables tests that create todo, habit, and pomodoro data in the configured test server/database.

## Current coverage

Default read-only smoke commands:

- `/info`
- `/todo overview`
- `/list directory`
- `/reminder list`
- `/habit list`
- `/pomodoro active`

Opt-in mutating smoke commands:

- `/todo add`
- `/habit add`
- `/pomodoro start`
- `/pomodoro stop`
