import datetime
from typing import Any, Dict, List, Optional

from bson.errors import InvalidId
from bson.objectid import ObjectId

from config.db import mongo_db

mongo_db["price_alerts"].create_index([("asset_type", 1), ("active", 1)])
mongo_db["price_alerts"].create_index([("asset_type", 1), ("active", 1), ("expires_at", 1)])
mongo_db["price_alerts"].create_index([("channel_id", 1), ("active", 1)])
mongo_db["price_alerts"].create_index([("user_id", 1), ("active", 1)])


def create_alert(
    asset_type: str,
    symbol: str,
    target_price: float,
    condition: str,
    channel_id: Optional[int],
    user_id: int,
    guild_id: Optional[int] = None,
    currency: Optional[str] = None,
    destination_type: str = "channel",
    expires_at: Optional[datetime.datetime] = None,
) -> str:
    document: Dict[str, Any] = {
        "asset_type": asset_type,
        "symbol": symbol,
        "target_price": float(target_price),
        "condition": condition,
        "currency": currency,
        "guild_id": guild_id,
        "channel_id": channel_id,
        "destination_type": destination_type,
        "user_id": user_id,
        "active": True,
        "created_at": datetime.datetime.now(),
        "expires_at": expires_at,
        "triggered_at": None,
        "triggered_price": None,
    }

    result = mongo_db["price_alerts"].insert_one(document)
    return str(result.inserted_id)


def fetch_active_alerts(
    asset_type: str,
    limit: int = 100,
) -> List[Dict[str, Any]]:
    now = datetime.datetime.now()
    cursor = (
        mongo_db["price_alerts"]
        .find(
            {
                "asset_type": asset_type,
                "active": True,
                "$or": [
                    {"expires_at": {"$exists": False}},
                    {"expires_at": None},
                    {"expires_at": {"$gt": now}},
                ],
            }
        )
        .sort("_id", 1)
        .limit(limit)
    )
    return list(cursor)


def fetch_user_active_alerts(
    asset_type: str,
    user_id: int,
    guild_id: Optional[int] = None,
    limit: int = 100,
) -> List[Dict[str, Any]]:
    now = datetime.datetime.now()
    query: Dict[str, Any] = {
        "asset_type": asset_type,
        "user_id": user_id,
        "active": True,
        "$or": [
            {"expires_at": {"$exists": False}},
            {"expires_at": None},
            {"expires_at": {"$gt": now}},
        ],
    }

    if guild_id is not None:
        query["guild_id"] = guild_id

    cursor = (
        mongo_db["price_alerts"]
        .find(query)
        .sort("_id", -1)
        .limit(limit)
    )
    return list(cursor)


def deactivate_alert(
    alert_id: str,
    user_id: int,
    asset_type: Optional[str] = None,
    guild_id: Optional[int] = None,
) -> bool:
    try:
        object_id = ObjectId(alert_id)
    except InvalidId as exc:
        raise ValueError("Invalid alert id.") from exc

    query: Dict[str, Any] = {
        "_id": object_id,
        "user_id": user_id,
        "active": True,
    }
    if asset_type:
        query["asset_type"] = asset_type
    if guild_id is not None:
        query["guild_id"] = guild_id

    result = mongo_db["price_alerts"].update_one(
        query,
        {
            "$set": {
                "active": False,
                "triggered_at": datetime.datetime.now(),
                "triggered_price": None,
            }
        },
    )
    return result.modified_count > 0


def should_trigger(alert: Dict[str, Any], current_price: float) -> bool:
    target_price = float(alert.get("target_price", 0))
    condition = alert.get("condition", "above")

    if condition == "below":
        return current_price <= target_price

    return current_price >= target_price


def mark_triggered(alert_id: ObjectId, current_price: float) -> None:
    mongo_db["price_alerts"].update_one(
        {"_id": alert_id},
        {
            "$set": {
                "active": False,
                "triggered_at": datetime.datetime.now(),
                "triggered_price": float(current_price),
            }
        },
    )


def delete_expired_alerts(asset_type: str) -> int:
    now = datetime.datetime.now()
    result = mongo_db["price_alerts"].delete_many(
        {
            "asset_type": asset_type,
            "active": True,
            "expires_at": {"$lte": now},
        }
    )
    return result.deleted_count
