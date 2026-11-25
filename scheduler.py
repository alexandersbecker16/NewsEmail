"""Windows Task Scheduler helpers.

The daily email is sent by the Gmail schedule in cloud_sync.py.
Any old Windows task is removed so opening the computer cannot send a second email.
"""

from __future__ import annotations

import subprocess
from datetime import datetime, timedelta

TASK_NAME = "DailyNewsBrief"


def next_run(send_time: str, now: datetime | None = None) -> datetime:
    """Next clock time that has not already passed. Never 'now'."""
    current = now or datetime.now()
    hour, minute = (int(part) for part in send_time.split(":"))
    candidate = current.replace(hour=hour, minute=minute, second=0, microsecond=0)
    if candidate <= current:
        candidate += timedelta(days=1)
    return candidate


def remove_scheduled_task() -> None:
    subprocess.run(
        ["schtasks", "/Delete", "/TN", TASK_NAME, "/F"],
        capture_output=True,
        text=True,
        shell=False,
    )


def task_status() -> dict:
    result = subprocess.run(
        ["schtasks", "/Query", "/TN", TASK_NAME, "/FO", "LIST", "/V"],
        capture_output=True,
        text=True,
        shell=False,
    )
    if result.returncode != 0:
        return {"exists": False, "raw": ""}
    return {"exists": True, "raw": result.stdout}
