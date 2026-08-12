"""Hear a whole Sabi lesson delivered by every available voice.

The prompt lab compares words. This compares delivery, which the research says
matters more: Moreno and Mayer found the agent's voice, not its persona, was the
significant contributor to learning outcomes.

Every voice speaks the SAME lesson — otherwise this would compare scripts, not
voices. The lesson is a real 8-turn run of prompt G, and the child's side is
rendered once and shared across all versions, so the only thing that changes
between voices is Sabi.

Sources: all 30 Gemini prebuilt voices, plus every speaker cloned on Sabi's own
Chatterbox server (which includes bukola, the original hackathon Sabi, and naomi,
the voice every non-Gemini caller hears today).

Usage (inside the sabi-server image, on the compose network, with secrets):
    python scripts/voice_bakeoff.py --transcript /out/round6.json --candidate G
    python scripts/voice_bakeoff.py --transcript /out/round6.json --voices kore,leda
"""

from __future__ import annotations

import argparse
import base64
import json
import struct
import time
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from html import escape
from pathlib import Path

GEMINI_TTS_MODEL = "gemini-3.1-flash-tts-preview"
GEMINI_URL = (
    "https://generativelanguage.googleapis.com/v1beta/models/"
    f"{GEMINI_TTS_MODEL}:generateContent"
)
# Sabi's own Chatterbox server holds cloned speakers, including bukola — so the
# original voice is reachable without ElevenLabs, whose subscription is unpaid.
CHATTERBOX_URL = "http://chatterbox:8001/tts"
CHATTERBOX_HEALTH = "http://chatterbox:8001/health"

# One fixed voice for the child across every column, so the only variable is Sabi.
CHILD_VOICE = "Puck"

# Google's own one-word descriptor for each prebuilt voice.
GEMINI_VOICES: dict[str, str] = {
    "Kore": "Firm", "Leda": "Youthful", "Sulafat": "Warm", "Achird": "Friendly",
    "Vindemiatrix": "Gentle", "Sadachbia": "Lively", "Laomedeia": "Upbeat",
    "Callirrhoe": "Easy-going", "Autonoe": "Bright", "Zephyr": "Bright",
    "Aoede": "Breezy", "Despina": "Smooth", "Erinome": "Clear", "Achernar": "Soft",
    "Pulcherrima": "Forward", "Schedar": "Even", "Gacrux": "Mature",
    "Algieba": "Smooth", "Umbriel": "Easy-going", "Puck": "Upbeat",
    "Charon": "Informative", "Fenrir": "Excitable", "Orus": "Firm",
    "Enceladus": "Breathy", "Iapetus": "Clear", "Algenib": "Gravelly",
    "Rasalgethi": "Informative", "Alnilam": "Firm", "Zubenelgenubi": "Casual",
    "Sadaltager": "Knowledgeable",
}

# Voices that are already in play, called out so they are easy to find in a long list.
NOTES: dict[str, str] = {
    "bukola": "the original hackathon Sabi",
    "naomi": "live today on the non-Gemini lane",
    "Kore": "live today on your number",
}


# Rendering all 30 Gemini voices x 8 turns means 240 rate-limited calls. These get
# the whole lesson; every other voice gets one characterful line to screen it by,
# and can be promoted to a full render with --voices.
FULL_LESSON = {
    "Kore", "Leda", "Sulafat", "Achird", "Vindemiatrix",
    "Sadachbia", "Laomedeia", "Callirrhoe",
}


@dataclass(frozen=True)
class Voice:
    key: str
    label: str
    detail: str
    provider: str
    name: str
    full: bool = True


def _secret(name: str) -> str:
    path = Path(f"/run/secrets/{name}")
    if path.exists():
        return path.read_text().strip()
    raise SystemExit(f"missing credential: {name}")


