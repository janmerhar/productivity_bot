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
        "paused": False,
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
                "paused": {"$ne": True},
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


def fetch_user_alert_by_id(
    alert_id: str,
    user_id: int,
    asset_type: Optional[str] = None,
    guild_id: Optional[int] = None,
    active_only: bool = True,
) -> Optional[Dict[str, Any]]:
    try:
        object_id = ObjectId(alert_id)
    except InvalidId as exc:
        raise ValueError("Invalid alert id.") from exc

    query: Dict[str, Any] = {
        "_id": object_id,
        "user_id": user_id,
    }
    if active_only:
        query["active"] = True
    if asset_type:
        query["asset_type"] = asset_type
    if guild_id is not None:
        query["guild_id"] = guild_id

    return mongo_db["price_alerts"].find_one(query)


def update_alert(
    alert_id: str,
    user_id: int,
    *,
    asset_type: Optional[str] = None,
    guild_id: Optional[int] = None,
    target_price: Optional[float] = None,
    condition: Optional[str] = None,
    destination_type: Optional[str] = None,
    channel_id: Optional[int] = None,
    expires_at: Optional[datetime.datetime] = None,
    clear_expires_at: bool = False,
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

    set_fields: Dict[str, Any] = {}
    if target_price is not None:
        set_fields["target_price"] = float(target_price)
    if condition is not None:
        set_fields["condition"] = condition
    if destination_type is not None:
        set_fields["destination_type"] = destination_type
        set_fields["channel_id"] = channel_id
    if clear_expires_at:
        set_fields["expires_at"] = None
    elif expires_at is not None:
        set_fields["expires_at"] = expires_at

    if not set_fields:
        return False

    result = mongo_db["price_alerts"].update_one(
        query,
        {"$set": set_fields},
    )
    return result.modified_count > 0


def set_alert_paused(
    alert_id: str,
    user_id: int,
    paused: bool,
    *,
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
        {"$set": {"paused": bool(paused)}},
    )
    return result.modified_count > 0


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
