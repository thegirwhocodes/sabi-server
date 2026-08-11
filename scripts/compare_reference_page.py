"""Side-by-side viewer: the Haiku reference voice against a candidate prompt.

Renders a static page in the same visual language as the Gemini hearing replay
dashboard, and serves it on the same address (127.0.0.1:8765). Static on purpose —
the replay dashboard's one-second refresh rebuilt every element and made playback
blink, and this data is already computed.

Usage:
    python scripts/compare_reference_page.py round5.json --candidate G
    python scripts/compare_reference_page.py round5.json --candidate G --serve
"""

from __future__ import annotations

import argparse
import functools
import http.server
import json
import socketserver
from html import escape
from pathlib import Path

PORT = 8765

CSS = """
:root{--ivory:#fbf6e9;--card:#fffdf7;--ink:#221d17;--muted:#71675b;--gold:#b88a25;
--line:#e4d8bc;--green:#28745a;--red:#a6453d;--blue:#315b8b}
*{box-sizing:border-box}
body{margin:0;background:var(--ivory);color:var(--ink);
font:15px/1.5 -apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif}
header{position:sticky;top:0;z-index:3;padding:20px 28px;color:#fff;
background:linear-gradient(115deg,#211a11,#4b3517);box-shadow:0 5px 22px #33240d26}
h1{margin:0;font:700 25px Georgia,serif}
.sub{color:#eadcb9;margin-top:4px;font-size:13.5px}
main{max-width:1500px;margin:auto;padding:20px 28px 60px}
.stats{display:grid;grid-template-columns:repeat(5,1fr);gap:10px;margin-bottom:18px}
.stat{background:var(--card);border:1px solid var(--line);border-radius:12px;padding:11px 14px;font-size:12px;color:var(--muted)}
.stat b{display:block;color:var(--gold);font-size:22px;margin-bottom:2px}
.legend{background:#fff9e9;border:1px solid var(--line);border-radius:12px;padding:12px 15px;margin-bottom:18px;font-size:13.5px;color:#514a40}
.legend b{color:var(--ink)}
h2{margin:26px 0 12px;font:700 21px Georgia,serif}
.beat{background:var(--card);border:1px solid var(--line);border-radius:15px;
margin-bottom:14px;overflow:hidden}
.beathead{padding:12px 16px;background:#fff8e7;border-bottom:1px solid var(--line);
display:flex;justify-content:space-between;gap:14px;align-items:baseline;flex-wrap:wrap}
.probe{font-size:11px;font-weight:800;text-transform:uppercase;letter-spacing:.5px;color:var(--gold)}
.learner{font-weight:720}
.learner span{color:var(--muted);font-weight:400;font-size:12px;text-transform:uppercase;letter-spacing:.5px;margin-right:8px}
.cols{display:grid;grid-template-columns:1fr 1fr;gap:0}
.col{padding:14px 16px}
.col+.col{border-left:1px solid var(--line)}
.col.ref{background:#faf5e8}
.who{color:var(--gold);font-size:11px;font-weight:800;text-transform:uppercase;
letter-spacing:.5px;margin-bottom:6px;display:flex;align-items:center;gap:8px}
.badge{padding:3px 8px;border-radius:99px;font-size:10px;font-weight:850;letter-spacing:.4px}
.b-ref{color:var(--blue);background:#dbe8f8}
.b-cand{color:var(--green);background:#dcefe8}
.say{white-space:pre-wrap}
.empty{color:var(--muted);font-style:italic}
@media(max-width:820px){.cols{grid-template-columns:1fr}.col+.col{border-left:0;border-top:1px solid var(--line)}
.stats{grid-template-columns:repeat(2,1fr)}main,header{padding-left:14px;padding-right:14px}}
"""


