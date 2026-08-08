#!/usr/bin/env python3
"""Probe short phone clips against Gemini Live without running a lesson.

The lesson replay harness answers a different question: how the complete Sabi
agent reacts while historical caller audio arrives.  This probe isolates audio
recognition.  Every clip gets a fresh Live session, the production model and
VAD settings, and no expected answer in the prompt.  It records both Gemini's
auxiliary input transcript and the semantic value Gemini reports through a
small evaluation tool.
"""

from __future__ import annotations

import argparse
import asyncio
import base64
import html
import json
from pathlib import Path
import time
from typing import Any
import wave

from gemini_live import (
    FRAME_BYTES_8K,
    GEMINI_LIVE_MAX_MESSAGE_BYTES,
    GEMINI_LIVE_MODEL,
    GEMINI_LIVE_SETUP_TIMEOUT_SECONDS,
    GEMINI_LIVE_VOICE,
    LIVE_ENDPOINT,
    merge_stream_text,
)
from secret_loader import get_secret


SYSTEM_PROMPT = """You are testing whether a speech system can hear one short
Nigerian telephone utterance. You are not a tutor and must not answer or teach.
Listen to the audio exactly as spoken. Do not translate it into another
language and do not invent words from context; there is no lesson context and
you are not shown the expected answer. Call report_clip_hearing exactly once.
Put your best verbatim hearing in verbatim_text. Classify the meaning as name,
number, other, or unclear. For a name or number, put only that understood name
or numeric value in semantic_value. If genuinely uncertain, use unclear and
briefly say why in uncertainty_note."""


def _setup_payload() -> dict[str, Any]:
    return {
        "setup": {
            "model": f"models/{GEMINI_LIVE_MODEL}",
            "generationConfig": {
                "responseModalities": ["AUDIO"],
                "speechConfig": {
                    "voiceConfig": {
                        "prebuiltVoiceConfig": {"voiceName": GEMINI_LIVE_VOICE}
                    }
                },
                "thinkingConfig": {"thinkingLevel": "minimal"},
            },
            "systemInstruction": {"parts": [{"text": SYSTEM_PROMPT}]},
            "inputAudioTranscription": {},
            "realtimeInputConfig": {
                "automaticActivityDetection": {
                    "disabled": False,
                    "startOfSpeechSensitivity": "START_SENSITIVITY_LOW",
                    "endOfSpeechSensitivity": "END_SENSITIVITY_LOW",
                    "prefixPaddingMs": 160,
                    "silenceDurationMs": 650,
                },
                "activityHandling": "START_OF_ACTIVITY_INTERRUPTS",
                "turnCoverage": "TURN_INCLUDES_ONLY_ACTIVITY",
            },
            "tools": [
                {
                    "functionDeclarations": [
                        {
                            "name": "report_clip_hearing",
                            "description": "Report exactly what the one phone clip contained.",
                            "parameters": {
                                "type": "OBJECT",
                                "properties": {
                                    "verbatim_text": {"type": "STRING"},
                                    "semantic_kind": {
                                        "type": "STRING",
                                        "enum": ["name", "number", "other", "unclear"],
                                    },
                                    "semantic_value": {"type": "STRING"},
                                    "uncertainty_note": {"type": "STRING"},
                                },
                                "required": [
                                    "verbatim_text",
                                    "semantic_kind",
                                    "semantic_value",
                                    "uncertainty_note",
                                ],
                            },
                        }
                    ]
                }
            ],
        }
    }


def _read_pcm(path: Path) -> bytes:
    with wave.open(str(path), "rb") as wav:
        audio_format = (wav.getframerate(), wav.getnchannels(), wav.getsampwidth())
        if audio_format != (8_000, 1, 2):
            raise ValueError(f"{path} has unsupported WAV format {audio_format}")
        return wav.readframes(wav.getnframes())


