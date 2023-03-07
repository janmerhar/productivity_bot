import inspect
from abc import ABC, abstractmethod


class FunctionsAbstract(ABC):
    @abstractmethod
    def saveShortcut2(self, command: str, alias: str, param: object = {}):
        pass

    def findSavedShortcut(self, alias: str):
        saved_shortcut = self.mongo_aliases.find_one({"alias": alias})

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
