"""Admin-only browser mimic of a Sabi phone call, including flash-callback.

This is never a public production route. ``SABI_BRIEF_PREVIEW_SIMULATOR`` must
be on, the page lives under ``/admin/preview-call``, and the media path speaks
the same AudioSocket protocol a real handset uses (8 kHz PCM, UUID, hangup).
"""

from __future__ import annotations

import array
import asyncio
import json
import logging
import os
import uuid
from typing import Any

from voice_realtime import (
    AUDIO_TYPE_HANGUP,
    AUDIO_TYPE_PCM_8K,
    AUDIO_TYPE_UUID,
    FRAME_BYTES,
    SAMPLE_RATE,
    register_call,
)

logger = logging.getLogger("sabi.preview_call")

PREVIEW_CALLBACK_MODE = "preview_callback"
FLASH_SECONDS = 2.0
DEFAULT_CALLBACK_WAIT_SECONDS = 4.0
DEFAULT_PHONE = "+15555550100"


def simulator_enabled(configured: str | None = None) -> bool:
    value = os.getenv("SABI_BRIEF_PREVIEW_SIMULATOR", "0") if configured is None else configured
    return str(value or "0").strip().lower() in {"1", "true", "yes", "on"}


def callback_wait_seconds() -> float:
    raw = os.getenv("FLASH_CALLBACK_DELAY_SECONDS", str(DEFAULT_CALLBACK_WAIT_SECONDS))
    try:
        return max(1.0, float(raw))
    except (TypeError, ValueError):
        return DEFAULT_CALLBACK_WAIT_SECONDS


def audiosocket_target() -> tuple[str, int]:
    host = os.getenv("SABI_PREVIEW_AUDIOSOCKET_HOST", "127.0.0.1").strip() or "127.0.0.1"
    try:
        port = int(os.getenv("SABI_PREVIEW_AUDIOSOCKET_PORT", "9019"))
    except (TypeError, ValueError):
        port = 9019
    return host, port


def encode_audiosocket_packet(packet_type: int, payload: bytes = b"") -> bytes:
    return bytes([packet_type]) + len(payload).to_bytes(2, "big") + payload


def resample_pcm16(pcm: bytes, source_rate: int, dest_rate: int = SAMPLE_RATE) -> bytes:
    """Linear-resample signed 16-bit mono PCM. Phone path is always 8 kHz."""
    if not pcm or source_rate <= 0:
        return b""
    if len(pcm) % 2:
        pcm = pcm[:-1]
    if source_rate == dest_rate:
        return pcm
    samples = array.array("h")
    samples.frombytes(pcm)
    if not samples:
        return b""
    ratio = dest_rate / source_rate
    n_out = max(1, int(round(len(samples) * ratio)))
    out = array.array("h")
    last = len(samples) - 1
    for i in range(n_out):
        src = i / ratio
        left = min(last, int(src))
        right = min(last, left + 1)
        frac = src - left
        value = samples[left] + (samples[right] - samples[left]) * frac
        out.append(max(-32768, min(32767, int(value))))
    return out.tobytes()


def pad_frame(pcm: bytes, frame_bytes: int = FRAME_BYTES) -> bytes:
    if len(pcm) >= frame_bytes:
        return pcm[:frame_bytes]
    return pcm + bytes(frame_bytes - len(pcm))


def iter_frames(pcm: bytes, frame_bytes: int = FRAME_BYTES):
    for offset in range(0, len(pcm), frame_bytes):
        yield pad_frame(pcm[offset : offset + frame_bytes], frame_bytes)


def simulator_disabled_payload() -> tuple[int, dict[str, str]]:
    return 404, {
        "error": "Browser phone mimic is demoted. Set SABI_BRIEF_PREVIEW_SIMULATOR=1 to enable it; it is not a production route.",
    }


