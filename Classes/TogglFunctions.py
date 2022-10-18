from ast import List
import pymongo
from pymongo import MongoClient
from typing import Dict, Optional, Tuple, Union
import requests
from dateutil import parser
import datetime
import json
from bson.objectid import ObjectId

from dotenv import dotenv_values
env = dotenv_values(".env")


class TogglFunctions:
    def __init__(self, API_KEY: str):
        self.auth = (API_KEY, "api_token")
        self.workspace_id = self.aboutMe()["default_workspace_id"]
        # save a default project/workspace id
        # and have functions to change them

        # add implementation for API_KEY and email:passwd authentications
        client = pymongo.MongoClient(
            f"mongodb+srv://{env['MONGO_USERNAME']}:{env['MONGO_PASSWORD']}@cluster0.puvwbmu.mongodb.net/?retryWrites=true&w=majority")
        self.mongo_commands = client["productivity_bot"]["custom_commands"]
        self.mongo_aliases = client["productivity_bot"]["aliases"]

        self.custom_commands = []
        self.updateSavedTimers()

    #
    # Authentication
    # https://developers.track.toggl.com/docs/authentication
    #

    def aboutMe(self):
        res = requests.get(
            'https://api.track.toggl.com/api/v9/me', auth=self.auth)
        return res.json()
    #
    # Tracking
    # https://developers.track.toggl.com/docs/tracking
    #

    def startCurrentTimeEntry(self, workspace_id, billable=None, description=None,
                              pid=None, tags=[], tid=None,):

        start_date = datetime.datetime.utcnow().replace(
            tzinfo=datetime.timezone.utc).isoformat()

        json_data = {
            'created_with': 'API example code',
            'workspace_id': workspace_id,
            'project_id': pid,
            'pid': pid,
            'tid': tid,
            'description': description,
            'tags': tags,
            'billable': billable,
            'duration': -1663338980,
            'wid': workspace_id,
            'at': start_date,
            "server_deleted_at": None,
            'start': start_date,
            "duronly": False,
        }

        res = requests.post(
            'https://api.track.toggl.com/api/v9/time_entries', json=json_data, auth=self.auth)
        return res.json()

    def getCurrentTimeEntry(self):
        res = requests.get('https://api.track.toggl.com/api/v9/me/time_entries/current',
                           headers={'Content-Type': 'application/json'}, auth=self.auth)
        return res.json()

    def stopCurrentTimeEntry(self):
        currentTask = self.getCurrentTimeEntry()

        if currentTask is None:
            return

        time_entry_id = self.getCurrentTimeEntry()["id"]
        workspace_id = self.getCurrentTimeEntry()["wid"]

        res = requests.patch(f'https://api.track.toggl.com/api/v9/workspaces/{workspace_id}/time_entries/{time_entry_id}/stop', headers={
                             'Content-Type': 'application/json'}, auth=self.auth)
        return res.json()

    def insertTimeEntry(self, workspace_id, billable=None, created_with="curl", description=None,
                        duration=None, duronly=None, pid=None, postedFields=[], project_id=None,
                        start=None, start_date=None, stop=None, tag_action=None, tag_ids=[],
                        tags=[], task_id=None, tid=None, uid=None, user_id=None):

        json_data = {
            'billable': billable,
            'created_with': created_with,
            'description': description,
            'duration': duration,
            'duronly': duronly,
            'pid': pid,
            'postedFields': postedFields,
            'project_id': project_id,
            'start': start,
            'start_date': start_date,
            'stop': stop,
            'tag_action': tag_action,
            'tag_ids': tag_ids,
            'tags': tags,
            'task_id': task_id,
            'tid': tid,
            'uid': uid,
            'user_id': user_id,
            'workspace_id': workspace_id,
        }

        res = requests.post(
            f'https://api.track.toggl.com/api/v9/workspaces/{workspace_id}/time_entries', json=json_data, auth=self.auth)
        return res.json()

    def getTimeEntryHistory(self, start_date, end_date):
        # Start date and end date cannot be the same
        # update end date to +1 day
        if start_date == end_date:
            tmp_date = parser.parse(start_date)
            tmp_date = tmp_date + datetime.timedelta(days=1)
            end_date = tmp_date.strftime("%Y-%m-%d")

        params = {
            'start_date': start_date,
            'end_date': end_date,
        }

        res = requests.get('https://api.track.toggl.com/api/v9/me/time_entries',
                           params=params, headers={'Content-Type': 'application/json'}, auth=self.auth)
        return res.json()

    def getLastNTimeEntryHistory(self, n) -> List:
        res = requests.get('https://api.track.toggl.com/api/v9/me/time_entries',
                           headers={'Content-Type': 'application/json'}, auth=self.auth)
        entries = res.json()
        return entries[0:n] if len(entries) >= n else entries

    #
    # Saved timers
    # mongoDB
    #

    def saveTimer(self, command, workspace_id=None, billable=None, description=None,
                  project=None, tags=[], tid=None,):

        if project is None:
            project_data = None
            pid = None
        else:
            workspace_id = workspace_id if workspace_id is not None else self.workspace_id
            project_data = self.getProjectById(
                workspace_id=workspace_id, project_id=project)
            pid = project_data["id"] if project_data["id"] is not None else None

        data = {
            "command": command,
            "application": "toggl",
            "number_of_runs": 0,
            "project": project_data,
            "param": {
                "workspace_id": workspace_id if workspace_id is not None else self.workspace_id,
                "billable": billable,
                "description": description,
                "pid": pid,
                "tags": tags,
                "tid": tid
            }
        }

        res = self.mongo_commands.insert_one(data)
        self.updateSavedTimers()

        return res.inserted_id

    def updateSavedTimers(self):
        search = {
            "application": "toggl"
        }

        commands = list(self.mongo_commands.find(search))
        self.custom_commands = commands

        return commands

    def startSavedTimer(self, command: str) -> Union[None, int]:
        # Cheking for ative timer
        current_timer = self.getCurrentTimeEntry()

        # Stopping an active timer
        if current_timer is not None:
            self.stopCurrentTimeEntry()

        # Search for the timer in database
        search_timer = self.mongo_commands.find_one({"command": command})

        # Not starting the timer if it is not found in database
        if search_timer is None:
            return None

        self.startCurrentTimeEntry(**search_timer["param"])
        # Increment number_of_runs
        search_param = {"_id": search_timer["_id"]}
        update_param = {"$inc": {"number_of_runs": 1}}

        res = self.mongo_commands.update_one(search_param, update_param)
        return search_timer["param"]

    def mostCommonlyUsedTimers(self, n: int):
        search_param = {"application": "toggl"}

        res = self.mongo_commands.find(search_param, limit=n).sort(
            "number_of_runs", -1)

        return list(res)

    def findSavedTimer(self, identifier: str):
        res_command = list(self.mongo_commands.find({"command": identifier}))

        if len(res_command) == 0:
            try:
                search_id = ObjectId(identifier)
            except:
                return None

            res_id = list(self.mongo_commands.find({"_id": search_id}))

            if len(res_id) == 0:
                return None
            else:
                return res_id[0]
        else:
            return res_command[0]

    def removeSavedTimer(self, identifier: str) -> bool:
        timer = self.findSavedTimer(identifier)

        if timer is None:
            return False
        else:
            self.mongo_commands.delete_one({"_id": timer["_id"]})
            return True

    #
    # Workspace
    # https://developers.track.toggl.com/docs/workspace
    #

    def getWorkspaces(self):
        res = requests.get('https://api.track.toggl.com/api/v9/workspaces',
                           headers={'Content-Type': 'application/json'}, auth=self.auth)
        return res.json()

    #
    # Projects
    # https://developers.track.toggl.com/docs/projects
    #

    def createProject(self, workspace_id, name, active=True, auto_estimates=None, billable=None,
                      color=None, currency="EUR", estimated_hours=1, is_private=None, template=None):
        json_data = {
            'active': active,
            'auto_estimates': auto_estimates,
            'billable': billable,
            'color': color,
            'currency': currency,
            'estimated_hours': estimated_hours,
            'is_private': is_private,
            'name': name,
            'template': template,
        }

        res = requests.post(
            f'https://api.track.toggl.com/api/v9/workspaces/{workspace_id}/projects', json=json_data, auth=self.auth)
        return res.json()

    def getAllProjects(self):
        res = requests.get('https://api.track.toggl.com/api/v9/me/projects',
                           headers={'Content-Type': 'application/json'}, auth=self.auth)
        return res.json()

    def getProjectsByWorkspace(self, workspace_id):
        res = requests.get(f'https://api.track.toggl.com/api/v9/workspaces/{workspace_id}/projects', headers={
            'Content-Type': 'application/json'}, auth=self.auth)
        return res.json()

    def getProjectById(self, project_id: int, workspace_id: Optional[int] = None) -> Union[None, dict]:
        if workspace_id is not None:
            res = requests.get(f'https://api.track.toggl.com/api/v9/workspaces/{workspace_id}/projects/{project_id}', headers={
                'Content-Type': 'application/json'}, auth=self.auth)

            # Checking for 403 error
            try:
                res = res.json()
            except:
                return None

            if type(res) == dict:
                return res
            else:
                return None
        else:
            projects = self.getAllProjects()
            search_projects = list(
                filter(lambda el: el["id"] == project_id, projects))

            return search_projects[0] if len(search_projects) > 0 else None

    def getProjectByName(self, project_name: str, workspace_id: Optional[int] = None) -> Union[None, dict]:
        if workspace_id is None:
            projects = self.getAllProjects()
        else:
            projects = self.getProjectsByWorkspace(workspace_id)

        search_projects = list(
            filter(lambda el: el["name"].lower() == project_name.lower(), projects))

        return search_projects[0] if len(search_projects) > 0 else None

    def getProject(self, identifier: str) -> Union[None, dict]:
        try:
            identifier_int = int(identifier)
            project = self.getProjectById(
                workspace_id=self.workspace_id, project_id=identifier_int)
        except:
            project = self.getProjectByName(identifier)

        return project

    #
    # Shortcuts
    #

    def saveShortcut(self, command: str, alias: str, arguments: str) -> dict:
        param = self.parseShortcutArguments(arguments)

        data = {
            "alias": alias,         # Name of the shortened command
            "command": command,     # Name of the slash command
            "application": "toggl",
            "number_of_runs": 0,
            "param": param,         # Parameters passed to aliased slash command
        }

        res = self.mongo_aliases.insert_one(data)

        return data

    def parseShortcutArguments(self, arguments: str) -> dict[str, str]:
        param = {}

        arg_lines = arguments.split(";")

        for arg_line in arg_lines:
            arg_line = arg_line.strip()
            command = arg_line.split(" ")[0].strip()

            if len(command) > 0:
                param[command] = " ".join(arg_line.split(" ")[1:]).strip()

        return param

    def findSavedShortcut(self, alias: str):
        saved_shortcut = self.mongo_aliases.find_one({"alias": alias})

        return saved_shortcut


