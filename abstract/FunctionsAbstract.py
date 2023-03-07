import inspect
from abc import ABC, abstractmethod


class FunctionsAbstract(ABC):
    @abstractmethod
    def saveShortcut2(self, command: str, alias: str, param: object = {}):
        pass
