"""Hear the same Sabi lines in different voices, side by side.

The prompt lab compares words. This compares delivery, which the research says
matters more: Moreno and Mayer found the agent's voice, not its persona, was the
significant contributor to learning outcomes.

Every voice speaks the SAME lines — otherwise this would compare scripts, not
voices. Lines default to real output from prompt G.

Voices:
  bukola   ElevenLabs, the original hackathon Sabi (young, Nigerian, conversational)
  kore     Gemini prebuilt — what Sabi speaks today. Google's descriptor: "Firm"
  leda     Gemini prebuilt — Google's descriptor: "Youthful"

Usage (inside the sabi-server image, with secrets mounted):
    python scripts/voice_bakeoff.py --out /out/voices
"""

from __future__ import annotations

import argparse
import base64
import json
import struct
import urllib.request
from dataclasses import dataclass
from html import escape
from pathlib import Path

GEMINI_TTS_MODEL = "gemini-3.1-flash-tts-preview"
GEMINI_URL = (
    "https://generativelanguage.googleapis.com/v1beta/models/"
    f"{GEMINI_TTS_MODEL}:generateContent"
)
ELEVEN_URL = "https://api.elevenlabs.io/v1/text-to-speech/{voice_id}"
# Sabi's own Chatterbox server holds cloned speakers, including bukola — so the
# original voice is reachable without ElevenLabs, whose subscription is unpaid.
CHATTERBOX_URL = "http://chatterbox:8001/tts"

# Real turns from prompt G, chosen to span the registers that matter on a call:
# the opening, a child who is stuck, a correction, and a celebration.
LINES: list[tuple[str, str]] = [
    ("opening", "Naomi! Oya, come and help me quickly — I went to the shop and I bought "
                "two packets of chin-chin, and there are two crunchy pieces inside each packet."),
    ("stuck", "No wahala, Naomi, we will count them together! You have the first sachet "
              "that costs two naira, and then you pick up the second one — so if you start "
              "at two and count up two more, what number do you land on?"),
    ("wrong answer", "Hmm, let me think small with you. Look — two in the first basket, and "
                     "two in the second basket. Start at two and count the second basket for me."),
    ("celebration", "Ah ah! So fast! Sharp sharp! You got it — I knew you were sharp, Naomi."),
]


@dataclass(frozen=True)
class Voice:
    key: str
    label: str
    detail: str
    provider: str
    name: str


VOICES: list[Voice] = [
    Voice("bukola", "Bukola — the original Sabi",
          "Chatterbox clone · young, Nigerian, conversational", "chatterbox", "bukola"),
    Voice("kore", "Kore — your number today",
          'Gemini prebuilt · Google\'s descriptor: "Firm"', "gemini", "Kore"),
    Voice("leda", "Leda — a warmer Gemini option",
          'Gemini prebuilt · Google\'s descriptor: "Youthful"', "gemini", "Leda"),
    Voice("naomi", "Naomi — every other caller today",
          "Chatterbox clone · the live TTS on the non-Gemini lane", "chatterbox", "naomi"),
]


def _secret(name: str) -> str:
    path = Path(f"/run/secrets/{name}")
    if path.exists():
        return path.read_text().strip()
    raise SystemExit(f"missing credential: {name}")


def _post(url: str, payload: dict | None, headers: dict[str, str]) -> bytes:
    data = json.dumps(payload).encode() if payload is not None else None
    request = urllib.request.Request(url, data=data, headers=headers)
    with urllib.request.urlopen(request, timeout=120) as response:
        return response.read()


def wav_from_pcm(pcm: bytes, rate: int = 24000, channels: int = 1, width: int = 2) -> bytes:
    """Gemini returns raw little-endian PCM; browsers need a RIFF header."""
    block = channels * width
    header = b"RIFF" + struct.pack("<I", 36 + len(pcm)) + b"WAVEfmt " + struct.pack(
        "<IHHIIHH", 16, 1, channels, rate, rate * block, block, width * 8
    ) + b"data" + struct.pack("<I", len(pcm))
    return header + pcm


def say_gemini(text: str, voice_name: str, key: str) -> tuple[bytes, str]:
    payload = {
        "contents": [{"parts": [{"text": text}]}],
        "generationConfig": {
            "responseModalities": ["AUDIO"],
            "speechConfig": {
                "voiceConfig": {"prebuiltVoiceConfig": {"voiceName": voice_name}}
            },
        },
    }
    raw = _post(f"{GEMINI_URL}?key={key}", payload, {"content-type": "application/json"})
    part = json.loads(raw)["candidates"][0]["content"]["parts"][0]["inlineData"]
    return wav_from_pcm(base64.b64decode(part["data"])), "wav"


def say_chatterbox(text: str, speaker: str) -> tuple[bytes, str]:
    audio = _post(
        CHATTERBOX_URL,
        {"text": text[:2000], "speaker_name": speaker, "format": "mp3"},
        {"content-type": "application/json"},
    )
    return audio, "mp3"


def say_eleven(text: str, voice_id: str, key: str) -> tuple[bytes, str]:
    payload = {"text": text, "model_id": "eleven_multilingual_v2"}
    audio = _post(
        ELEVEN_URL.format(voice_id=voice_id),
        payload,
        {"content-type": "application/json", "xi-api-key": key, "accept": "audio/mpeg"},
    )
    return audio, "mp3"


