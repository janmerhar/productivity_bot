import datetime
from dataclasses import dataclass
from typing import Optional


@dataclass
class DailyJob:
    channel_id: int
    hour: int
    minute: int
    type: str
    data: dict
    last_run: Optional[datetime.date] = None


class DailyTaskFunctions:
    tasks: list[DailyJob] = []
    pass


if __name__ == "__main__":
    pass
