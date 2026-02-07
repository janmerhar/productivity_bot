import datetime
from typing import Any, Dict, List, Optional

from bson.objectid import ObjectId

from config.db import mongo_db

mongo_db["price_alerts"].create_index([("asset_type", 1), ("active", 1)])
mongo_db["price_alerts"].create_index([("channel_id", 1), ("active", 1)])
mongo_db["price_alerts"].create_index([("user_id", 1), ("active", 1)])


def create_alert(
    asset_type: str,
    symbol: str,
    target_price: float,
    condition: str,
    channel_id: int,
    user_id: int,
    guild_id: Optional[int] = None,
    currency: Optional[str] = None,
) -> str:
    document: Dict[str, Any] = {
        "asset_type": asset_type,
        "symbol": symbol,
        "target_price": float(target_price),
        "condition": condition,
        "currency": currency,
        "guild_id": guild_id,
        "channel_id": channel_id,
        "user_id": user_id,
        "active": True,
        "created_at": datetime.datetime.utcnow(),
        "triggered_at": None,
        "triggered_price": None,
    }

    result = mongo_db["price_alerts"].insert_one(document)
    return str(result.inserted_id)


def fetch_active_alerts(
    asset_type: str,
    limit: int = 100,
) -> List[Dict[str, Any]]:
    cursor = (
        mongo_db["price_alerts"]
        .find({"asset_type": asset_type, "active": True})
        .sort("_id", 1)
        .limit(limit)
    )
    return list(cursor)


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
                "triggered_at": datetime.datetime.utcnow(),
                "triggered_price": float(current_price),
            }
        },
    )
