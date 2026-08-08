#!/usr/bin/env python3
"""Replay archived Sabi calls turn-by-turn as a Gemini Live hearing test.

Unlike a full-duplex agent replay, this harness never asks current Sabi to
continue an old conversation.  It gives Gemini the historical line immediately
preceding each learner clip, streams the original 8 kHz learner audio, and asks
Gemini only to report what it heard.  The stored learner transcript is withheld
until after inference and is displayed only as a non-authoritative comparison.
"""

from __future__ import annotations

import argparse
import asyncio
import base64
import html
import json
from pathlib import Path
import shutil
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


DEFAULT_CALL_IDS = (
    "341e0f5f-1def-45e3-bba5-0d3a7585a6fc",
    "2a8232e7-fb0a-4bb6-aa50-f64e662b97a6",
    "1088e5d4-255e-440c-b267-1a4f07ec6617",
    "b2e0ff90-35c8-454e-afe2-69b576f4f67f",
    "894b6040-7c47-4058-8ca6-9d0d21ed53cc",
    "be48a49b-8121-476f-bb9b-83d849a135f0",
    "e66ee2b7-f4e8-4c59-ad2d-7129a7ac84be",
    "e7f2f9c3-2092-43e5-8998-decc3a6bcbc9",
    "b3b8e2f5-eb56-4b74-bafb-44faa4145e45",
    "94313af4-59fd-4275-8938-47fc49ba5a04",
)


SYSTEM_TEMPLATE = """You are a hearing evaluator replaying one turn from a
historical Sabi phone tutoring conversation. This is not a live conversation.
Do not answer the learner, teach, grade, praise, correct, or continue the
lesson. Listen to the learner's short 8 kHz telephone clip and call
report_turn_hearing exactly once with only what you heard.

The historical Sabi line immediately before this clip was:
{preceding_sabi}

Use that line only as normal conversational context. You are not shown the
saved learner transcript or any expected answer. Preserve the learner's own
words and language. Do not translate into French, Spanish, Korean, Hindi, or
any other language. Do not fill in inaudible words merely because an answer
would fit the lesson. If the clip is unclear, report unclear and explain the
specific uncertainty briefly.

Recent replay context, based only on what you previously reported hearing:
{recent_context}
"""


def _setup_payload(system_prompt: str) -> dict[str, Any]:
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
            "systemInstruction": {"parts": [{"text": system_prompt}]},
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
                            "name": "report_turn_hearing",
                            "description": "Report only what was heard in the learner clip.",
                            "parameters": {
                                "type": "OBJECT",
                                "properties": {
                                    "verbatim_text": {"type": "STRING"},
                                    "semantic_kind": {
                                        "type": "STRING",
                                        "enum": [
                                            "name",
                                            "number",
                                            "phrase",
                                            "non_speech",
                                            "unclear",
                                        ],
                                    },
                                    "semantic_value": {"type": "STRING"},
                                    "certainty": {
                                        "type": "STRING",
                                        "enum": ["high", "medium", "low"],
                                    },
                                    "uncertainty_note": {"type": "STRING"},
                                },
                                "required": [
                                    "verbatim_text",
                                    "semantic_kind",
                                    "semantic_value",
                                    "certainty",
                                    "uncertainty_note",
                                ],
                            },
                        }
                    ]
                }
            ],
        }
    }


def _resolve_audio(audio_root: Path, value: Any) -> Path | None:
    raw = str(value or "").strip()
    if not raw:
        return None
    path = Path(raw)
    if raw.startswith("/shared/audio/"):
        path = audio_root / raw.removeprefix("/shared/audio/")
    elif not path.is_absolute():
        path = audio_root / path
    return path if path.exists() else None


def _read_pcm(path: Path) -> bytes:
    with wave.open(str(path), "rb") as wav:
        audio_format = (wav.getframerate(), wav.getnchannels(), wav.getsampwidth())
        if audio_format != (8_000, 1, 2):
            raise ValueError(f"unsupported WAV format {audio_format}")
        return wav.readframes(wav.getnframes())


