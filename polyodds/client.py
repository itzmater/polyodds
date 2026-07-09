"""Live data client for Polymarket's public prediction-market APIs.

No third-party dependencies. Uses only the Python standard library.
All endpoints are read-only and require no authentication.

APIs used:
  - Gamma API  (gamma-api.polymarket.com) : discovery / search / browse
  - CLOB API   (clob.polymarket.com)      : real-time prices, history

Known API quirks handled here:
  - Gamma ignores the `title` search param, so ``search_markets`` fetches a
    batch and filters client-side for real relevance.
  - Gamma's ``/slug/{slug}`` path 404s; the ``?slug=`` query param works.
  - CLOB's ``prices-history`` wants ``market=`` (a conditionId), not
    ``conditionId=``. New markets may return an empty history.
"""

from __future__ import annotations

import json
import urllib.parse
import urllib.request
from dataclasses import dataclass, field
from typing import Dict, List, Optional

GAMMA_BASE = "https://gamma-api.polymarket.com"
CLOB_BASE = "https://clob.polymarket.com"


class PolyOddsError(Exception):
    """Raised when a Polymarket API call fails or returns unexpected data."""


def _get_json(url: str, params: Optional[Dict[str, str]] = None) -> object:
    if params:
        url = url + "?" + urllib.parse.urlencode(params)
    req = urllib.request.Request(url, headers={"User-Agent": "polyodds/0.1"})
    try:
        with urllib.request.urlopen(req, timeout=20) as resp:
            raw = resp.read().decode("utf-8")
    except urllib.error.HTTPError as e:
        raise PolyOddsError(f"HTTP {e.code} from {url}: {e.reason}") from e
    except urllib.error.URLError as e:
        raise PolyOddsError(f"network error contacting {url}: {e.reason}") from e
    try:
        return json.loads(raw)
    except json.JSONDecodeError as e:
        raise PolyOddsError(f"invalid JSON from {url}: {e}") from e


@dataclass
class Market:
    """A single binary prediction market (Yes / No)."""

    question: str
    condition_id: str
    yes_price: float
    no_price: float
    volume: float
    slug: str = ""
    outcomes: List[str] = field(default_factory=list)
    clob_token_ids: List[str] = field(default_factory=list)

    @property
    def yes_pct(self) -> float:
        return round(self.yes_price * 100, 1)

    @property
    def no_pct(self) -> float:
        return round(self.no_price * 100, 1)


def _parse_outcome_prices(market: dict) -> List[float]:
    """Gamma returns outcomePrices as a JSON-encoded string inside JSON."""
    raw = market.get("outcomePrices")
    if isinstance(raw, str):
        try:
            return [float(p) for p in json.loads(raw)]
        except (ValueError, json.JSONDecodeError):
            return []
    return []


def _to_market(m: dict) -> Market:
    prices = _parse_outcome_prices(m)
    yes = prices[0] if len(prices) >= 2 else 0.0
    no = prices[1] if len(prices) >= 2 else 0.0
    clob = m.get("clobTokenIds")
    if isinstance(clob, str):
        try:
            clob = json.loads(clob)
        except json.JSONDecodeError:
            clob = []
    outcomes = m.get("outcomes")
    if isinstance(outcomes, str):
        try:
            outcomes = json.loads(outcomes)
        except json.JSONDecodeError:
            outcomes = []
    return Market(
        question=m.get("question", "(untitled)"),
        condition_id=m.get("conditionId", ""),
        yes_price=yes,
        no_price=no,
        volume=float(m.get("volume") or 0.0),
        slug=m.get("slug", ""),
        outcomes=outcomes if isinstance(outcomes, list) else [],
        clob_token_ids=clob if isinstance(clob, list) else [],
    )


def _fetch_markets_batch(limit: int, offset: int = 0) -> List[dict]:
    data = _get_json(
        f"{GAMMA_BASE}/markets",
        params={
            "limit": str(limit),
            "active": "true",
            "closed": "false",
            "order": "volume",
            "ascending": "false",
            "offset": str(offset),
        },
    )
    if not isinstance(data, list):
        raise PolyOddsError("unexpected response from Gamma markets")
    return data


def search_markets(query: str, limit: int = 10, scan: int = 300) -> List[Market]:
    """Search Polymarket for markets matching a free-text query.

    Gamma ignores its ``title`` filter, so this pulls a batch of the
    highest-volume markets and ranks them by how well the query terms
    appear in the question.
    """
    query_terms = [t for t in query.lower().split() if len(t) > 2]
    seen: set = set()
    ranked: List[tuple] = []
    offset = 0
    while len(seen) < scan and offset < scan:
        batch = _fetch_markets_batch(limit=min(100, scan - offset), offset=offset)
        if not batch:
            break
        for m in batch:
            cid = m.get("conditionId")
            if not cid or cid in seen:
                continue
            seen.add(cid)
            q = (m.get("question") or "").lower()
            score = sum(1 for t in query_terms if t in q)
            if query_terms and score == 0:
                continue
            ranked.append((score, m))
        offset += len(batch)
    ranked.sort(key=lambda x: (x[0], -(float(x[1].get("volume") or 0.0))), reverse=True)
    return [_to_market(m) for _, m in ranked[:limit]]


def get_market(condition_id: str) -> Market:
    """Fetch a single market by its conditionId.

    Gamma silently ignores the conditionId filter and returns a batch, so we
    page through the highest-volume markets until we locate the exact match.
    """
    offset = 0
    while offset < 1000:
        batch = _fetch_markets_batch(limit=100, offset=offset)
        if not batch:
            break
        for m in batch:
            if m.get("conditionId") == condition_id:
                return _to_market(m)
        offset += len(batch)
    raise PolyOddsError(f"no market found for conditionId {condition_id}")


def get_market_by_slug(slug: str) -> Market:
    """Fetch a single market by its URL slug (via the ``?slug=`` query param)."""
    data = _get_json(f"{GAMMA_BASE}/markets", params={"slug": slug})
    if not isinstance(data, list) or not data:
        raise PolyOddsError(f"no market found for slug {slug}")
    return _to_market(data[0])


def price_history(condition_id: str, days: int = 30) -> List[Dict[str, float]]:
    """Return historical Yes-price points for a market.

    Each item is a dict with keys: ``t`` (unix seconds), ``yes`` (float price).
    Note: very new markets may return an empty list.
    """
    data = _get_json(
        f"{CLOB_BASE}/prices-history",
        params={
            "market": condition_id,
            "interval": "1d",
            "fidelity": str(max(1, days)),
        },
    )
    if not isinstance(data, dict):
        raise PolyOddsError("unexpected response from CLOB price history")
    history = data.get("history") or []
    out: List[Dict[str, float]] = []
    for point in history:
        # Each point has { t, p } in the CLOB response.
        if isinstance(point, dict) and "p" in point and "t" in point:
            out.append({"t": float(point["t"]), "yes": float(point["p"])})
    return out
