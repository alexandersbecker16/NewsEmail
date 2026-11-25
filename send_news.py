"""
Entrypoint for Windows Task Scheduler.
Runs at the scheduled time (waking the computer if it is asleep), then exits.
A full shutdown that missed the time sends once at the next sign-in.
Waking from sleep does not start a send. Each send time produces one email.
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


def _wait_for_network(timeout: int = 45) -> bool:
    """Wi-Fi is often still down for a few seconds after a wake or boot."""
    import socket

    targets = (("1.1.1.1", 443), ("8.8.8.8", 443), ("smtp.gmail.com", 587))
    deadline = time.time() + timeout
    while True:
        for host, port in targets:
            try:
                with socket.create_connection((host, port), timeout=3):
                    return True
            except OSError:
                continue
        if time.time() >= deadline:
            return False
        time.sleep(3)


@contextmanager
def _send_lock():
    """Keep the daily task and a sign-in catch-up from sending together."""
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

            if not _wait_for_network():
                raise RuntimeError("No network after waiting. The email was not sent.")

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
