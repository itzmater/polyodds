"""Tests for the polyodds watch/alerts engine (polyodds.watch)."""

import argparse
import json
import os
import tempfile
from unittest import mock

import pytest

from polyodds import watch
from polyodds.watch import (
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
from polyodds.client import Market, PolyOddsError


@pytest.fixture
def tmp_path_factory_():
    d = tempfile.mkdtemp()
    return os.path.join(d, "watchlist.json")


def test_watch_roundtrip(tmp_path_factory_):
    w = add_watch("cid1", name="Q?", above=60.0, below=30.0, path=tmp_path_factory_)
    assert w.above == 60.0 and w.below == 30.0
    loaded = load_watches(tmp_path_factory_)
    assert "cid1" in loaded
    assert loaded["cid1"].name == "Q?"
    assert loaded["cid1"].above == 60.0


def test_add_watch_requires_trigger(tmp_path_factory_):
    with pytest.raises(WatchError):
        add_watch("cid", path=tmp_path_factory_)


def test_remove_watch(tmp_path_factory_):
    add_watch("cid", above=50.0, path=tmp_path_factory_)
    assert remove_watch("cid", path=tmp_path_factory_) is True
    assert remove_watch("cid", path=tmp_path_factory_) is False


def test_eval_fires_above(tmp_path_factory_):
    add_watch("cidA", name="CrossUp", above=50.0, path=tmp_path_factory_)
    fake = Market("CrossUp", "cidA", 0.65, 0.35, 0.0)
    with mock.patch.object(watch.client, "get_market", return_value=fake):
        fired = eval_watches(tmp_path_factory_)
    assert len(fired) == 1
    assert any("ABOVE" in r for r in fired[0].reasons)


def test_eval_fires_below(tmp_path_factory_):
    add_watch("cidB", name="CrossDown", below=40.0, path=tmp_path_factory_)
    fake = Market("CrossDown", "cidB", 0.20, 0.80, 0.0)
    with mock.patch.object(watch.client, "get_market", return_value=fake):
        fired = eval_watches(tmp_path_factory_)
    assert len(fired) == 1
    assert any("BELOW" in r for r in fired[0].reasons)


def test_eval_moved_trigger(tmp_path_factory_):
    # Seed last_yes at 50, then price jumps to 70 (>10pt move).
    add_watch("cidC", name="Mover", moved=10.0, path=tmp_path_factory_)
    watches = load_watches(tmp_path_factory_)
    watches["cidC"].last_yes = 50.0
    save_watches(watches, tmp_path_factory_)

    fake = Market("Mover", "cidC", 0.70, 0.30, 0.0)
    with mock.patch.object(watch.client, "get_market", return_value=fake):
        fired = eval_watches(tmp_path_factory_)
    assert len(fired) == 1
    assert any("moved" in r.lower() for r in fired[0].reasons)


def test_eval_no_fire_when_quiet(tmp_path_factory_):
    add_watch("cidD", name="Quiet", above=90.0, path=tmp_path_factory_)
    fake = Market("Quiet", "cidD", 0.40, 0.60, 0.0)
    with mock.patch.object(watch.client, "get_market", return_value=fake):
        fired = eval_watches(tmp_path_factory_)
    assert fired == []


def test_eval_skips_api_errors(tmp_path_factory_):
    add_watch("cidE", name="Gone", above=10.0, path=tmp_path_factory_)
    with mock.patch.object(watch.client, "get_market", side_effect=PolyOddsError("404")):
        fired = eval_watches(tmp_path_factory_)
    assert fired == []


def test_eval_updates_last_yes(tmp_path_factory_):
    add_watch("cidF", name="Track", moved=1.0, path=tmp_path_factory_)
    fake = Market("Track", "cidF", 0.55, 0.45, 0.0)
    with mock.patch.object(watch.client, "get_market", return_value=fake):
        eval_watches(tmp_path_factory_)
    saved = load_watches(tmp_path_factory_)
    assert saved["cidF"].last_yes == 55.0


def test_load_watches_empty_path(tmp_path_factory_):
    assert load_watches(tmp_path_factory_) == {}


def test_load_watches_bad_json(tmp_path_factory_):
    with open(tmp_path_factory_, "w") as f:
        f.write("not json{")
    with pytest.raises(WatchError):
        load_watches(tmp_path_factory_)


def test_notify_emits_block_when_firing(tmp_path_factory_):
    from polyodds.cli import cmd_notify
    import argparse, io, contextlib

    add_watch("cidN", name="NotifyMe", above=40.0, path=tmp_path_factory_)
    fake = Market("NotifyMe", "cidN", 0.75, 0.25, 0.0)
    with mock.patch.object(watch.client, "get_market", return_value=fake):
        # cmd_notify -> eval_watches() uses watch.DEFAULT_PATH; point it at temp
        saved = watch.DEFAULT_PATH
        watch.DEFAULT_PATH = tmp_path_factory_
        try:
            buf = io.StringIO()
            with contextlib.redirect_stdout(buf):
                rc = cmd_notify(argparse.Namespace())
        finally:
            watch.DEFAULT_PATH = saved
    assert rc == 1
    out = buf.getvalue()
    assert "polyodds alert" in out
    assert "NotifyMe" in out


def test_notify_quiet_when_no_fire(tmp_path_factory_):
    from polyodds.cli import cmd_notify
    import argparse, io, contextlib

    add_watch("cidQ", name="Quiet", above=95.0, path=tmp_path_factory_)
    fake = Market("Quiet", "cidQ", 0.30, 0.70, 0.0)
    with mock.patch.object(watch.client, "get_market", return_value=fake):
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            rc = cmd_notify(argparse.Namespace())
    assert rc == 0
    assert buf.getvalue().strip() == ""


# ---------------------------------------------------------------------------
# Live integration test (network) — opt-in via `python tests/test_watch.py --live`
# ---------------------------------------------------------------------------

def _live_watch_cycle():
    # Grab a real market, add a watch, check it, then clean up.
    markets = watch.client.search_markets("bitcoin", limit=1)
    assert markets, "no market to watch"
    cid = markets[0].condition_id
    add_watch(cid, name=markets[0].question, above=0.0, path=DEFAULT_PATH)
    try:
        fired = eval_watches(DEFAULT_PATH)
        assert isinstance(fired, list)
        # above=0 must always fire for a valid market
        assert any(a.condition_id == cid for a in fired)
    finally:
        remove_watch(cid, path=DEFAULT_PATH)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--live", action="store_true")
    args, _ = parser.parse_known_args()
    if args.live:
        try:
            _live_watch_cycle()
            print("LIVE OK")
        except Exception as e:
            print(f"LIVE FAIL: {e}")
            raise
    else:
        import sys

        sys.exit(pytest.main([__file__, "-q"]))