async def _send_audio(websocket: Any, pcm: bytes) -> None:
    padded = (b"\x00" * FRAME_BYTES_8K * 18) + pcm + (b"\x00" * FRAME_BYTES_8K * 55)
    for offset in range(0, len(padded), FRAME_BYTES_8K):
        frame = padded[offset : offset + FRAME_BYTES_8K].ljust(FRAME_BYTES_8K, b"\x00")
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


async def hear_turn(
    audio_path: Path,
    preceding_sabi: str,
    recent_context: list[tuple[str, str]],
) -> dict[str, Any]:
    import websockets

    key = get_secret("GEMINI_API_KEY")
    if not key:
        raise RuntimeError("GEMINI_API_KEY is not configured")
    context_text = "\n".join(
        f"Sabi: {sabi}\nGemini heard learner: {learner}"
        for sabi, learner in recent_context[-4:]
    ) or "[This is the first available learner turn.]"
    system_prompt = SYSTEM_TEMPLATE.format(
        preceding_sabi=preceding_sabi or "[Opening Sabi line was not retained in the review record.]",
        recent_context=context_text,
    )
    started = time.monotonic()
    literal = ""
    report: dict[str, Any] = {}
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
        await websocket.send(json.dumps(_setup_payload(system_prompt)))
        setup = json.loads(
            await asyncio.wait_for(
                websocket.recv(), timeout=GEMINI_LIVE_SETUP_TIMEOUT_SECONDS
            )
        )
        if "setupComplete" not in setup:
            raise RuntimeError(f"setup not acknowledged: {sorted(setup)}")
        await _send_audio(websocket, _read_pcm(audio_path))

        deadline = time.monotonic() + 14
        while time.monotonic() < deadline and not report:
            raw = await asyncio.wait_for(
                websocket.recv(), timeout=max(0.1, deadline - time.monotonic())
            )
            event = json.loads(raw)
            content = event.get("serverContent") or {}
            piece = (content.get("inputTranscription") or {}).get("text")
            if piece:
                literal = merge_stream_text(literal, piece)
            for call in (event.get("toolCall") or {}).get("functionCalls") or []:
                if call.get("name") == "report_turn_hearing":
                    report = dict(call.get("args") or {})
                    break
        if not report:
            error = "No hearing report (VAD or model timeout)"
    except Exception as exc:
        error = f"{type(exc).__name__}: {exc}"
    finally:
        if websocket is not None:
            await websocket.close()
    return {
        "literal_transcript": " ".join(literal.split()),
        "report": report,
        "elapsed_seconds": round(time.monotonic() - started, 3),
        "error": error,
    }


def _load_calls(audio_root: Path, call_ids: list[str]) -> list[dict[str, Any]]:
    calls = []
    for call_id in call_ids:
        record_path = audio_root / f"call_{call_id}.json"
        if not record_path.exists():
            calls.append({"call_id": call_id, "status": "failed", "error": "record missing", "turns": []})
            continue
        record = json.loads(record_path.read_text())
        turns = []
        previous_assistant_text = ""
        previous_assistant_audio = None
        for index, stored in enumerate(record.get("turns") or []):
            user = stored.get("user") or {}
            assistant = stored.get("assistant") or {}
            user_audio = _resolve_audio(audio_root, user.get("audio_path"))
            assistant_audio = _resolve_audio(audio_root, assistant.get("audio_path"))
            turns.append(
                {
                    "turn": int(stored.get("turn_index", index)),
                    "preceding_sabi": previous_assistant_text,
                    "preceding_sabi_audio_source": str(previous_assistant_audio or ""),
                    "learner_audio_source": str(user_audio or ""),
                    "historical_saved_transcript": str(user.get("stt_transcript") or ""),
                    "historical_sabi_response": str(assistant.get("text") or ""),
                    "historical_sabi_audio_source": str(assistant_audio or ""),
                    "literal_transcript": "",
                    "report": {},
                    "elapsed_seconds": None,
                    "error": None if user_audio else "learner audio missing",
                    "status": "pending" if user_audio else "failed",
                }
            )
            previous_assistant_text = str(assistant.get("text") or "")
            previous_assistant_audio = assistant_audio
        calls.append(
            {
                "call_id": call_id,
                "date": str(record.get("created_at") or "")[:10],
                "duration_seconds": record.get("duration_seconds"),
                "end_reason": record.get("end_reason"),
                "status": "pending",
                "error": None,
                "turns": turns,
            }
        )
    return calls