CSS = """
:root{--ivory:#fbf6e9;--card:#fffdf7;--ink:#221d17;--muted:#71675b;--gold:#b88a25;
--line:#e4d8bc;--blue:#315b8b;--green:#28745a}
*{box-sizing:border-box}
body{margin:0;background:var(--ivory);color:var(--ink);
font:15px/1.5 -apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif}
header{position:sticky;top:0;z-index:3;padding:20px 28px;color:#fff;
background:linear-gradient(115deg,#211a11,#4b3517);box-shadow:0 5px 22px #33240d26}
h1{margin:0;font:700 25px Georgia,serif}
.sub{color:#eadcb9;margin-top:4px;font-size:13.5px}
main{max-width:1400px;margin:auto;padding:20px 28px 60px}
.legend{background:#fff9e9;border:1px solid var(--line);border-radius:12px;
padding:12px 15px;margin-bottom:18px;font-size:13.5px;color:#514a40}
.legend b{color:var(--ink)}
.beat{background:var(--card);border:1px solid var(--line);border-radius:15px;
margin-bottom:15px;overflow:hidden}
.beathead{padding:13px 16px;background:#fff8e7;border-bottom:1px solid var(--line)}
.probe{font-size:11px;font-weight:800;text-transform:uppercase;letter-spacing:.5px;
color:var(--gold);margin-bottom:5px}
.said{font-weight:640}
.cols{display:grid;gap:0}
.col{padding:14px 16px}
.col+.col{border-left:1px solid var(--line)}
.col.now{background:#faf5e8}
.who{font-size:12px;font-weight:800;margin-bottom:2px}
.detail{color:var(--muted);font-size:12px;margin-bottom:8px}
.badge{display:inline-block;padding:3px 8px;border-radius:99px;font-size:10px;
font-weight:850;letter-spacing:.4px;margin-bottom:6px}
.b-old{color:var(--blue);background:#dbe8f8}
.b-now{color:#80601b;background:#f7eac4}
.b-alt{color:var(--green);background:#dcefe8}
audio{width:100%;height:36px}
.err{color:#a6453d;font-size:13px}
@media(max-width:820px){.cols{grid-template-columns:1fr!important}
.col+.col{border-left:0;border-top:1px solid var(--line)}
main,header{padding-left:14px;padding-right:14px}}
"""

BADGES = {"bukola": "b-old", "kore": "b-now", "leda": "b-alt", "naomi": "b-old"}


def build_page(rendered: dict[tuple[str, str], str | None]) -> str:
    beats = []
    for probe, text in LINES:
        cols = []
        for voice in VOICES:
            src = rendered.get((voice.key, probe))
            player = (
                f"<audio controls preload=none src='{escape(src)}'></audio>"
                if src else "<div class=err>could not synthesise</div>"
            )
            klass = "col now" if voice.key == "kore" else "col"
            cols.append(
                f"<div class='{klass}'><span class='badge {BADGES[voice.key]}'>"
                f"{escape(voice.key)}</span>"
                f"<div class=who>{escape(voice.label)}</div>"
                f"<div class=detail>{escape(voice.detail)}</div>{player}</div>"
            )
        beats.append(
            "<article class=beat><div class=beathead>"
            f"<div class=probe>{escape(probe)}</div>"
            f"<div class=said>{escape(text)}</div></div>"
            f"<div class=cols style='grid-template-columns:repeat({len(cols)},1fr)'>"
            + "".join(cols) + "</div></article>"
        )

    return (
        "<!doctype html><html lang=en><head><meta charset=utf-8>"
        "<meta name=viewport content='width=device-width,initial-scale=1'>"
        f"<title>Sabi — voice bake-off</title><style>{CSS}</style></head><body>"
        "<header><h1>Sabi voice bake-off</h1>"
        "<div class=sub>The same lines from prompt G, spoken three ways.</div></header>"
        "<main><div class=legend><b>Every voice reads identical text</b>, so what you are "
        "hearing is delivery only. Bukola is the original hackathon Sabi — the one people "
        "liked. Kore is what the live number uses today. Leda is the warm Gemini "
        "alternative, and Naomi is the Chatterbox clone every non-Gemini caller hears today. "
        "Voice is worth taking seriously: in the pedagogical-agent research it "
        "was the agent's voice, not its persona, that moved learning outcomes.</div>"
        + "".join(beats) + "</main></body></html>"
    )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", default="/out/voices")
    args = parser.parse_args()

    out = Path(args.out)
    (out / "audio").mkdir(parents=True, exist_ok=True)

    gemini_key = _secret("GEMINI_API_KEY")
    eleven_key = eleven_voice = ""  # only needed if an elevenlabs voice is listed

    rendered: dict[tuple[str, str], str | None] = {}
    for voice in VOICES:
        for probe, text in LINES:
            slug = f"{voice.key}_{probe.replace(' ', '-')}"
            try:
                if voice.provider == "gemini":
                    audio, ext = say_gemini(text, voice.name, gemini_key)
                elif voice.provider == "chatterbox":
                    audio, ext = say_chatterbox(text, voice.name)
                else:
                    audio, ext = say_eleven(text, eleven_voice, eleven_key)
            except Exception as exc:  # keep the other voices usable
                print(f"  {slug}: FAILED {exc}", flush=True)
                rendered[(voice.key, probe)] = None
                continue
            path = out / "audio" / f"{slug}.{ext}"
            path.write_bytes(audio)
            rendered[(voice.key, probe)] = f"audio/{path.name}"
            print(f"  {slug}: {len(audio) // 1024} KB", flush=True)

    page = out / "voice_bakeoff.html"
    page.write_text(build_page(rendered))
    print(f"wrote {page}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
