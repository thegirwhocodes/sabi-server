"""
Sabi Server Load Test
Simulates concurrent voice call turns to measure real GPU throughput.

Usage:
    python3 load_test.py              # default 5 concurrent
    python3 load_test.py --concurrent 10
    python3 load_test.py --concurrent 20 --turns 5
"""

import asyncio
import argparse
import time
import statistics
import httpx
import os
import struct
import math

SERVER = os.getenv("SABI_URL", "http://localhost:8000")
CHATTERBOX = os.getenv("CHATTERBOX_URL", "http://sabi-chatterbox:8001")
API_KEY = os.getenv("SABI_API_KEY", "")

# Try loading from Docker secrets if env var not set
if not API_KEY:
    try:
        from secret_loader import get_secret
        API_KEY = get_secret("SABI_API_KEY")
    except:
        pass

HEADERS = {"X-API-Key": API_KEY} if API_KEY else {}

# Generate a synthetic WAV file with speech-like audio (sine wave)
def generate_test_wav(duration_s=3, sample_rate=16000, freq=300):
    """Generate a WAV file bytes with a sine wave (simulates speech audio)."""
    n_samples = int(duration_s * sample_rate)
    samples = []
    for i in range(n_samples):
        t = i / sample_rate
        # Mix frequencies to sound more speech-like
        val = 0.3 * math.sin(2 * math.pi * freq * t) + \
              0.2 * math.sin(2 * math.pi * (freq * 1.5) * t) + \
              0.1 * math.sin(2 * math.pi * (freq * 2.1) * t)
        samples.append(int(val * 32767))

    # Build WAV header
    data_size = n_samples * 2  # 16-bit = 2 bytes per sample
    header = struct.pack('<4sI4s4sIHHIIHH4sI',
        b'RIFF', 36 + data_size, b'WAVE',
        b'fmt ', 16, 1, 1, sample_rate, sample_rate * 2, 2, 16,
        b'data', data_size)
    audio_data = struct.pack(f'<{n_samples}h', *samples)
    return header + audio_data


async def simulate_turn(client, turn_id, audio_bytes, results):
    """Simulate one full voice turn: STT -> LLM -> TTS."""
    turn_start = time.monotonic()
    timings = {}

    try:
        # 1. STT
        stt_start = time.monotonic()
        resp = await client.post(
            f"{SERVER}/stt",
            files={"audio": ("test.wav", audio_bytes, "audio/wav")},
            headers=HEADERS,
            timeout=30.0
        )
        resp.raise_for_status()
        timings["stt"] = time.monotonic() - stt_start
        stt_result = resp.json()

        # 2. LLM
        llm_start = time.monotonic()
        resp = await client.post(
            f"{SERVER}/llm",
            headers=HEADERS,
            json={
                "messages": [
                    {"role": "user", "content": stt_result.get("text", "What is 2 plus 3?")}
                ],
                "student_id": f"loadtest-{turn_id}",
                "current_module": 2
            },
            timeout=30.0
        )
        resp.raise_for_status()
        timings["llm"] = time.monotonic() - llm_start
        llm_text = resp.json().get("response", "Well done!")

        # 3. TTS (Chatterbox)
        tts_start = time.monotonic()
        resp = await client.post(
            f"{SERVER}/tts",
            headers=HEADERS,
            json={"text": llm_text[:500]},
            timeout=30.0
        )
        resp.raise_for_status()
        timings["tts"] = time.monotonic() - tts_start

        timings["total"] = time.monotonic() - turn_start
        timings["success"] = True

    except Exception as e:
        timings["total"] = time.monotonic() - turn_start
        timings["success"] = False
        timings["error"] = str(e)

    results.append(timings)
    return timings


async def simulate_call(client, call_id, num_turns, audio_bytes, all_results):
    """Simulate a full call with multiple turns, with realistic pauses between turns."""
    for turn in range(num_turns):
        result = await simulate_turn(client, f"{call_id}-t{turn}", audio_bytes, all_results)
        status = "OK" if result.get("success") else f"FAIL: {result.get('error', '?')[:60]}"
        print(f"  Call {call_id:>3} | Turn {turn+1}/{num_turns} | "
              f"STT {result.get('stt', 0):.2f}s | LLM {result.get('llm', 0):.2f}s | "
              f"TTS {result.get('tts', 0):.2f}s | Total {result.get('total', 0):.2f}s | {status}")

        # Simulate child listening to response + thinking + speaking (~10-15s)
        # In a real call this is where the GPU is FREE to serve other calls
        if turn < num_turns - 1:
            await asyncio.sleep(0.1)  # Minimal pause for load test (not simulating real gaps)


