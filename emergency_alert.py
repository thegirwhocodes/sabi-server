"""Best-effort emergency alerts for Sabi phone safeguarding incidents.

This mirrors the curriculum-app alert fanout for the live Python phone path.
Every function is intentionally fail-soft: an alert channel can fail without
breaking the child-facing turn.
"""

from __future__ import annotations

import base64
import json
import logging
import os
import urllib.parse
import urllib.request
from datetime import datetime, timedelta, timezone
from typing import Any

log = logging.getLogger("sabi.emergency_alert")


def _env(name: str) -> str:
    return os.environ.get(name, "").strip()


def _post_json(url: str, payload: dict[str, Any], headers: dict[str, str] | None = None, timeout: int = 5) -> tuple[bool, str]:
    try:
        data = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(
            url,
            data=data,
            method="POST",
            headers={"Content-Type": "application/json", **(headers or {})},
        )
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return 200 <= resp.status < 300, f"http {resp.status}"
    except Exception as exc:  # noqa: BLE001 - alerting must never throw
        return False, str(exc)


def _post_form(
    url: str,
    payload: dict[str, Any],
    headers: dict[str, str] | None = None,
    timeout: int = 5,
) -> tuple[bool, str]:
    try:
        data = urllib.parse.urlencode(payload).encode("utf-8")
        req = urllib.request.Request(
            url,
            data=data,
            method="POST",
            headers={"Content-Type": "application/x-www-form-urlencoded", **(headers or {})},
        )
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return 200 <= resp.status < 300, f"http {resp.status}"
    except Exception as exc:  # noqa: BLE001
        return False, str(exc)


def _alert_recipients() -> list[str]:
    seen: set[str] = set()
    recipients: list[str] = []
    for name in ("EMERGENCY_ALERT_PHONE", "EMERGENCY_ALERT_PHONE_BACKUP"):
        value = _env(name)
        if value and value not in seen:
            seen.add(value)
            recipients.append(value)
    return recipients


def _summary(*, category: str, risk_level: int, reason: str, student_id: str | None, call_id: str | None, utterance: str) -> str:
    snippet = (utterance or "").replace("\n", " ")[:220]
    return (
        f"SABI SAFEGUARDING risk={risk_level} category={category} reason={reason}. "
        f"student={student_id or 'unknown'} call={call_id or 'unknown'}. "
        f"utterance={snippet}"
    )


def _send_at_sms(recipients: list[str], message: str) -> tuple[bool, str]:
    api_key = _env("AT_API_KEY") or _env("AFRICASTALKING_API_KEY")
    username = _env("AT_USERNAME") or _env("AFRICASTALKING_USERNAME")
    if not (api_key and username and recipients):
        return False, "not configured"
    payload: dict[str, Any] = {
        "username": username,
        "to": ",".join(recipients),
        "message": message[:1600],
    }
    sender = _env("AT_SENDER_ID")
    if sender:
        payload["from"] = sender
    return _post_form(
        "https://api.africastalking.com/version1/messaging",
        payload,
        headers={"apiKey": api_key, "Accept": "application/json"},
        timeout=8,
    )


def _send_twilio_sms(recipients: list[str], message: str) -> tuple[bool, str]:
    sid = _env("TWILIO_ACCOUNT_SID")
    token = _env("TWILIO_AUTH_TOKEN")
    from_number = _env("TWILIO_PHONE_NUMBER")
    if not (sid and token and from_number and recipients):
        return False, "not configured"

    auth = base64.b64encode(f"{sid}:{token}".encode("utf-8")).decode("ascii")
    results = []
    ok_any = False
    for recipient in recipients:
        ok, detail = _post_form(
            f"https://api.twilio.com/2010-04-01/Accounts/{sid}/Messages.json",
            {"From": from_number, "To": recipient, "Body": message[:1500]},
            headers={"Authorization": f"Basic {auth}"},
            timeout=8,
        )
        ok_any = ok_any or ok
        results.append(f"{recipient}:{detail}")
    return ok_any, "; ".join(results)


