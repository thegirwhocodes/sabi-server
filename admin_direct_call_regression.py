#!/usr/bin/env python3
"""Focused regression checks for the protected admin direct-call control."""

from __future__ import annotations

import re
import sys
from pathlib import Path


def check(name: str, condition: bool, detail: object = "") -> bool:
    status = "PASS" if condition else "FAIL"
    print(f"{status} {name}" + (f" - {detail}" if detail and not condition else ""))
    return condition


def main() -> int:
    source = Path("main.py").read_text()
    ui = Path("admin_review.py").read_text()
    ok = True

    direct_call_block = source.split("async def direct_sabi_call(", 1)[1].split("async def ", 1)[0]
    auth_block = source.split("class APIKeyMiddleware", 1)[1].split("app.add_middleware", 1)[0]

    ok &= check(
        "server_normalizes_and_validates_direct_call_number",
        "def normalize_direct_call_phone" in source
        and "normalized_phone = normalize_direct_call_phone(phone)" in direct_call_block
        and "8 <= len(digits) <= 15" in source,
    )
    ok &= check(
        "server_rejects_invalid_number_before_originate",
        '"reason": "invalid_phone"' in direct_call_block
        and direct_call_block.index("if not normalized_phone") < direct_call_block.index("ami_originate("),
    )
    ok &= check(
        "server_returns_only_safe_call_metadata",
        '"status": "direct_call_initiated"' in direct_call_block
        and '"phone": normalized_phone' in direct_call_block
        and "AMI_SECRET" not in direct_call_block
        and "SABI_API_KEY" not in direct_call_block,
    )
    ok &= check(
        "read_only_pin_cannot_place_call",
        "request.method in READ_ONLY_ADMIN_METHODS" in auth_block
        and 'READ_ONLY_ADMIN_METHODS = {"GET", "HEAD", "OPTIONS"}' in source
        and "if key != SABI_API_KEY" in auth_block,
    )
    ok &= check(
        "ui_has_explicit_operator_action_and_states",
        'id="call-number"' in ui
        and "Call a phone number" in ui
        and 'id="call-submit"' in ui
        and "Asking Sabi to place the call..." in ui
        and "Sabi could not start the call" in ui,
    )
    ok &= check(
        "ui_does_not_embed_server_secrets",
        not re.search(r"SABI_API_KEY\s*=|AMI_SECRET\s*=", ui),
    )
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