async def run_load_test(concurrent, turns_per_call):
    """Run the full load test."""
    print(f"\n{'='*80}")
    print(f"SABI SERVER LOAD TEST")
    print(f"{'='*80}")
    print(f"Server:      {SERVER}")
    print(f"Concurrent:  {concurrent} calls")
    print(f"Turns/call:  {turns_per_call}")
    print(f"Total turns: {concurrent * turns_per_call}")
    print(f"{'='*80}\n")

    # Check server health
    async with httpx.AsyncClient() as client:
        try:
            resp = await client.get(f"{SERVER}/health", timeout=5.0)
            health = resp.json()
            print(f"Server health: {health}")
        except Exception as e:
            print(f"ERROR: Server unreachable at {SERVER}: {e}")
            return

    # Generate test audio
    print("\nGenerating test audio (3s WAV)...")
    audio_bytes = generate_test_wav(duration_s=3)
    print(f"Audio size: {len(audio_bytes)} bytes")

    # Run concurrent calls
    all_results = []
    print(f"\nStarting {concurrent} concurrent calls...\n")
    test_start = time.monotonic()

    async with httpx.AsyncClient() as client:
        tasks = [
            simulate_call(client, i, turns_per_call, audio_bytes, all_results)
            for i in range(concurrent)
        ]
        await asyncio.gather(*tasks)

    total_time = time.monotonic() - test_start

    # Analyze results
    print(f"\n{'='*80}")
    print(f"RESULTS")
    print(f"{'='*80}")

    successful = [r for r in all_results if r.get("success")]
    failed = [r for r in all_results if not r.get("success")]

    print(f"\nTotal turns:  {len(all_results)}")
    print(f"Successful:   {len(successful)}")
    print(f"Failed:       {len(failed)}")
    print(f"Total time:   {total_time:.2f}s")

    if failed:
        print(f"\nErrors:")
        for f in failed[:5]:
            print(f"  - {f.get('error', 'unknown')[:100]}")

    if successful:
        totals = [r["total"] for r in successful]
        stts = [r["stt"] for r in successful if "stt" in r]
        llms = [r["llm"] for r in successful if "llm" in r]
        ttss = [r["tts"] for r in successful if "tts" in r]

        print(f"\n--- Per-Turn Latency (seconds) ---")
        print(f"{'':>12} {'Mean':>8} {'Median':>8} {'P95':>8} {'Min':>8} {'Max':>8}")

        for name, data in [("STT", stts), ("LLM", llms), ("TTS", ttss), ("Total", totals)]:
            if data:
                data_sorted = sorted(data)
                p95_idx = int(len(data_sorted) * 0.95)
                print(f"{name:>12} {statistics.mean(data):>8.2f} {statistics.median(data):>8.2f} "
                      f"{data_sorted[p95_idx]:>8.2f} {min(data):>8.2f} {max(data):>8.2f}")

        # Throughput
        turns_per_sec = len(successful) / total_time
        print(f"\n--- Throughput ---")
        print(f"Turns/second:           {turns_per_sec:.2f}")
        print(f"Equivalent calls/hour:  {turns_per_sec * 3600 / 7:.0f}  (at 7 turns/call)")
        print(f"Equivalent calls/day:   {turns_per_sec * 3600 * 14 / 7:.0f}  (14hr day)")

        # Capacity estimate
        # In real calls, child listens+speaks for ~50s between turns
        # So GPU serves other calls during that time
        real_turn_interval = 55  # seconds between turns in a real call
        gpu_time_per_turn = statistics.mean(totals)
        concurrent_capacity = real_turn_interval / gpu_time_per_turn
        calls_per_day = concurrent_capacity * (14 * 60 / 7)  # 14hr day, 7min calls

        print(f"\n--- Estimated Real-World Capacity (1 server) ---")
        print(f"GPU time per turn:      {gpu_time_per_turn:.2f}s")
        print(f"Real turn interval:     {real_turn_interval}s (child listens + speaks)")
        print(f"Max concurrent calls:   {concurrent_capacity:.0f}")
        print(f"Calls per day (14hr):   {calls_per_day:.0f}")
        print(f"Students per server:    {calls_per_day * 7 / 5:.0f}  (5 calls/week)")
        print(f"Students per server:    {calls_per_day * 7 / 3:.0f}  (3 calls/week)")

    print(f"\n{'='*80}")
    print(f"DONE")
    print(f"{'='*80}\n")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Sabi Server Load Test")
    parser.add_argument("--concurrent", type=int, default=5, help="Number of concurrent calls")
    parser.add_argument("--turns", type=int, default=3, help="Turns per call")
    args = parser.parse_args()

    asyncio.run(run_load_test(args.concurrent, args.turns))
