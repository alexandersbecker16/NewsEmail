"""Schedule the daily email on Gmail so this PC does not have to be awake."""

from __future__ import annotations

import json
import os
import re
import secrets
import subprocess
import webbrowser
from pathlib import Path
from typing import Any

from scheduler import next_run, remove_scheduled_task

ROOT = Path(__file__).resolve().parent
CLOUD_DIR = ROOT / "cloud"
STATE_PATH = CLOUD_DIR / "state.json"
TOOLS_DIR = Path(os.environ.get("LOCALAPPDATA", str(ROOT))) / "DailyNewsBrief"
DEPLOYMENT_RE = re.compile(r"(AKfycb[0-9A-Za-z_-]+)")

WINDOWS_TO_IANA = {
    "Dateline Standard Time": "Etc/GMT+12",
    "UTC-11": "Etc/GMT+11",
    "Aleutian Standard Time": "America/Adak",
    "Hawaiian Standard Time": "Pacific/Honolulu",
    "Marquesas Standard Time": "Pacific/Marquesas",
    "Alaskan Standard Time": "America/Anchorage",
    "UTC-09": "Etc/GMT+9",
    "Pacific Standard Time (Mexico)": "America/Tijuana",
    "UTC-08": "Etc/GMT+8",
    "Pacific Standard Time": "America/Los_Angeles",
    "US Mountain Standard Time": "America/Phoenix",
    "Mountain Standard Time (Mexico)": "America/Mazatlan",
    "Mountain Standard Time": "America/Denver",
    "Yukon Standard Time": "America/Whitehorse",
    "Central America Standard Time": "America/Guatemala",
    "Central Standard Time": "America/Chicago",
    "Easter Island Standard Time": "Pacific/Easter",
    "Central Standard Time (Mexico)": "America/Mexico_City",
    "Canada Central Standard Time": "America/Regina",
    "SA Pacific Standard Time": "America/Bogota",
    "Eastern Standard Time (Mexico)": "America/Cancun",
    "Eastern Standard Time": "America/New_York",
    "US Eastern Standard Time": "America/Indiana/Indianapolis",
    "Cuba Standard Time": "America/Havana",
    "SA Western Standard Time": "America/Caracas",
    "Atlantic Standard Time": "America/Halifax",
    "Newfoundland Standard Time": "America/St_Johns",
    "SA Eastern Standard Time": "America/Cayenne",
    "Argentina Standard Time": "America/Buenos_Aires",
    "E. South America Standard Time": "America/Sao_Paulo",
    "Greenland Standard Time": "America/Godthab",
    "UTC-02": "Etc/GMT+2",
    "Mid-Atlantic Standard Time": "Etc/GMT+2",
    "Azores Standard Time": "Atlantic/Azores",
    "Cape Verde Standard Time": "Atlantic/Cape_Verde",
    "UTC": "Etc/UTC",
    "GMT Standard Time": "Europe/London",
    "Greenwich Standard Time": "Atlantic/Reykjavik",
    "W. Europe Standard Time": "Europe/Berlin",
    "Central Europe Standard Time": "Europe/Budapest",
    "Romance Standard Time": "Europe/Paris",
    "Central European Standard Time": "Europe/Warsaw",
    "W. Central Africa Standard Time": "Africa/Lagos",
    "GTB Standard Time": "Europe/Bucharest",
    "Middle East Standard Time": "Asia/Beirut",
    "Egypt Standard Time": "Africa/Cairo",
    "E. Europe Standard Time": "Europe/Chisinau",
    "South Africa Standard Time": "Africa/Johannesburg",
    "Israel Standard Time": "Asia/Jerusalem",
    "Russian Standard Time": "Europe/Moscow",
    "Turkey Standard Time": "Europe/Istanbul",
    "Arab Standard Time": "Asia/Riyadh",
    "E. Africa Standard Time": "Africa/Nairobi",
    "Iran Standard Time": "Asia/Tehran",
    "Arabian Standard Time": "Asia/Dubai",
    "Azerbaijan Standard Time": "Asia/Baku",
    "Russia Time Zone 3": "Europe/Samara",
    "Afghanistan Standard Time": "Asia/Kabul",
    "West Asia Standard Time": "Asia/Tashkent",
    "Pakistan Standard Time": "Asia/Karachi",
    "India Standard Time": "Asia/Kolkata",
    "Sri Lanka Standard Time": "Asia/Colombo",
    "Nepal Standard Time": "Asia/Kathmandu",
    "Central Asia Standard Time": "Asia/Almaty",
    "Bangladesh Standard Time": "Asia/Dhaka",
    "Myanmar Standard Time": "Asia/Yangon",
    "SE Asia Standard Time": "Asia/Bangkok",
    "Altai Standard Time": "Asia/Barnaul",
    "N. Central Asia Standard Time": "Asia/Novosibirsk",
    "China Standard Time": "Asia/Shanghai",
    "Singapore Standard Time": "Asia/Singapore",
    "W. Australia Standard Time": "Australia/Perth",
    "Taipei Standard Time": "Asia/Taipei",
    "Tokyo Standard Time": "Asia/Tokyo",
    "Korea Standard Time": "Asia/Seoul",
    "AUS Central Standard Time": "Australia/Darwin",
    "Cen. Australia Standard Time": "Australia/Adelaide",
    "AUS Eastern Standard Time": "Australia/Sydney",
    "E. Australia Standard Time": "Australia/Brisbane",
    "Tasmania Standard Time": "Australia/Hobart",
    "West Pacific Standard Time": "Pacific/Port_Moresby",
    "Vladivostok Standard Time": "Asia/Vladivostok",
    "New Zealand Standard Time": "Pacific/Auckland",
    "Fiji Standard Time": "Pacific/Fiji",
    "UTC+12": "Etc/GMT-12",
    "Samoa Standard Time": "Pacific/Apia",
    "Tonga Standard Time": "Pacific/Tongatapu",
}


