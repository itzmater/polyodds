#!/usr/bin/env python3
"""Self-bootstrapping polyodds alert notifier for cron.

Designed for an ephemeral sandbox: clones the repo fresh each run, reads the
committed watchlist.json, checks live prices, and (if anything fired) posts
the formatted alert block to the Telegram chat via the bot token from env.

Stdout is the alert text (or empty when quiet) so a cron wrapper can deliver it.
"""

import io
import json
import os
import subprocess
import sys
import tempfile
import urllib.request

REPO = "https://github.com/itzmater/polyodds.git"
CHAT_ID = "415991812"
WATCHLIST = "watchlist.json"  # committed in repo root


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


def main() -> int:
    token = os.environ.get("TELEGRAM_BOT_TOKEN")
    if not token:
        print("[notify] TELEGRAM_BOT_TOKEN not set", file=sys.stderr)
        return 2

    # Clone fresh into a temp dir (sandbox is ephemeral).
    work = tempfile.mkdtemp(prefix="polyodds_")
    try:
        subprocess.run(
            ["git", "clone", "-q", REPO, work],
            check=True,
            capture_output=True,
        )
    except subprocess.CalledProcessError as e:
        print(f"[notify] clone failed: {e.stderr.decode()}", file=sys.stderr)
        return 2

    # Install (editable, no deps) + run notify against the committed watchlist.
    env = dict(os.environ, POLYODDS_WATCHLIST=os.path.join(work, WATCHLIST))
    subprocess.run(
        [sys.executable, "-m", "pip", "install", "-q", "-e", work],
        capture_output=True,
    )
    proc = subprocess.run(
        [sys.executable, "-m", "polyodds.cli", "notify"],
        cwd=work,
        env=env,
        capture_output=True,
        text=True,
    )
    alert_text = proc.stdout.strip()
    if proc.returncode == 0 or not alert_text:
        return 0  # quiet

    # Something fired — deliver to Telegram.
    ok = post_to_telegram(token, CHAT_ID, alert_text)
    print(alert_text)  # also emit to cron stdout for Hermes delivery fallback
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
