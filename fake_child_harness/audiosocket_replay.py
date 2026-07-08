from __future__ import annotations

import argparse
import asyncio
from dataclasses import dataclass
import json
from pathlib import Path
import time
import uuid
import wave
from typing import Any


AUDIO_TYPE_HANGUP = 0x00
AUDIO_TYPE_UUID = 0x01
AUDIO_TYPE_DTMF = 0x03
AUDIO_TYPE_PCM_8K = 0x10
AUDIO_TYPE_ERROR = 0xFF
SAMPLE_RATE = 8000
SAMPLE_WIDTH = 2
CHANNELS = 1
FRAME_MS = 20
FRAME_BYTES = int(SAMPLE_RATE * SAMPLE_WIDTH * FRAME_MS / 1000)


@dataclass(frozen=True)
class AudioSocketReplayResult:
    call_uuid: str
    host: str
    port: int
    sent_audio_seconds: float
    sent_audio_bytes: int
    sent_dtmf: tuple[str, ...]
    received_audio_seconds: float
    received_audio_bytes: int
    received_packets: int
    error_packets: tuple[str, ...]
    output_wav: str | None
    elapsed_seconds: float

    def to_dict(self) -> dict[str, Any]:
        return {
            "call_uuid": self.call_uuid,
            "host": self.host,
            "port": self.port,
            "sent_audio_seconds": self.sent_audio_seconds,
            "sent_audio_bytes": self.sent_audio_bytes,
            "sent_dtmf": list(self.sent_dtmf),
            "received_audio_seconds": self.received_audio_seconds,
            "received_audio_bytes": self.received_audio_bytes,
            "received_packets": self.received_packets,
            "error_packets": list(self.error_packets),
            "output_wav": self.output_wav,
            "elapsed_seconds": self.elapsed_seconds,
        }


async def replay_wav_to_audiosocket(
    *,
    wav_path: Path,
    host: str,
    port: int,
    call_uuid: str | None = None,
    output_wav: Path | None = None,
    frame_ms: int = FRAME_MS,
    realtime: bool = True,
    dtmf_sequence: str = "",
    dtmf_after_seconds: float = 0.0,
    receive_grace_seconds: float = 4.0,
) -> AudioSocketReplayResult:
    pcm = read_8khz_mono_pcm(wav_path)
    safe_uuid = str(uuid.UUID(call_uuid)) if call_uuid else str(uuid.uuid4())
    sent_dtmf: list[str] = []
    received_audio = bytearray()
    error_packets: list[str] = []
    received_packets = 0
    start = time.monotonic()

    reader, writer = await asyncio.open_connection(host, port)
    receiver_task = asyncio.create_task(
        _receive_packets(reader, received_audio=received_audio, error_packets=error_packets)
    )

    try:
        await send_packet(writer, AUDIO_TYPE_UUID, uuid.UUID(safe_uuid).bytes)
        dtmf_task = None
        if dtmf_sequence:
            dtmf_task = asyncio.create_task(
                _send_dtmf_sequence(
                    writer,
                    dtmf_sequence=dtmf_sequence,
                    delay_seconds=dtmf_after_seconds,
                    sent_dtmf=sent_dtmf,
                )
            )
        step = int(SAMPLE_RATE * SAMPLE_WIDTH * frame_ms / 1000)
        step = max(2, step - (step % 2))
        for offset in range(0, len(pcm), step):
            before = time.monotonic()
            await send_packet(writer, AUDIO_TYPE_PCM_8K, pcm[offset : offset + step])
            if realtime:
                elapsed = time.monotonic() - before
                await asyncio.sleep(max(0.0, frame_ms / 1000 - elapsed))
        if dtmf_task:
            await dtmf_task
        await asyncio.sleep(max(0.0, receive_grace_seconds))
        await send_packet(writer, AUDIO_TYPE_HANGUP)
    finally:
        writer.close()
        try:
            await writer.wait_closed()
        except Exception:
            pass
        try:
            received_packets = await asyncio.wait_for(receiver_task, timeout=1.0)
        except Exception:
            receiver_task.cancel()

    output_path: str | None = None
    if output_wav and received_audio:
        write_8khz_mono_wav(output_wav, bytes(received_audio))
        output_path = str(output_wav)

    elapsed_seconds = round(time.monotonic() - start, 3)
    return AudioSocketReplayResult(
        call_uuid=safe_uuid,
        host=host,
        port=port,
        sent_audio_seconds=round(len(pcm) / (SAMPLE_RATE * SAMPLE_WIDTH), 3),
        sent_audio_bytes=len(pcm),
        sent_dtmf=tuple(sent_dtmf),
        received_audio_seconds=round(len(received_audio) / (SAMPLE_RATE * SAMPLE_WIDTH), 3),
        received_audio_bytes=len(received_audio),
        received_packets=received_packets,
        error_packets=tuple(error_packets),
        output_wav=output_path,
        elapsed_seconds=elapsed_seconds,
    )


