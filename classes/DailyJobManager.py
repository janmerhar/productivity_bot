import datetime
from typing import Any, Dict, List, Mapping, Optional, Tuple, Union

from bson.errors import InvalidId
from bson.objectid import ObjectId
from classes.DailyJob import DailyJob, ScheduleConfig


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
        guild_id: Optional[int],
        channel_id: Optional[int],
        type: str,
        data: dict,
        schedule: Optional[Union[ScheduleConfig, Mapping[str, Any]]] = None,
    ) -> DailyJob:
        created_job = DailyJob.insert(guild_id, channel_id, type, data, schedule)
        self.fetch_jobs()
        return created_job

    @staticmethod
    def _parse_job_id(job_id: str) -> ObjectId:
        try:
            return ObjectId(job_id)
        except InvalidId:
            raise ValueError("Invalid job id.")

    def get_job(
        self,
        job_id: str,
        channel_id: Optional[int] = None,
        guild_id: Optional[int] = None,
    ) -> Optional[DailyJob]:
        object_id = self._parse_job_id(job_id)
        self.fetch_jobs()
        return DailyJob.fetch_by_id(
            object_id,
            channel_id=channel_id,
            guild_id=guild_id,
        )

    def list_jobs(
        self,
        channel_id: Optional[int] = None,
        guild_id: Optional[int] = None,
    ) -> List[DailyJob]:
        self.fetch_jobs()
        jobs = self.cron_jobs + self.one_time_jobs

        if channel_id is None and guild_id is None:
            return jobs

        filtered: List[DailyJob] = []
        for job in jobs:
            if channel_id is not None and job.channel_id != channel_id:
                continue
            if guild_id is not None and job.guild_id != guild_id:
                continue
            filtered.append(job)
        return filtered

    def delete_job(
        self,
        job_id: str,
        channel_id: Optional[int] = None,
        guild_id: Optional[int] = None,
    ) -> bool:
        object_id = self._parse_job_id(job_id)

        deleted = DailyJob.delete(
            object_id,
            channel_id=channel_id,
            guild_id=guild_id,
        )

        if deleted:
            self.fetch_jobs()

        return deleted

    def update_job(
        self,
        job_id: str,
        data: Optional[Dict[str, Any]] = None,
        schedule: Optional[Union[ScheduleConfig, Mapping[str, Any]]] = None,
        new_channel_id: Optional[int] = None,
        channel_id: Optional[int] = None,
        guild_id: Optional[int] = None,
    ) -> bool:
        object_id = self._parse_job_id(job_id)

        updated = DailyJob.update(
            object_id,
            data=data,
            schedule=schedule,
            new_channel_id=new_channel_id,
            channel_id=channel_id,
            guild_id=guild_id,
        )
        if updated:
            self.fetch_jobs()
        return updated

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
