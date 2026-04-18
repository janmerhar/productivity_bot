from pymongo import MongoClient

from config.env import settings

mongo_client = MongoClient(settings.mongo_uri)
mongo_db = mongo_client[settings.mongo_db]