async def send_packet(writer: asyncio.StreamWriter, packet_type: int, payload: bytes = b"") -> None:
    writer.write(bytes([packet_type]) + len(payload).to_bytes(2, "big") + payload)
    await writer.drain()


async def read_packet(reader: asyncio.StreamReader) -> tuple[int, bytes]:
    header = await reader.readexactly(3)
    packet_type = header[0]
    length = int.from_bytes(header[1:3], "big")
    payload = await reader.readexactly(length) if length else b""
    return packet_type, payload


async def _receive_packets(
    reader: asyncio.StreamReader,
    *,
    received_audio: bytearray,
    error_packets: list[str],
) -> int:
    packets = 0
    while True:
        try:
            packet_type, payload = await read_packet(reader)
        except (asyncio.IncompleteReadError, ConnectionError):
            break
        packets += 1
        if packet_type == AUDIO_TYPE_PCM_8K:
            received_audio.extend(payload)
        elif packet_type == AUDIO_TYPE_ERROR:
            error_packets.append(payload.decode("utf-8", errors="replace"))
        elif packet_type == AUDIO_TYPE_HANGUP:
            break
    return packets


async def _send_dtmf_sequence(
    writer: asyncio.StreamWriter,
    *,
    dtmf_sequence: str,
    delay_seconds: float,
    sent_dtmf: list[str],
) -> None:
    await asyncio.sleep(max(0.0, delay_seconds))
    for digit in dtmf_sequence:
        await send_packet(writer, AUDIO_TYPE_DTMF, digit.encode("ascii", errors="ignore"))
        sent_dtmf.append(digit)
        await asyncio.sleep(0.08)


def read_8khz_mono_pcm(path: Path) -> bytes:
    with wave.open(str(path), "rb") as wav:
        rate = wav.getframerate()
        channels = wav.getnchannels()
        width = wav.getsampwidth()
        if (rate, channels, width) != (SAMPLE_RATE, CHANNELS, SAMPLE_WIDTH):
            raise ValueError(
                f"{path} must be 8 kHz mono 16-bit PCM WAV; got rate={rate} channels={channels} width={width}"
            )
        return wav.readframes(wav.getnframes())


def write_8khz_mono_wav(path: Path, pcm: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with wave.open(str(path), "wb") as wav:
        wav.setnchannels(CHANNELS)
        wav.setsampwidth(SAMPLE_WIDTH)
        wav.setframerate(SAMPLE_RATE)
        wav.writeframes(pcm)


def main() -> None:
    parser = argparse.ArgumentParser(description="Replay an 8 kHz WAV into a Sabi AudioSocket listener.")
    parser.add_argument("--wav", type=Path, required=True)
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=9019)
    parser.add_argument("--uuid", dest="call_uuid")
    parser.add_argument("--output-wav", type=Path)
    parser.add_argument("--dtmf", default="", help="Optional DTMF sequence to send, e.g. 45#")
    parser.add_argument("--dtmf-after-seconds", type=float, default=0.0)
    parser.add_argument("--receive-grace-seconds", type=float, default=4.0)
    parser.add_argument("--no-realtime", action="store_true", help="Send frames as fast as possible.")
    args = parser.parse_args()

    result = asyncio.run(
        replay_wav_to_audiosocket(
            wav_path=args.wav,
            host=args.host,
            port=args.port,
            call_uuid=args.call_uuid,
            output_wav=args.output_wav,
            realtime=not args.no_realtime,
            dtmf_sequence=args.dtmf,
            dtmf_after_seconds=args.dtmf_after_seconds,
            receive_grace_seconds=args.receive_grace_seconds,
        )
    )
    print(json.dumps(result.to_dict(), indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