async def _send_audio(websocket: Any, pcm: bytes) -> None:
    # A short leading pad lets the production VAD establish the phone noise
    # floor.  Trailing silence closes even sub-second name/number turns.
    padded = (b"\x00" * FRAME_BYTES_8K * 20) + pcm + (b"\x00" * FRAME_BYTES_8K * 55)
    for offset in range(0, len(padded), FRAME_BYTES_8K):
        frame = padded[offset : offset + FRAME_BYTES_8K]
        if len(frame) < FRAME_BYTES_8K:
            frame = frame.ljust(FRAME_BYTES_8K, b"\x00")
        await websocket.send(
            json.dumps(
                {
                    "realtimeInput": {
                        "audio": {
                            "data": base64.b64encode(frame).decode("ascii"),
                            "mimeType": "audio/pcm;rate=8000",
                        }
                    }
                }
            )
        )
        await asyncio.sleep(0.02)
    await websocket.send(json.dumps({"realtimeInput": {"audioStreamEnd": True}}))


async def probe_clip(label: str, expected: str, path: Path) -> dict[str, Any]:
    import websockets

    key = get_secret("GEMINI_API_KEY")
    if not key:
        raise RuntimeError("GEMINI_API_KEY is not configured")
    started = time.monotonic()
    literal = ""
    semantic: dict[str, Any] = {}
    error = None
    websocket = None
    try:
        websocket = await websockets.connect(
            f"{LIVE_ENDPOINT}?key={key}",
            open_timeout=GEMINI_LIVE_SETUP_TIMEOUT_SECONDS,
            close_timeout=3,
            ping_interval=20,
            ping_timeout=20,
            max_size=GEMINI_LIVE_MAX_MESSAGE_BYTES,
        )
        await websocket.send(json.dumps(_setup_payload()))
        setup = json.loads(
            await asyncio.wait_for(
                websocket.recv(), timeout=GEMINI_LIVE_SETUP_TIMEOUT_SECONDS
            )
        )
        if "setupComplete" not in setup:
            raise RuntimeError(f"setup not acknowledged: {sorted(setup)}")
        await _send_audio(websocket, _read_pcm(path))

        deadline = time.monotonic() + 15
        turn_complete = False
        while time.monotonic() < deadline and not (semantic and turn_complete):
            raw = await asyncio.wait_for(websocket.recv(), timeout=max(0.1, deadline - time.monotonic()))
            event = json.loads(raw)
            content = event.get("serverContent") or {}
            piece = (content.get("inputTranscription") or {}).get("text")
            if piece:
                literal = merge_stream_text(literal, piece)
            turn_complete = turn_complete or bool(content.get("turnComplete"))
            calls = (event.get("toolCall") or {}).get("functionCalls") or []
            for call in calls:
                if call.get("name") != "report_clip_hearing":
                    continue
                semantic = dict(call.get("args") or {})
                await websocket.send(
                    json.dumps(
                        {
                            "toolResponse": {
                                "functionResponses": [
                                    {
                                        "name": "report_clip_hearing",
                                        "id": call.get("id"),
                                        "response": {"result": {"recorded": True}},
                                    }
                                ]
                            }
                        }
                    )
                )
        if not semantic:
            error = "Gemini did not emit the hearing report tool call"
    except Exception as exc:
        error = f"{type(exc).__name__}: {exc}"
    finally:
        if websocket is not None:
            await websocket.close()
    return {
        "label": label,
        "expected": expected,
        "audio_file": path.name,
        "literal_transcript": " ".join(literal.split()),
        "semantic": semantic,
        "elapsed_seconds": round(time.monotonic() - started, 3),
        "error": error,
    }


