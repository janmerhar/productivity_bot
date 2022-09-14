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
    # https://developers.track.toggl.com/docs/authentication
    # 
    def aboutMe(self) -> dict:
        res = requests.get('https://api.track.toggl.com/api/v9/me', auth=self.auth)
        return json.loads(res.text)

    
    def getCurrentTimeEntry(self) -> Dict:
        pass

    def stopCurrentTimeEntry(self):
        pass

    def insertTimeEntry(self, entry: dict):
        pass

if __name__ == "__main__":
    toggl = TogglFunctions(env["TOGGL_TOKEN"])
    print(toggl.aboutMe())