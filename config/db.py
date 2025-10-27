from pymongo import MongoClient

from config.env import env

mongo_client = MongoClient(env["MONGO_URI"])
mongo_db = mongo_client[env.get("MONGO_DB", "productivity_bot")]