def render(data: dict, candidates: list[str]) -> str:
    rounds = data["rounds"]
    names = data.get("names", {})
    def stat(label: str, value) -> str:
        return f"<div class=stat><b>{escape(str(value))}</b>{escape(label)}</div>"

    # Average words per turn, since length is the thing being compared by eye.
    def avg_words(turns: list[dict[str, str]]) -> int:
        spoken = [len((t.get("sabi") or "").split()) for t in turns]
        return round(sum(spoken) / len(spoken)) if spoken else 0

    ref_words = [avg_words(r["reference"]) for r in rounds if r.get("reference")]
    stats = [stat("words/turn — Haiku", round(sum(ref_words) / len(ref_words)) if ref_words else "—")]
    for cand in candidates:
        per = [avg_words(r["transcripts"][cand]) for r in rounds if r["transcripts"].get(cand)]
        stats.append(stat(f"words/turn — {cand}", round(sum(per) / len(per)) if per else "—"))
    stats.append(stat("runs shown", len(rounds)))
    stats = "".join(stats)

    sections = []
    for entry in rounds:
        reference = entry.get("reference")
        if not reference or not any(entry["transcripts"].get(c) for c in candidates):
            continue

        beats = []
        for index, ref_turn in enumerate(reference):
            def say(text: str) -> str:
                text = (text or "").strip()
                return f"<div class=say>{escape(text)}</div>" if text else \
                       "<div class='say empty'>(said nothing)</div>"

            cols = [
                "<div class='col ref'><div class=who><span class='badge b-ref'>reference</span>"
                "Claude Haiku · original prompt</div>"
                f"{say(ref_turn['sabi'])}</div>"
            ]
            for cand in candidates:
                turns = entry["transcripts"].get(cand) or []
                turn = turns[index] if index < len(turns) else {}
                cols.append(
                    f"<div class=col><div class=who><span class='badge b-cand'>{escape(cand)}</span>"
                    f"{escape(names.get(cand, cand))}</div>{say(turn.get('sabi', ''))}</div>"
                )

            beats.append(
                "<article class=beat>"
                "<div class=beathead>"
                f"<div class=learner><span>child</span>{escape(ref_turn['learner'])}</div>"
                f"<div class=probe>{escape(ref_turn['probe'])}</div>"
                "</div>"
                f"<div class=cols style='grid-template-columns:repeat({len(cols)},1fr)'>"
                + "".join(cols) + "</div></article>"
            )

        sections.append(f"<h2>Run {entry['rep']}</h2>" + "".join(beats))

    label = escape(", ".join(candidates))
    return (
        "<!doctype html><html lang=en><head><meta charset=utf-8>"
        "<meta name=viewport content='width=device-width,initial-scale=1'>"
        f"<title>Sabi — {label} vs Haiku</title><style>{CSS}</style></head><body>"
        "<header><h1>Sabi voice comparison</h1>"
        f"<div class=sub>Prompts {label} against the voice we are trying to recover. "
        "Same scripted lesson, same learner turns, every column.</div></header>"
        f"<main><div class=stats>{stats}</div>"
        "<div class=legend><b>Read the left column for the voice, not the teaching.</b> "
        "The reference sounds like the Sabi people loved, but it is the worst teacher in the "
        "set — it abandons a question when the child struggles and starts winding up at ninety "
        "seconds. The candidate is trying to take its warmth without its habits. "
        "Text only: this is the prompt lab's proxy model, not the live audio model.</div>"
        + "".join(sections) +
        "</main></body></html>"
    )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("results", help="a prompt_lab results json")
    parser.add_argument("--candidate", default="G", help="comma-separated, e.g. G,I")
    parser.add_argument("--out", default="sabi_voice_comparison.html")
    parser.add_argument("--serve", action="store_true", help=f"serve on 127.0.0.1:{PORT}")
    args = parser.parse_args()

    data = json.loads(Path(args.results).read_text())
    out = Path(args.out)
    out.write_text(render(data, [c.strip() for c in args.candidate.split(",") if c.strip()]))
    print(f"wrote {out}")

    if args.serve:
        handler = functools.partial(
            http.server.SimpleHTTPRequestHandler, directory=str(out.parent.resolve())
        )
        socketserver.TCPServer.allow_reuse_address = True
        with socketserver.TCPServer(("127.0.0.1", PORT), handler) as httpd:
            print(f"serving http://127.0.0.1:{PORT}/{out.name} — ctrl-c to stop", flush=True)
            httpd.serve_forever()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
