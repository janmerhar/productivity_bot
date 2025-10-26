import datetime
from pathlib import Path
import sys

import pymongo

if __name__ == "__main__":
    ROOT_DIR = Path(__file__).resolve().parents[1]
    if str(ROOT_DIR) not in sys.path:
        sys.path.insert(0, str(ROOT_DIR))

from classes.DailySchedule import DailyJob, DailySchedule
from config import env


class DailyTaskFunctions:
    def __init__(self):
        client = pymongo.MongoClient(env["MONGO_URI"])
        db_name = env.get("MONGO_DB", "productivity_bot")
        self.mongo_tasks = client[db_name]["tasks"]
        self.tasks: list[DailyJob] = []

        self.load_tasks()

    def insert_task(self, job: DailyJob) -> DailyJob:
        self.mongo_tasks.insert_one(job.to_dict())
        self.tasks.append(job)

        return job

    def fetch_tasks(self) -> list[DailyJob]:
        tasks = []
        for doc in self.mongo_tasks.find({}):
            job = DailyJob.from_document(doc)
            tasks.append(job)
        return tasks

    def load_tasks(self) -> None:
        self.tasks.clear()
        self.tasks.extend(self.fetch_tasks())

    def run_due_tasks(self) -> None:
        now = datetime.datetime.now()

        for job in self.tasks:
            if job.is_due(now):
                self.run_task(job)

    def run_task(self, job: DailyJob) -> None:
        # check if task has already been run (today)
        job.mark_ran(datetime.datetime.now())


if __name__ == "__main__":
    task_manager = DailyTaskFunctions()
    example_job = DailyJob(
        channel_id=1429429050086129814,
        type="message",
        data={"message": "Daily standup reminder"},
        schedule=DailySchedule(hour=9, minute=30),
    )
    task_manager.insert_task(example_job)
    task_manager.load_tasks()

    print("All scheduled tasks:")
    for task in task_manager.tasks:
        print(task)
