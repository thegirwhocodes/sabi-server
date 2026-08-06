#!/usr/bin/env python3
"""Regression checks for Twilio/AT carrier selection around one lesson lane."""

from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parent


def check(name: str, condition: bool) -> bool:
    print(f"{'PASS' if condition else 'FAIL'} {name}")
    return condition


def section(source: str, name: str) -> str:
    start = source.index(f"[{name}]")
    end = source.find("\n[", start + len(name) + 2)
    return source[start:] if end == -1 else source[start:end]


def main() -> int:
    app = (ROOT / "main.py").read_text()
    pjsip = (ROOT / "asterisk" / "pjsip.conf").read_text()
    dialplan = (ROOT / "asterisk" / "extensions.conf").read_text()
    example_env = (ROOT / ".env.example").read_text()

    twilio = section(pjsip, "twilio")
    twilio_aor = section(pjsip, "twilio-aor")
    twilio_identify = section(pjsip, "twilio-identify")
    incoming = section(dialplan, "from-twilio")
    callback = section(dialplan, "sabi-callback-run")

    ok = True
    ok &= check(
        "runtime_provider_selects_named_pjsip_endpoint",
        'SABI_SIP_PROVIDER = os.getenv("SABI_SIP_PROVIDER", "africastalking")' in app
        and '"africastalking": "africastalking"' in app
        and '"twilio": "twilio"' in app
        and 'f"Channel: PJSIP/{phone}@{SABI_SIP_ENDPOINT}\\r\\n"' in app,
    )
    ok &= check(
        "unknown_provider_falls_back_to_at",
        'SABI_SIP_PROVIDER = "africastalking"' in app,
    )
    ok &= check(
        "twilio_uses_ip_acl_without_sip_secret",
        "context=from-twilio" in twilio
        and "outbound_auth=" not in twilio
        and "password=" not in pjsip
        and "sabi-education-for-equality.pstn.twilio.com" in twilio_aor,
    )
    ok &= check(
        "twilio_keeps_g711_phone_audio",
        "allow=ulaw" in twilio and "allow=alaw" in twilio,
    )
    ok &= check(
        "twilio_signaling_is_allowlisted",
        "endpoint=twilio" in twilio_identify and "match=54.172.60.0/23" in twilio_identify,
    )
    ok &= check(
        "twilio_inbound_reuses_production_lane",
        "Goto(sabi-inbound,s,1)" in incoming
        and "AudioSocket(${AS_UUID},sabi:9020)" in callback,
    )
    ok &= check(
        "at_route_remains_available_for_rollback",
        "[africastalking]" in pjsip and "[from-at]" in dialplan,
    )
    ok &= check(
        "example_environment_documents_twilio_switch",
        "SABI_SIP_PROVIDER=twilio" in example_env
        and "TWILIO_PHONE_NUMBER=+17153122345" in example_env,
    )
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
