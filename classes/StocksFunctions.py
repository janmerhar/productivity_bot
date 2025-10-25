import yfinance as yf


class StocksFunctions:
    @staticmethod
    def fetchPrice(ticker: str):
        def pct(new, old):
            if new is None or old in (None, 0):
                return None
            return (float(new) / float(old) - 1.0) * 100.0

        ticker_obj = yf.Ticker(ticker)

        price = None
        currency = None

        try:
            fast_info = getattr(ticker_obj, "fast_info", None)
        except Exception:
            fast_info = None

        if fast_info is not None:
            price = getattr(fast_info, "last_price", None)
            currency = getattr(fast_info, "currency", None)

        day_hist = ticker_obj.history(period="1d")
        if price is None and not day_hist.empty:
            price = day_hist["Close"].iloc[-1]

        hist = ticker_obj.history(period="2y", interval="1d").dropna()

        result = {
            "symbol": ticker,
            "price": float(price) if price is not None else None,
            "change1D_pct": None,
            "change1W_pct": None,
            "change1M_pct": None,
            "change1Y_pct": None,
            "currency": currency,
        }

        if hist.empty:
            return result

        closes = hist["Close"]
        last_close = closes.iloc[-1]
        if result["price"] is None:
            result["price"] = float(last_close)

        lookbacks = {
            "change1D_pct": 1,
            "change1W_pct": 5,
            "change1M_pct": 21,
            "change1Y_pct": 252,
        }

        for key, steps in lookbacks.items():
            if len(closes) > steps:
                past_close = closes.iloc[-(steps + 1)]
                result[key] = pct(last_close, past_close)

        return result

    @staticmethod
    def fetchPrices(tickers: list[str]):
        quotes = []

        for raw_ticker in tickers:
            symbol = (raw_ticker or "").strip()
            if not symbol:
                continue

            try:
                quote = StocksFunctions.fetchPrice(symbol)
            except Exception:
                quote = {
                    "symbol": symbol,
                    "price": None,
                    "change1D_pct": None,
                    "change1W_pct": None,
                    "change1M_pct": None,
                    "change1Y_pct": None,
                    "currency": None,
                }

            if "symbol" not in quote or not quote["symbol"]:
                quote["symbol"] = symbol

            quotes.append(quote)

        return quotes


if __name__ == "__main__":
    tickers = ["VWCE.DE"]

    for ticker in tickers:
        print(StocksFunctions.fetchPrice(ticker))
