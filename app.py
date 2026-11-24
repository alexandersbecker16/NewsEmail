"""Local dashboard for Daily News Brief."""

from __future__ import annotations

import re
import webbrowser
from datetime import datetime
from threading import Timer

from flask import Flask, jsonify, render_template, request

from config_store import load_config, public_config, save_config
from email_sender import send_news_email
from news_fetcher import fetch_headlines
from scheduler import sync_scheduled_task, task_status

app = Flask(__name__)

EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
TIME_RE = re.compile(r"^([01]\d|2[0-3]):([0-5]\d)$")


@app.get("/")
def index():
    return render_template("index.html")


@app.get("/api/config")
def get_config():
    config = load_config()
    return jsonify({"config": public_config(config), "task": task_status()})


@app.post("/api/config")
def update_config():
    payload = request.get_json(force=True) or {}
    config = load_config()

    if "enabled" in payload:
        config["enabled"] = bool(payload["enabled"])

    if "send_time" in payload:
        send_time = str(payload["send_time"]).strip()
        if not TIME_RE.match(send_time):
            return jsonify({"ok": False, "error": "Pick a valid send time."}), 400
        config["send_time"] = send_time

    if "email_title" in payload:
        title = str(payload["email_title"]).strip() or "Daily News Brief"
        config["email_title"] = title

    if "recipients" in payload:
        recipients = []
        for raw in payload["recipients"]:
            email = str(raw).strip()
            if not email:
                continue
            if not EMAIL_RE.match(email):
                return jsonify({"ok": False, "error": f"Invalid email: {email}"}), 400
            if email not in recipients:
                recipients.append(email)
        config["recipients"] = recipients

    if "from_name" in payload:
        config["from_name"] = str(payload["from_name"]).strip() or "Daily News Brief"

    if "from_email" in payload:
        from_email = str(payload["from_email"]).strip()
        if from_email and not EMAIL_RE.match(from_email):
            return jsonify({"ok": False, "error": "From email looks invalid."}), 400
        config["from_email"] = from_email

    if "password" in payload and str(payload["password"]).strip():
        config["password"] = str(payload["password"]).strip()

    try:
        schedule_msg = sync_scheduled_task(config["enabled"], config["send_time"])
    except Exception as exc:
        return jsonify({"ok": False, "error": f"Could not update schedule: {exc}"}), 500

    save_config(config)
    return jsonify(
        {
            "ok": True,
            "message": f"Saved. {schedule_msg}",
            "config": public_config(config),
            "task": task_status(),
        }
    )


@app.post("/api/send-now")
def send_now():
    config = load_config()
    try:
        headlines = fetch_headlines(5)
        if not headlines:
            raise RuntimeError("No headlines available right now.")
        send_news_email(config, headlines)
        config["last_sent"] = datetime.now().isoformat(timespec="seconds")
        config["last_error"] = None
        save_config(config)
        return jsonify(
            {
                "ok": True,
                "message": f"Sent to {len(config['recipients'])} recipient(s).",
                "config": public_config(config),
            }
        )
    except Exception as exc:
        config["last_error"] = str(exc)
        save_config(config)
        return jsonify({"ok": False, "error": str(exc), "config": public_config(config)}), 500


def main() -> None:
    config = load_config()
    try:
        sync_scheduled_task(config["enabled"], config["send_time"])
    except Exception as exc:
        print(f"Warning: could not sync Task Scheduler: {exc}")

    Timer(0.8, lambda: webbrowser.open("http://127.0.0.1:5055")).start()
    # Threaded so saving settings can't block the page from loading.
    app.run(host="127.0.0.1", port=5055, debug=False, threaded=True)


if __name__ == "__main__":
    main()