def _copy_audio(output_dir: Path, calls: list[dict[str, Any]]) -> None:
    audio_dir = output_dir / "audio"
    audio_dir.mkdir(parents=True, exist_ok=True)
    for call in calls:
        short = call["call_id"][:8]
        for turn in call["turns"]:
            for source_key, url_key, role in (
                ("learner_audio_source", "learner_audio_url", "learner"),
                ("historical_sabi_audio_source", "historical_sabi_audio_url", "sabi-after"),
                ("preceding_sabi_audio_source", "preceding_sabi_audio_url", "sabi-before"),
            ):
                source = Path(turn.get(source_key) or "")
                if not source.is_file():
                    turn[url_key] = ""
                    continue
                name = f"{short}-turn-{int(turn['turn']):02d}-{role}.wav"
                destination = audio_dir / name
                if not destination.exists():
                    shutil.copyfile(source, destination)
                turn[url_key] = f"audio/{name}"
            for key in (
                "learner_audio_source",
                "historical_sabi_audio_source",
                "preceding_sabi_audio_source",
            ):
                turn.pop(key, None)


def _status_payload(calls: list[dict[str, Any]]) -> dict[str, Any]:
    all_turns = [turn for call in calls for turn in call["turns"]]
    return {
        "summary": {
            "calls": len(calls),
            "complete_calls": sum(call["status"] == "complete" for call in calls),
            "running_calls": sum(call["status"] == "running" for call in calls),
            "turns": len(all_turns),
            "heard": sum(turn["status"] == "complete" for turn in all_turns),
            "failed": sum(turn["status"] == "failed" for turn in all_turns),
        },
        "calls": calls,
        "updated_at": time.time(),
    }


def _write_status(output_dir: Path, calls: list[dict[str, Any]]) -> None:
    payload = _status_payload(calls)
    temporary = output_dir / "hearing_status.json.tmp"
    temporary.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    temporary.replace(output_dir / "hearing_status.json")


