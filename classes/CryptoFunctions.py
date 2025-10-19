import pymongo
from dotenv import dotenv_values
import requests

env = dotenv_values(".env")


class CryptoFunctions:
    def __init__(self):
        client = pymongo.MongoClient(env["MONGO_URI"])
        # self.mongo_commands = client["productivity_bot"]["custom_commands"]
        # self.mongo_aliases = client["productivity_bot"]["aliases"]

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

    #
    def fetchPrices(tickers: str, currency: str, change_periods=["24h"]):
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
