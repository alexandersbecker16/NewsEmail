"""
Entrypoint for Windows Task Scheduler.
Runs once at the scheduled time, sends email, then exits.
"""

from __future__ import annotations

import time
import traceback
from datetime import datetime
from pathlib import Path

from config_store import load_config, save_config
from email_sender import send_news_email
from news_fetcher import fetch_headlines

LOG_PATH = Path(__file__).resolve().parent / "run_log.txt"


def _log(message: str) -> None:
    line = f"{datetime.now().isoformat(timespec='seconds')} {message}\n"
    with LOG_PATH.open("a", encoding="utf-8") as handle:
        handle.write(line)
    print(message)


def main() -> int:
    config = load_config()
    now = datetime.now()

    if not config.get("enabled"):
        config["last_error"] = "Skipped: emailing is disabled."
        save_config(config)
        _log("Emailing disabled — nothing sent.")
        return 0

    hour, minute = (int(part) for part in (config.get("send_time") or "08:00").split(":"))
    due = now.replace(hour=hour, minute=minute, second=0, microsecond=0)
    if now < due:
        _log("Computer is on before send time — waiting for the scheduled time.")
        return 0

    try:
        headlines: list = []
        for attempt in range(6):
            headlines = fetch_headlines(5)
            if headlines:
                break
            time.sleep(10)
        if len(headlines) < 1:
            raise RuntimeError("Could not fetch any headlines from trusted sources.")

        send_news_email(config, headlines)
        config["last_sent"] = datetime.now().isoformat(timespec="seconds")
        config["last_error"] = None
        save_config(config)
        _log(f"Sent {len(headlines)} headlines to {len(config.get('recipients', []))} recipient(s).")
        return 0
    except Exception as exc:
        config["last_error"] = f"{exc}\n{traceback.format_exc()}"
        save_config(config)
        _log(f"ERROR: {exc}")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