def _write_dashboard(output_dir: Path) -> None:
    output_dir.joinpath("index.html").write_text(
        """<!doctype html><html><head><meta charset=utf-8><meta name=viewport content='width=device-width,initial-scale=1'>
<title>Sabi · Turn-by-turn Gemini hearing</title><style>
:root{--ivory:#fbf6e9;--card:#fffdf7;--ink:#221d17;--muted:#71675b;--gold:#b88a25;--line:#e4d8bc;--green:#28745a;--red:#a6453d;--blue:#315b8b}
*{box-sizing:border-box}body{margin:0;background:var(--ivory);color:var(--ink);font:15px/1.45 -apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif}header{position:sticky;top:0;z-index:3;padding:20px 28px;color:#fff;background:linear-gradient(115deg,#211a11,#4b3517);box-shadow:0 5px 22px #33240d26}h1{margin:0;font:700 25px Georgia,serif}.sub{color:#eadcb9;margin-top:4px}main{max-width:1500px;margin:auto;padding:20px 28px 48px}.stats{display:grid;grid-template-columns:repeat(5,1fr);gap:10px;margin-bottom:17px}.stat{background:var(--card);border:1px solid var(--line);border-radius:12px;padding:11px 14px}.stat b{display:block;color:var(--gold);font-size:22px}.call{background:var(--card);border:1px solid var(--line);border-radius:15px;margin-bottom:15px;overflow:hidden}.callhead{display:flex;justify-content:space-between;gap:12px;padding:14px 16px;background:#fff8e7;border-bottom:1px solid var(--line)}.status{font-size:11px;font-weight:800;text-transform:uppercase;padding:4px 9px;border-radius:99px;height:max-content;background:#eee7d8}.running{color:var(--blue);background:#dbe8f8}.complete{color:var(--green);background:#dcefe8}.failed{color:var(--red);background:#f5deda}.turns{display:grid;grid-template-columns:repeat(auto-fit,minmax(370px,1fr));gap:12px;padding:13px}.turn{border:1px solid var(--line);border-radius:11px;padding:12px;background:#faf5e8}.who{margin-top:7px;color:var(--gold);font-size:11px;font-weight:800;text-transform:uppercase;letter-spacing:.5px}.text{margin-top:2px}.heard{font-weight:700}.raw{color:var(--muted)}audio{width:100%;height:34px}.meta{color:var(--muted);font-size:12px}.err{color:var(--red)}button{border:0;border-radius:9px;padding:8px 11px;background:#2e261b;color:white;font-weight:700;cursor:pointer}.playlist{margin-top:8px}.pending{opacity:.72}@media(max-width:700px){main,header{padding-left:13px;padding-right:13px}.stats{grid-template-columns:repeat(2,1fr)}.turns{grid-template-columns:1fr}}</style></head>
<body><header><h1>Sabi · full-conversation hearing replay</h1><div class=sub>Historical Sabi context → original learner turn → Gemini reports only what it heard</div></header><main><section class=stats id=stats></section><section id=calls></section></main>
<script>
const esc=s=>String(s??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
let playing=null;async function playCall(id){if(playing)playing.pause();const urls=JSON.parse(document.getElementById(id).dataset.urls||'[]');for(const u of urls){await new Promise(resolve=>{const a=new Audio(u);playing=a;a.onended=resolve;a.onerror=resolve;a.play().catch(resolve);});}playing=null;}
function player(label,url){return url?`<div class=who>${label}</div><audio controls preload=metadata src="${esc(url)}"></audio>`:''}
function turnCard(t){const r=t.report||{};return `<article class="turn ${esc(t.status)}"><div class=who>Turn ${esc(t.turn)} · Sabi immediately before</div><div class=text>${esc(t.preceding_sabi||'[Opening line was not retained]')}</div>${player('Play preceding Sabi',t.preceding_sabi_audio_url)}<div class=who>Original learner audio</div><audio controls preload=metadata src="${esc(t.learner_audio_url)}"></audio><div class=who>Gemini raw transcript</div><div class="text raw">${esc(t.literal_transcript||'[empty]')}</div><div class=who>Gemini says it heard</div><div class="text heard">${esc(r.verbatim_text||'[waiting / unclear]')}</div><div class=meta>${esc(r.semantic_kind||'')} ${r.semantic_value?'· '+esc(r.semantic_value):''} ${r.certainty?'· '+esc(r.certainty)+' certainty':''}</div>${r.uncertainty_note?`<div class=meta>${esc(r.uncertainty_note)}</div>`:''}<div class=who>Historical saved transcript · comparison only</div><div class=text>${esc(t.historical_saved_transcript||'[empty]')}</div><div class=who>Historical Sabi replied</div><div class=text>${esc(t.historical_sabi_response||'[no saved reply]')}</div>${player('Play historical Sabi reply',t.historical_sabi_audio_url)}${t.error?`<div class=err>${esc(t.error)}</div>`:''}</article>`}
async function refresh(){try{const d=await fetch('hearing_status.json?'+Date.now()).then(r=>r.json());const s=d.summary;document.getElementById('stats').innerHTML=[['Calls',s.calls],['Running',s.running_calls],['Complete',s.complete_calls],['Turns heard',s.heard],['Failed',s.failed]].map(([k,v])=>`<div class=stat><b>${v}</b><span>${k}</span></div>`).join('');document.getElementById('calls').innerHTML=d.calls.map(c=>{const urls=[];for(const t of c.turns){if(t.learner_audio_url)urls.push(t.learner_audio_url);if(t.historical_sabi_audio_url)urls.push(t.historical_sabi_audio_url)}const pid='p'+c.call_id.slice(0,8);return `<section class=call><div class=callhead><div><b>Call ${esc(c.call_id.slice(0,8))}</b><div class=meta>${esc(c.duration_seconds)} seconds · ${esc(c.turns.length)} saved turns</div><button class=playlist id=${pid} data-urls='${esc(JSON.stringify(urls))}' onclick="playCall('${pid}')">▶ Play full historical conversation</button></div><span class="status ${esc(c.status)}">${esc(c.status)}</span></div><div class=turns>${c.turns.map(turnCard).join('')}</div></section>`}).join('')}catch(e){}}refresh();setInterval(refresh,1200);
</script></body></html>""",
        encoding="utf-8",
    )


