"""polyodds: live Polymarket odds from your terminal."""

from .client import (
    Market,
    PolyOddsError,
    get_market,
    get_market_by_slug,
    price_history,
    search_markets,
)
from .watch import (
    DEFAULT_PATH,
    FiredAlert,
    Watch,
    WatchError,
    add_watch,
    eval_watches,
    load_watches,
    remove_watch,
    save_watches,
)

__all__ = [
    "Market",
    "PolyOddsError",
    "get_market",
    "get_market_by_slug",
    "price_history",
    "search_markets",
    "Watch",
    "FiredAlert",
    "WatchError",
    "add_watch",
    "remove_watch",
    "load_watches",
    "save_watches",
    "eval_watches",
    "DEFAULT_PATH",
]
