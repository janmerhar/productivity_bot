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
        data = response.json()

        return data


if __name__ == "__main__":
    print("Testing CryptoFunctions class...")
    res = CryptoFunctions.fetch_prices(
        ["bitcoin"],
        "usd",
    )

    print(res)
    print(len(res))
