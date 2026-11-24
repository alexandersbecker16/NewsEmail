"""Create / update / remove the Windows Task Scheduler job."""

from __future__ import annotations

import subprocess
import sys
from datetime import datetime, timedelta
from pathlib import Path

TASK_NAME = "DailyNewsBrief"
ROOT = Path(__file__).resolve().parent


def _python_exe() -> Path:
    venv_python = ROOT / ".venv" / "Scripts" / "python.exe"
    if venv_python.exists():
        return venv_python
    return Path(sys.executable)


def _next_run(send_time: str) -> datetime:
    """Next clock time that has not already passed. Never 'now'."""
    hour, minute = (int(part) for part in send_time.split(":"))
    candidate = datetime.now().replace(hour=hour, minute=minute, second=0, microsecond=0)
    if candidate <= datetime.now():
        candidate += timedelta(days=1)
    return candidate


def sync_scheduled_task(enabled: bool, send_time: str) -> str:
    """
    Register a daily task that launches only at send_time, then exits.
    The first run is the next future occurrence, so updating the schedule
    does not send an email immediately.
    Runs on battery, and runs after wake if the computer was asleep.
    """
    if not enabled:
        remove_scheduled_task()
        return "Task removed (emailing disabled)."

    nxt = _next_run(send_time)
    hour, minute = (int(part) for part in send_time.split(":"))
    due_today = datetime.now().replace(hour=hour, minute=minute, second=0, microsecond=0)
    python = _python_exe()
    script = ROOT / "send_news.py"
    # Wake-from-sleep is included because turning a PC back on often does not count as a new sign-in.
    # At startup needs administrator rights on this PC, so it is not registered.
    ps = """
$ErrorActionPreference = 'Stop'
$daily = New-ScheduledTaskTrigger -Daily -At '{time}'
$daily.StartBoundary = '{due_today}'
$logon = New-ScheduledTaskTrigger -AtLogOn -User $env:USERNAME
$logon.Delay = 'PT1M'
$wakeClass = Get-CimClass -ClassName MSFT_TaskEventTrigger -Namespace Root/Microsoft/Windows/TaskScheduler
$wake = New-CimInstance -CimClass $wakeClass -ClientOnly
$wake.Enabled = $true
$wake.Delay = 'PT1M'
$wake.Subscription = "<QueryList><Query Id='0' Path='System'><Select Path='System'>*[System[Provider[@Name='Microsoft-Windows-Kernel-Power'] and EventID=107]]</Select></Query></QueryList>"
$action = New-ScheduledTaskAction -Execute '{python}' -Argument '"{script}"' -WorkingDirectory '{root}'
$settings = New-ScheduledTaskSettingsSet -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries -StartWhenAvailable -MultipleInstances IgnoreNew
Register-ScheduledTask -TaskName '{name}' -Action $action -Trigger $daily,$logon,$wake -Settings $settings -Force | Out-Null
""".format(
        time=due_today.strftime("%H:%M"),
        due_today=due_today.strftime("%Y-%m-%dT%H:%M:%S"),
        python=str(python).replace("'", "''"),
        script=str(script).replace("'", "''"),
        root=str(ROOT).replace("'", "''"),
        name=TASK_NAME,
    )
    result = subprocess.run(
        ["powershell", "-NoProfile", "-NonInteractive", "-Command", ps],
        capture_output=True,
        text=True,
        shell=False,
    )
    if result.returncode != 0:
        detail = (result.stderr or result.stdout or "Unknown scheduler error").strip()
        raise RuntimeError(detail)
    return f"Scheduled daily at {nxt.strftime('%H:%M')}. Next run {nxt.strftime('%Y-%m-%d %H:%M')}."


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
