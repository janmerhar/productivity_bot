import datetime
from typing import Any, Dict, List, Optional, Tuple
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

    def insert_job(
        self,
        channel_id: int,
        type: str,
        data: dict,
        schedule: dict = None,
    ):
        DailyJob.insert(channel_id, type, data, schedule)
        self.fetch_jobs()

    def get_due_jobs(self) -> List[DailyJob]:
        now = datetime.datetime.now()
        due_jobs: List[DailyJob] = []

        for job in self.cron_jobs:
            if job.is_due(now):
                due_jobs.append(job)

        for job in self.one_time_jobs:
            if job.is_due(now):
                due_jobs.append(job)

        return due_jobs

    def run_due_jobs(self) -> List[Tuple[DailyJob, Dict[str, Any]]]:
        runs: List[Tuple[DailyJob, Dict[str, Any]]] = []
        due_jobs = self.get_due_jobs()

        for job in due_jobs:
            runs.append((job, job.run()))

        if due_jobs:
            self.fetch_jobs()

        return runs
