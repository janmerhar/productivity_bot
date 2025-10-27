import requests

from config.db import mongo_db


class CryptoFunctions:
    def __init__(self):
        self.mongo_db = mongo_db

    # Insert into mongoDB
    def inserTracker(
        self,  # for mongodb
        ticker: str,
        change_periods,
        currency: str,
        channel_id: str,
        interval: int,
    ):
        pass

    def fetchPrices(
        tickers: list[str],
        currency: str,
        change_periods=("24h", "7d", "30d"),
    ):
        url = f"https://api.coingecko.com/api/v3/coins/markets"
        params = {
            "vs_currency": currency,
            "ids": ",".join(tickers),
            "price_change_percentage": ",".join(change_periods),
        }

        response = requests.get(url, params=params)
        print(f"fetchCryptoPrice request URL: {response.url}")
        data = response.json()

        return data


if __name__ == "__main__":
    print("Testing CryptoFunctions class...")
    res = CryptoFunctions.fetchPrices(
        ["bitcoin"],
        "usd",
    )

    print(res)
    print(len(res))
