import inspect
from abc import ABC, abstractmethod


class FunctionsAbstract(ABC):
    @abstractmethod
    def saveShortcut2(
        self,
        guild_id: int,
        user_id: int,
        command: str,
        alias: str,
        param: object = {},
    ):
        pass

    def findSavedShortcut(self, alias: str, guild_id: int, user_id: int):
        saved_shortcut = self.mongo_aliases.find_one(
            {
                "alias": alias,
                "guild_id": guild_id,
                "user_id": user_id,
            }
        )

        return saved_shortcut

    def parseShortcutArguments(arguments: str) -> dict[str, str]:
        param = {}

        arg_lines = arguments.split(";")

        for arg_line in arg_lines:
            arg_line = arg_line.strip()
            command = arg_line.split(" ")[0].strip()

            if len(command) > 0:
                param[command] = " ".join(arg_line.split(" ")[1:]).strip()

        return param
