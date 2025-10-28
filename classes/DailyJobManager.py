from typing import List
from classes.DailyJob import DailyJob


class DailyJobManager:
    cron_jobs: List[DailyJob]
    one_time_jobs: List[DailyJob]

    def __init__(self):
        self.fetch_jobs()

    def fetch_jobs(self):
        self.cron_jobs = DailyJob.fetch_cron_jobs()
        self.one_time_jobs = DailyJob.fetch_one_time_jobs()
