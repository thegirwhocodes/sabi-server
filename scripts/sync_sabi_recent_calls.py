#!/usr/bin/env python3
"""Maintain a private, browser-friendly local library of recent Sabi calls.

The raw call evidence remains on the Sabi server. This script reuses the
existing secure call-audio sync, then builds a local-only HTML dashboard whose
audio controls play WAV files in the browser instead of importing them into
Apple Music.
"""

from __future__ import annotations

import argparse
from datetime import datetime, timedelta
from html import escape
import json
import os
from pathlib import Path
import sys
from urllib.parse import quote

import sync_sabi_call_audio_to_onedrive as call_sync


DEFAULT_DESTINATION = Path("/Users/naomiivie/Sabi Recent Calls")
DEFAULT_RECENT_LIMIT = 20


def _record_timestamp(record: dict) -> float:
    try:
        return float(record.get("created_at") or 0)
    except (TypeError, ValueError):
        return 0


def _records(destination: Path) -> list[dict]:
    records: list[dict] = []
    for sidecar in (destination / ".metadata").glob("call_*.json"):
        try:
            record = json.loads(sidecar.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        if str(record.get("call_uuid") or "").strip():
            records.append(record)
    return sorted(records, key=_record_timestamp, reverse=True)


def _file_href(destination: Path, file_path: Path) -> str:
    relative = file_path.relative_to(destination).as_posix()
    return quote(relative, safe="/._-()")


def _display_time(record: dict) -> str:
    stamp = _record_timestamp(record)
    if not stamp:
        return "Unknown date"
    return datetime.fromtimestamp(stamp).astimezone().strftime("%A, %B %-d at %-I:%M %p %Z")


def _turn_rows(destination: Path, call_dir: Path, record: dict) -> str:
    rows: list[str] = []
    for turn in record.get("turns") or []:
        if not isinstance(turn, dict):
            continue
        index = turn.get("turn_index")
        if not isinstance(index, int):
            continue
        clip = call_dir / f"user_turn_{index:02d}.wav"
        user = turn.get("user") if isinstance(turn.get("user"), dict) else {}
        assistant = turn.get("assistant") if isinstance(turn.get("assistant"), dict) else {}
        timings = turn.get("timings") if isinstance(turn.get("timings"), dict) else {}
        flags = turn.get("flags") if isinstance(turn.get("flags"), list) else []
        heard = escape(str(user.get("stt_transcript") or "[empty]"))
        reply = escape(str(assistant.get("text") or "[no saved reply]"))
        provider = escape(str(user.get("stt_provider") or "unknown"))
        stt_seconds = escape(str(timings.get("stt_seconds") or 0))
        flag_text = escape(", ".join(str(flag) for flag in flags) or "none")
        if clip.exists():
            player = (
                f'<audio controls preload="none" src="{_file_href(destination, clip)}">'
                "Your browser cannot play this WAV file.</audio>"
            )
        else:
            player = '<span class="missing">Clip unavailable</span>'
        rows.append(
            "<tr>"
            f'<td class="turn">{index}</td><td>{player}</td>'
            f'<td><strong>{heard}</strong><small>{provider} · {stt_seconds}s</small></td>'
            f"<td>{reply}<small>{flag_text}</small></td>"
            "</tr>"
        )
    if not rows:
        return '<tr><td colspan="4" class="empty">No saved learner turns.</td></tr>'
    return "".join(rows)


def _call_card(destination: Path, call_dir: Path, record: dict, position: int) -> str:
    call_uuid = escape(str(record.get("call_uuid") or "unknown"))
    folder_name = escape(call_dir.name.replace("_", " · "))
    duration = escape(str(round(float(record.get("duration_seconds") or 0), 1)))
    end_reason = escape(str(record.get("end_reason") or "unknown").replace("_", " "))
    full_call = call_dir / "full-caller-only.wav"
    if full_call.exists():
        full_player = (
            '<div class="full-call"><span>Full caller-only recording</span>'
            f'<audio controls preload="none" src="{_file_href(destination, full_call)}">'
            "Your browser cannot play this WAV file.</audio></div>"
        )
    else:
        full_player = '<div class="full-call missing">Full caller-only recording unavailable</div>'
    transcript = call_dir / "what-sabi-heard.txt"
    transcript_link = (
        f'<a href="{_file_href(destination, transcript)}">Open what Sabi heard</a>'
        if transcript.exists()
        else ""
    )
    return (
        f'<details class="call" {"open" if position == 0 else ""}>'
        f'<summary><span><strong>{folder_name}</strong><small>{escape(_display_time(record))}</small></span>'
        f'<span class="summary-meta">{duration}s · {end_reason}</span></summary>'
        '<div class="call-body">'
        f"{full_player}"
        f'<div class="call-links">{transcript_link}<span>Call ID: {call_uuid}</span></div>'
        '<div class="table-wrap"><table><thead><tr><th>Turn</th><th>Actual clip</th>'
        '<th>What Sabi heard</th><th>Sabi replied</th></tr></thead><tbody>'
        f"{_turn_rows(destination, call_dir, record)}"
        "</tbody></table></div></div></details>"
    )


def _update_symlink(link: Path, target: Path | None) -> None:
    if link.is_symlink():
        link.unlink()
    elif link.exists():
        # Never overwrite a user-created file or folder with a shortcut.
        return
    if target and target.exists():
        link.symlink_to(os.path.relpath(target, link.parent), target_is_directory=True)


def _refresh_shortcuts(destination: Path, records: list[dict], call_dirs: dict[str, Path]) -> None:
    newest = None
    if records:
        newest = call_dirs.get(str(records[0].get("call_uuid") or ""))
    _update_symlink(destination / "Latest Call", newest)

    now = datetime.now().astimezone()
    for label, date_value in (
        ("Today's Calls", now.date()),
        ("Yesterday's Calls", (now - timedelta(days=1)).date()),
    ):
        target = None
        for record in records:
            stamp = _record_timestamp(record)
            if not stamp or datetime.fromtimestamp(stamp).astimezone().date() != date_value:
                continue
            call_dir = call_dirs.get(str(record.get("call_uuid") or ""))
            if call_dir:
                target = call_dir.parent
                break
        _update_symlink(destination / label, target)


def _write_dashboard(destination: Path, recent_limit: int) -> tuple[int, int]:
    records = _records(destination)
    call_dirs = call_sync._existing_call_dirs(destination)
    recent: list[tuple[dict, Path]] = []
    for record in records:
        call_uuid = str(record.get("call_uuid") or "")
        call_dir = call_dirs.get(call_uuid)
        if call_dir:
            recent.append((record, call_dir))
        if len(recent) >= recent_limit:
            break
    _refresh_shortcuts(destination, records, call_dirs)

    cards = "".join(
        _call_card(destination, call_dir, record, position)
        for position, (record, call_dir) in enumerate(recent)
    ) or '<p class="empty">No calls have synced yet.</p>'
    refreshed = datetime.now().astimezone().strftime("%B %-d, %Y at %-I:%M:%S %p %Z")
    html = f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <meta http-equiv="refresh" content="120">
  <title>Sabi Recent Calls</title>
  <style>
    :root {{ color-scheme: light; --ink:#1f241f; --muted:#696c65; --gold:#b88a22; --line:#ded8c9; --paper:#fffdf7; --wash:#f2ede0; }}
    * {{ box-sizing:border-box; }} body {{ margin:0; background:var(--wash); color:var(--ink); font:15px/1.45 -apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif; }}
    header {{ background:#24261f; color:#fffdf7; padding:28px max(24px,calc((100vw - 1180px)/2)); border-bottom:4px solid var(--gold); }}
    h1 {{ margin:0 0 4px; font:600 32px/1.15 Georgia,serif; }} header p {{ margin:0; color:#d7d4ca; }}
    main {{ max-width:1180px; margin:24px auto 60px; padding:0 20px; }}
    .notice {{ background:#fff8dd; border:1px solid #e0c876; padding:12px 16px; border-radius:10px; margin-bottom:18px; }}
    .call {{ background:var(--paper); border:1px solid var(--line); border-radius:12px; margin:12px 0; overflow:hidden; box-shadow:0 2px 8px #584d3020; }}
    summary {{ cursor:pointer; display:flex; align-items:center; justify-content:space-between; gap:18px; padding:16px 18px; }}
    summary strong {{ display:block; font-size:17px; }} small {{ display:block; color:var(--muted); margin-top:3px; }}
    .summary-meta {{ color:var(--muted); white-space:nowrap; }} .call-body {{ border-top:1px solid var(--line); padding:16px 18px 20px; }}
    .full-call {{ display:flex; align-items:center; gap:16px; flex-wrap:wrap; font-weight:600; margin-bottom:10px; }} audio {{ height:36px; max-width:100%; }}
    .call-links {{ display:flex; gap:18px; justify-content:space-between; color:var(--muted); font-size:13px; margin-bottom:14px; }} a {{ color:#76570e; }}
    .table-wrap {{ overflow-x:auto; }} table {{ width:100%; border-collapse:collapse; min-width:760px; }} th {{ text-align:left; color:var(--muted); font-size:12px; text-transform:uppercase; letter-spacing:.04em; }}
    th,td {{ border-top:1px solid #e8e3d7; padding:10px 8px; vertical-align:top; }} thead th {{ border-top:0; }} td.turn {{ width:48px; font-weight:700; }} td small {{ max-width:310px; }}
    .missing,.empty {{ color:#8a5e55; }} footer {{ color:var(--muted); font-size:13px; margin-top:22px; }}
    @media (max-width:650px) {{ h1 {{ font-size:26px; }} summary {{ align-items:flex-start; }} .summary-meta {{ font-size:12px; }} .call-links {{ display:block; }} .call-links span {{ display:block; margin-top:4px; }} }}
  </style>
</head>
<body>
  <header><h1>Sabi Recent Calls</h1><p>Private, local troubleshooting library · refreshed every two minutes</p></header>
  <main>
    <div class="notice"><strong>Actual audio is the evidence.</strong> “What Sabi heard” is model output, not ground truth. Browser playback prevents these clips from being imported into Apple Music.</div>
    {cards}
    <footer>Showing the newest {len(recent)} of {len(records)} locally synced calls. Last refreshed {escape(refreshed)}. Audio and transcripts stay on this Mac.</footer>
  </main>
</body>
</html>
"""
    temp_index = destination / ".index.html.tmp"
    temp_index.write_text(html, encoding="utf-8")
    temp_index.replace(destination / "index.html")
    (destination / "README.txt").write_text(
        "SABI RECENT CALLS — LOCAL TROUBLESHOOTING LIBRARY\n"
        "=================================================\n\n"
        "Open index.html in Safari to listen without importing WAV files into Apple Music.\n"
        "Latest Call, Today's Calls, and Yesterday's Calls are local Finder shortcuts.\n\n"
        "The folder refreshes automatically every two minutes when this Mac is awake. It is outside\n"
        "Library/CloudStorage and does not sync to OneDrive. The Sabi server remains the source of truth.\n\n"
        "Calls/ contains the full local call archive so older evidence remains immediately available;\n"
        f"the dashboard shows only the newest {recent_limit} calls for fast troubleshooting.\n\n"
        "what-sabi-heard.txt contains model output, not a ground-truth transcript. These files may\n"
        "contain children's voices and personal information; keep this folder private.\n",
        encoding="utf-8",
    )
    return len(recent), len(records)


def refresh(server: str, remote_root: str, destination: Path, recent_limit: int) -> tuple[int, int]:
    destination.mkdir(parents=True, exist_ok=True)
    destination.chmod(0o700)
    call_sync.sync(server, remote_root, destination)
    result = _write_dashboard(destination, recent_limit)
    destination.chmod(0o700)
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--server", default=call_sync.DEFAULT_SERVER)
    parser.add_argument("--remote-root", default=call_sync.DEFAULT_REMOTE_ROOT)
    parser.add_argument("--destination", type=Path, default=DEFAULT_DESTINATION)
    parser.add_argument("--recent-limit", type=int, default=DEFAULT_RECENT_LIMIT)
    args = parser.parse_args()
    if args.recent_limit < 1:
        parser.error("--recent-limit must be at least 1")
    try:
        visible, total = refresh(
            args.server,
            args.remote_root.rstrip("/"),
            args.destination,
            args.recent_limit,
        )
    except Exception as exc:  # launchd needs a concise durable error log
        print(f"Sabi recent-call refresh failed: {exc}", file=sys.stderr)
        return 1
    print(f"Sabi recent-call refresh complete: newest {visible} of {total} calls are on the dashboard")
    print(args.destination / "index.html")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
