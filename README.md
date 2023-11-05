# About The project

The productivity bot is a self-hosted discord bot that helps users manage their time, tasks, and events more effectively. The bot connects to three popular APIs: Toggl, TickTick, and Google Calendar, and allows users to access their features through various commands.

With the productivity bot, users can:

- Track their time entries with Toggl. Users can start, stop, and view their time entries on Toggl, a time tracking app that helps users monitor their work hours and productivity.
- Manage their tasks and lists with TickTick. Users can create, delete, and view their tasks and lists on TickTick, a task management app that helps users organize their to-do lists and deadlines.
- Schedule and view their events and calendars with Google Calendar. Users can create, delete, and view their events and calendars on Google Calendar, a calendar app that helps users plan their meetings and appointments.

## Built with

- Python
- Discord.py
- Google Calendar API
- TickTick API
- Toggl API

# Getting started

To get started you need to complete the following steps.

## Prerequisites

- Python 3.10.7 or greater
- MongoDB database instance
- Discord bot token
- Google Calendar API credentials
- TickTick API credentials

## Installation

### Configuration

In order to provide API access to the bot, you need to create a `.env` file in the root directory of the project and add the following variables:

```bash
DISCORD_TOKEN

TOGGL_TOKEN

TICK_ID
TICK_SECRET
TICK_URI
TICK_EMAIL
TICK_PASSWORD

MONGO_USERNAME
MONGO_PASSWORD
```

### Setup

1. Provide `.env` file in the root directory of the project
2. Install Python and Pip
3. Clone the repository
   `git clone https://github.com/janmerhar/productivity_bot`
4. Install the required packages
   `pip install -r packages.txt`

## Usage

To start the bot run the following command:
`python main.py`

### Commands

Toggl commands:

- `aboutme` Returns information about the Toggl user.
- `start` Starts a new Toggl timer with an optional project and description.
- `timer` Returns information about the active Toggl timer.
- `stop` Stops the active Toggl timer.
- `inserttimer` Inserts a past Toggl timer.
- `savetimer` Saves a Toggl timer with an optional workspace ID, billable status, description, project ID, and tags.
- `removetimer` Removes a saved Toggl timer.
- `startsaved` Starts a saved Toggl timer by its identifier.
- `populartimers` Returns the most popular Toggl timers.
- `timerhistory` Returns a history of Toggl timers.
- `newproject` Creates a new Toggl project with a given name.
- `workspaceprojects` Returns all Toggl projects in the current workspace.
- `getproject` Returns a Toggl project by its ID.
- `createalias` Creates an alias for a Toggl command with optional arguments.

TickTick coommands:

- `newtask` Adds a new task to TickTick with optional parameters. This command takes several optional parameters, including project_id, content, desc, start_date, due_date, time_zone, reminders, repeat, priority, sort_order, and items.
- `newsubtask` Adds a new subtask to an existing task in TickTick with optional parameters. This command takes several optional parameters, including parent, project_id, content, desc, start_date, due_date, time_zone, reminders, repeat, priority, sort_order, and items.
- `complete` Marks a task as completed in TickTick. This command takes one required parameter: name (the name of the task to be completed).
- `updatetask` Updates an existing task in TickTick with optional parameters. This command takes several optional parameters, including name, project_id, content, desc, start_date, due_date, time_zone, reminders, repeat, priority, sort_order, and items.
- `movetask` Moves a task to a different list in TickTick. This command takes two required parameters: task_details (the name of the task to be moved) and list (the name of the destination list).
- `deletetask` Deletes a task from TickTick. This command takes one required parameter: name (the name of the task to be deleted).
- `getlist` Returns information about a list in TickTick. This command takes one required parameter: identifier (the name of the list to retrieve).
- `newlist` Creates a new list in TickTick with optional parameters. This command takes several optional parameters, including name, color, project_type, and folder_id.
- `changelist` Updates an existing list in TickTick with optional parameters. This command takes several optional parameters, including name, color, project_type, and folder_id.
- `deletelist` Deletes a list from TickTick. This command takes one required parameter: identifier (the name of the list to be deleted).

Alias commands:

- `usealias` Shortcuts use alias. This command takes one required parameter: alias (the alias of the command to be used).
- `findaliases` Shortcuts find aliases. This command takes one required parameter: alias (the alias of the command to be found).
- `popularalias` Most popular aliases. This command takes one optional parameter: n (the number of most popular aliases to display).

### Demo

![Toggl Example](docs/media/toggl_example.gif)

## Contributing

To contribute to this project follow these steps:

1. Fork the repository
2. Create feature branch (`git checkout -b feature/NewFeature`)
3. Commit changes (`git commit -m 'Add some changes'`)
4. Push to the branch (`git push origin feature/NewFeature`)
5. Open a pull request
