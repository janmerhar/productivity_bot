import yfinance as yf

from classes.OpenAIFunctions import OpenAIFunctions


class StocksFunctions:
    STOCK_QUOTE_TYPES = {"EQUITY", "ETF"}

    @staticmethod
    def fetch_price(ticker: str):
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
    def fetch_prices(tickers: list[str]):
        quotes = []

        for raw_ticker in tickers:
            symbol = (raw_ticker or "").strip()
            if not symbol:
                continue

            try:
                quote = StocksFunctions.fetch_price(symbol)
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

    @staticmethod
    def search_candidates(
        query: str,
        limit: int = 8,
        quote_types: set[str] | None = None,
        use_openai_rerank: bool = False,
    ) -> list[dict]:
        text = (query or "").strip()
        if not text or limit <= 0:
            return []

        try:
            search = yf.Search(
                text,
                max_results=max(limit * 2, 8),
                news_count=0,
                include_cb=False,
                enable_fuzzy_query=True,
                raise_errors=False,
            )
            raw_quotes = getattr(search, "quotes", None) or []
        except Exception:
            return []

        candidates: list[dict] = []
        seen_symbols: set[str] = set()
        allowed_quote_types = {value.upper() for value in quote_types} if quote_types else None

        for row in raw_quotes:
            symbol = str(row.get("symbol") or "").strip().upper()
            if not symbol or symbol in seen_symbols:
                continue

            quote_type = str(row.get("quoteType") or "").strip().upper()
            if allowed_quote_types and quote_type not in allowed_quote_types:
                continue

            short_name = str(
                row.get("shortname") or row.get("longname") or ""
            ).strip()
            exchange = str(row.get("exchange") or row.get("exchDisp") or "").strip()

            candidates.append(
                {
                    "symbol": symbol,
                    "name": short_name,
                    "exchange": exchange,
                    "quote_type": quote_type,
                }
            )
            seen_symbols.add(symbol)

        if not candidates:
            return []

        if use_openai_rerank:
            ranked_symbols = OpenAIFunctions.rank_stock_candidates(text, candidates)
            if ranked_symbols:
                by_symbol = {item["symbol"]: item for item in candidates}
                ranked_candidates: list[dict] = []
                added_symbols: set[str] = set()

                for symbol in ranked_symbols:
                    item = by_symbol.get(symbol)
                    if item is not None and symbol not in added_symbols:
                        ranked_candidates.append(item)
                        added_symbols.add(symbol)

                for item in candidates:
                    symbol = item["symbol"]
                    if symbol not in added_symbols:
                        ranked_candidates.append(item)
                        added_symbols.add(symbol)

                candidates = ranked_candidates

        return candidates[:limit]