def _write_oluremi_gideon_dashboard(output_dir: Path) -> None:
    """Write the focused, gold-aware review requested for the two July calls."""
    output_dir.joinpath("index.html").write_text(
        """<!doctype html><html><head><meta charset=utf-8><meta name=viewport content='width=device-width,initial-scale=1'>
<title>Oluremi & Gideon · Gemini hearing</title><style>
:root{--ivory:#fbf6e9;--card:#fffdf7;--ink:#221d17;--muted:#71675b;--gold:#b88a25;--line:#e4d8bc;--green:#28745a;--red:#a6453d;--blue:#315b8b}
*{box-sizing:border-box}body{margin:0;background:var(--ivory);color:var(--ink);font:15px/1.45 -apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif}header{position:sticky;top:0;z-index:3;padding:21px 28px;color:#fff;background:linear-gradient(115deg,#211a11,#4b3517);box-shadow:0 5px 22px #33240d26}h1{margin:0;font:700 26px Georgia,serif}.sub{color:#eadcb9;margin-top:4px}main{max-width:1400px;margin:auto;padding:20px 28px 48px}.stats{display:grid;grid-template-columns:repeat(4,1fr);gap:10px;margin-bottom:17px}.stat{background:var(--card);border:1px solid var(--line);border-radius:12px;padding:11px 14px}.stat b{display:block;color:var(--gold);font-size:22px}.call{margin-bottom:20px}.callhead{display:flex;justify-content:space-between;align-items:flex-start;gap:12px;margin-bottom:11px}.callhead h2{margin:0;font:700 23px Georgia,serif}.meta{color:var(--muted);font-size:12px}.cards{display:grid;grid-template-columns:repeat(auto-fit,minmax(360px,1fr));gap:13px}.turn{background:var(--card);border:1px solid var(--line);border-radius:14px;padding:14px;box-shadow:0 6px 18px #5d461315}.top{display:flex;justify-content:space-between;gap:10px}.badge{height:max-content;padding:4px 9px;border-radius:99px;font-size:10px;font-weight:850;letter-spacing:.45px}.match{color:var(--green);background:#dcefe8}.check{color:var(--red);background:#f5deda}.same{color:var(--blue);background:#dbe8f8}.different{color:#80601b;background:#f7eac4}.waiting{color:var(--muted);background:#eee7d8}.who{margin-top:8px;color:var(--gold);font-size:11px;font-weight:800;text-transform:uppercase;letter-spacing:.5px}.answer{font-weight:720;margin-top:2px}.context{color:#514a40;margin-top:2px}.muted{color:var(--muted)}audio{width:100%;height:35px;margin-top:4px}.err{color:var(--red);margin-top:6px}.playlist{border:0;border-radius:9px;padding:8px 11px;background:#2e261b;color:#fff;font-weight:750;cursor:pointer;margin-top:7px}.legend{background:#fff9e9;border:1px solid var(--line);border-radius:12px;padding:11px 14px;margin-bottom:16px}.status{font-size:11px;font-weight:800;text-transform:uppercase;color:var(--blue)}@media(max-width:700px){main,header{padding-left:13px;padding-right:13px}.stats{grid-template-columns:repeat(2,1fr)}.cards{grid-template-columns:1fr}}</style></head>
<body><header><h1>Oluremi & Gideon · full-conversation hearing test</h1><div class=sub>Historical Sabi context → original learner audio → Gemini reports only what it heard</div></header><main><div class=legend><b>How to read the badges:</b> MATCH/CHECK uses independently verified words. SAME AS OLD/DIFFERENT FROM OLD compares against the old saved transcript, which is not guaranteed to be correct.</div><section class=stats id=stats></section><section id=calls></section></main>
<script>
const FOCUS=['be48a49b-8121-476f-bb9b-83d849a135f0','e66ee2b7-f4e8-4c59-ad2d-7129a7ac84be'];
const NAMES={'be48a49b-8121-476f-bb9b-83d849a135f0':'Oluremi','e66ee2b7-f4e8-4c59-ad2d-7129a7ac84be':'Gideon'};
const GOLD={
 'be48a49b-8121-476f-bb9b-83d849a135f0:0':'My name is Oluremi',
 'be48a49b-8121-476f-bb9b-83d849a135f0:4':'Thirty',
 'be48a49b-8121-476f-bb9b-83d849a135f0:5':'Thirty',
 'be48a49b-8121-476f-bb9b-83d849a135f0:8':'Fifteen',
 'be48a49b-8121-476f-bb9b-83d849a135f0:9':'Thirty',
 'e66ee2b7-f4e8-4c59-ad2d-7129a7ac84be:1':'My name is Gideon',
 'e66ee2b7-f4e8-4c59-ad2d-7129a7ac84be:2':'My name is Gideon'};
const NUM={zero:'0',one:'1',two:'2',three:'3',four:'4',five:'5',six:'6',seven:'7',eight:'8',nine:'9',ten:'10',eleven:'11',twelve:'12',thirteen:'13',fourteen:'14',fifteen:'15',sixteen:'16',seventeen:'17',eighteen:'18',nineteen:'19',twenty:'20',thirty:'30'};
const esc=s=>String(s??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
function norm(s){let x=String(s??'').toLowerCase().replace(/[^a-z0-9 ]/g,' ').replace(/\\s+/g,' ').trim();return NUM[x]||x}
let playing=null;async function playCall(id){if(playing)playing.pause();const urls=JSON.parse(document.getElementById(id).dataset.urls||'[]');for(const u of urls){await new Promise(resolve=>{const a=new Audio(u);playing=a;a.onended=resolve;a.onerror=resolve;a.play().catch(resolve)})}playing=null}
function turnCard(call,t){const r=t.report||{},key=call.call_id+':'+t.turn,verified=Object.hasOwn(GOLD,key),reference=verified?GOLD[key]:(t.historical_saved_transcript||'[empty]'),candidates=[r.verbatim_text,r.semantic_value,t.literal_transcript].map(norm),done=t.status==='complete',same=done&&candidates.includes(norm(reference));let label='WAITING',cls='waiting';if(done){label=verified?(same?'MATCH':'CHECK'):(same?'SAME AS OLD':'DIFFERENT FROM OLD');cls=verified?(same?'match':'check'):(same?'same':'different')}else if(t.status==='failed'){label='NO HEARING REPORT';cls='check'}return `<article class=turn><div class=top><b>Turn ${esc(t.turn)}</b><span class="badge ${cls}">${label}</span></div><div class=who>Sabi immediately before</div><div class=context>${esc(t.preceding_sabi||'[Opening line was not retained]')}</div>${t.preceding_sabi_audio_url?`<audio controls preload=metadata src="${esc(t.preceding_sabi_audio_url)}"></audio>`:''}<div class=who>Play original learner turn</div><audio controls preload=metadata src="${esc(t.learner_audio_url)}"></audio><div class=who>${verified?'Known words':'Old saved transcript · not verified'}</div><div class=answer>${esc(reference)}</div><div class=who>Gemini literal transcript</div><div class="answer muted">${esc(t.literal_transcript||'[empty]')}</div><div class=who>Gemini says it heard</div><div class=answer>${esc(r.verbatim_text||'[waiting / unclear]')}</div><div class=meta>${esc(r.semantic_kind||'')} ${r.semantic_value?'· '+esc(r.semantic_value):''} ${r.certainty?'· '+esc(r.certainty)+' certainty':''}</div>${r.uncertainty_note?`<div class=meta>${esc(r.uncertainty_note)}</div>`:''}<div class=who>Historical Sabi replied</div><div class=context>${esc(t.historical_sabi_response||'[no saved reply]')}</div>${t.historical_sabi_audio_url?`<audio controls preload=metadata src="${esc(t.historical_sabi_audio_url)}"></audio>`:''}${t.error?`<div class=err>${esc(t.error)}</div>`:''}</article>`}
async function refresh(){try{const d=await fetch('hearing_status.json?'+Date.now()).then(r=>r.json()),calls=d.calls.filter(c=>FOCUS.includes(c.call_id)),turns=calls.flatMap(c=>c.turns),verified=turns.filter(t=>Object.hasOwn(GOLD,calls.find(c=>c.turns.includes(t)).call_id+':'+t.turn));document.getElementById('stats').innerHTML=[['Conversations',calls.length],['All turns',turns.length],['Processed',turns.filter(t=>['complete','failed'].includes(t.status)).length],['Verified turns',verified.length]].map(([k,v])=>`<div class=stat><b>${v}</b><span>${k}</span></div>`).join('');document.getElementById('calls').innerHTML=calls.map(c=>{const urls=[];for(const t of c.turns){if(t.learner_audio_url)urls.push(t.learner_audio_url);if(t.historical_sabi_audio_url)urls.push(t.historical_sabi_audio_url)}const pid='p'+c.call_id.slice(0,8);return `<section class=call><div class=callhead><div><h2>${esc(NAMES[c.call_id])}</h2><div class=meta>${esc(c.turns.length)} learner turns · ${esc(c.duration_seconds)} seconds</div><button class=playlist id=${pid} data-urls='${esc(JSON.stringify(urls))}' onclick="playCall('${pid}')">▶ Play full historical conversation</button></div><span class=status>${esc(c.status)}</span></div><div class=cards>${c.turns.map(t=>turnCard(c,t)).join('')}</div></section>`}).join('')}catch(e){}}refresh();
</script></body></html>""",
        encoding="utf-8",
    )


