"""
Entrypoint for Windows Task Scheduler.
Runs at the scheduled time, or after wake/sign-in if that time was missed.
Sends at most once for each day's send time, then exits.
"""

from __future__ import annotations

import msvcrt
import time
import traceback
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path

from config_store import load_config, save_config
from email_sender import send_news_email
from news_fetcher import fetch_headlines

LOG_PATH = Path(__file__).resolve().parent / "run_log.txt"
LOCK_PATH = Path(__file__).resolve().parent / "send.lock"


def _log(message: str) -> None:
    line = f"{datetime.now().isoformat(timespec='seconds')} {message}\n"
    with LOG_PATH.open("a", encoding="utf-8") as handle:
        handle.write(line)
    print(message)


def _due_today(now: datetime, send_time: str) -> datetime:
    hour, minute = (int(part) for part in (send_time or "08:00").split(":"))
    return now.replace(hour=hour, minute=minute, second=0, microsecond=0)


def _sent_at(config: dict) -> datetime | None:
    raw = config.get("last_sent")
    if not raw:
        return None
    try:
        sent_at = datetime.fromisoformat(str(raw))
    except ValueError:
        return None
    if sent_at.tzinfo is not None:
        sent_at = sent_at.replace(tzinfo=None)
    return sent_at


def _already_sent_today(config: dict, due: datetime) -> bool:
    """True when this send time already produced an email today."""
    sent_at = _sent_at(config)
    return sent_at is not None and sent_at >= due


@contextmanager
def _send_lock():
    """Keep a wake trigger and a sign-in trigger from sending together."""
    handle = LOCK_PATH.open("a+b")
    handle.seek(0)
    if handle.read(1) != b"\0":
        handle.seek(0)
        handle.write(b"\0")
        handle.flush()
    handle.seek(0)
    try:
        msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
    except OSError:
        handle.close()
        yield False
        return
    try:
        yield True
    finally:
        handle.seek(0)
        msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)
        handle.close()


def main() -> int:
    config = load_config()
    now = datetime.now()

    if not config.get("enabled"):
        config["last_error"] = "Skipped: emailing is disabled."
        save_config(config)
        _log("Emailing disabled — nothing sent.")
        return 0

    due = _due_today(now, config.get("send_time") or "08:00")
    if now < due:
        _log("Computer is on before send time — waiting for the scheduled time.")
        return 0

    if _already_sent_today(config, due):
        _log(f"Already sent for {due.strftime('%H:%M')} today — nothing sent.")
        return 0

    with _send_lock() as acquired:
        if not acquired:
            _log("Another send is already running — nothing sent.")
            return 0

        try:
            config = load_config()
            if not config.get("enabled"):
                _log("Emailing disabled — nothing sent.")
                return 0
            due = _due_today(datetime.now(), config.get("send_time") or "08:00")
            if _already_sent_today(config, due):
                _log(f"Already sent for {due.strftime('%H:%M')} today — nothing sent.")
                return 0

            headlines: list = []
            for _attempt in range(6):
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