def _send_webhook(payload: dict[str, Any]) -> tuple[bool, str]:
    url = _env("EMERGENCY_ALERT_WEBHOOK_URL")
    if not url:
        return False, "not configured"
    return _post_json(url, payload, timeout=8)


def _send_calendar_event(title: str, message: str) -> tuple[bool, str]:
    client_id = _env("GOOGLE_OAUTH_CLIENT_ID")
    client_secret = _env("GOOGLE_OAUTH_CLIENT_SECRET")
    refresh_token = _env("GOOGLE_OAUTH_REFRESH_TOKEN")
    calendar_id = _env("GOOGLE_CALENDAR_ID") or "primary"
    if not (client_id and client_secret and refresh_token):
        return False, "not configured"

    try:
        token_req = urllib.request.Request(
            "https://oauth2.googleapis.com/token",
            data=urllib.parse.urlencode({
                "client_id": client_id,
                "client_secret": client_secret,
                "refresh_token": refresh_token,
                "grant_type": "refresh_token",
            }).encode("utf-8"),
            method="POST",
            headers={"Content-Type": "application/x-www-form-urlencoded"},
        )
        with urllib.request.urlopen(token_req, timeout=8) as resp:
            access_token = json.loads(resp.read().decode("utf-8")).get("access_token")
        if not access_token:
            return False, "no access token"
    except Exception as exc:  # noqa: BLE001
        return False, f"token:{exc}"

    start = datetime.now(timezone.utc)
    end = start + timedelta(minutes=15)
    event = {
        "summary": title,
        "description": message,
        "start": {"dateTime": start.isoformat()},
        "end": {"dateTime": end.isoformat()},
        "reminders": {"useDefault": False, "overrides": [{"method": "popup", "minutes": 0}]},
    }
    return _post_json(
        f"https://www.googleapis.com/calendar/v3/calendars/{urllib.parse.quote(calendar_id, safe='')}/events",
        event,
        headers={"Authorization": f"Bearer {access_token}"},
        timeout=8,
    )


def dispatch_emergency_alert_sync(
    *,
    student_id: str | None,
    category: str,
    risk_level: int,
    reason: str,
    utterance_redacted: str,
    channel: str | None = None,
    call_id: str | None = None,
) -> list[dict[str, Any]]:
    if os.environ.get("SABI_DISABLE_EMERGENCY_ALERTS", "0").lower() in {"1", "true", "yes", "on"}:
        return [{"channel": "all", "ok": False, "detail": "disabled"}]

    message = _summary(
        category=category,
        risk_level=risk_level,
        reason=reason,
        student_id=student_id,
        call_id=call_id,
        utterance=utterance_redacted,
    )
    payload = {
        "type": "sabi_safeguarding_alert",
        "student_id": student_id,
        "category": category,
        "risk_level": risk_level,
        "reason": reason,
        "utterance_redacted": utterance_redacted,
        "channel": channel,
        "call_id": call_id,
        "message": message,
    }
    recipients = _alert_recipients()
    results: list[dict[str, Any]] = []

    at_ok, at_detail = _send_at_sms(recipients, message)
    results.append({"channel": "africas_talking_sms", "ok": at_ok, "detail": at_detail})
    if not at_ok:
        tw_ok, tw_detail = _send_twilio_sms(recipients, message)
        results.append({"channel": "twilio_sms", "ok": tw_ok, "detail": tw_detail})

    webhook_ok, webhook_detail = _send_webhook(payload)
    results.append({"channel": "webhook", "ok": webhook_ok, "detail": webhook_detail})

    cal_ok, cal_detail = _send_calendar_event("Sabi safeguarding alert", message)
    results.append({"channel": "calendar", "ok": cal_ok, "detail": cal_detail})

    for result in results:
        if result["ok"]:
            log.warning("[EMERGENCY_ALERT] sent via %s", result["channel"])
        else:
            log.info("[EMERGENCY_ALERT] %s skipped/failed: %s", result["channel"], result["detail"])
    return results