def _post(url: str, payload: dict, headers: dict[str, str], attempts: int = 6) -> bytes:
    """Gemini TTS rate-limits aggressively; a first pass at six workers lost 240 of
    279 clips to 429s. Back off and honour Retry-After rather than dropping voices."""
    delay = 4.0
    for attempt in range(attempts):
        request = urllib.request.Request(
            url, data=json.dumps(payload).encode(), headers=headers
        )
        try:
            with urllib.request.urlopen(request, timeout=180) as response:
                return response.read()
        except urllib.error.HTTPError as exc:
            if exc.code not in (429, 500, 502, 503) or attempt == attempts - 1:
                raise
            wait = float(exc.headers.get("Retry-After") or 0) or delay
            time.sleep(wait)
            delay = min(delay * 2, 90)
    raise RuntimeError("unreachable")


def discover_voices(only: list[str] | None) -> list[Voice]:
    voices: list[Voice] = []

    # Chatterbox first — these are Sabi's own clones, so they matter most.
    try:
        with urllib.request.urlopen(CHATTERBOX_HEALTH, timeout=15) as response:
            speakers = json.load(response).get("speakers", [])
    except Exception as exc:
        print(f"chatterbox unavailable ({exc}) — Gemini voices only", flush=True)
        speakers = []

    for speaker in speakers:
        note = NOTES.get(speaker)
        voices.append(Voice(
            speaker, speaker.title(),
            "Chatterbox clone" + (f" · {note}" if note else ""),
            "chatterbox", speaker,
        ))

    for name, descriptor in GEMINI_VOICES.items():
        note = NOTES.get(name)
        voices.append(Voice(
            name.lower(), name,
            f'Gemini · "{descriptor}"' + (f" · {note}" if note else ""),
            "gemini", name, name in FULL_LESSON,
        ))

    if only:
        wanted = {v.strip().lower() for v in only}
        # An explicitly requested voice always gets the full lesson.
        voices = [Voice(v.key, v.label, v.detail, v.provider, v.name, True)
                  for v in voices if v.key in wanted]
    return voices


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


CSS = """
:root{--ivory:#fbf6e9;--card:#fffdf7;--ink:#221d17;--muted:#71675b;--gold:#b88a25;
--line:#e4d8bc;--blue:#315b8b;--green:#28745a}
*{box-sizing:border-box}
body{margin:0;background:var(--ivory);color:var(--ink);
font:15px/1.5 -apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif}
header{position:sticky;top:0;z-index:5;padding:18px 28px;color:#fff;
background:linear-gradient(115deg,#211a11,#4b3517);box-shadow:0 5px 22px #33240d26}
h1{margin:0;font:700 24px Georgia,serif}
.sub{color:#eadcb9;margin-top:3px;font-size:13px}
main{max-width:1500px;margin:auto;padding:20px 28px 70px}
.legend{background:#fff9e9;border:1px solid var(--line);border-radius:12px;
padding:12px 15px;margin-bottom:20px;font-size:13.5px;color:#514a40}
.legend b{color:var(--ink)}
h2{margin:26px 0 12px;font:700 20px Georgia,serif}
.grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(290px,1fr));gap:12px}
.vcard{background:var(--card);border:1px solid var(--line);border-radius:14px;padding:14px 15px}
.vcard.live{box-shadow:inset 3px 0 0 var(--gold)}
.who{font-size:14px;font-weight:800}
.detail{color:var(--muted);font-size:12px;margin:2px 0 10px;min-height:32px}
.play{border:0;border-radius:10px;padding:9px 13px;background:#2e261b;color:#fff;
font-weight:750;cursor:pointer;font-size:13.5px;width:100%}
.play:hover{background:#463a29}
.play[aria-pressed=true]{background:var(--gold);color:#211a11}
.nowplay{margin-top:7px;font-size:11.5px;color:var(--muted);min-height:15px}
details{margin-top:9px}
summary{cursor:pointer;font-size:12px;color:var(--gold);font-weight:700}
.turnrow{margin-top:8px}
.turnlabel{font-size:11px;color:var(--muted);text-transform:uppercase;letter-spacing:.4px}
audio{width:100%;height:32px}
.script{background:var(--card);border:1px solid var(--line);border-radius:14px;overflow:hidden}
.line{padding:11px 15px;border-bottom:1px solid var(--line)}
.line:last-child{border-bottom:0}
.probe{font-size:10.5px;font-weight:800;text-transform:uppercase;letter-spacing:.5px;color:var(--gold)}
.child{font-weight:700;margin-top:4px}
.child span{color:var(--muted);font-weight:400;font-size:11px;text-transform:uppercase;
letter-spacing:.5px;margin-right:7px}
.said{margin-top:5px;color:#3f382e}
.err{color:#a6453d;font-size:12.5px}
@media(max-width:700px){main,header{padding-left:14px;padding-right:14px}}
"""


