# polyodds

A small, **dependency-free** Python CLI for pulling **live Polymarket** prediction-market odds, searching markets, and tracking price history. Prices *are* probabilities: a market showing `Yes 65.2%` means the crowd thinks there's a 65.2% chance.

Built with only the Python standard library — no `requests`, no pandas, nothing to `pip install` beyond the package itself.

## Install

```bash
pip install -e .
```

## Usage

### Search markets by keyword

Polymarket's API ignores keyword search server-side, so `polyodds` fetches the
top markets by volume and ranks them by how well your terms match the question.

```bash
polyodds search "president" -n 5
```

```
Top 3 markets for 'president':
1. Will Gérald Darmanin advance to the second round of the next French presidential election?
    Yes   1.3%   No  98.7%   vol $968
    id: 0xf299f84f3d666bd2068f6630d93cd1edbcc70dfeddfe54f2288397f222067473
2. Will Élisabeth Borne be on the ballot for the 2027 French presidential election?
    Yes   1.9%   No  98.1%   vol $970
    id: 0xab960c4193899ac65bc3858afb07aa3eb607299b62ec5c76b33feb484b992c8d
3. Will Michel Barnier advance to the second round of the next French presidential election?
    Yes   2.4%   No  97.7%   vol $971
    id: 0xeeef274e198202339b090ad9c011dda1623332b678612edf0d812dc445992fc3
```

### Show one market's current odds

```bash
polyodds market -i 0xf299f84f3d666bd2068f6630d93cd1edbcc70dfeddfe54f2288397f222067473
```

### Track a market's price history

```bash
polyodds track --slug "will-the-fed-cut-rates" -d 30
```

```
Will the Fed cut rates in September?
Last 30 daily Yes-price points (oldest -> newest):
  2026-06-09  Yes  48.0%
  2026-06-10  Yes  51.3%
  ...
  2026-07-09  Yes  62.4%
  ---
  48.0% -> 62.4%  (+14.4 pts over 30d)
```

### Watch markets and get alerts

Build a local watchlist and have `polyodds` tell you when a market crosses a
price or moves sharply.

```bash
# Alert when this market's Yes% goes above 60 or below 30
polyodds watch -i 0xf299f84f... --above 60 --below 30

# Alert when the Yes% moves 5+ points since the last check
polyodds watch -i 0xf299f84f... --moved 5

# List what you're watching (with last-seen price)
polyodds watches

# Check everything against live prices. Fires alerts, exits non-zero if any fired
polyodds check

# Stop watching
polyodds unwatch -i 0xf299f84f...
```

The watchlist lives at `~/.polyodds/watchlist.json`. Because `check` exits
with code `1` when an alert fires (and `0` when quiet), it pairs perfectly with
a cron job or CI step that only notifies you on movement.

## APIs

- **Gamma API** (`gamma-api.polymarket.com`) — discovery, search, browse
- **CLOB API** (`clob.polymarket.com`) — real-time prices, history

All endpoints are read-only and require no authentication.

## License

MIT
