from typing import Any, Dict, List, Sequence

import requests


class CryptoFunctions:
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
        url = "https://api.coingecko.com/api/v3/coins/markets"
        params = {
            "vs_currency": currency,
            "ids": ",".join(tickers),
            "price_change_percentage": ",".join(change_periods),
        }

        response = requests.get(url, params=params, timeout=15)
        response.raise_for_status()
        data = response.json()

        if not isinstance(data, list):
            raise ValueError("Unexpected response format from CoinGecko.")

        return data


if __name__ == "__main__":
    print("Testing CryptoFunctions class...")
    res = CryptoFunctions.fetch_prices(
        ["bitcoin"],
        "usd",
    )

    print(res)
    print(len(res))
