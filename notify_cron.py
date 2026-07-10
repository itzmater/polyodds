#!/usr/bin/env python3
"""Self-bootstrapping polyodds alert notifier for cron.

On an ephemeral sandbox the repo may be gone, so we ensure a local copy
exists (clone once into a fixed path), then run the ``polyodds notify``
console script with POLYODDS_WATCHLIST pointing at the committed
watchlist.json. If anything fired, the formatted alert block is posted to
the Telegram chat via the bot token from the environment.

Stdout is the alert text (or empty when quiet) so a cron wrapper can also
deliver it as a fallback.
"""

import json
import os
import subprocess
import sys
import urllib.request

REPO = "https://github.com/itzmater/polyodds.git"
LOCAL = os.path.expanduser("~/polyodds")
CHAT_ID = "415991812"
WATCHLIST = os.path.join(LOCAL, "watchlist.json")


def post_to_telegram(token: str, chat_id: str, text: str) -> bool:
    url = f"https://api.telegram.org/bot{token}/sendMessage"
    payload = json.dumps(
        {"chat_id": chat_id, "text": text, "parse_mode": "Markdown"}
    ).encode()
    req = urllib.request.Request(
        url, data=payload, headers={"Content-Type": "application/json"}
    )
    try:
        with urllib.request.urlopen(req, timeout=20) as r:
            return json.loads(r.read()).get("ok", False)
    except Exception as e:
        print(f"[notify] telegram post failed: {e}", file=sys.stderr)
        return False


def ensure_repo() -> None:
    if not os.path.isdir(os.path.join(LOCAL, ".git")):
        subprocess.run(["git", "clone", "-q", REPO, LOCAL], check=True)


def main() -> int:
    token = os.environ.get("TELEGRAM_BOT_TOKEN")
    if not token:
        print("[notify] TELEGRAM_BOT_TOKEN not set", file=sys.stderr)
        return 2
    try:
        ensure_repo()
    except subprocess.CalledProcessError as e:
        print(f"[notify] clone failed: {e}", file=sys.stderr)
        return 2

    # Install once (console script 'polyodds' created) — quiet if already done.
    subprocess.run(
        [sys.executable, "-m", "pip", "install", "-q", "-e", LOCAL],
        capture_output=True,
    )
    env = dict(os.environ, POLYODDS_WATCHLIST=WATCHLIST)
    proc = subprocess.run(
        ["polyodds", "notify"],
        cwd=LOCAL,
        env=env,
        capture_output=True,
        text=True,
    )
    alert_text = proc.stdout.strip()
    if proc.returncode == 0 or not alert_text:
        return 0  # quiet

    ok = post_to_telegram(token, CHAT_ID, alert_text)
    print(alert_text)  # also emit to cron stdout for Hermes fallback delivery
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
