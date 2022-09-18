from typing import Dict
from toggl.TogglPy import Toggl
import requests
from dateutil import parser
import datetime
import json

from dotenv import dotenv_values
env = dotenv_values(".env")


class TogglFunctions:
    def __init__(self, API_KEY: str):
        self.auth = (API_KEY, "api_token")
        self.workspace_id = self.aboutMe()["default_workspace_id"]
        # save a default project/workspace id
        # and have functions to change them

        # add implementation for API_KEY and email:passwd authentications

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
        params = {
            'start_date': start_date,
            'end_date': end_date,
        }

        res = requests.get('https://api.track.toggl.com/api/v9/me/time_entries',
                           params=params, headers={'Content-Type': 'application/json'}, auth=self.auth)
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

    def getLastNTimeEntryHistory(self, n):
        res = requests.get('https://api.track.toggl.com/api/v9/me/time_entries',
                           headers={'Content-Type': 'application/json'}, auth=self.auth)
        return res.json()[0:n]

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

    def getProjectById(self, workspace_id, project_id):
        res = requests.get(f'https://api.track.toggl.com/api/v9/workspaces/{workspace_id}/projects/{project_id}', headers={
                           'Content-Type': 'application/json'}, auth=self.auth)
        return res.json()


if __name__ == "__main__":
    toggl = TogglFunctions(env["TOGGL_TOKEN"])
    res = toggl.getCurrentTimeEntry()
    # res = toggl.stopCurrentTimeEntry()
    # res = toggl.getTimeEntryHistory("2022-08-29", "2022-08-29")
    # res = toggl.getLastNTimeEntryHistory(5)
    # res = toggl.aboutMe()
    # res = toggl.createProject(workspace_id=5175304, name="Testni projekt iz pythona2 asdfds", is_private=True)
    # res = toggl.getAllProjects()
    # res = toggl.getProjectsByWorkspace(5175304)
    # res = toggl.getProjectById(5175304, 185503661)
    # res = toggl.insertTimeEntry(5175304, description="Task iz nekje", pid=168206660, duration=1200, start="2022-09-15T12:12:12.000Z")
    # res = toggl.startCurrentTimeEntry(
    # 5175304, description="Tekoci task iz nekje69", pid=168206660,)
    print(json.dumps(res, indent=2))
    # print(type(res))
