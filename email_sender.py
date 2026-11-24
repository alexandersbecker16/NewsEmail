"""Build and send the daily news email."""

from __future__ import annotations

import smtplib
import ssl
from datetime import datetime
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from typing import Any


def build_email_html(
    headlines: list[dict[str, Any]],
    send_date: datetime | None = None,
    title: str = "Daily News Brief",
) -> str:
    when = (send_date or datetime.now()).strftime("%A, %B %d, %Y")
    items = []
    for i, story in enumerate(headlines, start=1):
        link = story.get("link") or "#"
        items.append(
            f"""
            <tr>
              <td style="padding:0 0 28px 0;border-bottom:1px solid #e6e2da;">
                <p style="margin:0 0 6px 0;font-size:12px;letter-spacing:0.08em;text-transform:uppercase;color:#6b655c;">
                  {i}. {story.get('source', 'News')}
                </p>
                <h2 style="margin:0 0 10px 0;font-size:20px;line-height:1.35;color:#1c1915;">
                  <a href="{link}" style="color:#1c1915;text-decoration:none;">{story['title']}</a>
                </h2>
                <p style="margin:0 0 12px 0;font-size:15px;line-height:1.55;color:#4a453c;">
                  {story.get('summary', '')}
                </p>
                <a href="{link}" style="font-size:14px;color:#0b5fff;text-decoration:none;font-weight:600;">
                  Read more →
                </a>
              </td>
            </tr>
            """
        )

    return f"""
    <!DOCTYPE html>
    <html>
    <body style="margin:0;padding:0;background:#f3efe7;font-family:Georgia,'Times New Roman',serif;">
      <table role="presentation" width="100%" cellspacing="0" cellpadding="0" style="background:#f3efe7;padding:32px 16px;">
        <tr>
          <td align="center">
            <table role="presentation" width="600" cellspacing="0" cellpadding="0" style="max-width:600px;background:#fffdf8;border:1px solid #ddd6c8;padding:36px 32px;">
              <tr>
                <td>
                  <p style="margin:0 0 4px 0;font-size:12px;letter-spacing:0.14em;text-transform:uppercase;color:#8a8276;">
                    {title}
                  </p>
                  <h1 style="margin:0 0 8px 0;font-size:28px;color:#1c1915;">Market-moving headlines</h1>
                  <p style="margin:0 0 28px 0;font-size:14px;color:#6b655c;">{when}</p>
                  <table role="presentation" width="100%" cellspacing="0" cellpadding="0">
                    {''.join(items)}
                  </table>
                  <p style="margin:28px 0 0 0;font-size:12px;color:#8a8276;line-height:1.5;">
                    Ranked by likely market impact, largest first. Sources include Reuters, AP, the Financial Times, The Wall Street Journal, The Economist, and BBC.
                  </p>
                </td>
              </tr>
            </table>
          </td>
        </tr>
      </table>
    </body>
    </html>
    """


def build_email_text(
    headlines: list[dict[str, Any]],
    send_date: datetime | None = None,
    title: str = "Daily News Brief",
) -> str:
    when = (send_date or datetime.now()).strftime("%A, %B %d, %Y")
    lines = [f"{title} — {when}", "", "Market-moving headlines, largest impact first", ""]
    for i, story in enumerate(headlines, start=1):
        lines.append(f"{i}. [{story.get('source', 'News')}] {story['title']}")
        lines.append(story.get("summary", ""))
        if story.get("link"):
            lines.append(story["link"])
        lines.append("")
    lines.append("Sources: Reuters, AP, Financial Times, Wall Street Journal, The Economist, BBC")
    return "\n".join(lines)


def send_news_email(config: dict[str, Any], headlines: list[dict[str, Any]]) -> None:
    from config_store import smtp_for_email

    recipients = [r.strip() for r in config.get("recipients", []) if r and r.strip()]
    if not recipients:
        raise ValueError("Add at least one recipient.")

    from_email = (config.get("from_email") or "").strip()
    from_name = (config.get("from_name") or "Daily News Brief").strip()
    password = (config.get("password") or "").strip()
    # Backward-compatible with older smtp config shape
    smtp = config.get("smtp") or {}
    if not from_email:
        from_email = (smtp.get("from_email") or smtp.get("username") or "").strip()
    if not password:
        password = (smtp.get("password") or "").strip()
    if from_name == "Daily News Brief" and smtp.get("from_name"):
        from_name = str(smtp["from_name"]).strip() or from_name

    if not from_email or not password:
        raise ValueError("Set who the email comes from (email + password).")

    host, port = smtp_for_email(from_email)
    now = datetime.now()
    title = (config.get("email_title") or "Daily News Brief").strip()
    subject = f"{title} — {now.strftime('%b %d, %Y')}"
    html_body = build_email_html(headlines, now, title=title)
    text_body = build_email_text(headlines, now, title=title)

    message = MIMEMultipart("alternative")
    message["Subject"] = subject
    message["From"] = f"{from_name} <{from_email}>"
    message["To"] = ", ".join(recipients)
    message.attach(MIMEText(text_body, "plain", "utf-8"))
    message.attach(MIMEText(html_body, "html", "utf-8"))

    context = ssl.create_default_context()
    try:
        with smtplib.SMTP(host, port, timeout=30) as server:
            server.ehlo()
            server.starttls(context=context)
            server.ehlo()
            server.login(from_email, password)
            server.sendmail(from_email, recipients, message.as_string())
    except smtplib.SMTPAuthenticationError as exc:
        raise ValueError(_login_help(from_email)) from exc
    except (smtplib.SMTPServerDisconnected, ConnectionResetError, TimeoutError) as exc:
        raise ValueError(_login_help(from_email)) from exc


def _login_help(from_email: str) -> str:
    if from_email.lower().endswith("@gmail.com") or from_email.lower().endswith("@googlemail.com"):
        return (
            "Gmail refused the sign-in. Use a Gmail App Password "
            "(16 letters), not your normal Gmail password. "
            "Create one at https://myaccount.google.com/apppasswords"
        )
    return "The email server closed the sign-in. Check the email and password."