class CloudSetupNeeded(Exception):
    def __init__(self, message: str, url: str = ""):
        super().__init__(message)
        self.url = url


def cloud_public_status() -> dict[str, bool]:
    state = load_state()
    ready = bool(state.get("trigger_ready"))
    return {
        "ready": ready,
        "awaiting_approval": bool(state.get("exec_url")) and not ready,
    }


def expected_ready_token() -> str:
    return str(load_state().get("ready_token") or "")


def mark_trigger_ready() -> None:
    state = load_state()
    state["trigger_ready"] = True
    save_state(state)
    remove_scheduled_task()


def sync_cloud(config: dict[str, Any], *, prompt: bool = False) -> str:
    """Push the saved settings to Gmail and keep the Windows task from also sending."""
    send_time = str(config.get("send_time") or "08:00")
    slot = next_run(send_time)
    if not config.get("enabled"):
        remove_scheduled_task()
        if _tools_present() and _logged_in():
            _push_settings(config)
        return "Emails are off. Nothing will be sent."

    ensure_scheduler()
    if not _logged_in():
        login_gmail()
    _push_settings(config)
    state = load_state()
    if state.get("trigger_ready"):
        remove_scheduled_task()
        return (
            f"One email a day at {send_time}, even if this computer is closed, asleep, or off. "
            f"Next send {slot.strftime('%Y-%m-%d %H:%M')}. "
            "Opening the computer does not send another."
        )

    url = _deploy_setup_page(state)
    editor = ""
    clasp_file = CLOUD_DIR / ".clasp.json"
    if clasp_file.exists():
        script_id = str(json.loads(clasp_file.read_text(encoding="utf-8")).get("scriptId") or "")
        if script_id:
            editor = f"https://script.google.com/d/{script_id}/edit"
    if prompt and editor:
        webbrowser.open(editor)
    raise CloudSetupNeeded(
        "In the script that opened, choose installSchedule, click Run, then Allow. "
        f"After that, one email sends at {send_time} even if this computer is closed, asleep, or off.",
        url=editor or url,
    )


