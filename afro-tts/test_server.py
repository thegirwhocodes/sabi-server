"""
Test script for the Afro-TTS server.
Run this after the server is up to verify it works.

Usage:
    python test_server.py [--url http://localhost:8001]
"""

import sys
import time
import argparse
import urllib.request
import json


def test_health(base_url: str) -> bool:
    """Test the health endpoint."""
    print("1. Testing /health...")
    try:
        req = urllib.request.Request(f"{base_url}/health")
        with urllib.request.urlopen(req, timeout=10) as resp:
            data = json.loads(resp.read())
            print(f"   Status: {data['status']}")
            print(f"   Model: {data['model']}")
            print(f"   Speakers: {data.get('speakers', [])}")
            print(f"   GPU: {data.get('gpu', {})}")
            return data["status"] == "ok"
    except Exception as e:
        print(f"   FAILED: {e}")
        return False


def test_voices(base_url: str) -> bool:
    """Test the voices endpoint."""
    print("2. Testing /voices...")
    try:
        req = urllib.request.Request(f"{base_url}/voices")
        with urllib.request.urlopen(req, timeout=10) as resp:
            data = json.loads(resp.read())
            print(f"   Voices: {data['voices']}")
            print(f"   Default: {data['default']}")
            return True
    except Exception as e:
        print(f"   FAILED: {e}")
        return False


def test_tts_wav(base_url: str) -> bool:
    """Test TTS with WAV output."""
    print("3. Testing /tts (WAV output)...")
    payload = json.dumps({
        "text": "Hello! My name is Sabi, and I am here to help you learn.",
        "format": "wav",
    }).encode("utf-8")

    try:
        req = urllib.request.Request(
            f"{base_url}/tts",
            data=payload,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        start = time.time()
        with urllib.request.urlopen(req, timeout=120) as resp:
            audio_data = resp.read()
            elapsed = time.time() - start
            inference_time = resp.headers.get("X-Inference-Time", "?")
            audio_duration = resp.headers.get("X-Audio-Duration", "?")

            print(f"   Content-Type: {resp.headers.get('Content-Type')}")
            print(f"   Audio size: {len(audio_data):,} bytes")
            print(f"   Inference time: {inference_time}s")
            print(f"   Audio duration: {audio_duration}s")
            print(f"   Total request time: {elapsed:.2f}s")

            # Save the output
            with open("/tmp/afro_tts_test.wav", "wb") as f:
                f.write(audio_data)
            print("   Saved to /tmp/afro_tts_test.wav")

            return len(audio_data) > 100
    except Exception as e:
        print(f"   FAILED: {e}")
        return False


def test_tts_mp3(base_url: str) -> bool:
    """Test TTS with MP3 output."""
    print("4. Testing /tts (MP3 output)...")
    payload = json.dumps({
        "text": "Let us count together. One, two, three, four, five.",
        "format": "mp3",
    }).encode("utf-8")

    try:
        req = urllib.request.Request(
            f"{base_url}/tts",
            data=payload,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        start = time.time()
        with urllib.request.urlopen(req, timeout=120) as resp:
            audio_data = resp.read()
            elapsed = time.time() - start

            print(f"   Content-Type: {resp.headers.get('Content-Type')}")
            print(f"   Audio size: {len(audio_data):,} bytes")
            print(f"   Total request time: {elapsed:.2f}s")

            with open("/tmp/afro_tts_test.mp3", "wb") as f:
                f.write(audio_data)
            print("   Saved to /tmp/afro_tts_test.mp3")

            return len(audio_data) > 100
    except Exception as e:
        print(f"   FAILED: {e}")
        return False


def main():
    parser = argparse.ArgumentParser(description="Test Afro-TTS server")
    parser.add_argument("--url", default="http://localhost:8001", help="Server URL")
    args = parser.parse_args()

    base_url = args.url.rstrip("/")
    print(f"Testing Afro-TTS server at {base_url}")
    print("=" * 50)

    results = []
    results.append(("Health", test_health(base_url)))
    results.append(("Voices", test_voices(base_url)))
    results.append(("TTS WAV", test_tts_wav(base_url)))
    results.append(("TTS MP3", test_tts_mp3(base_url)))

    print("=" * 50)
    print("Results:")
    all_passed = True
    for name, passed in results:
        status = "PASS" if passed else "FAIL"
        print(f"  {name}: {status}")
        if not passed:
            all_passed = False

    sys.exit(0 if all_passed else 1)


if __name__ == "__main__":
    main()
