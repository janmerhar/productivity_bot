from typing import List, Optional
from classes.DailyJob import DailyJob


class DailyJobManager:
    cron_jobs: List[DailyJob]
    one_time_jobs: List[DailyJob]
    _instance: Optional["DailyJobManager"] = None
    _initialized: bool = False

    def __new__(cls, *args, **kwargs):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def __init__(self):
        if self.__class__._initialized:
            return
        self.fetch_jobs()
        self.__class__._initialized = True

    def fetch_jobs(self):
        self.cron_jobs = DailyJob.fetch_cron_jobs()
        self.one_time_jobs = DailyJob.fetch_one_time_jobs()