async def replay_call(
    call: dict[str, Any],
    calls: list[dict[str, Any]],
    output_dir: Path,
    semaphore: asyncio.Semaphore,
) -> None:
    async with semaphore:
        if call.get("error"):
            return
        call["status"] = "running"
        _write_status(output_dir, calls)
        recent: list[tuple[str, str]] = []
        for turn in call["turns"]:
            if turn["status"] == "failed":
                continue
            turn["status"] = "running"
            _write_status(output_dir, calls)
            try:
                result = await hear_turn(
                    output_dir / turn["learner_audio_url"],
                    turn["preceding_sabi"],
                    recent,
                )
                turn.update(result)
                turn["status"] = "failed" if result["error"] else "complete"
                heard = (result.get("report") or {}).get("verbatim_text") or "[unclear]"
                recent.append((turn["historical_sabi_response"], str(heard)))
                print(
                    json.dumps(
                        {
                            "call": call["call_id"][:8],
                            "turn": turn["turn"],
                            "raw": result["literal_transcript"],
                            "heard": heard,
                            "error": result["error"],
                        },
                        ensure_ascii=False,
                    ),
                    flush=True,
                )
            except Exception as exc:
                turn["status"] = "failed"
                turn["error"] = f"{type(exc).__name__}: {exc}"
            _write_status(output_dir, calls)
        call["status"] = "failed" if any(t["status"] == "failed" for t in call["turns"]) else "complete"
        _write_status(output_dir, calls)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--audio-root", type=Path, default=Path("/shared/audio"))
    parser.add_argument("--output-dir", type=Path, default=Path("/results"))
    parser.add_argument("--call-id", action="append", default=[])
    parser.add_argument("--concurrency", type=int, default=3)
    parser.add_argument("--limit-calls", type=int, default=0)
    return parser.parse_args()


async def main() -> None:
    args = parse_args()
    call_ids = args.call_id or list(DEFAULT_CALL_IDS)
    if args.limit_calls:
        call_ids = call_ids[: args.limit_calls]
    args.output_dir.mkdir(parents=True, exist_ok=True)
    calls = _load_calls(args.audio_root, call_ids)
    _copy_audio(args.output_dir, calls)
    if set(FOCUS_CALL_IDS := (
        "be48a49b-8121-476f-bb9b-83d849a135f0",
        "e66ee2b7-f4e8-4c59-ad2d-7129a7ac84be",
    )).issubset(set(call_ids)):
        _write_oluremi_gideon_dashboard(args.output_dir)
    else:
        _write_dashboard(args.output_dir)
    _write_status(args.output_dir, calls)
    semaphore = asyncio.Semaphore(max(1, args.concurrency))
    await asyncio.gather(
        *(replay_call(call, calls, args.output_dir, semaphore) for call in calls)
    )
    print(json.dumps(_status_payload(calls)["summary"], sort_keys=True), flush=True)


if __name__ == "__main__":
    asyncio.run(main())
