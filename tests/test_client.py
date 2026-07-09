"""Unit + live-integration tests for polyodds.

Unit tests use fake HTTP responses (no network).
The live test is opt-in via `python tests/test_client.py --live`.
"""

import argparse
from unittest import mock

import pytest

import polyodds.client as c
from polyodds.client import Market, PolyOddsError, _to_market


# ---------------------------------------------------------------------------
# Unit tests (no network)
# ---------------------------------------------------------------------------

def test_parse_double_encoded_outcome_prices():
    m = {"outcomePrices": '["0.65", "0.35"]'}
    prices = c._parse_outcome_prices(m)
    assert prices == [0.65, 0.35]


def test_parse_outcome_prices_bad_string_returns_empty():
    assert c._parse_outcome_prices({"outcomePrices": "not-json"}) == []


def test_to_market_builds_correct_object():
    raw = {
        "question": "Will it rain?",
        "conditionId": "abc123",
        "outcomePrices": '["0.80", "0.20"]',
        "volume": "12345.6",
        "slug": "will-it-rain",
        "outcomes": '["Yes", "No"]',
        "clobTokenIds": '["t1", "t2"]',
    }
    m = _to_market(raw)
    assert isinstance(m, Market)
    assert m.question == "Will it rain?"
    assert m.yes_price == 0.80
    assert m.no_price == 0.20
    assert m.yes_pct == 80.0
    assert m.no_pct == 20.0
    assert m.volume == 12345.6
    assert m.outcomes == ["Yes", "No"]
    assert m.clob_token_ids == ["t1", "t2"]


def test_yes_no_pct_rounding():
    m = Market("q", "id", 0.654, 0.346, 0.0)
    assert m.yes_pct == 65.4
    assert m.no_pct == 34.6


def test_search_markets_filters_client_side():
    batch = [
        {"question": "Will it rain tomorrow?", "conditionId": "1",
         "outcomePrices": '["0.9","0.1"]', "volume": "10"},
        {"question": "Best pizza in town", "conditionId": "2",
         "outcomePrices": '["0.1","0.9"]', "volume": "9999"},
        {"question": "Will it rain on Saturday?", "conditionId": "3",
         "outcomePrices": '["0.5","0.5"]', "volume": "20"},
    ]
    with mock.patch.object(c, "_fetch_markets_batch", return_value=batch):
        out = c.search_markets("rain", limit=5)
    assert len(out) == 2  # pizza excluded (no match)
    # higher-volume rain market ranks first
    assert out[0].question == "Will it rain tomorrow?"
    assert out[1].question == "Will it rain on Saturday?"


def test_search_market_raises_on_bad_type():
    with mock.patch.object(c, "_get_json", return_value={"weird": 1}):
        with pytest.raises(PolyOddsError):
            c.search_markets("x")


def test_get_market_finds_exact_condition_id():
    batch = [
        {"question": "A", "conditionId": "aaa", "outcomePrices": '["0.1","0.9"]', "volume": "1"},
        {"question": "B", "conditionId": "bbb", "outcomePrices": '["0.8","0.2"]', "volume": "2"},
    ]
    with mock.patch.object(c, "_fetch_markets_batch", return_value=batch):
        m = c.get_market("bbb")
    assert m.question == "B"
    assert m.yes_pct == 80.0


def test_get_market_raises_when_missing():
    batch = [{"question": "A", "conditionId": "aaa", "outcomePrices": '["0.1","0.9"]', "volume": "1"}]
    with mock.patch.object(c, "_fetch_markets_batch", return_value=batch):
        with pytest.raises(PolyOddsError):
            c.get_market("nonexistent")


def test_get_market_by_slug_calls_query_param():
    fake = [{"question": "S", "conditionId": "x", "outcomePrices": '["0.6","0.4"]', "volume": "1"}]
    with mock.patch.object(c, "_get_json", return_value=fake) as gj:
        m = c.get_market_by_slug("my-slug")
    # Confirm it used the slug query param, not the 404-prone path.
    called_params = gj.call_args[1].get("params")
    assert called_params == {"slug": "my-slug"}, called_params
    assert m.question == "S"


def test_price_history_parses_history_points():
    fake = {"history": [{"t": 1, "p": 0.4}, {"t": 2, "p": 0.7}]}
    with mock.patch.object(c, "_get_json", return_value=fake):
        hist = c.price_history("cid", days=2)
    assert hist == [{"t": 1, "yes": 0.4}, {"t": 2, "yes": 0.7}]


def test_price_history_empty_for_new_market():
    with mock.patch.object(c, "_get_json", return_value={"history": []}):
        assert c.price_history("cid") == []


def test_get_json_network_error_raises():
    import urllib.error

    with mock.patch.object(
        c.urllib.request, "urlopen", side_effect=urllib.error.URLError("boom")
    ):
        with pytest.raises(PolyOddsError):
            c._get_json("https://example.invalid/x")


def test_get_json_http_error_raises():
    import urllib.error

    with mock.patch.object(
        c.urllib.request,
        "urlopen",
        side_effect=urllib.error.HTTPError(None, 404, "nf", {}, None),
    ):
        with pytest.raises(PolyOddsError):
            c._get_json("https://example.invalid/x")


# ---------------------------------------------------------------------------
# Live integration test (network) — opt-in via --live
# ---------------------------------------------------------------------------

def _live_search_and_track():
    markets = c.search_markets("president", limit=3)
    assert len(markets) > 0, "expected at least one real market"
    assert 0.0 <= markets[0].yes_price <= 1.0
    # history may be empty for new markets; just assert it returns a list
    hist = c.price_history(markets[0].condition_id)
    assert isinstance(hist, list)
    return markets[0].question


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--live", action="store_true")
    args, _ = parser.parse_known_args()
    if args.live:
        try:
            q = _live_search_and_track()
            print(f"LIVE OK -> top match: {q}")
        except Exception as e:
            print(f"LIVE FAIL: {e}")
            raise
    else:
        import sys

        sys.exit(pytest.main([__file__, "-q"]))