def load_state() -> dict[str, Any]:
    if not STATE_PATH.exists():
        return {}
    try:
        data = json.loads(STATE_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return data if isinstance(data, dict) else {}


def save_state(state: dict[str, Any]) -> None:
    CLOUD_DIR.mkdir(exist_ok=True)
    STATE_PATH.write_text(json.dumps(state, indent=2) + "\n", encoding="utf-8")


def _push_settings(config: dict[str, Any]) -> None:
    if not _logged_in():
        raise CloudSetupNeeded(
            "Approve Gmail once so the email can send while this computer is closed or off."
        )
    _write_project_files(config)
    _ensure_project()
    result = _clasp(["push", "--force"])
    if result.returncode != 0:
        raise RuntimeError(_detail(result))


def _write_project_files(config: dict[str, Any]) -> None:
    state = load_state()
    if not state.get("ready_token"):
        state["ready_token"] = secrets.token_urlsafe(24)
        save_state(state)

    send_time = str(config.get("send_time") or "08:00")
    payload = {
        "enabled": bool(config.get("enabled")),
        "sendTime": send_time,
        "emailTitle": config.get("email_title") or "Daily News Brief",
        "fromName": config.get("from_name") or "Daily News Brief",
        "fromEmail": config.get("from_email") or "",
        "recipients": [str(email).strip() for email in (config.get("recipients") or []) if str(email).strip()],
        "timeZone": _iana_timezone(),
        "notBefore": next_run(send_time).strftime("%Y-%m-%dT%H:%M"),
        "readyToken": state["ready_token"],
    }
    if "password" in payload:
        raise RuntimeError("Refusing to upload the email password.")

    CLOUD_DIR.mkdir(exist_ok=True)
    (CLOUD_DIR / "Config.js").write_text(
        "var CONFIG = " + json.dumps(payload, indent=2) + ";\n",
        encoding="utf-8",
    )
    manifest_path = CLOUD_DIR / "appsscript.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["timeZone"] = payload["timeZone"]
    manifest_path.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")


def _ensure_project() -> None:
    if (CLOUD_DIR / ".clasp.json").exists():
        return
    result = _clasp(["create", "--title", "Daily News Brief", "--type", "standalone"])
    if result.returncode != 0:
        detail = _detail(result)
        if "Apps Script API" in detail or "script.googleapis.com" in detail:
            raise CloudSetupNeeded(
                "Turn on the Google Apps Script API, then click Save again.",
                url="https://script.google.com/home/usersettings",
            )
        raise RuntimeError(detail)


def _deploy_setup_page(state: dict[str, Any]) -> str:
    args = ["deploy", "--description", "Daily News Brief schedule"]
    if state.get("deployment_id"):
        args.extend(["--deploymentId", state["deployment_id"]])
    result = _clasp(args)
    output = f"{result.stdout}\n{result.stderr}"
    if result.returncode != 0:
        raise RuntimeError(_detail(result))
    match = DEPLOYMENT_RE.search(output)
    if not match:
        raise RuntimeError(_detail(result) or "Could not publish the Gmail schedule.")
    deployment_id = match.group(1)
    state["deployment_id"] = deployment_id
    state["exec_url"] = f"https://script.google.com/macros/s/{deployment_id}/exec"
    save_state(state)
    return state["exec_url"]


def _logged_in() -> bool:
    return (Path.home() / ".clasprc.json").exists()


def login_gmail() -> None:
    """Approve only the Gmail script access this schedule needs. No Cloud Platform scope."""
    if _logged_in():
        return

    import threading
    from http.server import BaseHTTPRequestHandler, HTTPServer
    from urllib.parse import parse_qs, urlencode, urlparse

    import requests

    client_id, client_secret = _clasp_oauth_client()
    scopes = [
        "https://www.googleapis.com/auth/script.deployments",
        "https://www.googleapis.com/auth/script.projects",
        "https://www.googleapis.com/auth/script.webapp.deploy",
        "https://www.googleapis.com/auth/userinfo.email",
    ]
    holder: dict[str, str] = {}

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self) -> None:  # noqa: N802
            query = parse_qs(urlparse(self.path).query)
            if "code" in query:
                holder["code"] = query["code"][0]
                body = b"Gmail scheduling is approved. You can close this tab."
                self.send_response(200)
            else:
                holder["error"] = query.get("error", ["denied"])[0]
                body = b"Gmail scheduling was not approved."
                self.send_response(400)
            self.send_header("Content-Type", "text/plain; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, format: str, *args: object) -> None:
            return

    server = HTTPServer(("127.0.0.1", 0), Handler)
    port = server.server_address[1]
    redirect_uri = f"http://localhost:{port}"
    thread = threading.Thread(target=server.handle_request, daemon=True)
    thread.start()
    auth_url = "https://accounts.google.com/o/oauth2/v2/auth?" + urlencode(
        {
            "access_type": "offline",
            "prompt": "consent",
            "response_type": "code",
            "client_id": client_id,
            "redirect_uri": redirect_uri,
            "scope": " ".join(scopes),
        }
    )
    print(auth_url, flush=True)
    webbrowser.open(auth_url)
    thread.join(timeout=300)
    server.server_close()
    if "code" not in holder:
        raise CloudSetupNeeded("Gmail was not approved, so the email cannot send while the computer is off.", auth_url)

    token_response = requests.post(
        "https://oauth2.googleapis.com/token",
        data={
            "code": holder["code"],
            "client_id": client_id,
            "client_secret": client_secret,
            "redirect_uri": redirect_uri,
            "grant_type": "authorization_code",
        },
        timeout=30,
    )
    token_response.raise_for_status()
    token = token_response.json()
    expires_in = int(token.get("expires_in") or 3600)
    payload = {
        "token": {
            "access_token": token["access_token"],
            "refresh_token": token.get("refresh_token"),
            "scope": token.get("scope") or " ".join(scopes),
            "token_type": token.get("token_type") or "Bearer",
            "expiry_date": int((__import__("time").time() + expires_in) * 1000),
        },
        "oauth2ClientSettings": {
            "clientId": client_id,
            "clientSecret": client_secret,
            "redirectUri": "http://localhost",
        },
        "isLocalCreds": False,
    }
    path = Path.home() / ".clasprc.json"
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")


def _clasp_oauth_client() -> tuple[str, str]:
    auth_js = TOOLS_DIR / "node_modules" / "@google" / "clasp" / "build" / "src" / "auth.js"
    text = auth_js.read_text(encoding="utf-8")
    client_ids = re.findall(r"clientId: '([^']+)'", text)
    client_secrets = re.findall(r"clientSecret: '([^']+)'", text)
    if not client_ids or not client_secrets:
        raise CloudSetupNeeded("Could not prepare the Gmail approval.")
    return client_ids[0], client_secrets[0]


def _clasp(args: list[str]) -> subprocess.CompletedProcess[str]:
    clasp = _clasp_path()
    node_home = _node_home()
    env = os.environ.copy()
    env["PATH"] = str(node_home) + os.pathsep + env.get("PATH", "")
    return subprocess.run(
        ["cmd", "/c", str(clasp), *args],
        cwd=CLOUD_DIR,
        capture_output=True,
        text=True,
        timeout=120,
        env=env,
        shell=False,
    )


def _tools_present() -> bool:
    return _node_home_optional() is not None and (TOOLS_DIR / "node_modules" / ".bin" / "clasp.cmd").exists()


def ensure_scheduler() -> None:
    """Download a private copy of Node and clasp the first time someone turns emails on."""
    if _tools_present():
        return
    if os.name != "nt":
        raise CloudSetupNeeded("Double-click start_dashboard.bat on Windows to use this app.")
    TOOLS_DIR.mkdir(parents=True, exist_ok=True)
    node_home = _download_node()
    env = os.environ.copy()
    env["PATH"] = str(node_home) + os.pathsep + env.get("PATH", "")
    result = subprocess.run(
        [str(node_home / "npm.cmd"), "install", "--prefix", str(TOOLS_DIR), "@google/clasp@2.4.2"],
        cwd=TOOLS_DIR,
        capture_output=True,
        text=True,
        timeout=300,
        env=env,
        shell=False,
    )
    if result.returncode != 0 or not _tools_present():
        raise CloudSetupNeeded(
            "Could not set up the Gmail scheduler. Check your internet connection and click On again."
        )


def _download_node() -> Path:
    import urllib.request
    import zipfile

    version, folder = _node_release()
    dest = TOOLS_DIR / folder
    if not (dest / "node.exe").exists():
        zip_path = TOOLS_DIR / f"{folder}.zip"
        url = f"https://nodejs.org/dist/{version}/{folder}.zip"
        try:
            urllib.request.urlretrieve(url, zip_path)
            with zipfile.ZipFile(zip_path) as archive:
                archive.extractall(TOOLS_DIR)
        except (OSError, zipfile.BadZipFile) as exc:
            raise CloudSetupNeeded(
                "Could not set up the Gmail scheduler. Check your internet connection and click On again."
            ) from exc
        finally:
            zip_path.unlink(missing_ok=True)
    if not (dest / "node.exe").exists():
        raise CloudSetupNeeded(
            "Could not set up the Gmail scheduler. Check your internet connection and click On again."
        )
    (TOOLS_DIR / "nodehome.txt").write_text(str(dest), encoding="utf-8")
    return dest


def _node_release() -> tuple[str, str]:
    import urllib.request

    fallback = "v26.13.1"
    version = fallback
    try:
        with urllib.request.urlopen("https://nodejs.org/dist/index.json", timeout=30) as response:
            releases = json.loads(response.read().decode("utf-8"))
        for release in releases:
            if release.get("lts"):
                version = str(release["version"])
                break
    except (OSError, ValueError, KeyError):
        version = fallback
    return version, f"node-{version}-win-x64"


def _node_home_optional() -> Path | None:
    pointer = TOOLS_DIR / "nodehome.txt"
    if pointer.exists():
        home = Path(pointer.read_text(encoding="utf-8").strip())
        if (home / "node.exe").exists():
            return home
    matches = [path for path in TOOLS_DIR.glob("node-v*-win-x64") if (path / "node.exe").exists()]
    return matches[-1] if matches else None


def _clasp_path() -> Path:
    path = TOOLS_DIR / "node_modules" / ".bin" / "clasp.cmd"
    if not path.exists():
        raise CloudSetupNeeded(
            "The Gmail scheduler is not installed yet. Leave this window open and try Save again in a minute."
        )
    return path


def _node_home() -> Path:
    home = _node_home_optional()
    if home is not None:
        return home
    raise CloudSetupNeeded(
        "The Gmail scheduler is not installed yet. Leave this window open and click On again."
    )


def _iana_timezone() -> str:
    try:
        result = subprocess.run(
            ["powershell", "-NoProfile", "-Command", "(Get-TimeZone).Id"],
            capture_output=True,
            text=True,
            timeout=20,
            shell=False,
        )
        name = (result.stdout or "").strip()
    except (OSError, subprocess.TimeoutExpired):
        name = ""
    return WINDOWS_TO_IANA.get(name, "Etc/UTC")


def _detail(result: subprocess.CompletedProcess[str]) -> str:
    text = (result.stderr or result.stdout or "Could not update the Gmail schedule.").strip()
    return text[-1200:]