if __name__ == "__main__":
    toggl = TogglFunctions(env["TOGGL_TOKEN"])
    res = toggl.getCurrentTimeEntry()
    # res = toggl.stopCurrentTimeEntry()
    # res = toggl.getTimeEntryHistory("2022-08-29", "2022-08-29")
    # res = toggl.getLastNTimeEntryHistory(20000)
    # res = toggl.aboutMe()
    # res = toggl.createProject(workspace_id=5175304, name="Testni projekt iz pythona2 asdfds", is_private=True)
    # res = toggl.getAllProjects()
    # res = toggl.getProjectsByWorkspace(5175304)
    # res = toggl.getProjectById(185503661, 5175304)
    # res = toggl.insertTimeEntry(5175304, description="Task iz nekje", pid=168206660, duration=1200, start="2022-09-15T12:12:12.000Z")
    # res = toggl.startCurrentTimeEntry(
    # 5175304, description="Tekoci task iz nekje69", pid=168206660,)
    # res = toggl.saveTimer(command="saave", workspace_id=5175304,
    #   description="Testiranje2 komand iz mongoDB", project=185503661,)
    # res = toggl.updateSavedTimers()
    # res = toggl.startSavedTimer("Test command")
    # res = toggl.mostCommonlyUsedTimers(5)
    # res = toggl.findSavedTimer("6331bbb97da235c9d05e1f38")
    # res = toggl.removeSavedTimer("Test command2")
    # res = toggl.getProjectByName("Hrana", 5175304)
    # res = toggl.getProject(185503661)
    # res = toggl.getProject('Testni projekt iz pythona2')
    # print(json.dumps(res, indent=2))
    # print(toggl.custom_commands)
    # res = toggl.parseShortcutArguments("  command   aaa   BBB ;  lol LOL   ")
    # res = toggl.saveShortcut("command", "neki krajsega",
    #  "  command   aaa   BBB ;  lol LOL   ")
    # res = toggl.findSavedShortcut("abt")
    print(res)
