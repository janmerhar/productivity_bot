import datetime
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Optional
import sys

import pymongo

from config import env


@dataclass
class DailyJob:
    channel_id: int
    hour: int
    minute: int
    type: str
    data: dict
    last_run: Optional[datetime.date] = None


class DailyTaskFunctions:
    def __init__(self):
        client = pymongo.MongoClient(env["MONGO_URI"])
        db_name = env.get("MONGO_DB", "productivity_bot")
        self.mongo_tasks = client[db_name]["tasks"]
        self.tasks: list[DailyJob] = []

        self.load_tasks()

    def insert_task(self, job: DailyJob) -> DailyJob:
        self.mongo_tasks.insert_one(asdict(job))
        self.tasks.append(job)

        return job

    def fetch_tasks(self) -> list[DailyJob]:
        tasks = []
        for doc in self.mongo_tasks.find({}):
            job = DailyJob(
                channel_id=doc["channel_id"],
                hour=doc["hour"],
                minute=doc["minute"],
                type=doc["type"],
                data=doc["data"],
                last_run=doc.get("last_run"),
            )
            tasks.append(job)
        return tasks

    def load_tasks(self) -> None:
        self.tasks.clear()
        self.tasks.extend(self.fetch_tasks())

    def run_due_tasks(self) -> None:
        now = datetime.datetime.now()
        current_hour = now.hour
        current_minute = now.minute
        today = now.date()

        for job in self.tasks:
            if (
                job.hour == current_hour
                and job.minute == current_minute
                and job.last_run != today
            ):
                self.run_task(job)

    def run_task(self, job: DailyJob) -> None:
        # check if task has already been run (today)
        # update last_run to this moment
        pass


if __name__ == "__main__":
    task_manager = DailyTaskFunctions()
    example_job = DailyJob(
        channel_id=1429429050086129814,
        hour=9,
        minute=30,
        type="message",
        data={"message": "Daily standup reminder"},
    )
    task_manager.insert_task(example_job)
    task_manager.load_tasks()

    print("All scheduled tasks:")
    for task in task_manager.tasks:
        print(task)
