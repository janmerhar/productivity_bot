from typing import Dict
from toggl.TogglPy import Toggl
import requests
from dateutil import parser
import datetime

from dotenv import dotenv_values
env = dotenv_values(".env")

class TogglFunctions:
    def __init__(self, API_KEY: str):
        self.auth=(API_KEY, "api_token")
        # save a default project/workspace id
        # and have functions to change them

    # 
    # Authentication
    # https://developers.track.toggl.com/docs/authentication
    # 
    def aboutMe(self):
        res = requests.get('https://api.track.toggl.com/api/v9/me', auth=self.auth)
        return res.json()
    # 
    # Tracking
    # https://developers.track.toggl.com/docs/tracking
    # 
    def startCurrentTimeEntry(self):
        pass

    def getCurrentTimeEntry(self):
        headers = {
            'Content-Type': 'application/json',
        }
        res = requests.get('https://api.track.toggl.com/api/v9/me/time_entries/current', headers=headers, auth=self.auth)
        return res.json()

    # 
    # Not working for now
    # 
    def stopCurrentTimeEntry(self):
        time_entry_id = self.getCurrentTimeEntry()["id"]
        workspace_id = self.getCurrentTimeEntry()["wid"]

        if time_entry_id is None:
            return

        # Mogoce moram tukaj dodati end time v ISO formatu
        json_data = self.getCurrentTimeEntry()

        res = requests.put('https://api.track.toggl.com/api/v9/workspaces/{workspace_id}/time_entries/{time_entry_id}/stop', json=json_data, auth=self.auth)
        return res

    def insertTimeEntry(self, entry):
        pass

    # 
    # Not working for now
    # 
    # Return 405 -> method not allowed
    def stopCurrentTimeEntry(self):
        time_entry_id = self.getCurrentTimeEntry()["id"]
        workspace_id = self.getCurrentTimeEntry()["wid"]

        if time_entry_id is None:
            return

        # Mogoce moram tukaj dodati end time v ISO formatu
        json_data = self.getCurrentTimeEntry()

        res = requests.put('https://api.track.toggl.com/api/v9/workspaces/{workspace_id}/time_entries/{time_entry_id}/stop', json=json_data, auth=self.auth)
        return res

    def insertTimeEntry(self, entry):
        pass

    def getTimeEntryHistory(self, start_date, end_date):
        headers = {
            'Content-Type': 'application/json',
        }

        params = {
            'start_date': start_date,
            'end_date': end_date,
        }

        res = requests.get('https://api.track.toggl.com/api/v9/me/time_entries', params=params, headers=headers, auth=self.auth)
        return res.json()

    def getTimeEntryHistory(self, start_date, end_date):
        # Start date and end date cannot be the same
        # update end date to +1 day
        if start_date == end_date:
            tmp_date = parser.parse(start_date)
            tmp_date = tmp_date + datetime.timedelta(days=1)
            end_date = tmp_date.strftime("%Y-%m-%d")
            
        headers = {
            'Content-Type': 'application/json',
        }

        params = {
            'start_date': start_date,
            'end_date': end_date,
        }

        res = requests.get('https://api.track.toggl.com/api/v9/me/time_entries', params=params, headers=headers, auth=self.auth)
        return res.json()

    def getLastNTimeEntryHistory(self, n):
        headers = {
            'Content-Type': 'application/json',
        }

        params = {
            # 'start_date': start_date,
            # 'end_date': end_date,
        }

        res = requests.get('https://api.track.toggl.com/api/v9/me/time_entries', params=params, headers=headers, auth=self.auth)
        return res.json()[0:n]

    # 
    # Workspace
    # https://developers.track.toggl.com/docs/workspace
    # 

    def getWorkspaces(self):
        res = requests.get('https://api.track.toggl.com/api/v9/workspaces', headers={ 'Content-Type': 'application/json' }, auth=self.auth)
        return res.json()

    # 
    # Projects
    # https://developers.track.toggl.com/docs/projects
    # 

    def createProject(self, data):
        pass

    def getProjects(self, id=None, workspace=None):
        pass

    def addEntryToProject(self, data):
        pass
    
if __name__ == "__main__":
    toggl = TogglFunctions(env["TOGGL_TOKEN"])
    # res = toggl.stopCurrentTimeEntry()
    # res = toggl.getTimeEntryHistory("2022-08-29", "2022-08-29")
    res = toggl.getLastNTimeEntryHistory(5)
    res = toggl.getWorkspaces()
    print(res)