from ast import List
import pymongo
from pymongo import MongoClient
from typing import Dict, Optional, Tuple, Union
import requests
from dateutil import parser
import datetime
import time
import json
from bson.objectid import ObjectId

from dotenv import dotenv_values
env = dotenv_values(".env")


class AliasFunctions():
    def __init__(self):
        client = pymongo.MongoClient(
            f"mongodb+srv://{env['MONGO_USERNAME']}:{env['MONGO_PASSWORD']}@cluster0.puvwbmu.mongodb.net/?retryWrites=true&w=majority")

        self.mongo_commands = client["productivity_bot"]["custom_commands"]
        self.mongo_aliases = client["productivity_bot"]["aliases"]

    def findAliases(self, identifier: str = "", n: int = 0):
        res_command = self.mongo_aliases.find(
            {"alias": {"$regex": identifier, "$options": "i"}}).limit(int(n)).sort(
            "number_of_runs", -1)

        return list(res_command)


if __name__ == "__main__":
    alias = AliasFunctions()
    res = alias.findAliases("ptimers")

    print(res)
