from config.db import mongo_db


class AliasFunctions:
    def __init__(self):
        self.mongo_commands = None
        self.mongo_aliases = None

    def _connect(self):
        if self.mongo_aliases is None:
            self.mongo_commands = mongo_db["custom_commands"]
            self.mongo_aliases = mongo_db["aliases"]

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