def _write_dashboard(output_dir: Path, rows: list[dict[str, Any]]) -> None:
    number_aliases = {
        "zero": "0",
        "one": "1",
        "two": "2",
        "three": "3",
        "four": "4",
        "five": "5",
        "six": "6",
        "seven": "7",
        "eight": "8",
        "nine": "9",
        "ten": "10",
        "eleven": "11",
        "twelve": "12",
        "thirteen": "13",
        "fourteen": "14",
        "fifteen": "15",
        "sixteen": "16",
        "seventeen": "17",
        "eighteen": "18",
        "nineteen": "19",
        "twenty": "20",
        "thirty": "30",
    }

    def normalized(value: Any) -> str:
        cleaned = " ".join(str(value or "").strip().casefold().rstrip(".").split())
        return number_aliases.get(cleaned, cleaned)

    def e(value: Any) -> str:
        return html.escape(str(value or ""))

    cards = []
    for index, row in enumerate(rows, 1):
        semantic = row.get("semantic") or {}
        understood = semantic.get("semantic_value") or "[unclear]"
        candidates = (understood, semantic.get("verbatim_text"))
        correct = any(
            normalized(candidate) == normalized(row["expected"])
            for candidate in candidates
        )
        cards.append(
            f"""<article><div class=top><b>{index}. {e(row['label'])}</b>
            <span class={'pass' if correct else 'fail'}>{'MATCH' if correct else 'CHECK'}</span></div>
            <audio controls preload=metadata src="audio/{e(row['audio_file'])}"></audio>
            <dl><dt>Known words</dt><dd>{e(row['expected'])}</dd>
            <dt>Gemini literal transcript</dt><dd>{e(row['literal_transcript']) or '[empty]'}</dd>
            <dt>Gemini understood</dt><dd>{e(understood)} <small>({e(semantic.get('semantic_kind'))})</small></dd>
            <dt>Uncertainty</dt><dd>{e(semantic.get('uncertainty_note')) or '—'}</dd></dl>
            {f'<p class=err>{e(row["error"])}</p>' if row.get('error') else ''}</article>"""
        )
    output_dir.joinpath("index.html").write_text(
        """<!doctype html><meta charset=utf-8><meta name=viewport content='width=device-width,initial-scale=1'>
        <title>Gemini Live clip audibility</title><style>
        :root{--ivory:#fbf6e9;--ink:#231d15;--gold:#b48929;--line:#e4d8bc;--green:#217052;--red:#a44239}
        *{box-sizing:border-box}body{margin:0;background:var(--ivory);color:var(--ink);font:15px/1.45 -apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif}
        header{padding:24px 30px;color:white;background:linear-gradient(115deg,#211a11,#4b3517)}h1{margin:0;font:700 26px Georgia,serif}header p{margin:5px 0 0;color:#eadcb9}
        main{max-width:1200px;margin:auto;padding:22px 28px;display:grid;grid-template-columns:repeat(auto-fit,minmax(340px,1fr));gap:15px}
        article{background:#fffdf7;border:1px solid var(--line);border-radius:14px;padding:15px;box-shadow:0 6px 18px #5d461315}.top{display:flex;justify-content:space-between;gap:12px}.top span{font-size:11px;font-weight:800;padding:4px 8px;border-radius:99px}.pass{color:var(--green);background:#dcefe8}.fail{color:var(--red);background:#f5deda}audio{width:100%;margin:12px 0 5px}dl{margin:6px 0 0}dt{color:var(--gold);font-size:11px;font-weight:800;text-transform:uppercase;letter-spacing:.45px;margin-top:8px}dd{margin:1px 0 0}.err{color:var(--red)}small{color:#756b5f}</style>
        <header><h1>Can Gemini Live hear these phone clips?</h1><p>Fresh session per clip · production Live model and VAD · no expected answer shown to Gemini</p></header><main>"""
        + "".join(cards)
        + "</main>",
        encoding="utf-8",
    )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument(
        "--clip",
        action="append",
        nargs=3,
        metavar=("LABEL", "EXPECTED", "WAV"),
        required=True,
    )
    return parser.parse_args()


async def main() -> None:
    args = parse_args()
    args.output_dir.mkdir(parents=True, exist_ok=True)
    audio_dir = args.output_dir / "audio"
    audio_dir.mkdir(exist_ok=True)
    rows = []
    for label, expected, raw_path in args.clip:
        path = Path(raw_path)
        destination = audio_dir / path.name
        destination.write_bytes(path.read_bytes())
        row = await probe_clip(label, expected, path)
        rows.append(row)
        args.output_dir.joinpath("clip_results.json").write_text(
            json.dumps(rows, indent=2, ensure_ascii=False), encoding="utf-8"
        )
        _write_dashboard(args.output_dir, rows)
        print(json.dumps(row, ensure_ascii=False), flush=True)


if __name__ == "__main__":
    asyncio.run(main())
