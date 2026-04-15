from typing import Any, Dict, List, Sequence
import threading

import requests
from cachetools import TTLCache


class CryptoFunctions:
    _price_cache = TTLCache(maxsize=256, ttl=10.0)
    _cache_lock = threading.RLock()
    _thread_local = threading.local()

    @staticmethod
    def _session() -> requests.Session:
        session = getattr(CryptoFunctions._thread_local, "session", None)
        if session is None:
            session = requests.Session()
            CryptoFunctions._thread_local.session = session
        return session

    @staticmethod
    def _price_cache_key(
        tickers: Sequence[str],
        currency: str,
        change_periods: Sequence[str],
    ) -> tuple[tuple[str, ...], str, tuple[str, ...]]:
        normalized_tickers = tuple(
            item.strip().lower() for item in tickers if str(item or "").strip()
        )
        return (
            normalized_tickers,
            str(currency or "").strip().lower(),
            tuple(str(item or "").strip().lower() for item in change_periods),
        )

    # Insert into mongoDB
    @staticmethod
    def insert_tracker(
        ticker: str,
        change_periods,
        currency: str,
        channel_id: str,
        interval: int,
    ):
        pass

    @staticmethod
    def fetch_prices(
        tickers: Sequence[str],
        currency: str,
        change_periods=("24h", "7d", "30d"),
    ) -> List[Dict[str, Any]]:
        cache_key = CryptoFunctions._price_cache_key(tickers, currency, change_periods)
        with CryptoFunctions._cache_lock:
            cached = CryptoFunctions._price_cache.get(cache_key)
        if cached is not None:
            return [dict(item) for item in cached]

        url = "https://api.coingecko.com/api/v3/coins/markets"
        params = {
            "vs_currency": currency,
            "ids": ",".join(tickers),
            "price_change_percentage": ",".join(change_periods),
        }

        response = CryptoFunctions._session().get(url, params=params, timeout=15)
        response.raise_for_status()
        data = response.json()

        if not isinstance(data, list):
            raise ValueError("Unexpected response format from CoinGecko.")

        with CryptoFunctions._cache_lock:
            CryptoFunctions._price_cache[cache_key] = [
                dict(item) for item in data if isinstance(item, dict)
            ]
        return data


if __name__ == "__main__":
    print("Testing CryptoFunctions class...")
    res = CryptoFunctions.fetch_prices(
        ["bitcoin"],
        "usd",
    )

    print(res)
    print(len(res))
