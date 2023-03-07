import inspect
from abc import ABC, abstractmethod


class FunctionsAbstract(ABC):
    @abstractmethod
    def saveShortcut2(self, command: str, alias: str, param: object = {}):
        pass

    def findSavedShortcut(self, alias: str):
        saved_shortcut = self.mongo_aliases.find_one({"alias": alias})

        return saved_shortcut

