"""Protected browser review console for Sabi learner/call QA.

Board-facing operations console, rebuilt to Naomi's backend brief:
  - Board members immediately understand what they are looking at.
  - One row per learner; names + phone numbers always shown together.
  - No "Unnamed learner", no raw flags — everything in human language.
  - Real sort + filter controls (newest first is a labelled sort, not a pill).
  - Call review shows full/child/Sabi audio, per-turn clips, raw vs cleaned
    STT, confidence, provider, timings, exact TTS text, and feedback notes.
  - Curriculum shown as a node/branch map with green, subtle support states.
Visual identity follows the approved premium Sabi brand: warm ivory surfaces,
ink sidebar, gold spark, Cormorant Garamond display + Lexend body.
"""

from __future__ import annotations


def render_admin_review_page() -> str:
    """Return the internal board/admin console shell.

    The page is hosted by the Sabi API because protected call audio lives on
    the PBX volume. The API accepts the full SABI_API_KEY and a read-only admin
    PIN for GET /admin/* routes.
    """
    return """<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Sabi Admin Console</title>
  <link rel="preconnect" href="https://fonts.googleapis.com">
  <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
  <link href="https://fonts.googleapis.com/css2?family=Cormorant+Garamond:wght@500;600;700&family=Lexend:wght@300;400;500;600;700&display=swap" rel="stylesheet">
  <style>
    :root {
      color-scheme: light;
      --ink: #201a13;
      --ink-soft: #4c4438;
      --muted: #857a68;
      --paper: #f7f2e7;
      --card: #fffdf8;
      --line: #e8dfc9;
      --line-strong: #d9cdaf;
      --gold: #cba868;
      --gold-deep: #9a7536;
      --gold-soft: #f4ead4;
      --gold-wash: #faf4e6;
      --green: #1e7b43;
      --green-soft: #e6f3ea;
      --green-line: #b9dcc6;
      --warn: #9b5b00;
      --warn-bg: #faf0da;
      --warn-line: #ecd3a2;
      --bad: #b42318;
      --bad-bg: #fbeeec;
      --bad-line: #f0c1ba;
      --side: #1b1610;
      --side-soft: #2a2318;
      --side-text: #d8cdb8;
      --shadow: 0 24px 60px rgba(45, 36, 20, 0.16);
      --soft-shadow: 0 6px 22px rgba(45, 36, 20, 0.06);
      --serif: "Cormorant Garamond", Georgia, serif;
      --sans: "Lexend", ui-sans-serif, system-ui, -apple-system, sans-serif;
    }
    * { box-sizing: border-box; }
    html { scroll-behavior: smooth; }
    body {
      margin: 0;
      font-family: var(--sans);
      font-weight: 300;
      background:
        radial-gradient(1200px 500px at 85% -10%, rgba(203, 168, 104, 0.10), transparent 60%),
        var(--paper);
      color: var(--ink);
      font-size: 14px;
      line-height: 1.5;
    }
    h1, h2, h3 { margin: 0; font-weight: 600; }
    h1 { font-family: var(--serif); font-size: 30px; line-height: 1.05; letter-spacing: .01em; }
    h2 { font-size: 16px; font-weight: 500; }
    h3 { font-size: 13px; font-weight: 600; letter-spacing: .02em; }
    button, input, select {
      font: inherit;
      font-weight: 400;
      border: 1px solid var(--line-strong);
      border-radius: 9px;
      background: var(--card);
      color: var(--ink);
    }
    button {
      min-height: 38px;
      padding: 8px 14px;
      cursor: pointer;
      display: inline-flex;
      align-items: center;
      justify-content: center;
      gap: 7px;
      transition: background 140ms ease, border-color 140ms ease, transform 140ms ease;
    }
    button:hover { border-color: var(--gold); background: var(--gold-wash); }
    button:active { transform: translateY(1px); }
    button:focus-visible, input:focus-visible, select:focus-visible {
      outline: 2px solid var(--gold);
      outline-offset: 1px;
    }
    button.primary { background: var(--ink); border-color: var(--ink); color: #f6efe0; }
    button.primary:hover { background: #33291c; }
    input { min-height: 38px; padding: 8px 12px; min-width: 250px; }
    input::placeholder { color: var(--muted); }
    select { min-height: 38px; padding: 7px 10px; cursor: pointer; }
    label.control {
      display: inline-flex;
      align-items: center;
      gap: 7px;
      font-size: 12px;
      color: var(--muted);
      white-space: nowrap;
    }
    audio { width: 100%; margin-top: 8px; height: 36px; }
    .app { min-height: 100vh; display: grid; grid-template-columns: 246px minmax(0, 1fr); }

    /* ---------- Sidebar ---------- */
    .sidebar {
      background: linear-gradient(180deg, var(--side) 0%, #221b12 100%);
      color: var(--side-text);
      padding: 22px 14px 16px;
      position: sticky;
      top: 0;
      height: 100vh;
      display: flex;
      flex-direction: column;
      gap: 18px;
    }
    .brand { display: flex; align-items: center; gap: 12px; padding: 2px 8px 18px; border-bottom: 1px solid rgba(216, 205, 184, 0.16); }
    .brand-spark { width: 34px; height: 34px; flex: none; filter: drop-shadow(0 0 10px rgba(203,168,104,.35)); }
    .brand-title { font-family: var(--serif); font-size: 26px; font-weight: 600; color: #f1e6cd; line-height: 1; }
    .brand-subtitle { font-size: 10.5px; letter-spacing: .14em; text-transform: uppercase; color: rgba(216,205,184,.62); margin-top: 4px; }
    .nav { display: grid; gap: 3px; }
    .nav button {
      border: 0;
      background: transparent;
      justify-content: flex-start;
      width: 100%;
      color: var(--side-text);
      padding: 10px 12px;
      border-radius: 9px;
      font-weight: 300;
      font-size: 13.5px;
      gap: 11px;
    }
    .nav button svg { width: 16px; height: 16px; flex: none; opacity: .75; }
    .nav button:hover { background: rgba(203, 168, 104, 0.12); color: #f1e6cd; }
    .nav button[aria-selected="true"] {
      background: linear-gradient(90deg, rgba(203,168,104,.22), rgba(203,168,104,.08));
      color: #f6ecd6;
      font-weight: 500;
      box-shadow: inset 2.5px 0 0 var(--gold);
    }
    .nav-count {
      margin-left: auto;
      font-size: 10.5px;
      background: rgba(203,168,104,.18);
      color: #e6d3a8;
      border-radius: 99px;
      min-width: 20px;
      padding: 2px 7px;
      text-align: center;
    }
    .side-foot { margin-top: auto; display: grid; gap: 10px; padding: 12px 8px 0; border-top: 1px solid rgba(216,205,184,.14); font-size: 11.5px; color: rgba(216,205,184,.66); }
    .health { display: flex; align-items: center; gap: 8px; }
    .health-dot { width: 8px; height: 8px; border-radius: 99px; background: #6c6353; box-shadow: 0 0 0 3px rgba(108,99,83,.2); }
    .health-dot.ok { background: #4dbd7d; box-shadow: 0 0 0 3px rgba(77,189,125,.18); }
    .health-dot.down { background: #e0655a; box-shadow: 0 0 0 3px rgba(224,101,90,.18); }

    /* ---------- Topbar + workspace ---------- */
    .content { min-width: 0; }
    .topbar {
      min-height: 86px;
      background: rgba(255, 253, 248, 0.86);
      backdrop-filter: blur(8px);
      border-bottom: 1px solid var(--line);
      padding: 18px 26px;
      display: flex;
      align-items: center;
      justify-content: space-between;
      gap: 18px;
      position: sticky;
      top: 0;
      z-index: 20;
    }
    .topbar-copy { display: grid; gap: 3px; }
    .subtitle { font-size: 13px; color: var(--muted); font-weight: 300; }
    .top-actions { display: flex; align-items: center; gap: 9px; flex-wrap: wrap; }
    .workspace { padding: 22px 26px 34px; display: grid; gap: 18px; }

    .metrics { display: grid; grid-template-columns: repeat(6, minmax(130px, 1fr)); gap: 12px; }
    .metric {
      background: var(--card);
      border: 1px solid var(--line);
      border-radius: 13px;
      padding: 14px 16px;
      display: grid;
      gap: 2px;
      box-shadow: var(--soft-shadow);
      position: relative;
      overflow: hidden;
    }
    .metric::after { content: ""; position: absolute; inset: 0 0 auto 0; height: 2.5px; background: linear-gradient(90deg, var(--gold), transparent 70%); opacity: .55; }
    .metric-label { font-size: 11.5px; color: var(--muted); letter-spacing: .03em; }
    .metric-value { font-family: var(--serif); font-size: 27px; font-weight: 600; line-height: 1.15; }
    .metric-note { font-size: 11px; color: var(--muted); }

    .panel {
      background: var(--card);
      border: 1px solid var(--line);
      border-radius: 15px;
      overflow: hidden;
      box-shadow: var(--soft-shadow);
    }
    .panel-head {
      padding: 14px 18px;
      border-bottom: 1px solid var(--line);
      display: flex;
      align-items: center;
      justify-content: space-between;
      gap: 12px;
      flex-wrap: wrap;
      background: linear-gradient(180deg, #fffdf8, #fdf9ef);
    }
    .toolbar { display: flex; align-items: center; gap: 9px; flex-wrap: wrap; }
    .range { font-size: 12.5px; color: var(--muted); margin-left: 4px; white-space: nowrap; }
    .table-wrap { overflow: auto; max-height: calc(100vh - 300px); }
    table { width: 100%; min-width: 1060px; border-collapse: collapse; table-layout: fixed; }
    thead th {
      position: sticky;
      top: 0;
      z-index: 2;
      background: #f4edda;
      color: var(--ink-soft);
      text-align: left;
      font-weight: 600;
      font-size: 11.5px;
      letter-spacing: .06em;
      text-transform: uppercase;
      padding: 12px 15px;
      border-bottom: 2px solid var(--gold);
    }
    tbody tr { cursor: pointer; transition: background 120ms ease; }
    tbody tr:nth-child(even) { background: #fbf7ec; }
    tbody tr:hover { background: var(--gold-soft); }
    tbody tr.active { outline: 2px solid var(--gold); outline-offset: -2px; background: var(--gold-soft); }
    td { padding: 13px 15px; border-bottom: 1px solid #f1ead8; vertical-align: middle; overflow-wrap: anywhere; }
    .user-cell { display: grid; gap: 4px; }
    .user-name { font-weight: 500; font-size: 14px; }
    .user-phone { color: var(--muted); font-size: 12px; font-variant-numeric: tabular-nums; }
    .identity-row { display: flex; align-items: center; gap: 6px; flex-wrap: wrap; }
    .position-cell { display: grid; gap: 5px; font-size: 12.5px; }
    .position-line { display: flex; gap: 7px; align-items: baseline; }
    .position-tag { font-size: 10px; font-weight: 600; letter-spacing: .07em; text-transform: uppercase; color: var(--gold-deep); min-width: 26px; }

    .pill {
      display: inline-flex;
      align-items: center;
      gap: 5px;
      min-height: 22px;
      padding: 3px 9px;
      border-radius: 99px;
      font-size: 11.5px;
      font-weight: 400;
      line-height: 1.2;
      border: 1px solid var(--line-strong);
      background: #fff;
      color: var(--ink-soft);
      white-space: nowrap;
    }
    .pill.good { background: var(--green-soft); color: var(--green); border-color: var(--green-line); }
    .pill.warn { background: var(--warn-bg); color: var(--warn); border-color: var(--warn-line); }
    .pill.bad { background: var(--bad-bg); color: var(--bad); border-color: var(--bad-line); }
    .pill.gold { background: var(--gold-soft); color: var(--gold-deep); border-color: #e0cd9f; }
    .pill.ink { background: var(--ink); color: #f2e9d4; border-color: var(--ink); }
    .pill.soft { background: #faf6ec; color: var(--muted); border-color: var(--line); }
    .call-status-cell .pill, .flag-wrap .pill {
      max-width: 100%;
      white-space: normal;
      overflow-wrap: anywhere;
      line-height: 1.25;
      justify-content: flex-start;
    }
    .flag-wrap { display: flex; flex-wrap: wrap; gap: 5px; }
    .call-review-cell { min-width: 0; }
    .review-title { display: block; font-weight: 500; line-height: 1.3; font-size: 12.5px; }
    .review-id { display: block; margin-top: 3px; color: var(--muted); font-size: 10.5px; line-height: 1.25; overflow-wrap: anywhere; font-variant-numeric: tabular-nums; }
    .chevron { color: var(--gold-deep); font-size: 17px; text-align: center; }
    .progress-cell { min-width: 210px; }
    .sparkline { width: 100%; max-width: 250px; height: 44px; display: block; }
    .sparkline text { font-size: 9px; fill: var(--muted); font-family: var(--sans); }

    /* ---------- Drawer ---------- */
    .drawer {
      position: fixed;
      right: 0;
      top: 0;
      width: min(980px, calc(100vw - 250px));
      height: 100vh;
      background: var(--paper);
      box-shadow: var(--shadow);
      border-left: 1px solid var(--line-strong);
      transform: translateX(105%);
      transition: transform 220ms cubic-bezier(.3,.7,.3,1);
      z-index: 50;
      display: grid;
      grid-template-rows: auto 1fr;
    }
    .drawer.open { transform: translateX(0); }
    .drawer-head {
      padding: 20px 24px;
      border-bottom: 1px solid var(--line);
      background: var(--card);
      display: flex;
      align-items: flex-start;
      justify-content: space-between;
      gap: 12px;
    }
    .drawer-head h2 { font-family: var(--serif); font-size: 25px; font-weight: 600; }
    .drawer-body { overflow: auto; padding: 20px 24px 40px; display: grid; gap: 18px; }
    .close-button { border: 1px solid var(--line-strong); background: var(--card); width: 38px; padding: 0; font-size: 20px; border-radius: 99px; }
    .detail-grid { display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); gap: 10px; }
    .kv {
      border: 1px solid var(--line);
      border-radius: 11px;
      background: var(--card);
      padding: 11px 12px;
      min-width: 0;
      box-shadow: 0 1px 0 rgba(45,36,20,.02);
    }
    .kv-label { color: var(--muted); font-size: 10.5px; letter-spacing: .05em; text-transform: uppercase; font-weight: 500; }
    .kv-value { margin-top: 4px; font-weight: 400; overflow-wrap: anywhere; font-size: 13.5px; line-height: 1.35; }
    .section { display: grid; gap: 10px; }
    .section-title-row { display: flex; align-items: center; justify-content: space-between; gap: 10px; flex-wrap: wrap; }
    .section-caption { font-size: 12px; color: var(--muted); }
    .mini-table { display: grid; gap: 8px; }
    .mini-row {
      display: grid;
      grid-template-columns: minmax(250px, 1fr) 90px 120px 88px;
      gap: 10px;
      align-items: center;
      padding: 11px 13px;
      border: 1px solid var(--line);
      border-radius: 11px;
      background: var(--card);
      cursor: pointer;
      transition: border-color 120ms ease, background 120ms ease;
    }
    .mini-row:hover { background: var(--gold-soft); border-color: var(--gold); }
    .conversation-date { font-size: 13.5px; font-weight: 500; }
    .conversation-summary { margin-top: 3px; color: var(--muted); font-size: 12.5px; line-height: 1.4; }
    .conversation-meta { display: grid; gap: 2px; font-size: 13px; font-weight: 400; }
    .mini-label { font-size: 9.5px; text-transform: uppercase; letter-spacing: .07em; color: var(--muted); font-weight: 600; }
    .conversation-action {
      display: inline-flex;
      justify-content: center;
      align-items: center;
      min-height: 30px;
      border-radius: 99px;
      font-size: 12px;
      font-weight: 500;
      border: 1px solid var(--line-strong);
      color: var(--muted);
      background: var(--card);
      padding: 0 12px;
    }
    .conversation-action.open { background: var(--ink); border-color: var(--ink); color: #f2e9d4; }
    .quote {
      background: var(--gold-wash);
      border-left: 3px solid var(--gold);
      padding: 10px 12px;
      border-radius: 6px;
      white-space: pre-wrap;
      overflow-wrap: anywhere;
      font-size: 13px;
      line-height: 1.5;
    }
    .callout {
      border: 1px solid var(--warn-line);
      background: var(--warn-bg);
      color: var(--warn);
      border-radius: 11px;
      padding: 11px 13px;
      font-size: 13px;
      line-height: 1.45;
    }

    /* ---------- Conversation transcript ---------- */
    .conversation-timeline { display: grid; gap: 12px; }
    .timeline-turn { border: 1px solid var(--line); border-radius: 13px; background: var(--card); overflow: hidden; box-shadow: 0 1px 0 rgba(45,36,20,.02); }
    .timeline-turn-head {
      padding: 9px 14px;
      border-bottom: 1px solid var(--line);
      background: #faf5e8;
      display: flex;
      align-items: center;
      justify-content: space-between;
      gap: 10px;
      flex-wrap: wrap;
      font-size: 12px;
    }
    .timings { font-size: 11px; color: var(--muted); font-variant-numeric: tabular-nums; }
    .timeline-pair { display: grid; grid-template-columns: minmax(0, 1fr) minmax(0, 1fr); }
    .timeline-side { padding: 13px; display: grid; gap: 8px; border-right: 1px solid var(--line); min-width: 0; align-content: start; }
    .timeline-side:last-child { border-right: 0; background: var(--gold-wash); }
    .timeline-role { display: flex; align-items: center; justify-content: space-between; gap: 8px; color: var(--muted); font-size: 10.5px; font-weight: 600; letter-spacing: .05em; text-transform: uppercase; }
    .timeline-label { display: inline-flex; align-items: center; gap: 7px; color: var(--ink); font-size: 12.5px; font-weight: 500; letter-spacing: 0; text-transform: none; }
    .timeline-dot { width: 8px; height: 8px; border-radius: 99px; background: var(--green); display: inline-block; }
    .timeline-dot.sabi { background: var(--gold-deep); }
    .timeline-text { font-size: 14px; line-height: 1.5; overflow-wrap: anywhere; white-space: pre-wrap; background: #fffdf8; border: 1px solid var(--line); border-radius: 9px; padding: 10px 11px; }
    .timeline-note { color: var(--muted); font-size: 11.5px; line-height: 1.4; }
    .audio-grid { display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); gap: 10px; }
    .turn-card { border: 1px solid var(--line); border-radius: 13px; background: var(--card); overflow: hidden; }
    .turn-head { padding: 11px 14px; background: #faf5e8; border-bottom: 1px solid var(--line); display: flex; align-items: center; justify-content: space-between; gap: 10px; flex-wrap: wrap; }
    .turn-body { padding: 13px; display: grid; gap: 12px; }
    .turn-columns { display: grid; grid-template-columns: 1fr 1fr; gap: 12px; }
    .feedback-card { border: 1px solid var(--line); border-radius: 13px; background: var(--card); padding: 14px 16px; display: grid; gap: 9px; }
    .feedback-card.gold { border-color: #e0cd9f; background: var(--gold-wash); }

    /* ---------- Curriculum ---------- */
    .curriculum-card { border: 1px solid var(--line); border-radius: 13px; background: var(--card); padding: 15px; display: grid; gap: 10px; }
    .curriculum-card.compact { padding: 17px; }
    .curriculum-map { width: 100%; height: 140px; display: block; }
    .curriculum-map text { font-size: 10px; fill: var(--muted); font-family: var(--sans); }
    .curriculum-map .map-active-label { fill: var(--gold-deep); font-weight: 600; }
    .curriculum-map .map-branch-label { font-size: 9px; }
    .map-caption { display: flex; align-items: center; justify-content: space-between; gap: 10px; flex-wrap: wrap; padding-top: 2px; }
    .map-caption strong { font-size: 13.5px; font-weight: 500; }
    .module-grid { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 10px; }
    details.module { border: 1px solid var(--line); border-radius: 11px; background: var(--card); overflow: hidden; }
    details.module summary { cursor: pointer; padding: 11px 13px; font-weight: 500; display: flex; justify-content: space-between; gap: 10px; align-items: center; }
    details.module summary:hover { background: var(--gold-wash); }
    .module-body { border-top: 1px solid var(--line); padding: 11px 13px; display: grid; gap: 8px; }
    .lesson { display: grid; grid-template-columns: 74px minmax(0, 1fr); gap: 8px; padding: 7px 9px; background: #faf6ec; border: 1px solid var(--line); border-radius: 7px; font-size: 12px; }
    .code { font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace; color: var(--gold-deep); font-weight: 600; font-size: 11px; }

    /* ---------- Overview ---------- */
    .overview-layout { padding: 18px; display: grid; gap: 18px; }
    .command-grid { display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); gap: 12px; }
    .command-card {
      border: 1px solid var(--line);
      border-radius: 13px;
      background: var(--card);
      padding: 15px;
      display: grid;
      gap: 8px;
      min-height: 118px;
      align-content: start;
      box-shadow: 0 1px 0 rgba(45,36,20,.02);
    }
    .command-card strong { font-family: var(--serif); font-size: 17.5px; font-weight: 600; }
    .command-card p { margin: 0; color: var(--muted); font-size: 12.5px; line-height: 1.5; }
    .review-list { display: grid; gap: 8px; }
    .review-card {
      display: grid;
      grid-template-columns: minmax(220px, 1fr) 110px 160px 130px;
      gap: 12px;
      align-items: center;
      padding: 12px 14px;
      border: 1px solid var(--line);
      border-radius: 11px;
      background: var(--card);
      cursor: pointer;
      transition: border-color 120ms ease, background 120ms ease;
    }
    .review-card:hover { border-color: var(--gold); background: var(--gold-soft); }
    .source-grid { display: grid; grid-template-columns: repeat(4, minmax(0, 1fr)); gap: 10px; }
    .source-chip { border: 1px solid var(--line); background: #fbf7ec; border-radius: 11px; padding: 11px 12px; display: grid; gap: 5px; }
    .source-chip strong { font-size: 12.5px; font-weight: 600; }
    .gate-grid { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 12px; }
    .gate-card { border: 1px solid var(--line); border-radius: 13px; background: var(--card); padding: 15px; display: grid; gap: 10px; }
    .gate-card.blocked { border-color: var(--bad-line); background: #fefaf9; }
    .gate-card.pass { border-color: var(--green-line); background: #fbfdf9; }
    .gate-card.watch, .gate-card.not_started { border-color: var(--warn-line); background: #fefcf5; }
    .gate-head { display: flex; align-items: flex-start; justify-content: space-between; gap: 10px; }
    .gate-head h3 { font-family: var(--serif); font-size: 17px; }
    .gate-evidence { margin: 0; padding-left: 18px; color: var(--muted); font-size: 12.5px; line-height: 1.45; }

    .empty, .error {
      color: var(--muted);
      padding: 30px 24px;
      text-align: center;
      border: 1px dashed var(--line-strong);
      border-radius: 11px;
      background: #fbf8ef;
      font-size: 13px;
      line-height: 1.5;
    }
    .error { color: var(--bad); background: var(--bad-bg); border-color: var(--bad-line); }
    .small { font-size: 11.5px; color: var(--muted); line-height: 1.4; }
    .hidden { display: none !important; }
    .skeleton { display: grid; gap: 10px; padding: 18px; }
    .skeleton .bone { height: 52px; border-radius: 11px; background: linear-gradient(90deg, #f2ecdc 25%, #faf5e8 50%, #f2ecdc 75%); background-size: 200% 100%; animation: shimmer 1.2s infinite linear; }
    @keyframes shimmer { to { background-position: -200% 0; } }

    @media (max-width: 1100px) {
      .app { grid-template-columns: 1fr; }
      .sidebar { position: static; height: auto; }
      .nav { grid-template-columns: repeat(4, 1fr); }
      .metrics { grid-template-columns: repeat(2, minmax(0, 1fr)); }
      .detail-grid, .turn-columns, .audio-grid, .module-grid, .command-grid, .source-grid, .gate-grid { grid-template-columns: 1fr; }
      .review-card, .mini-row { grid-template-columns: 1fr; }
      .drawer { width: 100vw; }
      .timeline-pair { grid-template-columns: 1fr; }
      .timeline-side { border-right: 0; border-bottom: 1px solid var(--line); }
      .timeline-side:last-child { border-bottom: 0; }
      .topbar { align-items: flex-start; flex-direction: column; }
      input { min-width: 0; width: 100%; }
    }
  </style>
</head>
<body>
  <div class="app">
    <aside class="sidebar">
      <div class="brand">
        <svg class="brand-spark" viewBox="0 0 24 24" aria-hidden="true">
          <path d="M11 1.4 L13 8.6 L19.4 11 L13 13.4 L11 20.6 L9 13.4 L2.6 11 L9 8.6 Z" fill="#cba868"/>
          <path d="M18.6 15.4 L19.5 18 L22 19 L19.5 20 L18.6 22.6 L17.7 20 L15.2 19 L17.7 18 Z" fill="#e2c88e"/>
        </svg>
        <div>
          <div class="brand-title">Sabi</div>
          <div class="brand-subtitle">Education for Equality</div>
        </div>
      </div>
      <nav class="nav" aria-label="Sabi admin navigation">
        <button id="nav-overview" aria-selected="true"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7"><path d="M3 12l9-8 9 8"/><path d="M5 10v10h14V10"/></svg>Overview<span class="nav-count" id="count-review"></span></button>
        <button id="nav-learners" aria-selected="false"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7"><circle cx="12" cy="8" r="4"/><path d="M4 21c1.5-4 5-6 8-6s6.5 2 8 6"/></svg>Learners<span class="nav-count" id="count-learners"></span></button>
        <button id="nav-kids" aria-selected="false"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7"><circle cx="9" cy="9" r="3.4"/><circle cx="17" cy="10.5" r="2.6"/><path d="M3 20c1-3.4 3.6-5 6-5s5 1.6 6 5"/></svg>Kids<span class="nav-count" id="count-kids"></span></button>
        <button id="nav-calls" aria-selected="false"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7"><path d="M5 4h4l2 5-2.5 1.5a12 12 0 0 0 5 5L15 13l5 2v4a2 2 0 0 1-2 2A16 16 0 0 1 3 6a2 2 0 0 1 2-2z"/></svg>Calls<span class="nav-count" id="count-calls"></span></button>
        <button id="nav-feedback" aria-selected="false"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7"><path d="M21 12a8 8 0 0 1-8 8H4l2-3a8 8 0 1 1 15-5z"/><path d="M9 11h6M9 14h4"/></svg>Feedback<span class="nav-count" id="count-feedback"></span></button>
        <button id="nav-curriculum" aria-selected="false"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7"><path d="M4 5a3 3 0 0 1 3-3h13v18H7a3 3 0 0 0-3 3z"/><path d="M4 20V5"/></svg>Curriculum</button>
        <button id="nav-gates" aria-selected="false"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7"><path d="M12 2l8 4v6c0 5-3.5 8.5-8 10-4.5-1.5-8-5-8-10V6z"/><path d="M9 12l2 2 4-4"/></svg>Launch Gates</button>
      </nav>
      <div class="side-foot">
        <div class="health"><span class="health-dot" id="health-dot"></span><span id="health-text">Checking systems...</span></div>
        <div>Board console &middot; read-only PIN</div>
      </div>
    </aside>
    <div class="content">
      <header class="topbar">
        <div class="topbar-copy">
          <h1 id="page-title">Overview</h1>
          <div class="subtitle" id="page-subtitle">Launch readiness, review queue, and learning operations.</div>
        </div>
        <div class="top-actions">
          <input id="search" placeholder="Search learners or phone numbers" autocomplete="off">
          <button id="export">Download CSV</button>
          <button id="refresh" class="primary">Refresh</button>
        </div>
      </header>
      <main class="workspace">
        <section class="metrics" id="metrics"></section>
        <section class="panel">
          <div class="panel-head">
            <h2 id="panel-title">Launch Control</h2>
            <div class="toolbar" id="view-toolbar"></div>
            <div class="toolbar">
              <span class="range" id="range">0 - 0</span>
              <button id="prev-page">Previous</button>
              <button id="next-page">Next</button>
            </div>
          </div>
          <div class="table-wrap" id="table-wrap"><div class="skeleton"><div class="bone"></div><div class="bone"></div><div class="bone"></div><div class="bone"></div></div></div>
        </section>
      </main>
    </div>
  </div>
  <aside class="drawer" id="drawer" aria-live="polite">
    <div class="drawer-head">
      <div>
        <h2 id="drawer-title">Detail</h2>
        <div id="drawer-subtitle" class="subtitle" style="margin-top:6px; display:flex; gap:6px; flex-wrap:wrap; align-items:center;"></div>
      </div>
      <button id="drawer-close" class="close-button" aria-label="Close">&times;</button>
    </div>
    <div id="drawer-body" class="drawer-body"></div>
  </aside>
  <script>
    const params = new URLSearchParams(window.location.search);
    const accessKey = params.get("key") || params.get("api_key") || params.get("pin") || localStorage.getItem("sabi_admin_key") || "";
    if (accessKey) localStorage.setItem("sabi_admin_key", accessKey);
    const headers = accessKey ? {"X-Admin-Pin": accessKey} : {};
    const authParamName = params.get("api_key") ? "api_key" : "key";
    const state = {
      view: "overview",
      learners: [],
      calls: [],
      feedback: [],
      curriculum: null,
      launchGates: null,
      selectedLearner: "",
      selectedCall: "",
      selectedFeedback: "",
      page: 0,
      pageSize: 50,
      sort: { learners: "recent", kids: "recent", calls: "newest", feedback: "newest" },
      filters: { provider: "", status: "", course: "" },
      localQuery: "",
    };
    // Remember the board member's sort + filter choices across refreshes.
    try { Object.assign(state.sort, JSON.parse(localStorage.getItem("sabi_admin_sort") || "{}")); } catch (e) {}
    try { Object.assign(state.filters, JSON.parse(localStorage.getItem("sabi_admin_filters") || "{}")); } catch (e) {}
    const bootHash = window.location.hash;
    const moduleNames = { 1: "Counting", 2: "Addition", 3: "Subtraction", 4: "Multiply", 5: "Division", 6: "Problems" };
    const literacyModuleNames = { 1: "Sounds", 2: "Words", 3: "Stories", 4: "Grammar", 5: "Sound play" };
    const search = document.getElementById("search");
    const tableWrap = document.getElementById("table-wrap");
    const metrics = document.getElementById("metrics");
    const viewToolbar = document.getElementById("view-toolbar");
    const drawer = document.getElementById("drawer");
    const drawerTitle = document.getElementById("drawer-title");
    const drawerSubtitle = document.getElementById("drawer-subtitle");
    const drawerBody = document.getElementById("drawer-body");

    /* ---------------- formatting helpers ---------------- */
    function escapeHtml(value) {
      return String(value ?? "").replace(/[&<>"']/g, ch => ({
        "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;"
      }[ch]));
    }
    function fmtSeconds(seconds) {
      const n = Number(seconds || 0);
      if (!n) return "0s";
      const m = Math.floor(n / 60);
      const s = Math.round(n % 60);
      return m ? `${m}m ${s}s` : `${s}s`;
    }
    function fmtDate(epoch) {
      const n = Number(epoch || 0);
      if (!n) return "";
      return new Date(n * 1000).toLocaleString([], {month: "short", day: "numeric", hour: "numeric", minute: "2-digit"});
    }
    function fmtTimestamp(value) {
      if (!value) return "No date saved";
      const date = typeof value === "number" ? new Date(value * 1000) : new Date(value);
      if (Number.isNaN(date.getTime())) return String(value);
      return date.toLocaleString([], {month: "short", day: "numeric", year: "numeric", hour: "numeric", minute: "2-digit"});
    }
    function greetingWord() {
      const h = new Date().getHours();
      if (h < 12) return "Good morning";
      if (h < 17) return "Good afternoon";
      return "Good evening";
    }
    function displayPhone(record) {
      const phone = record && (record.display_phone || record.phone_number_normalized || record.phone_number || (record.calling || {}).last_phone_number);
      return phone || "Phone not captured yet";
    }
    function phoneNote(record) {
      const label = (record && record.identity_label) || "";
      if (!label) return "";
      const status = (record && record.identity_status) || "";
      const kind = status === "named" ? "good" : (status === "phone_pending_name" ? "soft" : "warn");
      return pill(label, kind);
    }
    function learnerName(record) {
      const direct = record && record.display_name;
      if (direct) return direct;
      const name = String((record && record.name) || "").trim();
      if (name && !["unnamed learner", "unknown", "none", "null"].includes(name.toLowerCase())) return name;
      const phone = displayPhone(record);
      const digits = phone.replace(/\\D/g, "");
      if (digits) return `Learner ${digits.slice(-4)}`;
      const id = String((record && (record.id || record.browser_id)) || "pending");
      return `Profile ${id.slice(0, 8)}`;
    }
    function digitsOnly(value) {
      return String(value || "").replace(/\\D/g, "");
    }
    function learnerForCall(call) {
      if (!call) return null;
      const studentId = String(call.student_id || "");
      if (studentId) {
        const byId = state.learners.find(learner => String(learner.id || "") === studentId);
        if (byId) return byId;
      }
      const callDigits = digitsOnly(call.phone_number);
      if (!callDigits) return null;
      return state.learners.find(learner => {
        const learnerDigits = digitsOnly(displayPhone(learner));
        return learnerDigits && (
          learnerDigits === callDigits ||
          learnerDigits.endsWith(callDigits.slice(-10)) ||
          callDigits.endsWith(learnerDigits.slice(-10))
        );
      }) || null;
    }
    function callLearnerName(call) {
      const learner = learnerForCall(call);
      if (learner) return learnerName(learner);
      const digits = digitsOnly(call && call.phone_number);
      return digits ? `Caller ${digits.slice(-4)}` : "Caller awaiting match";
    }
    function callDisplayPhone(call) {
      const learner = learnerForCall(call);
      return (call && call.phone_number) || (learner && displayPhone(learner)) || "Phone not captured yet";
    }
    function callerCell(call) {
      return `<div class="user-cell"><span class="user-name">${escapeHtml(callLearnerName(call))}</span><span class="user-phone">${escapeHtml(callDisplayPhone(call))}</span></div>`;
    }
    function isChildProfile(record) {
      const type = String(
        (record && (record.participant_type || record.profile_type || record.learner_type || record.kind)) || ""
      ).toLowerCase();
      const school = String((record && (record.school_status || record.enrollment_status || record.child_status)) || "").toLowerCase();
      const hasPilotFields = Boolean(
        record && (
          record.consent_status ||
          record.assent_status ||
          record.caregiver_phone ||
          record.network ||
          record.prepilot_status ||
          record.is_child
        )
      );
      if (type.includes("adult") || type.includes("tester") || type.includes("staff")) return false;
      if (type.includes("child") || type.includes("student") || school.includes("school") || hasPilotFields) return true;
      return false;
    }
    function kidItems() {
      return state.learners.filter(isChildProfile);
    }
    function preview(text, limit = 80) {
      const clean = String(text || "").replace(/\\s+/g, " ").trim();
      return clean.length > limit ? clean.slice(0, limit - 3) + "..." : clean;
    }
    function audioUrl(path) {
      if (!path) return "";
      const separator = path.includes("?") ? "&" : "?";
      return accessKey ? `${path}${separator}${authParamName}=${encodeURIComponent(accessKey)}` : path;
    }
    function pill(text, kind = "") {
      return `<span class="pill ${kind}">${escapeHtml(text)}</span>`;
    }
    function safeModule(stateObj) {
      return Math.max(1, Math.min(6, Number((stateObj || {}).current_module || 1)));
    }
    function scaffoldDepth(stateObj) {
      return Math.max(0, Math.min(3, Number((stateObj || {}).scaffold_depth || 0)));
    }

    /* ---------------- human-language dictionaries ---------------- */
    function callFlagLabel(value) {
      const key = String(value || "").trim();
      const labels = {
        very_short_call: "Very short call",
        short_call: "Short call",
        ended_before_minimum_lesson_window: "Ended too soon",
        no_child_turns: "No child speech",
        no_sabi_turns: "Sabi never spoke",
        no_usable_speech: "No usable speech",
        carrier_or_voicemail_audio: "Voicemail or carrier message",
        server_exception: "Server issue",
        channel_closed: "Call closed",
        sabi_wrap_up: "Lesson completed",
        max_call_seconds: "Reached the time limit",
        normal_loop_complete: "Completed",
        no_utterance: "Caller went quiet",
        asterisk_sent_hangup: "Caller hung up",
        audiosocket_closed_by_asterisk_or_network: "Call ended",
        channel_closed_during_greeting: "Dropped during greeting",
        channel_closed_during_playback: "Dropped while Sabi spoke",
        channel_closed_before_playback: "Dropped before Sabi spoke",
        channel_closed_waiting_for_speech: "Dropped while listening",
        channel_closed_waiting_for_optional_speech: "Dropped during feedback window",
        channel_closed_collecting_utterance: "Dropped mid-answer",
        Success: "Success",
      };
      if (labels[key]) return labels[key];
      if (key.startsWith("exception:")) return "Server issue";
      if (key.startsWith("dialstatus_")) return `Network: ${key.slice(11).replaceAll("_", " ")}`;
      if (key.startsWith("hangup_cause_")) return `Hangup code ${key.slice(13)}`;
      return key.replaceAll("_", " ");
    }
    function turnFlagLabel(value) {
      const key = String(value || "").trim();
      const labels = {
        barge_in: "Child jumped in",
        retry_prompt: "Asked to repeat",
        low_confidence: "Unclear audio, accepted",
        usable_low_confidence: "Unclear but usable",
        low_confidence_rejected: "Too unclear, asked again",
        empty_or_hallucinated_transcript: "Nothing usable heard",
        transcript_normalized: "Transcript cleaned up",
        literacy_stt: "Literacy listening mode",
        numeric_stt: "Number listening mode",
        literacy_short_answer: "Short literacy answer",
        ignored_filler: "Ignored a filler sound",
        carrier_or_voicemail_audio: "Voicemail detected",
      };
      return labels[key] || key.replaceAll("_", " ");
    }
    function turnFlagKind(flag) {
      const key = String(flag || "");
      if (key.includes("rejected") || key.includes("hallucinated") || key.includes("carrier")) return "warn";
      if (key.includes("low") || key.includes("retry")) return "warn";
      return "soft";
    }
    function providerLabel(value) {
      const labels = {
        groq: "Groq Whisper",
        intron: "Intron",
        local_whisper: "Local Whisper",
        local_literacy_salvage: "Literacy salvage",
      };
      const key = String(value || "").trim();
      return labels[key] || (key ? key.replaceAll("_", " ") : "");
    }
    const REVIEW_STATUS_LABELS = {
      unreviewed: "Not reviewed",
      reviewed: "Reviewed",
      follow_up: "Needs follow-up",
      safety_escalation: "Safety escalation",
    };
    function reviewStatusOf(call) {
      const s = String((call && call.review_status) || "unreviewed");
      return REVIEW_STATUS_LABELS[s] ? s : "unreviewed";
    }
    function reviewStatusKind(status) {
      if (status === "reviewed") return "good";
      if (status === "safety_escalation") return "bad";
      if (status === "follow_up") return "warn";
      return "soft";
    }
    function reviewStatusPill(call) {
      const s = reviewStatusOf(call);
      if (s === "unreviewed") return "";
      return pill(REVIEW_STATUS_LABELS[s], reviewStatusKind(s));
    }
    function providerPills(call) {
      const providers = (call && call.stt_providers_used) || [];
      if (!providers.length) return pill("Not recorded", "soft");
      return providers.map(p => pill(providerLabel(p), p === "intron" ? "gold" : "soft")).join(" ");
    }
    function timingsLine(timings) {
      const t = timings || {};
      const parts = [];
      if (t.stt_seconds) parts.push(`Heard in ${Number(t.stt_seconds).toFixed(1)}s`);
      if (t.llm_seconds) parts.push(`Thought in ${Number(t.llm_seconds).toFixed(1)}s`);
      if (t.tts_seconds) parts.push(`Spoke in ${Number(t.tts_seconds).toFixed(1)}s`);
      if (t.turn_total_seconds) parts.push(`Total ${Number(t.turn_total_seconds).toFixed(1)}s`);
      return parts.join(" &middot; ");
    }

    /* ---------------- toast ---------------- */
    let toastTimer;
    function toast(message, kind) {
      let el = document.getElementById("toast");
      if (!el) {
        el = document.createElement("div");
        el.id = "toast";
        el.style.cssText = "position:fixed;left:50%;bottom:28px;transform:translateX(-50%);z-index:80;padding:11px 18px;border-radius:99px;font-size:13px;font-weight:500;box-shadow:0 10px 30px rgba(45,36,20,.22);border:1px solid;max-width:min(560px,90vw);text-align:center;transition:opacity 180ms ease,transform 180ms ease;";
        document.body.appendChild(el);
      }
      const palette = kind === "bad"
        ? "background:#fbeeec;color:#b42318;border-color:#f0c1ba;"
        : kind === "warn"
          ? "background:#faf0da;color:#9b5b00;border-color:#ecd3a2;"
          : "background:#1b1610;color:#f1e6cd;border-color:#1b1610;";
      el.style.cssText += palette;
      el.textContent = message;
      el.style.opacity = "1";
      el.style.transform = "translateX(-50%) translateY(0)";
      clearTimeout(toastTimer);
      toastTimer = setTimeout(() => { el.style.opacity = "0"; el.style.transform = "translateX(-50%) translateY(8px)"; }, 3600);
    }

    /* ---------------- data loading ---------------- */
    async function getJson(path) {
      const res = await fetch(path, { headers });
      if (!res.ok) throw new Error(`${res.status} ${res.statusText}`);
      return res.json();
    }
    async function postForm(path, fields) {
      const body = new URLSearchParams(fields || {});
      const res = await fetch(path, { method: "POST", headers, body });
      if (res.status === 401 || res.status === 403) {
        const e = new Error("needs_full_key"); e.code = 401; throw e;
      }
      if (!res.ok) throw new Error(`${res.status} ${res.statusText}`);
      return res.json();
    }
    async function setReviewStatus(callUuid, status) {
      try {
        const updated = await postForm(`/admin/calls/${encodeURIComponent(callUuid)}/review-status`, { status });
        const idx = state.calls.findIndex(c => c.call_uuid === callUuid);
        if (idx >= 0) state.calls[idx] = { ...state.calls[idx], review_status: updated.review_status, reviewed_at: updated.reviewed_at };
        toast(status === "unreviewed" ? "Marked as not reviewed." : `Marked ${REVIEW_STATUS_LABELS[status].toLowerCase()}.`, status === "safety_escalation" ? "bad" : "");
        render();
        if (state.selectedCall === callUuid) openCall(callUuid);
      } catch (err) {
        if (err.code === 401) toast("To change review status, open the console with your full admin key (not the read-only PIN).", "warn");
        else toast(`Could not save: ${err.message}`, "bad");
      }
    }
    async function compareStt(callUuid, turnIndex, buttonEl) {
      const target = document.getElementById(`stt-compare-${turnIndex}`);
      if (target) target.innerHTML = `<div class="small">Replaying this clip through both speech systems...</div>`;
      if (buttonEl) buttonEl.disabled = true;
      try {
        const data = await postForm(`/admin/calls/${encodeURIComponent(callUuid)}/turns/${turnIndex}/stt-compare`, {});
        if (target) target.innerHTML = sttCompareHtml(data);
      } catch (err) {
        if (err.code === 401) { if (target) target.innerHTML = `<div class="small">This needs the full admin key. Open the console with your full key to run the Groq-vs-Intron comparison.</div>`; }
        else if (target) target.innerHTML = `<div class="small">Could not compare: ${escapeHtml(err.message)}</div>`;
      } finally {
        if (buttonEl) buttonEl.disabled = false;
      }
    }
    function sttCompareHtml(data) {
      const b = data.baseline || {};
      const i = data.intron || {};
      const note = data.intron_key_present
        ? (data.match ? "Both systems heard the same thing." : "The two systems disagreed — worth a listen.")
        : "Intron key is not set yet, so the Intron lane fell back to Groq/Whisper. Set INTRON_API_KEY to run a real comparison.";
      return `<div class="compare-grid">
        <div class="compare-col"><div class="mini-label">Production (${escapeHtml(providerLabel(b.provider) || "baseline")})</div><div class="compare-text">${escapeHtml(b.text || "(nothing heard)")}</div><div class="small">Confidence ${escapeHtml(b.confidence ?? "?")} &middot; ${escapeHtml(b.latency_ms ?? "?")}ms</div></div>
        <div class="compare-col"><div class="mini-label">Intron lane (${escapeHtml(providerLabel(i.provider) || "test")})</div><div class="compare-text">${escapeHtml(i.text || "(nothing heard)")}</div><div class="small">Confidence ${escapeHtml(i.confidence ?? "?")} &middot; ${escapeHtml(i.latency_ms ?? "?")}ms</div></div>
        <div class="compare-note ${data.intron_key_present ? (data.match ? "good" : "warn") : "soft"}">${escapeHtml(note)}</div>
      </div>`;
    }
    async function checkHealth() {
      const dot = document.getElementById("health-dot");
      const text = document.getElementById("health-text");
      try {
        const health = await getJson("/health");
        const ok = health && health.status === "ok";
        dot.className = `health-dot ${ok ? "ok" : "down"}`;
        text.textContent = ok ? "Live systems healthy" : "Systems degraded";
      } catch (err) {
        dot.className = "health-dot down";
        text.textContent = "Cannot reach Sabi API";
      }
    }
    async function loadData() {
      tableWrap.innerHTML = `<div class="skeleton"><div class="bone"></div><div class="bone"></div><div class="bone"></div><div class="bone"></div></div>`;
      const q = encodeURIComponent(search.value.trim());
      try {
        const [learners, calls, feedback, curriculum, launchGates] = await Promise.all([
          getJson(`/admin/learners?limit=100${q ? `&q=${q}` : ""}`),
          getJson(`/admin/calls?limit=100${q ? `&q=${q}` : ""}`),
          getJson(`/admin/feedback?limit=100${q ? `&q=${q}` : ""}`).catch(() => ({ items: [] })),
          state.curriculum ? Promise.resolve(state.curriculum) : getJson("/admin/curriculum-map"),
          getJson("/admin/launch-gates").catch(() => null),
        ]);
        state.learners = learners.items || [];
        state.calls = calls.items || [];
        state.feedback = feedback.items || [];
        state.curriculum = curriculum;
        state.launchGates = launchGates;
        state.page = 0;
        render();
        checkHealth();
      } catch (err) {
        tableWrap.innerHTML = `<div class="error">Could not load Sabi admin data: ${escapeHtml(err.message)}<br><span class="small">Check the PIN in your link, then press Refresh.</span></div>`;
      }
    }

    /* ---------------- sorting + filtering ---------------- */
    function localFilter(items, fields) {
      const q = state.localQuery.trim().toLowerCase();
      if (!q) return items;
      return items.filter(item => fields.some(fn => String(fn(item) || "").toLowerCase().includes(q)));
    }
    function sortedLearners(list) {
      const key = state.sort[state.view === "kids" ? "kids" : "learners"];
      const items = [...list];
      if (key === "sessions") items.sort((a, b) => Number(b.total_sessions || 0) - Number(a.total_sessions || 0));
      else if (key === "help") items.sort((a, b) => Number(b.total_wrong || 0) - Number(a.total_wrong || 0));
      else if (key === "name") items.sort((a, b) => learnerName(a).localeCompare(learnerName(b)));
      else items.sort((a, b) => String(b.updated_at || "").localeCompare(String(a.updated_at || "")));
      return items;
    }
    function visibleLearners() {
      let items = state.view === "kids" ? kidItems() : state.learners;
      if (state.filters.course) {
        items = items.filter(item => String((item.effective_state || {}).course || "numeracy") === state.filters.course);
      }
      items = localFilter(items, [learnerName, displayPhone, item => (item.effective_state || {}).active_skill]);
      return sortedLearners(items);
    }
    function sortedCalls(list) {
      const key = state.sort.calls;
      const items = [...list];
      if (key === "oldest") items.sort((a, b) => Number(a.created_at || 0) - Number(b.created_at || 0));
      else if (key === "longest") items.sort((a, b) => Number(b.duration_seconds || 0) - Number(a.duration_seconds || 0));
      else if (key === "shortest") items.sort((a, b) => Number(a.duration_seconds || 0) - Number(b.duration_seconds || 0));
      else if (key === "flagged") items.sort((a, b) => ((b.quality_flags || []).length - (a.quality_flags || []).length) || (Number(b.created_at || 0) - Number(a.created_at || 0)));
      else items.sort((a, b) => Number(b.created_at || 0) - Number(a.created_at || 0));
      return items;
    }
    function visibleCalls() {
      let items = state.calls;
      if (state.filters.provider) {
        items = items.filter(call => ((call.stt_providers_used || []).includes(state.filters.provider)));
      }
      if (state.filters.status === "flagged") items = items.filter(call => (call.quality_flags || []).length);
      if (state.filters.status === "clean") items = items.filter(call => !(call.quality_flags || []).length);
      items = localFilter(items, [callLearnerName, callDisplayPhone, call => call.call_uuid, call => (call.quality_flags || []).join(" ")]);
      return sortedCalls(items);
    }
    function visibleFeedback() {
      let items = [...state.feedback];
      items = localFilter(items, [f => f.phone_number, f => f.redacted_transcript, f => f.call_uuid]);
      items.sort((a, b) => String(b.created_at || "").localeCompare(String(a.created_at || "")));
      return items;
    }

    /* ---------------- shell rendering ---------------- */
    function savePrefs() {
      try {
        localStorage.setItem("sabi_admin_sort", JSON.stringify(state.sort));
        localStorage.setItem("sabi_admin_filters", JSON.stringify(state.filters));
      } catch (e) {}
    }
    function writeHash() {
      let target = state.view;
      if (state.selectedLearner) target = `learners/${encodeURIComponent(state.selectedLearner)}`;
      else if (state.selectedCall) target = `calls/${encodeURIComponent(state.selectedCall)}`;
      const next = `#${target}`;
      if (window.location.hash !== next) history.replaceState(null, "", next);
    }
    function applyHashFrom(hash) {
      const raw = decodeURIComponent(String(hash || "").replace(/^#\\/?/, ""));
      if (!raw) return;
      const [seg, id] = raw.split("/");
      if (id && seg === "learners") { setView("learners"); openLearner(id); return; }
      if (id && seg === "calls") { setView("calls"); openCall(id); return; }
      const views = ["overview", "learners", "kids", "calls", "feedback", "curriculum", "gates"];
      if (views.includes(seg)) setView(seg);
    }
    function closeDrawer() {
      drawer.classList.remove("open");
      state.selectedLearner = "";
      state.selectedCall = "";
      writeHash();
    }
    function setView(view) {
      state.view = view;
      state.page = 0;
      state.localQuery = search.value;
      state.selectedLearner = "";
      state.selectedCall = "";
      drawer.classList.remove("open");
      ["overview", "learners", "kids", "calls", "feedback", "curriculum", "gates"].forEach(name => {
        const el = document.getElementById(`nav-${name}`);
        if (el) el.setAttribute("aria-selected", String(view === name));
      });
      render();
    }
    function render() {
      savePrefs();
      writeHash();
      renderHeader();
      renderMetrics();
      renderToolbar();
      renderNavCounts();
      if (state.view === "overview") renderOverviewDashboard();
      if (state.view === "gates") renderLaunchGatesView();
      if (state.view === "learners") renderLearnersTable();
      if (state.view === "kids") renderKidsTable();
      if (state.view === "calls") renderCallsTable();
      if (state.view === "feedback") renderFeedbackList();
      if (state.view === "curriculum") renderCurriculumView();
    }
    function renderHeader() {
      const titles = {
        overview: [`${greetingWord()}, Naomi`, "Here is how the children are doing and what needs your eyes today.", "Launch Control"],
        gates: ["Launch Gates", "Evidence gates for adult canaries, child canaries, and pre-pilot launch.", "Launch Gate Report"],
        learners: ["Learners", "Every learner, their level, their journey, and their recent calls.", "Learner Database"],
        kids: ["Kids", "Pre-pilot child profiles: consent, call readiness, and learning evidence.", "Kids Backend"],
        calls: ["Calls", "Every phone lesson with audio, transcripts, and quality evidence.", "Voice Sessions"],
        feedback: ["Feedback", "Open voice notes left by testers, caregivers, and children after calls.", "Voice Notes"],
        curriculum: ["Curriculum", "The full learning path, lesson by lesson, and the support rules.", "Curriculum Map"],
      };
      const [title, subtitle, panel] = titles[state.view];
      document.getElementById("page-title").textContent = title;
      document.getElementById("page-subtitle").textContent = subtitle;
      document.getElementById("panel-title").textContent = panel;
      search.placeholder = state.view === "calls" ? "Search calls, names, or numbers" : "Search learners or phone numbers";
    }
    function renderNavCounts() {
      const set = (id, value) => { const el = document.getElementById(id); if (el) el.textContent = value || ""; };
      set("count-learners", state.learners.length);
      set("count-kids", kidItems().length);
      set("count-calls", state.calls.length);
      set("count-feedback", state.feedback.length);
      set("count-review", reviewQueueCalls().length || "");
    }
    function renderMetrics() {
      const learnerCount = state.learners.length;
      const childCount = kidItems().length;
      const callCount = state.calls.length;
      const totalMinutes = state.calls.reduce((sum, call) => sum + Number(call.duration_seconds || 0), 0) / 60;
      const flaggedCalls = state.calls.filter(call => (call.quality_flags || []).length).length;
      const launchStatus = (state.launchGates && state.launchGates.overall_status) || "loading";
      metrics.innerHTML = [
        metric("Learners", learnerCount, "profiles on record"),
        metric("Kids", childCount, "pre-pilot children"),
        metric("Recent calls", callCount, "in this window"),
        metric("Learning minutes", totalMinutes.toFixed(0), "across recent calls"),
        metric("Needs review", flaggedCalls, flaggedCalls ? "calls flagged" : "all clear"),
        metric("Launch status", launchStatus.replaceAll("_", " "), "from evidence gates"),
      ].join("");
    }
    function metric(label, value, note) {
      return `<div class="metric"><div class="metric-label">${escapeHtml(label)}</div><div class="metric-value">${escapeHtml(value)}</div><div class="metric-note">${escapeHtml(note || "")}</div></div>`;
    }
    function renderToolbar() {
      if (state.view === "calls") {
        const providers = [...new Set(state.calls.flatMap(call => call.stt_providers_used || []))];
        viewToolbar.innerHTML = `
          <label class="control">Sort
            <select id="sort-select">
              <option value="newest">Newest first</option>
              <option value="oldest">Oldest first</option>
              <option value="longest">Longest first</option>
              <option value="shortest">Shortest first</option>
              <option value="flagged">Flagged first</option>
            </select>
          </label>
          <label class="control">Heard by
            <select id="provider-select">
              <option value="">All providers</option>
              ${providers.map(p => `<option value="${escapeHtml(p)}">${escapeHtml(providerLabel(p))}</option>`).join("")}
            </select>
          </label>
          <label class="control">Status
            <select id="status-select">
              <option value="">All calls</option>
              <option value="flagged">Needs review</option>
              <option value="clean">Clean</option>
            </select>
          </label>`;
        document.getElementById("sort-select").value = state.sort.calls;
        document.getElementById("provider-select").value = state.filters.provider;
        document.getElementById("status-select").value = state.filters.status;
        document.getElementById("sort-select").addEventListener("change", e => { state.sort.calls = e.target.value; state.page = 0; render(); });
        document.getElementById("provider-select").addEventListener("change", e => { state.filters.provider = e.target.value; state.page = 0; render(); });
        document.getElementById("status-select").addEventListener("change", e => { state.filters.status = e.target.value; state.page = 0; render(); });
      } else if (state.view === "learners" || state.view === "kids") {
        const sortKey = state.view === "kids" ? "kids" : "learners";
        viewToolbar.innerHTML = `
          <label class="control">Sort
            <select id="sort-select">
              <option value="recent">Recently active</option>
              <option value="sessions">Most sessions</option>
              <option value="help">Needs help first</option>
              <option value="name">Name A to Z</option>
            </select>
          </label>
          <label class="control">Course
            <select id="course-select">
              <option value="">All courses</option>
              <option value="numeracy">Numeracy</option>
              <option value="literacy">Literacy</option>
            </select>
          </label>`;
        document.getElementById("sort-select").value = state.sort[sortKey];
        document.getElementById("course-select").value = state.filters.course;
        document.getElementById("sort-select").addEventListener("change", e => { state.sort[sortKey] = e.target.value; state.page = 0; render(); });
        document.getElementById("course-select").addEventListener("change", e => { state.filters.course = e.target.value; state.page = 0; render(); });
      } else if (state.view === "feedback") {
        viewToolbar.innerHTML = `<label class="control">Sort
          <select id="sort-select"><option value="newest">Newest first</option></select></label>`;
      } else {
        viewToolbar.innerHTML = "";
      }
    }
    function pageSlice(items) {
      const start = state.page * state.pageSize;
      return items.slice(start, start + state.pageSize);
    }
    function updateRange(total) {
      const start = total ? state.page * state.pageSize + 1 : 0;
      const end = Math.min(total, (state.page + 1) * state.pageSize);
      document.getElementById("range").textContent = `${start} - ${end} of ${total}`;
      document.getElementById("prev-page").disabled = state.page <= 0;
      document.getElementById("next-page").disabled = end >= total;
    }
    function staticRange(label) {
      document.getElementById("range").textContent = label;
      document.getElementById("prev-page").disabled = true;
      document.getElementById("next-page").disabled = true;
    }

    /* ---------------- overview ---------------- */
    function reviewQueueCalls() {
      return state.calls.filter(call => {
        const flags = call.quality_flags || [];
        return flags.length || Number(call.user_turns || 0) === 0 || Number(call.duration_seconds || 0) < 60;
      }).slice(0, 8);
    }
    function learnersNeedingAttention() {
      return state.learners.filter(learner => {
        const current = learner.effective_state || {};
        const calling = learner.calling || {};
        return scaffoldDepth(current) || Number(current.wrong_streak || 0) >= 3 || Number(calling.recent_call_count || 0) === 0;
      }).slice(0, 8);
    }
    function learnersToCelebrate() {
      return state.learners.filter(learner => {
        const current = learner.effective_state || {};
        return Number(current.correct_streak || 0) >= 2 && !scaffoldDepth(current);
      }).slice(0, 6);
    }
    function learnerActionLabel(learner) {
      const current = learner.effective_state || {};
      const calling = learner.calling || {};
      if (isChildProfile(learner) && !(learner.consent_status || learner.consent_recorded)) return "Get consent";
      if (scaffoldDepth(current)) return "Review support path";
      if (Number(current.wrong_streak || 0) >= 3) return "Check teaching move";
      if (Number(calling.recent_call_count || 0) === 0) return "Needs first call";
      return "Monitor";
    }
    function callActionLabel(call) {
      const flags = call.quality_flags || [];
      if (flags.includes("no_child_turns") || Number(call.user_turns || 0) === 0) return "Listen for audio";
      if (flags.includes("ended_before_minimum_lesson_window") || Number(call.duration_seconds || 0) < 60) return "Check why ended";
      if (!Number(call.turn_count || 0)) return "Full-call only";
      return "Review turns";
    }
    function statusKind(status) {
      if (status === "pass") return "good";
      if (status === "blocked") return "bad";
      if (status === "watch" || status === "not_started") return "warn";
      return "soft";
    }
    function renderOverviewDashboard() {
      staticRange("Board view");
      const reviewCalls = reviewQueueCalls();
      const attentionLearners = learnersNeedingAttention();
      const celebrate = learnersToCelebrate();
      const feedbackCount = state.feedback.length;
      const gateReport = state.launchGates || {};
      tableWrap.innerHTML = `<div class="overview-layout">
        <div class="command-grid">
          <div class="command-card">
            ${pill(reviewCalls.length ? `${reviewCalls.length} to review` : "Clear", reviewCalls.length ? "warn" : "good")}
            <strong>Call evidence</strong>
            <p>Open flagged calls first. Every review shows the child audio, what Sabi heard, the cleaned lesson text, Sabi's reply, the exact TTS text, and why the call ended.</p>
          </div>
          <div class="command-card">
            ${pill(feedbackCount ? `${feedbackCount} voice note${feedbackCount === 1 ? "" : "s"}` : "No notes yet", feedbackCount ? "gold" : "soft")}
            <strong>Feedback notes</strong>
            <p>Testers and families can leave an open voice note after each call. Listen to them in the Feedback tab; each note links back to its call.</p>
          </div>
          <div class="command-card">
            ${pill((gateReport.overall_status || "loading").replaceAll("_", " "), statusKind(gateReport.overall_status))}
            <strong>Launch posture</strong>
            <p>${escapeHtml(gateReport.summary || "The launch-gate report shows whether Sabi should keep testing, proceed, or pause.")}</p>
          </div>
        </div>
        <div class="section">
          <div class="section-title-row">
            <h3>Review Queue</h3>
            <span class="section-caption">Flagged, short, or speech-light calls &mdash; newest first</span>
          </div>
          <div class="review-list">
            ${reviewCalls.length ? reviewCalls.map(call => `<div class="review-card" data-call="${escapeHtml(call.call_uuid)}">
              <div>${callerCell(call)}<div class="conversation-summary">${escapeHtml(callFlagLabel((call.quality_flags || [])[0] || call.end_reason || "Review"))}</div></div>
              <div class="conversation-meta"><span class="mini-label">Length</span>${fmtSeconds(call.duration_seconds)}</div>
              <div class="conversation-meta"><span class="mini-label">Evidence</span>${escapeHtml(call.turn_count || 0)} clips &middot; ${escapeHtml(call.user_turns || 0)} child turns</div>
              <div>${pill(callActionLabel(call), (call.quality_flags || []).length ? "warn" : "soft")}</div>
            </div>`).join("") : `<div class="empty">Nothing waiting for review. Every recent call looks healthy.</div>`}
          </div>
        </div>
        <div class="section">
          <div class="section-title-row">
            <h3>Learners Needing Attention</h3>
            <span class="section-caption">No first call yet, on a support branch, or repeated misses</span>
          </div>
          <div class="review-list">
            ${attentionLearners.length ? attentionLearners.map(learner => `<div class="review-card" data-learner="${escapeHtml(learner.id)}">
              <div><div class="user-name">${escapeHtml(learnerName(learner))}</div><div class="user-phone">${escapeHtml(displayPhone(learner))}</div></div>
              <div class="conversation-meta"><span class="mini-label">Calls</span>${escapeHtml((learner.calling || {}).recent_call_count || 0)}</div>
              <div class="conversation-meta"><span class="mini-label">Learning</span>${escapeHtml(learner.total_correct || 0)} correct &middot; ${escapeHtml(learner.total_wrong || 0)} needs help</div>
              <div>${pill(learnerActionLabel(learner), "warn")}</div>
            </div>`).join("") : `<div class="empty">No learners need attention right now.</div>`}
          </div>
        </div>
        ${celebrate.length ? `<div class="section">
          <div class="section-title-row">
            <h3>Worth Celebrating</h3>
            <span class="section-caption">Learners on a correct streak and moving up</span>
          </div>
          <div class="review-list">
            ${celebrate.map(learner => `<div class="review-card" data-learner="${escapeHtml(learner.id)}">
              <div><div class="user-name">${escapeHtml(learnerName(learner))}</div><div class="user-phone">${escapeHtml(displayPhone(learner))}</div></div>
              <div class="conversation-meta"><span class="mini-label">Streak</span>${escapeHtml((learner.effective_state || {}).correct_streak || 0)} correct</div>
              <div class="conversation-meta"><span class="mini-label">Position</span>Module ${escapeHtml((learner.effective_state || {}).current_module ?? "?")}</div>
              <div>${pill("Moving up", "good")}</div>
            </div>`).join("")}
          </div>
        </div>` : ""}
        <div class="section">
          <div class="section-title-row">
            <h3>Backend Model We Are Copying</h3>
            <span class="section-caption">Learning evidence + AI launch evidence</span>
          </div>
          <div class="source-grid">
            <div class="source-chip"><strong>Khan style</strong><span class="small">Student rows, session evidence, responses, completion, export.</span></div>
            <div class="source-chip"><strong>Lexia style</strong><span class="small">Who needs help, who needs more time, who to celebrate, recommended next action.</span></div>
            <div class="source-chip"><strong>IXL style</strong><span class="small">Diagnostics, skills practiced, questions answered, cohort progress.</span></div>
            <div class="source-chip"><strong>OpenAI style</strong><span class="small">Do not launch without evals, red-team results, launch gates, monitoring, and rollback.</span></div>
          </div>
        </div>
      </div>`;
      tableWrap.querySelectorAll("[data-call]").forEach(row => row.addEventListener("click", () => openCall(row.dataset.call)));
      tableWrap.querySelectorAll("[data-learner]").forEach(row => row.addEventListener("click", () => openLearner(row.dataset.learner)));
    }

    /* ---------------- launch gates ---------------- */
    function renderLaunchGatesView() {
      staticRange("Evidence gates");
      const report = state.launchGates || {};
      const gates = report.gates || [];
      const reportMetrics = report.metrics || {};
      const config = report.config || {};
      tableWrap.innerHTML = `<div class="overview-layout">
        <div class="command-grid">
          <div class="command-card">
            ${pill((report.overall_status || "loading").replaceAll("_", " "), statusKind(report.overall_status))}
            <strong>Overall launch posture</strong>
            <p>${escapeHtml(report.summary || "Loading launch-gate evidence.")}</p>
          </div>
          <div class="command-card">
            ${pill(`${reportMetrics.recent_calls || 0} calls`, "soft")}
            <strong>Evidence window</strong>
            <p>${escapeHtml(reportMetrics.calls_with_turn_evidence || 0)} calls have per-turn evidence; ${escapeHtml(reportMetrics.flagged_calls || 0)} calls are flagged for review.</p>
          </div>
          <div class="command-card">
            ${pill(config.intron_api_key_present ? "Intron key present" : "Intron key missing", config.intron_api_key_present ? "good" : "bad")}
            <strong>Provider canary</strong>
            <p>Production stays on AudioSocket 9019. The test provider canary stays isolated on 9020 until evidence beats baseline.</p>
          </div>
        </div>
        <div class="gate-grid">
          ${gates.length ? gates.map(gateCard).join("") : `<div class="empty">No launch-gate report loaded.</div>`}
        </div>
      </div>`;
    }
    function gateCard(gate) {
      const status = gate.status || "not_started";
      return `<div class="gate-card ${escapeHtml(status)}">
        <div class="gate-head">
          <div>
            <h3>${escapeHtml(gate.name || gate.key || "Gate")}</h3>
            <div class="small">${escapeHtml(gate.summary || "")}</div>
          </div>
          ${pill(status.replaceAll("_", " "), statusKind(status))}
        </div>
        <ul class="gate-evidence">${(gate.evidence || []).map(item => `<li>${escapeHtml(item)}</li>`).join("")}</ul>
        <div class="quote">Next action: ${escapeHtml(gate.next_action || "")}</div>
      </div>`;
    }

    /* ---------------- learners + kids ---------------- */
    function positionCell(item) {
      const current = item.effective_state || {};
      const lit = current.literacy || {};
      const position = item.curriculum_position || {};
      const numeracy = position.numeracy || {};
      const literacy = position.literacy || {};
      return `<div class="position-cell">
        <div class="position-line"><span class="position-tag">Num</span><span>M${escapeHtml(current.current_module ?? "?")} &middot; ${escapeHtml(preview(numeracy.title || current.active_skill || "not placed yet", 34))}</span></div>
        <div class="position-line"><span class="position-tag">Lit</span><span>M${escapeHtml(lit.current_module ?? "?")} &middot; ${escapeHtml(preview(literacy.title || lit.active_skill || "not placed yet", 34))}</span></div>
      </div>`;
    }
    function renderLearnersTable() {
      const items = visibleLearners();
      updateRange(items.length);
      const rows = pageSlice(items).map(learnerRow).join("");
      tableWrap.innerHTML = `<table>
        <thead>
          <tr>
            <th style="width: 225px;">User</th>
            <th style="width: 105px;">Course</th>
            <th style="width: 235px;">Current Level</th>
            <th style="width: 250px;">Progress Map</th>
            <th style="width: 130px;">Recent Calls</th>
            <th style="width: 145px;">Learning</th>
            <th style="width: 125px;">Status</th>
            <th style="width: 52px;"></th>
          </tr>
        </thead>
        <tbody>${rows || `<tr><td colspan="8"><div class="empty">No learners match this view yet. Clear the search or filters to see everyone.</div></td></tr>`}</tbody>
      </table>`;
      tableWrap.querySelectorAll("[data-learner]").forEach(row => row.addEventListener("click", () => openLearner(row.dataset.learner)));
    }
    function learnerRow(item) {
      const current = item.effective_state || {};
      const calling = item.calling || {};
      const status = scaffoldDepth(current) ? pill("Support branch", "good") : (Number(current.correct_streak || 0) >= 2 ? pill("Moving up", "good") : pill("On level", "soft"));
      const active = state.selectedLearner === item.id ? " active" : "";
      return `<tr class="${active}" data-learner="${escapeHtml(item.id)}">
        <td><div class="user-cell"><span class="user-name">${escapeHtml(learnerName(item))}</span><span class="user-phone">${escapeHtml(displayPhone(item))}</span><div class="identity-row">${phoneNote(item)}</div></div></td>
        <td>${pill(current.course || "numeracy", "gold")}</td>
        <td>${positionCell(item)}</td>
        <td class="progress-cell">${progressSparkline(current)}</td>
        <td>${escapeHtml(calling.recent_call_count || 0)} calls<div class="small">${fmtSeconds(calling.recent_call_seconds)} &middot; ${escapeHtml(item.total_sessions || 0)} sessions</div></td>
        <td>${escapeHtml(item.total_correct || 0)} correct<div class="small">${escapeHtml(item.total_wrong || 0)} needs help</div></td>
        <td>${status}</td>
        <td class="chevron">&rsaquo;</td>
      </tr>`;
    }
    function renderKidsTable() {
      const kids = visibleLearners();
      updateRange(kids.length);
      const rows = pageSlice(kids).map(kidRow).join("");
      tableWrap.innerHTML = `<table>
        <thead>
          <tr>
            <th style="width: 225px;">Child</th>
            <th style="width: 145px;">Consent</th>
            <th style="width: 110px;">Network</th>
            <th style="width: 165px;">Call readiness</th>
            <th style="width: 250px;">Progress Map</th>
            <th style="width: 140px;">Recent practice</th>
            <th style="width: 140px;">Learning</th>
            <th style="width: 52px;"></th>
          </tr>
        </thead>
        <tbody>${rows || `<tr><td colspan="8"><div class="empty">No child profiles registered yet. Adult tester calls stay in Learners and Calls until a pre-pilot child has consent, caregiver details, or child-profile fields.</div></td></tr>`}</tbody>
      </table>`;
      tableWrap.querySelectorAll("[data-learner]").forEach(row => row.addEventListener("click", () => openLearner(row.dataset.learner)));
    }
    function kidRow(item) {
      const current = item.effective_state || {};
      const calling = item.calling || {};
      const consent = item.consent_status || (item.consent_recorded ? "consented" : "not recorded");
      const assent = item.assent_status || (item.assent_recorded ? "assented" : "not recorded");
      const readiness = calling.recent_call_count ? "Calls started" : "Ready to onboard";
      const network = item.network || item.mobile_network || "unknown";
      const active = state.selectedLearner === item.id ? " active" : "";
      return `<tr class="${active}" data-learner="${escapeHtml(item.id)}">
        <td><div class="user-cell"><span class="user-name">${escapeHtml(learnerName(item))}</span><span class="user-phone">${escapeHtml(displayPhone(item))}</span><div class="identity-row">${phoneNote(item)}</div></div></td>
        <td>${pill(consent, consent === "not recorded" ? "warn" : "good")}<div class="small">Assent: ${escapeHtml(assent)}</div></td>
        <td>${escapeHtml(network)}</td>
        <td>${pill(readiness, calling.recent_call_count ? "good" : "soft")}<div class="small">${escapeHtml(item.school_status || item.enrollment_status || "")}</div></td>
        <td class="progress-cell">${progressSparkline(current)}</td>
        <td>${escapeHtml(calling.recent_call_count || 0)} calls<div class="small">${fmtSeconds(calling.recent_call_seconds)}</div></td>
        <td>${escapeHtml(item.total_correct || 0)} correct<div class="small">${escapeHtml(item.total_wrong || 0)} needs help</div></td>
        <td class="chevron">&rsaquo;</td>
      </tr>`;
    }

    /* ---------------- calls ---------------- */
    function renderCallsTable() {
      const items = visibleCalls();
      updateRange(items.length);
      const rows = pageSlice(items).map(callRow).join("");
      tableWrap.innerHTML = `<table>
        <thead>
          <tr>
            <th style="width: 145px;">When</th>
            <th style="width: 210px;">Learner / Number</th>
            <th style="width: 95px;">Length</th>
            <th style="width: 115px;">Turns</th>
            <th style="width: 145px;">Heard by</th>
            <th style="width: 175px;">Status</th>
            <th>Review</th>
            <th style="width: 52px;"></th>
          </tr>
        </thead>
        <tbody>${rows || `<tr><td colspan="8"><div class="empty">No calls match this view. Try clearing the filters above.</div></td></tr>`}</tbody>
      </table>`;
      tableWrap.querySelectorAll("[data-call]").forEach(row => row.addEventListener("click", () => openCall(row.dataset.call)));
    }
    function callRow(item) {
      const flags = item.quality_flags || [];
      const hasClips = Number(item.turn_count || 0) > 0;
      const status = flags.length ? pill(callFlagLabel(flags[0]), "warn") : pill(callFlagLabel(item.end_reason || "Success"), "good");
      const review = hasClips ? "Turn audio and transcript ready" : "Full-call recording only";
      const active = state.selectedCall === item.call_uuid ? " active" : "";
      return `<tr class="${active}" data-call="${escapeHtml(item.call_uuid)}">
        <td>${escapeHtml(fmtDate(item.created_at) || "")}<div class="small">${escapeHtml(item.mode || "")}</div></td>
        <td>${callerCell(item)}</td>
        <td>${fmtSeconds(item.duration_seconds)}</td>
        <td>${escapeHtml(item.user_turns || 0)} child<div class="small">${escapeHtml(item.turn_count || 0)} clips</div></td>
        <td class="flag-wrap">${providerPills(item)}</td>
        <td class="call-status-cell">${status}${flags.length > 1 ? `<div class="small">+${flags.length - 1} more flag${flags.length > 2 ? "s" : ""}</div>` : ""}</td>
        <td class="call-review-cell"><span class="review-title">${escapeHtml(review)}</span><span class="review-id">${escapeHtml(item.call_uuid || "")}</span></td>
        <td class="chevron">&rsaquo;</td>
      </tr>`;
    }

    /* ---------------- feedback ---------------- */
    function renderFeedbackList() {
      const items = visibleFeedback();
      updateRange(items.length);
      const cards = pageSlice(items).map(feedbackCard).join("");
      tableWrap.innerHTML = `<div class="overview-layout">
        ${cards || `<div class="empty">No voice notes yet. When a caller leaves an open feedback note after a lesson, it appears here with its audio and transcript.</div>`}
      </div>`;
      tableWrap.querySelectorAll("[data-open-call]").forEach(el => el.addEventListener("click", () => openCall(el.dataset.openCall)));
    }
    function feedbackCard(item) {
      const hasAudio = Boolean(item.has_audio);
      const tags = (item.tags || []).map(tag => pill(tag.startsWith("no_audio") ? `No audio: ${callFlagLabel(tag.split(":")[1] || "")}` : tag.replaceAll("_", " "), tag.startsWith("no_audio") ? "warn" : "gold")).join(" ");
      return `<div class="feedback-card ${hasAudio ? "gold" : ""}">
        <div class="section-title-row">
          <div class="user-cell"><span class="user-name">${escapeHtml(item.phone_number || "Phone not captured yet")}</span><span class="user-phone">${escapeHtml(fmtTimestamp(item.created_at))} &middot; ${fmtSeconds(item.duration_seconds)}</span></div>
          <div class="flag-wrap">${tags}</div>
        </div>
        ${hasAudio ? `<audio controls preload="none" src="${escapeHtml(audioUrl(item.audio_endpoint))}"></audio>` : `<div class="small">No audio was captured for this note.</div>`}
        ${item.transcript_preview ? `<div class="quote">${escapeHtml(item.transcript_preview)}</div>` : ""}
        ${item.call_uuid ? `<div><button data-open-call="${escapeHtml(item.call_uuid)}">Open the call this note came from</button></div>` : ""}
      </div>`;
    }

    /* ---------------- curriculum view ---------------- */
    function renderCurriculumView() {
      staticRange("Map view");
      const curriculum = state.curriculum || {};
      const numeracy = (curriculum.numeracy || {}).modules || [];
      const literacy = (curriculum.literacy || {}).modules || [];
      tableWrap.innerHTML = `<div class="overview-layout">
        <div class="curriculum-card">
          <h3>Full Curriculum Line &mdash; Numeracy</h3>
          ${bigCurriculumMap({current_module: 4, scaffold_depth: 0, correct_streak: 0})}
          <div class="small">Six modules from counting to mixed word problems. The green line is a learner's progress; a support branch appears below when Sabi bumps down to rebuild a skill.</div>
        </div>
        <div class="module-grid">
          <div class="curriculum-card">
            <h3>Numeracy</h3>
            ${modulesHtml(numeracy, "numeracy")}
          </div>
          <div class="curriculum-card">
            <h3>Literacy</h3>
            ${modulesHtml(literacy, "literacy")}
          </div>
        </div>
        <div class="curriculum-card">
          <h3>Bump-Down Rules</h3>
          <div class="small">When a child struggles, Sabi never jumps them to a random level. It steps down within the same skill, rebuilds, then climbs back.</div>
          ${policyHtml(curriculum.bump_down_policy || {})}
        </div>
      </div>`;
    }
    function progressSparkline(current) {
      const module = safeModule(current);
      const depth = scaffoldDepth(current);
      const streak = Number((current || {}).correct_streak || 0);
      const x = 24 + (module - 1) * 38;
      const trackY = 22;
      const label = depth ? `support ${depth}` : (streak >= 2 ? "moving up" : `M${module}`);
      const color = streak >= 2 ? "#146334" : "#1e7b43";
      return `<svg class="sparkline" viewBox="0 0 240 44" role="img" aria-label="curriculum progress map">
        <line x1="24" y1="${trackY}" x2="216" y2="${trackY}" stroke="#e3dac2" stroke-width="4" stroke-linecap="round"/>
        ${[1,2,3,4,5,6].map(n => `<circle cx="${24 + (n - 1) * 38}" cy="${trackY}" r="4" fill="${n <= module ? "#1e7b43" : "#d8cfb6"}"/>`).join("")}
        <line x1="24" y1="${trackY}" x2="${x}" y2="${trackY}" stroke="${color}" stroke-width="2.5" stroke-linecap="round"/>
        <circle cx="${x}" cy="${trackY}" r="5" fill="#fffdf8" stroke="${color}" stroke-width="2.5"/>
        <text x="${Math.max(6, x - 20)}" y="41">${escapeHtml(label)}</text>
      </svg>`;
    }
    function curriculumStatusText(current) {
      const module = safeModule(current);
      const depth = scaffoldDepth(current);
      if (depth) return `Needs extra support in Module ${module}`;
      if (Number((current || {}).correct_streak || 0) >= 2) return `Ready to move up from Module ${module}`;
      return `Currently learning Module ${module}`;
    }
    function curriculumHelpText(current) {
      const depth = scaffoldDepth(current);
      if (depth) return "The branch shows the support path Sabi is using before returning to the main module path.";
      if (Number((current || {}).correct_streak || 0) >= 2) return "The line rises when the child is showing mastery.";
      return "The green line shows how far the child has reached in this path.";
    }
    function bigCurriculumMap(current, names) {
      const labels = names || moduleNames;
      const keys = Object.keys(labels).map(Number).sort((a, b) => a - b);
      const count = keys.length;
      const module = Math.max(1, Math.min(count, Number((current || {}).current_module || 1)));
      const depth = scaffoldDepth(current);
      const streak = Number((current || {}).correct_streak || 0);
      const step = count > 1 ? (480 / (count - 1)) : 0;
      const nodeX = n => 50 + (n - 1) * step;
      const x = nodeX(module);
      const trackY = 34;
      const branchY = 84;
      const color = streak >= 2 ? "#146334" : "#1e7b43";
      const supportNodes = [-48, 0, 48].map((offset, index) => ({
        x: Math.max(38, Math.min(542, x + offset)),
        label: `Support ${index + 1}`,
        level: index + 1,
      }));
      return `<svg class="curriculum-map" viewBox="0 0 580 140" role="img" aria-label="learner curriculum node map">
        <line x1="50" y1="${trackY}" x2="530" y2="${trackY}" stroke="#e3dac2" stroke-width="5" stroke-linecap="round"/>
        <line x1="50" y1="${trackY}" x2="${x}" y2="${trackY}" stroke="${color}" stroke-width="3" stroke-linecap="round"/>
        ${keys.map(n => {
          const cx = nodeX(n);
          const done = n <= module;
          const active = n === module;
          return `<circle cx="${cx}" cy="${trackY}" r="${active ? 8 : 6}" fill="${active ? "#fffdf8" : (done ? "#1e7b43" : "#d8cfb6")}" stroke="${active ? color : "transparent"}" stroke-width="3"/><text class="${active ? "map-active-label" : ""}" x="${cx}" y="63" text-anchor="middle">${escapeHtml(labels[n])}</text>`;
        }).join("")}
        ${depth ? `
          <path d="M ${x} ${trackY + 8} C ${x} ${trackY + 28}, ${supportNodes[1].x} ${branchY - 18}, ${supportNodes[1].x} ${branchY}" fill="none" stroke="${color}" stroke-width="2.5" stroke-linecap="round" opacity="0.8"/>
          <line x1="${supportNodes[0].x}" y1="${branchY}" x2="${supportNodes[2].x}" y2="${branchY}" stroke="#e3dac2" stroke-width="4" stroke-linecap="round"/>
          <line x1="${supportNodes[0].x}" y1="${branchY}" x2="${supportNodes[Math.max(0, depth - 1)].x}" y2="${branchY}" stroke="${color}" stroke-width="3" stroke-linecap="round"/>
          ${supportNodes.map(node => `<circle cx="${node.x}" cy="${branchY}" r="${node.level === depth ? 8 : 6}" fill="${node.level === depth ? "#fffdf8" : (node.level < depth ? "#1e7b43" : "#d8cfb6")}" stroke="${node.level <= depth ? color : "transparent"}" stroke-width="3"/><text class="map-branch-label ${node.level === depth ? "map-active-label" : ""}" x="${node.x}" y="112" text-anchor="middle">${escapeHtml(node.label)}</text>`).join("")}
        ` : ""}
      </svg>`;
    }
    function literacyMapState(current) {
      const lit = (current || {}).literacy || {};
      return {
        current_module: Math.max(1, Math.min(5, Number(lit.current_module || 1))),
        scaffold_depth: 0,
        correct_streak: 0,
      };
    }

    /* ---------------- learner detail ---------------- */
    async function openLearner(id) {
      state.selectedLearner = id;
      state.selectedCall = "";
      render();
      drawerTitle.textContent = "Learner";
      drawerSubtitle.textContent = "Loading...";
      drawerBody.innerHTML = `<div class="skeleton"><div class="bone"></div><div class="bone"></div><div class="bone"></div></div>`;
      drawer.classList.add("open");
      try {
        const data = await getJson(`/admin/learners/${encodeURIComponent(id)}?limit=24`);
        renderLearnerDetail(data.student || {});
      } catch (err) {
        drawerBody.innerHTML = `<div class="error">Could not load learner: ${escapeHtml(err.message)}</div>`;
      }
    }
    function renderLearnerDetail(student) {
      const current = student.effective_state || {};
      const lit = current.literacy || {};
      const position = student.curriculum_position || {};
      const numeracy = position.numeracy || {};
      const literacy = position.literacy || {};
      const calling = student.calling || {};
      const depth = scaffoldDepth(current);
      drawerTitle.textContent = learnerName(student);
      drawerSubtitle.innerHTML = `${pill(displayPhone(student), "ink")} ${phoneNote(student)} ${pill(current.course || "course", "gold")} ${depth ? pill(`Support level ${depth}`, "good") : pill("On level", "soft")}`;
      drawerBody.innerHTML = `
      ${depth || Number(current.wrong_streak || 0) >= 3 ? `<div class="callout">This learner is on a support branch. Sabi's next move: ${escapeHtml(preview(current.next_step || "rebuild the current skill with smaller steps.", 220))}</div>` : ""}
      <div class="section">
        <div class="curriculum-card compact">
          <div class="section-title-row"><h3>Numeracy Journey</h3><span class="section-caption">${escapeHtml(curriculumStatusText(current))}</span></div>
          ${bigCurriculumMap(current)}
          <div class="map-caption">
            <strong>Module ${escapeHtml(current.current_module ?? "?")}, Week ${escapeHtml(current.current_week ?? "?")}, Lesson ${escapeHtml(current.current_lesson ?? "?")}</strong>
            <span class="small">${escapeHtml(curriculumHelpText(current))}</span>
          </div>
        </div>
        <div class="curriculum-card compact">
          <div class="section-title-row"><h3>Literacy Journey</h3><span class="section-caption">Phase ${escapeHtml(lit.current_phase ?? 1)} &middot; oral foundations</span></div>
          ${bigCurriculumMap(literacyMapState(current), literacyModuleNames)}
          <div class="map-caption">
            <strong>Module ${escapeHtml(lit.current_module ?? "?")}, Week ${escapeHtml(lit.current_week ?? "?")}, Lesson ${escapeHtml(lit.current_lesson ?? "?")}</strong>
            <span class="small">Literacy runs as its own path and never collides with numeracy progress.</span>
          </div>
        </div>
        <div class="detail-grid">
          ${kv("Current numeracy lesson", numeracy.title || "not placed yet")}
          ${kv("Current literacy lesson", literacy.title || "not placed yet")}
          ${kv("Active skill", current.active_skill || "")}
          ${kv("Learning evidence", `${student.total_correct || 0} correct &middot; ${student.total_wrong || 0} needs help`, true)}
          ${kv("Recent practice", `${calling.recent_call_count || 0} calls &middot; ${fmtSeconds(calling.recent_call_seconds)}`, true)}
          ${kv("Sessions saved", student.total_sessions || 0)}
          ${kv("Recent struggles", `${current.wrong_streak ?? 0} in a row`)}
          ${kv("Correct streak", `${current.correct_streak ?? 0} in a row`)}
          ${kv("Support level", depth ? `Level ${depth} support` : "On level")}
          ${kv("Next step", preview(current.next_step || "", 160))}
          ${kv("Last call", calling.last_call_at ? fmtTimestamp(calling.last_call_at) : "No calls yet")}
          ${kv("Consent", student.consent_status || (student.consent_recorded ? "consented" : "not recorded"))}
        </div>
      </div>
      <div class="section">
        <div class="section-title-row">
          <h3>Recent Conversations</h3>
          <span class="section-caption">Newest first &middot; open any row for the full call review</span>
        </div>
        <div class="mini-table">${(student.recent_sessions || []).map(sessionRow).join("") || `<div class="empty">No sessions saved yet for this learner.</div>`}</div>
      </div>`;
      drawerBody.querySelectorAll("[data-open-call]").forEach(el => el.addEventListener("click", () => openCall(el.dataset.openCall)));
    }
    function sessionRow(session) {
      const childTurns = Number(session.child_turns || 0);
      return `<div class="mini-row" ${session.call_sid ? `data-open-call="${escapeHtml(session.call_sid)}"` : ""}>
        <div><strong class="conversation-date">${escapeHtml(fmtTimestamp(session.created_at))}</strong><div class="conversation-summary">${escapeHtml(preview(session.summary || "", 110))}</div></div>
        <div class="conversation-meta"><span class="mini-label">Length</span>${fmtSeconds(session.duration_seconds)}</div>
        <div class="conversation-meta"><span class="mini-label">Child turns</span>${escapeHtml(childTurns)} turn${childTurns === 1 ? "" : "s"}</div>
        <div><span class="conversation-action ${session.call_sid ? "open" : ""}">${session.call_sid ? "Open" : "Saved"}</span></div>
      </div>`;
    }

    /* ---------------- call detail ---------------- */
    async function openCall(id) {
      if (!id) return;
      state.selectedCall = id;
      state.selectedLearner = "";
      render();
      drawerTitle.textContent = "Call";
      drawerSubtitle.textContent = id;
      drawerBody.innerHTML = `<div class="skeleton"><div class="bone"></div><div class="bone"></div><div class="bone"></div></div>`;
      drawer.classList.add("open");
      try {
        const [call, feedback] = await Promise.all([
          getJson(`/admin/calls/${encodeURIComponent(id)}`),
          getJson(`/admin/feedback/${encodeURIComponent(id)}`).catch(() => null),
        ]);
        renderCallDetail(call, feedback);
      } catch (err) {
        drawerBody.innerHTML = `<div class="error">Could not load call: ${escapeHtml(err.message)}</div>`;
      }
    }
    function renderCallDetail(call, feedback) {
      const progression = call.learning_progression || {};
      const flags = call.quality_flags || [];
      drawerTitle.textContent = callLearnerName(call);
      drawerSubtitle.innerHTML = `${pill(callDisplayPhone(call), "ink")} ${pill(callFlagLabel(call.end_reason || "unknown"), flags.length ? "warn" : "good")} ${providerPills(call)} <span class="small">${escapeHtml(call.call_uuid || "")}</span>`;
      drawerBody.innerHTML = `
      ${flags.length ? `<div class="callout"><strong>Why this call is flagged:</strong> ${flags.map(f => escapeHtml(callFlagLabel(f))).join(" &middot; ")}</div>` : ""}
      <div class="section">
        <div class="detail-grid">
          ${kv("When", fmtDate(call.created_at) || "Not recorded")}
          ${kv("Duration", fmtSeconds(call.duration_seconds))}
          ${kv("Child turns", call.user_turns || 0)}
          ${kv("Sabi turns", call.assistant_turns || 0)}
          ${kv("Review clips", call.turn_count || 0)}
          ${kv("How it ended", callFlagLabel(call.end_reason || "unknown"))}
          ${kv("Call mode", call.mode || "")}
          ${kv("Heard by", ((call.stt_providers_used || []).map(providerLabel).join(", ")) || "Not recorded")}
          ${kv("Progression evidence", progression.has_turn_evidence ? "turn evidence available" : "full-call audio only")}
        </div>
      </div>
      ${recordingBlock(call.recordings || {})}
      ${conversationTranscriptBlock(call.turns || [])}
      <div class="section">
        <div class="section-title-row">
          <h3>Turn Evidence</h3>
          <span class="section-caption">Learning state, timings, and support moves per turn</span>
        </div>
        ${(call.turns || []).length ? (call.turns || []).map(turnBlock).join("") : `<div class="empty">No per-turn clips on this older call. New calls show child audio, STT transcript, lesson text, Sabi audio, and TTS text here.</div>`}
      </div>
      ${feedbackBlock(feedback)}`;
    }
    function feedbackBlock(feedback) {
      if (!feedback) {
        return `<div class="section"><h3>Feedback Note</h3><div class="empty">No voice note was left after this call.</div></div>`;
      }
      const tags = (feedback.tags || []).map(tag => pill(tag.startsWith("no_audio") ? `No audio: ${callFlagLabel(tag.split(":")[1] || "")}` : tag.replaceAll("_", " "), tag.startsWith("no_audio") ? "warn" : "gold")).join(" ");
      return `<div class="section">
        <div class="section-title-row"><h3>Feedback Note</h3><div class="flag-wrap">${tags}</div></div>
        <div class="feedback-card gold">
          <div class="small">${escapeHtml(fmtTimestamp(feedback.created_at))} &middot; ${fmtSeconds(feedback.duration_seconds)} &middot; ${escapeHtml(feedback.participant_type || "tester")}</div>
          ${feedback.has_audio ? `<audio controls preload="none" src="${escapeHtml(audioUrl(feedback.audio_endpoint))}"></audio>` : `<div class="small">No audio captured for this note.</div>`}
          ${feedback.redacted_transcript ? `<div class="quote">${escapeHtml(feedback.redacted_transcript)}</div>` : ""}
        </div>
      </div>`;
    }
    function recordingBlock(recordings) {
      const items = [
        ["Full conversation", recordings.mixed],
        ["Child side", recordings.rx_network],
        ["Sabi side", recordings.tx_sabi],
      ];
      return `<div class="section">
        <h3>Conversation Recording</h3>
        <div class="audio-grid">${items.map(([label, item]) => audioBox(label, item && item.audio_endpoint, item && item.exists)).join("")}</div>
      </div>`;
    }
    function audioBox(label, endpoint, exists) {
      return `<div class="kv"><div class="kv-label">${escapeHtml(label)}</div>${exists ? `<audio controls preload="none" src="${escapeHtml(audioUrl(endpoint))}"></audio>` : `<div class="small">No audio file.</div>`}</div>`;
    }
    function conversationTranscriptBlock(turns) {
      return `<div class="section">
        <div class="section-title-row">
          <h3>Conversation Transcript</h3>
          <span class="section-caption">Child audio + what Sabi heard + Sabi's reply, turn by turn</span>
        </div>
        <div class="conversation-timeline">
          ${turns.length ? turns.map(transcriptTurn).join("") : `<div class="empty">No per-turn transcript was saved for this older call. New calls show exactly what the child said, what Sabi heard, and what Sabi replied.</div>`}
        </div>
      </div>`;
    }
    function transcriptTurn(turn) {
      const user = turn.user || {};
      const assistant = turn.assistant || {};
      const flags = (turn.flags || []).map(flag => pill(turnFlagLabel(flag), turnFlagKind(flag))).join(" ");
      const childText = user.stt_transcript || "No transcript saved.";
      const lessonText = user.normalized_transcript || "";
      const sabiText = assistant.text || "No Sabi reply saved for this turn.";
      const ttsText = assistant.tts_text || "";
      const provider = providerLabel(user.stt_provider);
      const confidence = user.stt_confidence === undefined || user.stt_confidence === null || user.stt_confidence === ""
        ? ""
        : ` Confidence ${user.stt_confidence}.`;
      const timing = timingsLine(turn.timings);
      return `<div class="timeline-turn">
        <div class="timeline-turn-head">
          <span><strong>Turn ${escapeHtml(turn.turn_index)}</strong>${provider ? ` &middot; heard by ${escapeHtml(provider)}` : ""}</span>
          <span class="flag-wrap">${flags}</span>
          ${timing ? `<span class="timings">${timing}</span>` : ""}
        </div>
        <div class="timeline-pair">
          <div class="timeline-side">
            <div class="timeline-role">
              <span class="timeline-label"><span class="timeline-dot"></span>Child said</span>
              <span>${fmtSeconds(user.audio_seconds)}</span>
            </div>
            ${user.has_audio ? `<audio controls preload="none" src="${escapeHtml(audioUrl(user.audio_endpoint))}"></audio>` : `<div class="small">No child clip.</div>`}
            <div class="timeline-text">${escapeHtml(childText)}</div>
            <div class="timeline-note">This is what Sabi transcribed from the clip above.${escapeHtml(confidence)}</div>
            ${lessonText && lessonText !== childText ? `<div class="timeline-note">Lesson text after cleanup: ${escapeHtml(lessonText)}</div>` : ""}
          </div>
          <div class="timeline-side">
            <div class="timeline-role">
              <span class="timeline-label"><span class="timeline-dot sabi"></span>Sabi replied</span>
              <span>${fmtSeconds(assistant.audio_seconds)}</span>
            </div>
            ${assistant.has_audio ? `<audio controls preload="none" src="${escapeHtml(audioUrl(assistant.audio_endpoint))}"></audio>` : `<div class="small">No Sabi clip.</div>`}
            <div class="timeline-text">${escapeHtml(sabiText)}</div>
            ${ttsText && ttsText !== sabiText ? `<div class="timeline-note">Sent to TTS: ${escapeHtml(ttsText)}</div>` : `<div class="timeline-note">TTS text matches Sabi's reply.</div>`}
          </div>
        </div>
      </div>`;
    }
    function turnBlock(turn) {
      const user = turn.user || {};
      const assistant = turn.assistant || {};
      const before = turn.learning_state_before || {};
      const after = turn.learning_state_after || {};
      const bump = turn.bump_down || {};
      const bumpReasons = (bump.reasons || []).map(r => r.replaceAll("_", " ")).join(", ");
      return `<div class="turn-card">
        <div class="turn-head">
          <strong>Turn ${escapeHtml(turn.turn_index)}</strong>
          <span class="flag-wrap">${(turn.flags || []).map(flag => pill(turnFlagLabel(flag), turnFlagKind(flag))).join(" ")} ${bump.detected ? pill("bump-down", "gold") : ""}</span>
        </div>
        <div class="turn-body">
          <div class="turn-columns">
            <div class="section">
              <h3>Child</h3>
              ${user.has_audio ? `<audio controls preload="none" src="${escapeHtml(audioUrl(user.audio_endpoint))}"></audio>` : `<div class="small">No child clip.</div>`}
              <div class="quote">Transcribed: ${escapeHtml(user.stt_transcript || "")}</div>
              <div class="quote">Lesson text: ${escapeHtml(user.normalized_transcript || "")}</div>
              <div class="small">Confidence ${escapeHtml(user.stt_confidence ?? "")} &middot; ${fmtSeconds(user.audio_seconds)}${user.stt_provider ? ` &middot; heard by ${escapeHtml(providerLabel(user.stt_provider))}` : ""}</div>
            </div>
            <div class="section">
              <h3>Sabi</h3>
              ${assistant.has_audio ? `<audio controls preload="none" src="${escapeHtml(audioUrl(assistant.audio_endpoint))}"></audio>` : `<div class="small">No Sabi clip.</div>`}
              <div class="quote">Sabi said: ${escapeHtml(assistant.text || "")}</div>
              <div class="quote">Sent to TTS: ${escapeHtml(assistant.tts_text || "")}</div>
              <div class="small">TTS changed ${assistant.tts_text_changed ? "yes" : "no"} &middot; ${fmtSeconds(assistant.audio_seconds)}</div>
            </div>
          </div>
          <div class="detail-grid">
            ${kv("Before this turn", `Module ${before.current_module ?? "?"} &middot; support ${before.scaffold_depth ?? 0}`, true)}
            ${kv("After this turn", `Module ${after.current_module ?? "?"} &middot; support ${after.scaffold_depth ?? 0}`, true)}
            ${kv("Bump-down reasons", bumpReasons || "none")}
            ${kv("Teacher move", (bump.to || {}).teacher_move || (after.scaffold_ladder || {}).teacher_move || "")}
            ${kv("Timings", timingsLine(turn.timings) || "not recorded", true)}
          </div>
        </div>
      </div>`;
    }

    /* ---------------- curriculum modules ---------------- */
    function modulesHtml(modules, kind) {
      if (!modules.length) return `<div class="empty">No modules defined.</div>`;
      return modules.map((module, index) => `<details class="module" ${index === 0 ? "open" : ""}>
        <summary><span>Module ${escapeHtml(module.module)}: ${escapeHtml(module.module_name || "")}</span>${pill(`${(module.lessons || []).length} lessons`, "soft")}</summary>
        <div class="module-body">
          <div class="small">Skill: ${escapeHtml(module.active_skill || "")} &middot; starts week ${escapeHtml(module.start_week || "?")}</div>
          <div class="quote">${escapeHtml(module.principle || "")}</div>
          ${(module.lessons || []).slice(0, 12).map(lesson => lessonRow(lesson, kind)).join("")}
          ${(module.lessons || []).length > 12 ? `<div class="small">+ ${(module.lessons || []).length - 12} more lessons in this module.</div>` : ""}
        </div>
      </details>`).join("");
    }
    function lessonRow(lesson, kind) {
      const code = kind === "literacy" ? (lesson.lesson_code || lesson.script_lesson || "") : `L${lesson.global_lesson || ""}`;
      return `<div class="lesson"><span class="code">${escapeHtml(code)}</span><span>Week ${escapeHtml(lesson.week || "?")}, Lesson ${escapeHtml(lesson.lesson || "?")}: ${escapeHtml(lesson.title || "")}</span></div>`;
    }
    function policyHtml(policy) {
      return `<div class="detail-grid">${Object.entries(policy).map(([label, value]) => kv(label.replaceAll("_", " "), value)).join("")}</div>`;
    }
    function kv(label, value, raw) {
      const body = raw ? String(value ?? "") : escapeHtml(value);
      return `<div class="kv"><div class="kv-label">${escapeHtml(label)}</div><div class="kv-value">${body}</div></div>`;
    }

    /* ---------------- export ---------------- */
    function exportCsv() {
      let items, keys;
      if (state.view === "calls") {
        items = visibleCalls();
        keys = ["call_uuid", "phone_number", "duration_seconds", "end_reason", "turn_count", "user_turns", "assistant_turns", "stt_providers_used", "quality_flags"];
      } else if (state.view === "feedback") {
        items = visibleFeedback();
        keys = ["call_uuid", "phone_number", "duration_seconds", "created_at", "tags", "transcript_preview"];
      } else {
        items = visibleLearners().length ? visibleLearners() : state.learners;
        keys = ["id", "display_name", "name", "display_phone", "phone_number", "total_sessions", "total_correct", "total_wrong", "current_module"];
      }
      const rows = [keys.join(",")].concat(items.map(item => keys.map(key => `"${String(Array.isArray(item[key]) ? item[key].join("; ") : (item[key] ?? "")).replace(/"/g, '""')}"`).join(",")));
      const blob = new Blob([rows.join("\\n")], { type: "text/csv" });
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = `sabi-${state.view}.csv`;
      a.click();
      URL.revokeObjectURL(url);
    }

    /* ---------------- wiring ---------------- */
    document.getElementById("nav-overview").addEventListener("click", () => setView("overview"));
    document.getElementById("nav-gates").addEventListener("click", () => setView("gates"));
    document.getElementById("nav-learners").addEventListener("click", () => setView("learners"));
    document.getElementById("nav-kids").addEventListener("click", () => setView("kids"));
    document.getElementById("nav-calls").addEventListener("click", () => setView("calls"));
    document.getElementById("nav-feedback").addEventListener("click", () => setView("feedback"));
    document.getElementById("nav-curriculum").addEventListener("click", () => setView("curriculum"));
    document.getElementById("refresh").addEventListener("click", loadData);
    document.getElementById("export").addEventListener("click", exportCsv);
    document.getElementById("prev-page").addEventListener("click", () => { state.page = Math.max(0, state.page - 1); render(); });
    document.getElementById("next-page").addEventListener("click", () => { state.page += 1; render(); });
    document.getElementById("drawer-close").addEventListener("click", closeDrawer);
    document.addEventListener("keydown", event => { if (event.key === "Escape" && drawer.classList.contains("open")) closeDrawer(); });
    search.addEventListener("keydown", event => { if (event.key === "Enter") loadData(); });
    let searchTimer;
    search.addEventListener("input", () => {
      state.localQuery = search.value;
      state.page = 0;
      clearTimeout(searchTimer);
      searchTimer = setTimeout(() => { if (["learners", "kids", "calls", "feedback"].includes(state.view)) render(); }, 140);
    });
    window.addEventListener("hashchange", () => applyHashFrom(window.location.hash));
    loadData().then(() => applyHashFrom(bootHash));
  </script>
</body>
</html>"""
