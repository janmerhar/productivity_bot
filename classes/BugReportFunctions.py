import datetime
from typing import Any, Dict, Optional

from config.db import mongo_db


class BugReportFunctions:
    @staticmethod
    def insert_bug_report(
        guild_id: Optional[int],
        user_id: int,
        channel_id: int,
        bug: str,
        link: Optional[str] = None,
    ) -> Dict[str, Any]:
        cleaned_bug = bug.strip()
        if not cleaned_bug:
            raise ValueError("Bug report cannot be empty.")

        cleaned_link = link.strip() if link else None
        if cleaned_link == "":
            cleaned_link = None

        document: Dict[str, Any] = {
            "guild_id": guild_id,
            "user_id": user_id,
            "channel_id": channel_id,
            "description": cleaned_bug,
            "link": cleaned_link,
            "created_at": datetime.datetime.utcnow().isoformat(),
        }

        result = mongo_db["bug_reports"].insert_one(document)
        document["_id"] = result.inserted_id

        return document
