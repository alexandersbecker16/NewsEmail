"""Load and save local JSON configuration."""

from __future__ import annotations

import json
from copy import deepcopy
from pathlib import Path
from typing import Any

CONFIG_PATH = Path(__file__).resolve().parent / "config.json"

DEFAULT_CONFIG: dict[str, Any] = {
    "enabled": False,
    "send_time": "08:00",
    "email_title": "Daily News Brief",
    "recipients": [],
    "from_name": "Daily News Brief",
    "from_email": "",
    "password": "",
    "last_sent": None,
    "last_attempt": None,
    "last_error": None,
}

# Common providers — picked automatically from the from-email domain
SMTP_BY_DOMAIN = {
    "gmail.com": ("smtp.gmail.com", 587),
    "googlemail.com": ("smtp.gmail.com", 587),
    "outlook.com": ("smtp.office365.com", 587),
    "hotmail.com": ("smtp.office365.com", 587),
    "live.com": ("smtp.office365.com", 587),
    "yahoo.com": ("smtp.mail.yahoo.com", 587),
    "icloud.com": ("smtp.mail.me.com", 587),
    "me.com": ("smtp.mail.me.com", 587),
}


def smtp_for_email(email: str) -> tuple[str, int]:
    domain = (email or "").rsplit("@", 1)[-1].strip().lower()
    return SMTP_BY_DOMAIN.get(domain, ("smtp.gmail.com", 587))


def load_config() -> dict[str, Any]:
    if not CONFIG_PATH.exists():
        save_config(DEFAULT_CONFIG)
        return deepcopy(DEFAULT_CONFIG)

    with CONFIG_PATH.open("r", encoding="utf-8") as handle:
        data = json.load(handle)

    merged = deepcopy(DEFAULT_CONFIG)
    merged.update({k: v for k, v in data.items() if k != "smtp"})

    # Migrate older smtp-shaped configs
    smtp = data.get("smtp") or {}
    if smtp:
        if not merged.get("from_email") and smtp.get("from_email"):
            merged["from_email"] = smtp["from_email"]
        if not merged.get("from_name") and smtp.get("from_name"):
            merged["from_name"] = smtp["from_name"]
        if not merged.get("password") and smtp.get("password"):
            merged["password"] = smtp["password"]

    return merged


def save_config(config: dict[str, Any]) -> None:
    # Keep only the simple user-facing fields on disk
    clean = {
        "enabled": bool(config.get("enabled")),
        "send_time": config.get("send_time") or "08:00",
        "email_title": config.get("email_title") or "Daily News Brief",
        "recipients": list(config.get("recipients") or []),
        "from_name": config.get("from_name") or "Daily News Brief",
        "from_email": config.get("from_email") or "",
        "password": config.get("password") or "",
        "last_sent": config.get("last_sent"),
        "last_attempt": config.get("last_attempt"),
        "last_error": config.get("last_error"),
    }
    with CONFIG_PATH.open("w", encoding="utf-8") as handle:
        json.dump(clean, handle, indent=2)
        handle.write("\n")


def public_config(config: dict[str, Any]) -> dict[str, Any]:
    """Return config safe to show in the UI (mask password)."""
    visible = deepcopy(config)
    visible["password_set"] = bool(visible.get("password"))
    visible["password"] = ""
    return visible
