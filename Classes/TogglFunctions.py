from typing import Dict
from toggl.TogglPy import Toggl
import requests
import json

from dotenv import dotenv_values
env = dotenv_values(".env")

class TogglFunctions:
    def __init__(self, API_KEY: str):
        self.auth=(API_KEY, "api_token")

    # 
    # Authentication
    # https://developers.track.toggl.com/docs/authentication
    # 
    def aboutMe(self) -> dict:
        res = requests.get('https://api.track.toggl.com/api/v9/me', auth=self.auth)
        return json.loads(res.text)

    # 
    # Tracking
    # https://developers.track.toggl.com/docs/tracking
    # 
    def startCurrentTimeEntry(self) -> Dict:
        pass

    def getCurrentTimeEntry(self) -> Dict:
        pass

    def stopCurrentTimeEntry(self):
        pass

    def insertTimeEntry(self, entry: dict):
        pass

    def getTimeEntryHistory(self, start_date, end_date):
        pass

    # 
    # Workspace
    # https://developers.track.toggl.com/docs/workspace
    # 

    def getWorkspaces(self):
        pass

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
    res = toggl.aboutMe()
    print(res)