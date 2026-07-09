"""polyodds: live Polymarket odds from your terminal."""

from .client import (
    Market,
    PolyOddsError,
    get_market,
    get_market_by_slug,
    price_history,
    search_markets,
)

__all__ = [
    "Market",
    "PolyOddsError",
    "get_market",
    "get_market_by_slug",
    "price_history",
    "search_markets",
]
