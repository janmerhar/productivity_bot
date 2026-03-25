from dataclasses import dataclass
from typing import Any, Dict, Optional


@dataclass
class UserSettings:
    user_id: int
    timezone: Optional[str] = None
    toggl_api_key: Optional[str] = None
    toggl_workspace_id: Optional[int] = None
    created_at: Optional[str] = None
    updated_at: Optional[str] = None

    @staticmethod
    def from_document(document: Optional[Dict[str, Any]], user_id: int) -> "UserSettings":
        if not document:
            return UserSettings(user_id=int(user_id))

        return UserSettings(
            user_id=int(document.get("user_id", user_id)),
            timezone=document.get("timezone"),
            toggl_api_key=document.get("toggl_api_key"),
            toggl_workspace_id=document.get("toggl_workspace_id"),
            created_at=document.get("created_at"),
            updated_at=document.get("updated_at"),
        )

    def to_document(self) -> Dict[str, Any]:
        return {
            "user_id": self.user_id,
            "timezone": self.timezone,
            "toggl_api_key": self.toggl_api_key,
            "toggl_workspace_id": self.toggl_workspace_id,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }
