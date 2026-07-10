"""Watchlist persistence and alert evaluation for polyodds.

A watchlist is a JSON file (``~/.polyodds/watchlist.json``) mapping a market
conditionId to a set of trigger rules:

    {
      "<conditionId>": {
        "name": "Will X happen?",          # human-readable question
        "above": 60.0,                      # alert when Yes% >= 60
        "below": 30.0,                      # alert when Yes% <= 30
        "moved": 5.0,                       # alert when |yes - last| >= 5 pts
        "last_yes": 48.2                    # last seen Yes% (for `moved`)
      }
    }

Any of ``above`` / ``below`` / ``moved`` may be omitted. ``last_yes`` is
maintained automatically by :func:`eval_watches`.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from typing import Dict, List, Optional

from . import client
from .client import PolyOddsError

DEFAULT_PATH = os.path.join(os.path.expanduser("~"), ".polyodds", "watchlist.json")


class WatchError(Exception):
    """Raised for watchlist load/save problems."""


@dataclass
class Watch:
    condition_id: str
    name: str = ""
    above: Optional[float] = None
    below: Optional[float] = None
    moved: Optional[float] = None
    last_yes: Optional[float] = None

    def to_dict(self) -> Dict:
        d = {"name": self.name}
        if self.above is not None:
            d["above"] = self.above
        if self.below is not None:
            d["below"] = self.below
        if self.moved is not None:
            d["moved"] = self.moved
        if self.last_yes is not None:
            d["last_yes"] = self.last_yes
        return d

    @classmethod
    def from_dict(cls, condition_id: str, d: Dict) -> "Watch":
        return cls(
            condition_id=condition_id,
            name=d.get("name", ""),
            above=d.get("above"),
            below=d.get("below"),
            moved=d.get("moved"),
            last_yes=d.get("last_yes"),
        )


def load_watches(path: str = DEFAULT_PATH) -> Dict[str, Watch]:
    if not os.path.exists(path):
        return {}
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
    except (json.JSONDecodeError, OSError) as e:
        raise WatchError(f"could not read watchlist {path}: {e}") from e
    if not isinstance(data, dict):
        raise WatchError(f"watchlist {path} is not a JSON object")
    return {cid: Watch.from_dict(cid, v) for cid, v in data.items()}


def save_watches(watches: Dict[str, Watch], path: str = DEFAULT_PATH) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    try:
        with open(path, "w", encoding="utf-8") as f:
            json.dump({cid: w.to_dict() for cid, w in watches.items()}, f, indent=2)
    except OSError as e:
        raise WatchError(f"could not write watchlist {path}: {e}") from e


def add_watch(
    condition_id: str,
    name: str = "",
    above: Optional[float] = None,
    below: Optional[float] = None,
    moved: Optional[float] = None,
    path: str = DEFAULT_PATH,
) -> Watch:
    if above is None and below is None and moved is None:
        raise WatchError("a watch needs at least one trigger: --above, --below, or --moved")
    watches = load_watches(path)
    w = Watch(condition_id=condition_id, name=name, above=above, below=below, moved=moved)
    watches[condition_id] = w
    save_watches(watches, path)
    return w


def remove_watch(condition_id: str, path: str = DEFAULT_PATH) -> bool:
    watches = load_watches(path)
    if condition_id not in watches:
        return False
    del watches[condition_id]
    save_watches(watches, path)
    return True


@dataclass
class FiredAlert:
    condition_id: str
    name: str
    yes_pct: float
    reasons: List[str] = field(default_factory=list)


def eval_watches(path: str = DEFAULT_PATH) -> List[FiredAlert]:
    """Fetch live prices for every watch and return the ones that fired.

    Maintains ``last_yes`` for each watch so the ``moved`` trigger works
    across invocations.
    """
    watches = load_watches(path)
    if not watches:
        return []
    fired: List[FiredAlert] = []
    changed = False
    for cid, w in watches.items():
        try:
            m = client.get_market(cid)
        except PolyOddsError:
            # Market gone or API hiccup — skip silently, don't corrupt state.
            continue
        yes = m.yes_pct
        reasons: List[str] = []
        if w.above is not None and yes >= w.above:
            reasons.append(f"Yes {yes}% crossed ABOVE {w.above}%")
        if w.below is not None and yes <= w.below:
            reasons.append(f"Yes {yes}% crossed BELOW {w.below}%")
        if w.moved is not None and w.last_yes is not None:
            delta = abs(yes - w.last_yes)
            if delta >= w.moved:
                reasons.append(f"moved {delta:+.1f} pts (was {w.last_yes}%)")
        if reasons:
            fired.append(FiredAlert(cid, w.name or m.question, yes, reasons))
        # Update last-seen price regardless of fire.
        if w.last_yes != yes:
            w.last_yes = yes
            changed = True
    if changed:
        save_watches(watches, path)
    return fired
