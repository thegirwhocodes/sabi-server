#!/usr/bin/env python3
"""Static checks for internal AI rate-limit bypass wiring."""

from __future__ import annotations

from pathlib import Path
import sys


def check(name: str, condition: bool, detail: object = "") -> bool:
    status = "PASS" if condition else "FAIL"
    print(f"{status} {name}" + (f" - {detail}" if detail and not condition else ""))
    return condition


def main() -> int:
    source = Path("main.py").read_text(encoding="utf-8")
    ok = True
    ok &= check(
        "bypass_is_configurable",
        "SABI_TRUST_API_KEY_FOR_RATE_LIMIT_BYPASS" in source,
    )
    ok &= check(
        "bypass_only_checked_for_ai_paths",
        'if path in self.AI_PATHS:' in source
        and "if self._is_trusted_ai_request(request):" in source,
    )
    ok &= check(
        "trusted_request_requires_api_key",
        "supplied_key == SABI_API_KEY" in source
        and "not SABI_API_KEY" in source,
    )
    ok &= check(
        "voice_routes_still_limited",
        'elif path.startswith(self.VOICE_PREFIXES):' in source
        and 'tier = "voice"' in source,
    )
    ok &= check(
        "public_limit_response_unchanged",
        '{"error": "Too Many Requests"}' in source and "status_code=429" in source,
    )
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
