"""Regression checks for Sabi flash-callback test routing.

The public Sabi number should keep direct inbound call-in as the default, while
allowing specific testing caller IDs to be routed through flash-callback and
optionally aliased to a different callback target.

Run with:
    python flash_callback_mode_regression.py
"""

from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parent
DIALPLAN = ROOT / "asterisk" / "extensions.conf"
MAIN = ROOT / "main.py"


def _section(source: str, name: str) -> str:
    marker = f"[{name}]"
    start = source.index(marker)
    next_section = source.find("\n[", start + len(marker))
    if next_section == -1:
        return source[start:]
    return source[start:next_section]


def _check(name: str, condition: bool, detail: object = "") -> bool:
    status = "ok" if condition else "FAIL"
    suffix = f" - {detail}" if detail else ""
    print(f"[{status}] {name}{suffix}")
    return condition


def main() -> int:
    dialplan = DIALPLAN.read_text()
    main_source = MAIN.read_text()

    from_at = _section(dialplan, "from-at")
    sabi_inbound = _section(dialplan, "sabi-inbound")
    sabi_flash = _section(dialplan, "sabi-flash")

    ok = True
    ok &= _check(
        "from_at_accepts_plus_numbers",
        "exten => _+X.,1,Set(SAFE_CALLER=${FILTER(0-9+,${CALLERID(num)})})" in from_at,
    )
    ok &= _check(
        "from_at_accepts_bare_numbers",
        "exten => _X.,1,Set(SAFE_CALLER=${FILTER(0-9+,${CALLERID(num)})})" in from_at,
    )
    ok &= _check(
        "from_at_asks_sabi_for_route",
        "http://sabi:8000/asterisk/inbound-route" in from_at
        and '--data-urlencode "phone=${SAFE_CALLER}"' in from_at,
    )
    ok &= _check(
        "from_at_routes_flash_tests_to_callback",
        'GotoIf($["${SABI_ROUTE}" = "flash"]?sabi-flash,s,1)' in from_at,
    )
    ok &= _check(
        "from_at_defaults_to_inbound",
        "Goto(sabi-inbound,s,1)" in from_at,
    )
    ok &= _check(
        "flash_gives_short_ring_before_hangup",
        "Ringing()" in sabi_flash and "Wait(2)" in sabi_flash and "Hangup(16)" in sabi_flash,
    )
    ok &= _check(
        "flash_posts_callback_after_hangup",
        "http://sabi:8000/asterisk/flash" in sabi_flash
        and '--data-urlencode "phone=${CALLBACK_NUM}"' in sabi_flash,
    )
    ok &= _check(
        "inbound_uses_production_audiosocket",
        "AudioSocket(${AS_UUID},sabi:9019)" in sabi_inbound,
    )
    ok &= _check(
        "main_uses_shared_phone_normalizer",
        "from phone_utils import normalize_phone_number" in main_source
        and "normalized = normalize_phone_number(phone)" in main_source,
    )
    ok &= _check(
        "main_supports_callback_aliases",
        "SABI_FLASH_CALLBACK_PHONE_ALIASES" in main_source
        and "def resolve_flash_callback_phone" in main_source
        and "_flash_callback_aliases().get(incoming_phone, incoming_phone)" in main_source,
    )
    ok &= _check(
        "main_exposes_inbound_route_endpoint",
        '@app.post("/asterisk/inbound-route")' in main_source
        and "if incoming_phone and (FLASH_CALLBACK_ALL or callback_phone != incoming_phone):" in main_source
        and "PlainTextResponse(route)" in main_source,
    )
    ok &= _check(
        "flash_callback_all_defaults_on",
        'FLASH_CALLBACK_ALL = os.getenv("SABI_FLASH_CALLBACK_ALL", "1")' in main_source,
    )
    ok &= _check(
        "flash_callback_originate_uses_alias_target",
        "ami_originate(callback_phone, attempt=1)" in main_source
        and '"incoming_phone": incoming_phone' in main_source,
    )
    ok &= _check(
        "callback_defaults_are_telco_friendly",
        'FLASH_CALLBACK_DELAY_SECONDS = float(os.getenv("FLASH_CALLBACK_DELAY_SECONDS", "4"))' in main_source
        and 'FLASH_CALLBACK_COOLDOWN_SECONDS = int(os.getenv("FLASH_CALLBACK_COOLDOWN_SECONDS", "45"))'
        in main_source
        and 'FLASH_CALLBACK_RETRY_ENABLED = os.getenv("FLASH_CALLBACK_RETRY_ENABLED", "1")' in main_source,
    )

    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
