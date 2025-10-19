import pymongo

from config import env


class AliasFunctions:
    def __init__(self):
        self._client = None
        self.mongo_commands = None
        self.mongo_aliases = None

    def _connect(self):
        if self.mongo_aliases is None:
            self._client = pymongo.MongoClient(env["MONGO_URI"])
            self.mongo_commands = self._client["productivity_bot"]["custom_commands"]
            self.mongo_aliases = self._client["productivity_bot"]["aliases"]

    def findAliases(self, identifier: str = "", n: int = 0):
        self._connect()
        res_command = (
            self.mongo_aliases.find({"alias": {"$regex": identifier, "$options": "i"}})
            .limit(int(n))
            .sort("number_of_runs", -1)
        )

        return list(res_command)


if __name__ == "__main__":
    alias = AliasFunctions()
    res = alias.findAliases("ptimers")

    print(res)
