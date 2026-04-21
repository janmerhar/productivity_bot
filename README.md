# Productivity Bot

A Discord productivity bot for people and teams who want to manage work without leaving Discord.

It brings shared to-dos, personal reminders, habits, Pomodoro focus sessions, and Toggl time tracking into one bot, with support for both server channels and private workflows. The current bot covers to-dos with custom lists, assignees, and status tracking, reminders with flexible schedules and private destinations, habits with optional reminders, Pomodoro timers with voice playback, and Toggl timer, project, and tag management.

What makes it more useful than a plain command pack is the workflow design: messages can be turned into reminders, todos, Pomodoros, or timers from context-menu shortcuts, shared server workflows and private personal workflows both exist in the same bot, and common actions use buttons, selects, and modals instead of pushing everything through raw command syntax. It also includes `/assistant run` for translating natural language into existing slash commands.

## Quick Start

1. Create a root `.env` file. The current setup uses variables like:

```bash
DISCORD_TOKEN=
DEV_MODE=
DEV_GUILD_ID=
TICK_DISABLED=
MONGO_URI=
OPENAI_API_KEY=
POMODORO_AUDIO_VOLUME=
ALIAS_DISABLED=
```

2. Install dependencies:

```powershell
pip install -r packages.pip
```

3. Start the bot:

```powershell
python main.py
```

## Command Highlights

Core productivity commands:

- `/todo add`, `/todo overview`, `/todo assign`, `/todo complete`
- `/list create`, `/list show`, `/list directory`
- `/reminder add`, `/reminder list`, `/reminder pause`, `/reminder resume`
- `/habit add`, `/habit list`, `/habit mark`
- `/pomodoro start`, `/pomodoro active`, `/pomodoro pause`, `/pomodoro stop`
- `/toggl timer start`, `/toggl timer stop`, `/toggl project list`
- `/settings set timezone`, `/settings set toggl`
- `/bug report`, `/feature request`, `/assistant run`

Message shortcuts:

- `Create Reminder`
- `Add to Todo`
- `Add to Personal Todo`
- `Start Pomodoro`
- `Start Timer`

Parameters marked `?` are optional.

### To-dos

- `/todo overview sort?, status?, assignee?, visibility?`
- `/todo add todo, description?, due?, list?, status?, assignee?, notify_assignee?, visibility?`
- `/todo show todo, visibility?`
- `/todo edit todo, visibility?`
- `/todo status todo, status, visibility?`
- `/todo assign todo, assignee, visibility?`
- `/todo complete todo, visibility?`
- `/todo delete todo, visibility?`
- `/list show sort?, status?, list?, assignee?, visibility?`
- `/list directory scope?, visibility?`
- `/list create name, scope?, visibility?`
- `/list edit list, name, visibility?`
- `/list clear list?, visibility?`
- `/list delete list, visibility?`

### Reminders

- `/reminder add reminder, schedule, add_pings?, description?, expires?, destination?, visibility?`
- `/reminder list destination?, sort?, status?, visibility?`
- `/reminder show reminder, visibility?`
- `/reminder edit reminder, visibility?`
- `/reminder pause reminder, until?, visibility?`
- `/reminder resume reminder, visibility?`
- `/reminder remove reminder, visibility?`

### Habits

- `/habit add habit, description?, reminder?, destination?, visibility?`
- `/habit list status?, sort?, scope?, visibility?`
- `/habit show habit, visibility?`
- `/habit mark habit, status?, date?, visibility?`
- `/habit edit habit, visibility?`
- `/habit delete habit_name, visibility?`

### Pomodoro

- `/pomodoro start mode?, duration?, voice_channel?, autojoin?, visibility?`
- `/pomodoro active visibility?`
- `/pomodoro pause visibility?`
- `/pomodoro resume visibility?`
- `/pomodoro extend minutes?, visibility?`
- `/pomodoro stop visibility?`

### Toggl

- `/toggl account visibility?`
- `/toggl timer start project?, description?, billable?, visibility?`
- `/toggl timer active visibility?`
- `/toggl timer stop visibility?`
- `/toggl timer insert start, stop, project?, description?, tags?, billable?, visibility?`
- `/toggl timer list visibility?`
- `/toggl project create name, visibility?`
- `/toggl project list visibility?`
- `/toggl project get project, visibility?`
- `/toggl tag add name, visibility?`
- `/toggl tag show tag, visibility?`

### Core

- `/info`
- `/settings set timezone`
- `/settings set toggl`
- `/bug report visibility?`
- `/feature request visibility?`
- `/assistant run query, visibility?`

## Development

When `DEV_MODE=true` and `DEV_GUILD_ID` is set, the bot uses dev-mode command sync. In development mode commands are synced on each startup by default.

```bash
DEV_MODE=true
DEV_GUILD_ID=123456789012345678
```