def render_preview_call_page() -> str:
    wait = callback_wait_seconds()
    return f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Sabi preview call</title>
  <link rel="preconnect" href="https://fonts.googleapis.com">
  <link href="https://fonts.googleapis.com/css2?family=Cormorant+Garamond:wght@600;700&family=Lexend:wght@400;500;600&display=swap" rel="stylesheet">
  <style>
    :root {{ color-scheme: light; --ink:#201a13; --paper:#f7f2e7; --gold:#c4a35a; --muted:#857a68; }}
    * {{ box-sizing: border-box; }}
    body {{ margin:0; min-height:100vh; background:var(--paper); color:var(--ink); font-family:Lexend,sans-serif; }}
    main {{ max-width:420px; margin:0 auto; padding:32px 20px 64px; }}
    h1 {{ font-family:"Cormorant Garamond",serif; font-size:42px; margin:0 0 8px; }}
    .sub {{ color:var(--muted); line-height:1.5; margin-bottom:24px; }}
    .phone {{ background:#201a13; color:#f7f2e7; border-radius:36px; padding:28px 22px 32px; box-shadow:0 24px 60px rgba(32,26,19,.25); }}
    .screen {{ background:#2c241b; border-radius:24px; min-height:280px; padding:24px 20px; text-align:center; }}
    .status {{ font-size:13px; letter-spacing:.12em; text-transform:uppercase; color:var(--gold); margin-bottom:12px; }}
    .from {{ font-size:22px; margin:8px 0 20px; }}
    label {{ display:block; font-size:12px; color:#d9cbb3; text-align:left; margin:0 0 6px; }}
    input {{ width:100%; border:0; border-radius:12px; padding:12px 14px; font:inherit; }}
    button {{ width:100%; margin-top:12px; border:0; border-radius:999px; padding:14px; font:inherit; font-weight:600; cursor:pointer; }}
    .call {{ background:var(--gold); color:#201a13; }}
    .answer {{ background:#3d8b5a; color:white; }}
    .hang {{ background:#b4453a; color:white; }}
    .warn {{ font-size:12px; color:#d9cbb3; margin-top:16px; line-height:1.45; }}
  </style>
</head>
<body>
  <main>
    <h1>Preview call</h1>
    <p class="sub">This mimics a real Sabi phone call, including the missed-call hangup and callback. It is admin-only and off in production.</p>
    <div class="phone">
      <div class="screen">
        <div class="status" id="status">Ready</div>
        <div class="from" id="from">Sabi</div>
        <label for="phone">Your number (identity + memory)</label>
        <input id="phone" type="tel" value="{DEFAULT_PHONE}" autocomplete="tel">
        <button class="call" id="dial" type="button">Call Sabi</button>
        <button class="answer" id="answer" type="button" hidden>Answer</button>
        <button class="hang" id="hang" type="button" hidden>Hang up</button>
        <p class="warn" id="note">She will hang up after {FLASH_SECONDS:.0f} seconds, then ring you back after about {wait:.0f} seconds. Use headphones to reduce echo.</p>
      </div>
    </div>
  </main>
  <script>
    const FLASH_MS = {int(FLASH_SECONDS * 1000)};
    const CALLBACK_MS = {int(wait * 1000)};
    const statusEl = document.getElementById("status");
    const fromEl = document.getElementById("from");
    const phoneEl = document.getElementById("phone");
    const dialBtn = document.getElementById("dial");
    const answerBtn = document.getElementById("answer");
    const hangBtn = document.getElementById("hang");
    const noteEl = document.getElementById("note");
    const params = new URLSearchParams(location.search);
    let socket, audioCtx, playTime = 0, processor, mediaStream;

    function setUi(status, from, which) {{
      statusEl.textContent = status;
      fromEl.textContent = from;
      dialBtn.hidden = which !== "idle";
      answerBtn.hidden = which !== "incoming";
      hangBtn.hidden = which !== "in-call" && which !== "incoming";
      phoneEl.disabled = which !== "idle";
    }}

    function wsUrl() {{
      const proto = location.protocol === "https:" ? "wss" : "ws";
      const q = params.toString();
      return proto + "://" + location.host + "/admin/preview-call/ws" + (q ? "?" + q : "");
    }}

    async function downsampleAndSend(float32, sampleRate) {{
      if (!socket || socket.readyState !== 1) return;
      const data = new Int16Array(float32.length);
      for (let i = 0; i < float32.length; i++) {{
        const s = Math.max(-1, Math.min(1, float32[i]));
        data[i] = s < 0 ? s * 0x8000 : s * 0x7fff;
      }}
      socket.send(JSON.stringify({{ type: "audio", sample_rate: sampleRate }}));
      socket.send(data.buffer);
    }}

    function playPcm16(int16, sampleRate) {{
      if (!audioCtx) return;
      const buffer = audioCtx.createBuffer(1, int16.length, sampleRate);
      const channel = buffer.getChannelData(0);
      for (let i = 0; i < int16.length; i++) channel[i] = int16[i] / 32768;
      const src = audioCtx.createBufferSource();
      src.buffer = buffer;
      src.connect(audioCtx.destination);
      const startAt = Math.max(audioCtx.currentTime, playTime);
      src.start(startAt);
      playTime = startAt + buffer.duration;
    }}

    async function startMic() {{
      mediaStream = await navigator.mediaDevices.getUserMedia({{ audio: {{ echoCancellation: true, noiseSuppression: true }} }});
      audioCtx = audioCtx || new AudioContext();
      playTime = audioCtx.currentTime;
      const source = audioCtx.createMediaStreamSource(mediaStream);
      processor = audioCtx.createScriptProcessor(4096, 1, 1);
      processor.onaudioprocess = (event) => {{
        downsampleAndSend(event.inputBuffer.getChannelData(0), audioCtx.sampleRate);
      }};
      source.connect(processor);
      const mute = audioCtx.createGain();
      mute.gain.value = 0;
      processor.connect(mute);
      mute.connect(audioCtx.destination);
    }}

    function stopMic() {{
      if (processor) {{ try {{ processor.disconnect(); }} catch (e) {{}} processor = null; }}
      if (mediaStream) {{ mediaStream.getTracks().forEach((t) => t.stop()); mediaStream = null; }}
    }}

    dialBtn.onclick = async () => {{
      noteEl.textContent = "";
      setUi("Calling Sabi…", phoneEl.value.trim() || "{DEFAULT_PHONE}", "in-call");
      hangBtn.hidden = false;
      socket = new WebSocket(wsUrl());
      socket.binaryType = "arraybuffer";
      socket.onmessage = (event) => {{
        if (typeof event.data === "string") {{
          const msg = JSON.parse(event.data);
          if (msg.type === "flash") setUi("Ringing…", "Sabi", "in-call");
          if (msg.type === "hung_up") setUi("She hung up. Wait for callback…", "Missed call", "in-call");
          if (msg.type === "incoming") setUi("Incoming call", msg.from || "Sabi", "incoming");
          if (msg.type === "in_call") setUi("In lesson", "Sabi", "in-call");
          if (msg.type === "ended") {{ stopMic(); setUi("Call ended", "Sabi", "idle"); }}
          if (msg.type === "error") {{ noteEl.textContent = msg.error || "Could not start the mimic call."; stopMic(); setUi("Error", "Sabi", "idle"); }}
          return;
        }}
        playPcm16(new Int16Array(event.data), 8000);
      }};
      socket.onopen = () => {{
        socket.send(JSON.stringify({{ type: "dial", phone: phoneEl.value.trim() || "{DEFAULT_PHONE}" }}));
      }};
      socket.onclose = () => {{ stopMic(); setUi("Ready", "Sabi", "idle"); }};
    }};

    answerBtn.onclick = async () => {{
      try {{
        await startMic();
        socket.send(JSON.stringify({{ type: "answer" }}));
        setUi("Connecting…", "Sabi", "in-call");
      }} catch (err) {{
        noteEl.textContent = "Microphone permission is required for the mimic call.";
      }}
    }};

    hangBtn.onclick = () => {{
      if (socket && socket.readyState === 1) socket.send(JSON.stringify({{ type: "hangup" }}));
      stopMic();
      setUi("Ready", "Sabi", "idle");
    }};
  </script>
</body>
</html>
"""


async def _send_json(websocket: Any, payload: dict[str, Any]) -> None:
    await websocket.send_text(json.dumps(payload))


async def run_preview_session(websocket: Any) -> None:
    """Drive flash → hangup → incoming → AudioSocket lesson over one websocket."""
    from fastapi import WebSocketDisconnect
    flash_task: asyncio.Task | None = None
    bridge_task: asyncio.Task | None = None
    call_uuid = str(uuid.uuid4())
    phone = DEFAULT_PHONE
    answered = asyncio.Event()
    hanging = asyncio.Event()
    outbound: asyncio.Queue[bytes] = asyncio.Queue()

    async def flash_flow() -> None:
        await _send_json(websocket, {"type": "flash"})
        await asyncio.sleep(FLASH_SECONDS)
        if hanging.is_set():
            return
        await _send_json(websocket, {"type": "hung_up"})
        await asyncio.sleep(callback_wait_seconds())
        if hanging.is_set():
            return
        await _send_json(
            websocket,
            {"type": "incoming", "from": "Sabi", "waited_seconds": callback_wait_seconds()},
        )

    async def pump_caller_audio(sock_writer) -> None:
        while not hanging.is_set():
            try:
                frame = await asyncio.wait_for(outbound.get(), timeout=0.2)
            except asyncio.TimeoutError:
                continue
            sock_writer.write(encode_audiosocket_packet(AUDIO_TYPE_PCM_8K, frame))
            await sock_writer.drain()

    async def pump_sabi_audio(sock_reader) -> None:
        leftover = b""
        while not hanging.is_set():
            try:
                header = await asyncio.wait_for(sock_reader.readexactly(3), timeout=0.5)
            except asyncio.TimeoutError:
                continue
            except (asyncio.IncompleteReadError, ConnectionError):
                break
            packet_type = header[0]
            length = int.from_bytes(header[1:3], "big")
            payload = await sock_reader.readexactly(length) if length else b""
            if packet_type == AUDIO_TYPE_PCM_8K:
                leftover += payload
                while len(leftover) >= FRAME_BYTES:
                    await websocket.send_bytes(leftover[:FRAME_BYTES])
                    leftover = leftover[FRAME_BYTES:]
            elif packet_type == AUDIO_TYPE_HANGUP:
                break

    async def bridge() -> None:
        host, port = audiosocket_target()
        register_call(call_uuid, phone, PREVIEW_CALLBACK_MODE, "1")
        try:
            sock_reader, sock_writer = await asyncio.open_connection(host, port)
        except OSError as exc:
            await _send_json(
                websocket,
                {
                    "type": "error",
                    "error": (
                        f"Could not reach the local AudioSocket at {host}:{port}. "
                        "Start sabi-server first. This mimic is not a PSTN call."
                    ),
                    "detail": str(exc),
                },
            )
            return
        try:
            sock_writer.write(
                encode_audiosocket_packet(AUDIO_TYPE_UUID, uuid.UUID(call_uuid).bytes)
            )
            await sock_writer.drain()
            await _send_json(websocket, {"type": "in_call", "call_uuid": call_uuid, "phone": phone})
            await asyncio.gather(
                pump_caller_audio(sock_writer),
                pump_sabi_audio(sock_reader),
            )
        finally:
            try:
                sock_writer.write(encode_audiosocket_packet(AUDIO_TYPE_HANGUP))
                await sock_writer.drain()
            except Exception:
                pass
            sock_writer.close()
            try:
                await sock_writer.wait_closed()
            except Exception:
                pass

    pending_rate = SAMPLE_RATE
    try:
        while True:
            message = await websocket.receive()
            if message.get("type") == "websocket.disconnect":
                break
            if "text" in message and message["text"] is not None:
                try:
                    payload = json.loads(message["text"])
                except json.JSONDecodeError:
                    continue
                kind = str(payload.get("type") or "")
                if kind == "dial":
                    phone = str(payload.get("phone") or DEFAULT_PHONE).strip() or DEFAULT_PHONE
                    if flash_task is None:
                        flash_task = asyncio.create_task(flash_flow())
                elif kind == "answer":
                    answered.set()
                    if bridge_task is None:
                        bridge_task = asyncio.create_task(bridge())
                elif kind == "hangup":
                    hanging.set()
                    break
                elif kind == "audio":
                    try:
                        pending_rate = int(payload.get("sample_rate") or SAMPLE_RATE)
                    except (TypeError, ValueError):
                        pending_rate = SAMPLE_RATE
            elif "bytes" in message and message["bytes"] is not None:
                pcm8 = resample_pcm16(bytes(message["bytes"]), pending_rate, SAMPLE_RATE)
                for frame in iter_frames(pcm8):
                    await outbound.put(frame)
    except WebSocketDisconnect:
        pass
    finally:
        hanging.set()
        if flash_task:
            flash_task.cancel()
        if bridge_task:
            bridge_task.cancel()
        try:
            await _send_json(websocket, {"type": "ended"})
        except Exception:
            pass
        logger.info("Preview mimic session closed uuid=%s phone=%s", call_uuid, phone)


def preview_page_html() -> str | None:
    if not simulator_enabled():
        return None
    return render_preview_call_page()
