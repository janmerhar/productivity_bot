import datetime
from typing import Any, Dict, List, Mapping, Optional, Tuple, Union

from bson.errors import InvalidId
from bson.objectid import ObjectId
from classes.DailyJob import DailyJob, OneTimeSchedule2, ScheduleConfig


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
        schedule: Optional[Union[ScheduleConfig, Mapping[str, Any]]] = None,
    ):
        DailyJob.insert(channel_id, type, data, schedule)
        self.fetch_jobs()

    def insert_pomodoro_timer(
        self,
        channel_id: int,
        mode: str,
        duration_minutes: Optional[int],
        user_id: Union[int, str],
    ) -> Tuple[datetime.datetime, int]:
        normalized_mode = mode.lower()
        if normalized_mode not in ("focus", "break"):
            raise ValueError("Invalid pomodoro mode.")

        resolved_duration = duration_minutes
        if resolved_duration is None:
            resolved_duration = 50 if normalized_mode == "focus" else 20

        if resolved_duration <= 0:
            raise ValueError("Pomodoro duration must be greater than zero.")

        end_time = (
            datetime.datetime.now() + datetime.timedelta(minutes=resolved_duration)
        ).replace(second=0, microsecond=0)

        schedule = OneTimeSchedule2(datetime=end_time.isoformat())
        data = {
            "mode": normalized_mode,
            "duration": str(resolved_duration),
            "user": str(user_id),
        }

        self.insert_job(channel_id, "pomodoro", data, schedule)

        return end_time, resolved_duration

    def list_jobs(self, channel_id: Optional[int] = None) -> List[DailyJob]:
        self.fetch_jobs()
        jobs = self.cron_jobs + self.one_time_jobs

        if channel_id is None:
            return jobs

        return [job for job in jobs if job.channel_id == channel_id]

    def delete_job(self, job_id: str, channel_id: Optional[int] = None) -> bool:
        try:
            object_id = ObjectId(job_id)
        except InvalidId:
            raise ValueError("Invalid job id.")

        deleted = DailyJob.delete(object_id, channel_id=channel_id)

        if deleted:
            self.fetch_jobs()

        return deleted

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
