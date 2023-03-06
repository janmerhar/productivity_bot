import inspect
from abc import ABC, abstractmethod


class EmbedsAbstract(ABC):
    @abstractmethod
    def createalias_embed(self, command: str,  alias: str, arguments: str = "", cog_param: object = {}) -> dict:
        pass

    @abstractmethod
    def usealias_embed(self, alias: str):
        pass

    def getFunctionByName(self, name):
        try:
            fn = getattr(self, f"{name}_embed")
            return fn
        except:
            return None

