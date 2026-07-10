"""Command-line interface for polyodds."""

from __future__ import annotations

import argparse
import datetime as _dt
import sys
from typing import List

from . import client, watch
from .client import Market, PolyOddsError
from .watch import DEFAULT_PATH, WatchError


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


def cmd_watch(args: argparse.Namespace) -> int:
    try:
        if args.slug:
            m = client.get_market_by_slug(args.slug)
        else:
            m = client.get_market(args.condition_id)
        w = watch.add_watch(
            m.condition_id,
            name=m.question,
            above=args.above,
            below=args.below,
            moved=args.moved,
        )
    except (PolyOddsError, WatchError) as e:
        print(f"error: {e}", file=sys.stderr)
        return 1
    triggers = []
    if w.above is not None:
        triggers.append(f"above {w.above}%")
    if w.below is not None:
        triggers.append(f"below {w.below}%")
    if w.moved is not None:
        triggers.append(f"moved {w.moved}pts")
    print(f"watching: {m.question}")
    print(f"  id: {w.condition_id}")
    print(f"  triggers: {', '.join(triggers)}")
    print(f"  watchlist: {DEFAULT_PATH}")
    return 0


def cmd_unwatch(args: argparse.Namespace) -> int:
    try:
        removed = watch.remove_watch(args.condition_id)
    except WatchError as e:
        print(f"error: {e}", file=sys.stderr)
        return 1
    if removed:
        print(f"removed watch for {args.condition_id}")
        return 0
    print(f"no watch found for {args.condition_id}")
    return 1


def cmd_list_watches(args: argparse.Namespace) -> int:
    try:
        watches = watch.load_watches()
    except WatchError as e:
        print(f"error: {e}", file=sys.stderr)
        return 1
    if not watches:
        print("watchlist is empty — add one with: polyodds watch -i <id> --above 60")
        return 0
    print(f"{len(watches)} watched market(s):")
    for w in watches.values():
        trigs = []
        if w.above is not None:
            trigs.append(f"above {w.above}%")
        if w.below is not None:
            trigs.append(f"below {w.below}%")
        if w.moved is not None:
            trigs.append(f"moved {w.moved}pts")
        last = f" (last seen {w.last_yes}%)" if w.last_yes is not None else ""
        print(f"  {w.name}")
        print(f"    id: {w.condition_id}  | {', '.join(trigs)}{last}")
    return 0


def cmd_check(args: argparse.Namespace) -> int:
    try:
        fired = watch.eval_watches()
    except WatchError as e:
        print(f"error: {e}", file=sys.stderr)
        return 1
    if not fired:
        print("no alerts — all watches quiet")
        return 0
    print(f"{len(fired)} alert(s) firing:")
    for a in fired:
        print(f"  {a.name}")
        print(f"    id: {a.condition_id}  | Yes {a.yes_pct}%")
        for r in a.reasons:
            print(f"    - {r}")
    # Non-zero exit so this command can gate a cron/CI step.
    return 1


def cmd_notify(args: argparse.Namespace) -> int:
    """Check watches and emit a single formatted block for chat delivery.

    Intended for cron: prints nothing (exit 0) when quiet, or a clean
    Telegram-ready alert block (exit 1) when something fired. The caller is
    responsible for delivering stdout — Hermes delivers it to chat natively.
    """
    try:
        fired = watch.eval_watches()
    except WatchError as e:
        print(f"error: {e}")
        return 1
    if not fired:
        return 0
    lines = ["🚨 *polyodds alert*", ""]
    for a in fired:
        lines.append(f"*{a.name}*")
        lines.append(f"  Yes {a.yes_pct}%  ·  `id: {a.condition_id}`")
        for r in a.reasons:
            lines.append(f"  • {r}")
        lines.append("")
    print("\n".join(lines).strip())
    return 1


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

    w = sub.add_parser("watch", help="add a market to your alert watchlist")
    gw = w.add_mutually_exclusive_group(required=True)
    gw.add_argument("-i", "--condition-id", help="market conditionId")
    gw.add_argument("--slug", help="market URL slug")
    w.add_argument("--above", type=float, help="alert when Yes% crosses above this")
    w.add_argument("--below", type=float, help="alert when Yes% crosses below this")
    w.add_argument("--moved", type=float, help="alert when Yes% moves this many pts since last check")
    w.set_defaults(func=cmd_watch)

    u = sub.add_parser("unwatch", help="remove a market from your watchlist")
    u.add_argument("-i", "--condition-id", required=True, help="market conditionId to remove")
    u.set_defaults(func=cmd_unwatch)

    lw = sub.add_parser("watches", help="list your current watchlist")
    lw.set_defaults(func=cmd_list_watches)

    a = sub.add_parser("check", help="check watches against live prices; fires alerts")
    a.set_defaults(func=cmd_check)

    n = sub.add_parser("notify", help="check + format alert block for chat delivery (cron)")
    n.set_defaults(func=cmd_notify)

    return p


def main(argv: List[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
