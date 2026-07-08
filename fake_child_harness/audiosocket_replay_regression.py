#!/usr/bin/env python3
"""Regression checks for the AudioSocket replay harness."""

from __future__ import annotations

import asyncio
import math
from pathlib import Path
import struct
import tempfile
import uuid

from .audiosocket_replay import (
    AUDIO_TYPE_DTMF,
    AUDIO_TYPE_HANGUP,
    AUDIO_TYPE_PCM_8K,
    AUDIO_TYPE_UUID,
    FRAME_BYTES,
    SAMPLE_RATE,
    SAMPLE_WIDTH,
    read_packet,
    replay_wav_to_audiosocket,
    send_packet,
    write_8khz_mono_wav,
)


def check(name: str, condition: bool, detail: object = "") -> bool:
    status = "PASS" if condition else "FAIL"
    print(f"{status} {name}" + (f" - {detail}" if detail and not condition else ""))
    return condition


def _tone_pcm(seconds: float = 0.28) -> bytes:
    samples = int(SAMPLE_RATE * seconds)
    values = [
        int(1200 * math.sin(2 * math.pi * 440 * index / SAMPLE_RATE))
        for index in range(samples)
    ]
    return struct.pack(f"<{samples}h", *values)


async def _run_fake_server_replay(tmp_dir: Path) -> tuple[dict, dict]:
    sent_wav = tmp_dir / "caller.wav"
    response_wav = tmp_dir / "sabi-response.wav"
    caller_pcm = _tone_pcm(0.32)
    response_pcm = b"\0" * (FRAME_BYTES * 3)
    write_8khz_mono_wav(sent_wav, caller_pcm)

    observed: dict = {
        "uuid": "",
        "pcm_bytes": 0,
        "dtmf": [],
        "hangup": False,
        "packet_types": [],
    }

    async def handle_client(reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
        try:
            packet_type, payload = await read_packet(reader)
            observed["packet_types"].append(packet_type)
            if packet_type == AUDIO_TYPE_UUID:
                observed["uuid"] = str(uuid.UUID(bytes=payload))
            sent_response = False
            while True:
                packet_type, payload = await read_packet(reader)
                observed["packet_types"].append(packet_type)
                if packet_type == AUDIO_TYPE_PCM_8K:
                    observed["pcm_bytes"] += len(payload)
                    if not sent_response:
                        await send_packet(writer, AUDIO_TYPE_PCM_8K, response_pcm)
                        sent_response = True
                elif packet_type == AUDIO_TYPE_DTMF:
                    observed["dtmf"].append(payload.decode("ascii", errors="replace"))
                elif packet_type == AUDIO_TYPE_HANGUP:
                    observed["hangup"] = True
                    await send_packet(writer, AUDIO_TYPE_HANGUP)
                    break
        except asyncio.IncompleteReadError:
            pass
        finally:
            writer.close()
            await writer.wait_closed()

    server = await asyncio.start_server(handle_client, "127.0.0.1", 0)
    try:
        port = server.sockets[0].getsockname()[1]
        call_uuid = str(uuid.uuid4())
        result = await replay_wav_to_audiosocket(
            wav_path=sent_wav,
            host="127.0.0.1",
            port=port,
            call_uuid=call_uuid,
            output_wav=response_wav,
            realtime=False,
            dtmf_sequence="45#",
            dtmf_after_seconds=0.01,
            receive_grace_seconds=0.05,
        )
        observed["expected_uuid"] = call_uuid
        observed["expected_pcm_bytes"] = len(caller_pcm)
        observed["response_wav_exists"] = response_wav.exists()
        observed["response_wav_bytes"] = response_wav.stat().st_size if response_wav.exists() else 0
        return result.to_dict(), observed
    finally:
        server.close()
        await server.wait_closed()


def main() -> int:
    with tempfile.TemporaryDirectory(prefix="sabi-audiosocket-replay-") as tmp:
        result, observed = asyncio.run(_run_fake_server_replay(Path(tmp)))

    ok = True
    ok &= check("uuid_packet_sent", observed["uuid"] == observed["expected_uuid"], observed)
    ok &= check(
        "pcm_audio_sent",
        observed["pcm_bytes"] == observed["expected_pcm_bytes"] and result["sent_audio_bytes"] == observed["pcm_bytes"],
        {"result": result, "observed": observed},
    )
    ok &= check("dtmf_sequence_sent", observed["dtmf"] == ["4", "5", "#"], observed)
    ok &= check("hangup_packet_sent", observed["hangup"] is True, observed)
    ok &= check(
        "response_audio_captured",
        result["received_audio_bytes"] > 0 and observed["response_wav_exists"] and observed["response_wav_bytes"] > 44,
        {"result": result, "observed": observed},
    )
    ok &= check("no_error_packets", result["error_packets"] == [], result)
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
