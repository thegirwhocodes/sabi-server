#!/usr/bin/env python3
"""Static regression checks for board PIN admin access."""

from __future__ import annotations

from pathlib import Path
import sys


def check(name: str, condition: bool, detail: object = "") -> bool:
    status = "PASS" if condition else "FAIL"
    print(f"{status} {name}" + (f" - {detail}" if detail and not condition else ""))
    return condition


def main() -> int:
    source = Path("main.py").read_text()
    ok = True
    ok &= check("defines_simple_admin_pin", 'SABI_ADMIN_PIN = get_secret("SABI_ADMIN_PIN", "123")' in source)
    ok &= check("accepts_key_query_param", 'request.query_params.get("key")' in source)
    ok &= check("accepts_pin_header", 'request.headers.get("X-Admin-Pin")' in source)
    ok &= check("limits_pin_to_admin_paths", 'path.startswith("/admin/")' in source)
    ok &= check("limits_pin_to_read_only_methods", "READ_ONLY_ADMIN_METHODS" in source)
    ok &= check("keeps_full_api_key_path", "if key != SABI_API_KEY" in source)
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
