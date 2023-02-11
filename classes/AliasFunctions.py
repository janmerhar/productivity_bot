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
    pass

    def __init__(self):
        client = pymongo.MongoClient(
            f"mongodb+srv://{env['MONGO_USERNAME']}:{env['MONGO_PASSWORD']}@cluster0.puvwbmu.mongodb.net/?retryWrites=true&w=majority")

        self.mongo_commands = client["productivity_bot"]["custom_commands"]
        self.mongo_aliases = client["productivity_bot"]["aliases"]

