"""Command-line interface for polyodds."""

from __future__ import annotations

import argparse
import datetime as _dt
import sys
from typing import List

from . import client
from .client import Market, PolyOddsError


def _fmt_vol(v: float) -> str:
    if v >= 1_000_000:
        return f"${v/1_000_000:.1f}M"
    if v >= 1_000:
        return f"${v/1_000:.1f}K"
    return f"${v:.0f}"


def _print_market(m: Market, idx: int | None = None) -> None:
    tag = f"{idx}. " if idx is not None else ""
    print(f"{tag}{m.question}")
    print(f"    Yes {m.yes_pct:>5}%   No {m.no_pct:>5}%   vol {_fmt_vol(m.volume)}")
    print(f"    id: {m.condition_id}")


def cmd_search(args: argparse.Namespace) -> int:
    try:
        markets = client.search_markets(args.query, limit=args.limit)
    except PolyOddsError as e:
        print(f"error: {e}", file=sys.stderr)
        return 1
    if not markets:
        print(f"no active markets found for '{args.query}'")
        return 0
    print(f"Top {len(markets)} markets for '{args.query}':")
    for i, m in enumerate(markets, 1):
        _print_market(m, i)
    return 0


def cmd_market(args: argparse.Namespace) -> int:
    try:
        if args.slug:
            m = client.get_market_by_slug(args.slug)
        else:
            m = client.get_market(args.condition_id)
    except PolyOddsError as e:
        print(f"error: {e}", file=sys.stderr)
        return 1
    _print_market(m)
    return 0


def cmd_track(args: argparse.Namespace) -> int:
    try:
        if args.slug:
            m = client.get_market_by_slug(args.slug)
        else:
            m = client.get_market(args.condition_id)
        history = client.price_history(m.condition_id, days=args.days)
    except PolyOddsError as e:
        print(f"error: {e}", file=sys.stderr)
        return 1
    if not history:
        print("no price history available for this market")
        return 0
    print(f"{m.question}")
    print(f"Last {len(history)} daily Yes-price points (oldest -> newest):")
    first, last = history[0]["yes"], history[-1]["yes"]
    for pt in history:
        day = _dt.datetime.utcfromtimestamp(pt["t"]).strftime("%Y-%m-%d")
        print(f"  {day}  Yes {pt['yes']*100:5.1f}%")
    print(f"  ---")
    print(f"  {first*100:.1f}% -> {last*100:.1f}%  ({(last-first)*100:+.1f} pts over {len(history)}d)")
    return 0


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="polyodds",
        description="Live Polymarket odds, search, and price history. Prices are probabilities.",
    )
    sub = p.add_subparsers(dest="command", required=True)

    s = sub.add_parser("search", help="search markets by keyword")
    s.add_argument("query", help="free-text search term")
    s.add_argument("-n", "--limit", type=int, default=10, help="max results (default 10)")
    s.set_defaults(func=cmd_search)

    m = sub.add_parser("market", help="show one market's current odds")
    g = m.add_mutually_exclusive_group(required=True)
    g.add_argument("-i", "--condition-id", help="market conditionId")
    g.add_argument("--slug", help="market URL slug")
    m.set_defaults(func=cmd_market)

    t = sub.add_parser("track", help="show a market's price history")
    gt = t.add_mutually_exclusive_group(required=True)
    gt.add_argument("-i", "--condition-id", help="market conditionId")
    gt.add_argument("--slug", help="market URL slug")
    t.add_argument("-d", "--days", type=int, default=30, help="history window (default 30)")
    t.set_defaults(func=cmd_track)

    return p


def main(argv: List[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