def build_page(clips: dict, turns: list[dict], voices: list[Voice], candidate: str) -> str:
    playlists = {}
    for voice in voices:
        seq = []
        for index in range(len(turns)):
            child = clips.get(f"child_{index}")
            sabi = clips.get(f"{voice.key}_{index}")
            if child:
                seq.append([child, f"child: {turns[index]['learner'][:40]}"])
            if sabi:
                seq.append([sabi, f"{voice.label} — turn {index + 1} of {len(turns)}"])
        playlists[voice.key] = seq

    cards, samples = [], []
    for voice in voices:
        live = " live" if voice.key in ("kore", "naomi") else ""
        rows = []
        for index in range(len(turns)):
            src = clips.get(f"{voice.key}_{index}")
            player = (f"<audio controls preload=none src='{escape(src)}'></audio>"
                      if src else "<div class=err>not synthesised</div>")
            rows.append(
                f"<div class=turnrow><div class=turnlabel>turn {index + 1}</div>{player}</div>"
            )
        if voice.full:
            cards.append(
                f"<div class='vcard{live}'>"
                f"<div class=who>{escape(voice.label)}</div>"
                f"<div class=detail>{escape(voice.detail)}</div>"
                f"<button class=play id='btn-{escape(voice.key)}' aria-pressed=false "
                f'onclick="toggle(\'{escape(voice.key)}\')">▶ Play the whole lesson</button>'
                f"<div class=nowplay id='np-{escape(voice.key)}'></div>"
                f"<details><summary>turn by turn</summary>{''.join(rows)}</details>"
                "</div>"
            )
        else:
            src = clips.get(f"{voice.key}_{len(turns) - 1}")
            player = (f"<audio controls preload=none src='{escape(src)}'></audio>"
                      if src else "<div class=err>not synthesised</div>")
            samples.append(
                f"<div class=vcard><div class=who>{escape(voice.label)}</div>"
                f"<div class=detail>{escape(voice.detail)}</div>{player}</div>"
            )

    script_lines = []
    for index, turn in enumerate(turns):
        script_lines.append(
            f"<div class=line><div class=probe>turn {index + 1} · {escape(turn['probe'])}</div>"
            f"<div class=child><span>child</span>{escape(turn['learner'])}</div>"
            f"<div class=said>{escape(turn['sabi'])}</div></div>"
        )

    js = """
const PL = __PLAYLISTS__;
let audio = null, current = null;
function reset(key){
  const b=document.getElementById('btn-'+key);
  if(b){b.setAttribute('aria-pressed','false'); b.textContent='▶ Play the whole lesson';}
  const n=document.getElementById('np-'+key); if(n) n.textContent='';
}
function stop(){ if(audio){audio.pause(); audio=null;} if(current){reset(current);} current=null; }
function toggle(key){
  if(current===key){ stop(); return; }
  stop(); current=key;
  const btn=document.getElementById('btn-'+key), np=document.getElementById('np-'+key);
  btn.setAttribute('aria-pressed','true'); btn.textContent='■ Stop';
  let i=0;
  const next=()=>{
    if(current!==key) return;
    if(i>=PL[key].length){ stop(); return; }
    const item=PL[key][i++];
    np.textContent=item[1];
    audio=new Audio(item[0]);
    audio.onended=next; audio.onerror=next;
    audio.play().catch(()=>next());
  };
  next();
}
""".replace("__PLAYLISTS__", json.dumps(playlists))

    return (
        "<!doctype html><html lang=en><head><meta charset=utf-8>"
        "<meta name=viewport content='width=device-width,initial-scale=1'>"
        f"<title>Sabi — full lesson, {len(voices)} voices</title>"
        f"<style>{CSS}</style></head><body>"
        "<header><h1>Sabi voice bake-off — the whole lesson</h1>"
        f"<div class=sub>A complete {len(turns)}-turn run of prompt {escape(candidate)}, "
        f"delivered by {len(voices)} voices.</div></header><main>"
        "<div class=legend><b>Press play on any voice to hear the entire call.</b> Every "
        "voice reads identical words, and the child's side is the same recording throughout, "
        "so the only thing changing is Sabi. Gold-edged cards are what is live today. These "
        "are 24kHz studio renders — the real call is 8kHz narrowband, which flattens exactly "
        "the warmth you are listening for, so shortlist here and confirm on a phone.</div>"
        f"<div class=grid>{''.join(cards)}</div>"
        + (f"<h2>Every other voice — one line each</h2>"
           "<div class=legend>Screen these by ear, then ask for a full lesson in any of "
           "them.</div>"
           f"<div class=grid>{''.join(samples)}</div>" if samples else "")
        + f"<h2>The lesson they are all reading</h2>"
        f"<div class=script>{''.join(script_lines)}</div>"
        f"</main><script>{js}</script></body></html>"
    )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--transcript", required=True, help="a prompt_lab results json")
    parser.add_argument("--candidate", default="G")
    parser.add_argument("--rep", type=int, default=1, help="which run to voice")
    parser.add_argument("--voices", help="comma-separated subset; default is every voice")
    parser.add_argument("--workers", type=int, default=6)
    parser.add_argument("--out", default="/out/voices")
    args = parser.parse_args()

    data = json.loads(Path(args.transcript).read_text())
    entry = next(r for r in data["rounds"] if r["rep"] == args.rep)
    turns = entry["transcripts"][args.candidate]

    out = Path(args.out)
    (out / "audio").mkdir(parents=True, exist_ok=True)
    gemini_key = _secret("GEMINI_API_KEY")

    voices = discover_voices(args.voices.split(",") if args.voices else None)
    print(f"{len(voices)} voices x {len(turns)} turns", flush=True)

    jobs: list[tuple[str, str, str, str]] = []
    for index, turn in enumerate(turns):
        line = turn["learner"]
        if not line.startswith("["):  # the unclear-audio beat has no words to speak
            jobs.append((f"child_{index}", line, "gemini", CHILD_VOICE))
    # The last turn is the celebration — the most characterful line to screen by.
    sample_index = len(turns) - 1
    for voice in voices:
        wanted = range(len(turns)) if voice.full else [sample_index]
        for index in wanted:
            if (turns[index].get("sabi") or "").strip():
                jobs.append(
                    (f"{voice.key}_{index}", turns[index]["sabi"], voice.provider, voice.name)
                )

    clips: dict[str, str | None] = {}

    def render(job: tuple[str, str, str, str]) -> None:
        slug, text, provider, name = job
        try:
            audio, ext = (say_gemini(text, name, gemini_key) if provider == "gemini"
                          else say_chatterbox(text, name))
        except Exception as exc:  # one bad voice must not sink the rest
            print(f"  {slug}: FAILED {exc}", flush=True)
            clips[slug] = None
            return
        path = out / "audio" / f"{slug}.{ext}"
        path.write_bytes(audio)
        clips[slug] = f"audio/{path.name}"

    with ThreadPoolExecutor(max_workers=args.workers) as pool:
        for done, _ in enumerate(pool.map(render, jobs), 1):
            if done % 25 == 0:
                print(f"  {done}/{len(jobs)} clips", flush=True)

    failed = sum(1 for v in clips.values() if v is None)
    print(f"done: {len(jobs) - failed} clips, {failed} failed", flush=True)

    page = out / "voice_bakeoff.html"
    page.write_text(build_page(clips, turns, voices, args.candidate))
    print(f"wrote {page}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
