#!/usr/bin/env python3
"""Static checks for Chatterbox GPU backpressure and cache wiring."""

from __future__ import annotations

from pathlib import Path
import sys


def check(name: str, condition: bool, detail: object = "") -> bool:
    status = "PASS" if condition else "FAIL"
    print(f"{status} {name}" + (f" - {detail}" if detail and not condition else ""))
    return condition


def main() -> int:
    server = Path("chatterbox-tts/server.py").read_text(encoding="utf-8")
    compose = Path("docker-compose.yml").read_text(encoding="utf-8")
    ok = True
    ok &= check("max_concurrent_env", "CHATTERBOX_MAX_CONCURRENT" in server)
    ok &= check("queue_limit_env", "CHATTERBOX_MAX_QUEUE" in server)
    ok &= check("queue_timeout_env", "CHATTERBOX_QUEUE_TIMEOUT_SECONDS" in server)
    ok &= check("bounded_semaphore", "asyncio.BoundedSemaphore" in server)
    ok &= check("queue_backpressure_503", "queue_full" in server and "status_code=status" in server)
    ok &= check("blocking_gpu_work_off_event_loop", "asyncio.to_thread" in server)
    ok &= check("tts_cache_enabled", "CHATTERBOX_CACHE_ENABLED" in server and "X-Cache" in server)
    ok &= check("cache_key_hashes_processed_text", "hashlib.sha256" in server and "preprocess_text(text)" in server)
    ok &= check("health_exposes_inference_stats", '"inference":' in server and '"stats": stats' in server)
    ok &= check("compose_sets_gpu_envs", "CHATTERBOX_MAX_CONCURRENT" in compose and "CHATTERBOX_MAX_QUEUE" in compose)
    ok &= check("compose_persists_tts_cache", "chatterbox_tts_cache:/app/tts_cache" in compose)
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
