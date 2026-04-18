import datetime
from typing import Any, Dict, Optional

from config.db import mongo_db


class FeatureRequestFunctions:
    @staticmethod
    def insert_feature_request(
        guild_id: Optional[int],
        user_id: int,
        channel_id: int,
        request: str,
        link: Optional[str] = None,
        attachment_url: Optional[str] = None,
    ) -> Dict[str, Any]:
        cleaned_request = request.strip()
        if not cleaned_request:
            raise ValueError("Feature request cannot be empty.")

        cleaned_link = link.strip() if link else None
        if cleaned_link == "":
            cleaned_link = None

        cleaned_attachment_url = attachment_url.strip() if attachment_url else None
        if cleaned_attachment_url == "":
            cleaned_attachment_url = None

        document: Dict[str, Any] = {
            "guild_id": guild_id,
            "user_id": user_id,
            "channel_id": channel_id,
            "request": cleaned_request,
            "link": cleaned_link,
            "attachment_url": cleaned_attachment_url,
            "created_at": datetime.datetime.utcnow().isoformat(),
        }

        result = mongo_db["feature_requests"].insert_one(document)
        document["_id"] = result.inserted_id
        return document

