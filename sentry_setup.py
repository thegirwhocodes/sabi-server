"""
Sentry initialization for sabi-server.

Mirrors the privacy posture of curriculum-app's sentry.server.config.ts:
  - send_default_pii=False (NDPA + COPPA — child voice data must not leave our servers)
  - every outgoing event passes through scrub_event(), which masks phone numbers
    and strips auth headers/cookies before anything reaches Sentry
  - transcripts are never attached: we do not add breadcrumbs/extras with child
    speech, and local variables in stack traces stay disabled

Fail-open by design: if sentry-sdk is not installed or SENTRY_DSN is unset,
init_sentry() logs and returns without touching the app.

Do not regress send_default_pii to True without re-evaluating compliance.
"""

import logging
import os
import re

logger = logging.getLogger("sabi.sentry")

# Matches E.164 (+234...), local Nigerian (080...), US and general phone shapes,
# including the learner_key form "+234...::name" — the number part gets masked.
_PHONE_RE = re.compile(r"\+?\d[\d\s\-().]{6,}\d")

_SENSITIVE_HEADERS = {"authorization", "x-api-key", "cookie", "set-cookie", "x-sentry-auth"}


def _mask_text(value):
    if not isinstance(value, str):
        return value
    return _PHONE_RE.sub("[phone]", value)


def _scrub_container(obj, depth=0):
    """Recursively mask phone numbers in dict/list/str structures."""
    if depth > 8:
        return obj
    if isinstance(obj, str):
        return _mask_text(obj)
    if isinstance(obj, dict):
        return {k: _scrub_container(v, depth + 1) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_scrub_container(v, depth + 1) for v in obj]
    return obj


def scrub_event(event, hint=None):
    """before_send hook — mask phone numbers everywhere, drop sensitive headers."""
    try:
        for key in ("message", "transaction"):
            if event.get(key):
                event[key] = _mask_text(event[key])

        logentry = event.get("logentry")
        if logentry:
            for key in ("message", "formatted"):
                if logentry.get(key):
                    logentry[key] = _mask_text(logentry[key])
            if logentry.get("params"):
                logentry["params"] = _scrub_container(logentry["params"])

        for exc in (event.get("exception", {}) or {}).get("values", []) or []:
            if exc.get("value"):
                exc["value"] = _mask_text(exc["value"])

        for crumb in (event.get("breadcrumbs", {}) or {}).get("values", []) or []:
            if crumb.get("message"):
                crumb["message"] = _mask_text(crumb["message"])
            if crumb.get("data"):
                crumb["data"] = _scrub_container(crumb["data"])

        request = event.get("request")
        if request:
            headers = request.get("headers")
            if isinstance(headers, dict):
                request["headers"] = {
                    k: ("[filtered]" if k.lower() in _SENSITIVE_HEADERS else v)
                    for k, v in headers.items()
                }
            request.pop("cookies", None)
            if request.get("query_string"):
                request["query_string"] = _mask_text(request["query_string"])
            if request.get("url"):
                request["url"] = _mask_text(request["url"])
            if request.get("data"):
                request["data"] = _scrub_container(request["data"])

        if event.get("extra"):
            event["extra"] = _scrub_container(event["extra"])
        if event.get("tags"):
            event["tags"] = _scrub_container(event["tags"])
        if event.get("user"):
            # No child identity ever goes to Sentry.
            event["user"] = {"id": "[filtered]"}
    except Exception:
        # Scrubbing must never block error reporting entirely — but if the
        # scrubber itself breaks, dropping the event is safer than leaking PII.
        logger.exception("Sentry scrub failed — dropping event to avoid PII leak")
        return None
    return event


def init_sentry():
    dsn = os.getenv("SENTRY_DSN", "").strip()
    if not dsn:
        logger.info("SENTRY_DSN not set — Sentry disabled")
        return False
    try:
        import sentry_sdk
    except ImportError:
        logger.warning("sentry-sdk not installed — Sentry disabled")
        return False

    sentry_sdk.init(
        dsn=dsn,
        environment=os.getenv("SENTRY_ENVIRONMENT", "production"),
        traces_sample_rate=float(os.getenv("SENTRY_TRACES_SAMPLE_RATE", "1.0")),
        send_default_pii=False,
        include_local_variables=False,  # locals can hold transcripts/phone numbers
        before_send=scrub_event,
        before_send_transaction=scrub_event,
    )
    logger.info("Sentry initialized (env=%s)", os.getenv("SENTRY_ENVIRONMENT", "production"))
    return True
