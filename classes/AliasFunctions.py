from config.db import mongo_db


class AliasFunctions:
    @staticmethod
    def findAliases(guild_id: int, user_id: int, identifier: str = "", n: int = 0):
        collection = mongo_db["aliases"]
        res_command = (
            collection.find(
                {
                    "alias": {"$regex": identifier, "$options": "i"},
                    "guild_id": guild_id,
                    "user_id": user_id,
                }
            )
            .limit(int(n))
            .sort("number_of_runs", -1)
        )

        return list(res_command)


if __name__ == "__main__":
    res = AliasFunctions.findAliases(0, 0, "ptimers")

    print(res)
