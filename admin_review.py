"""Protected browser review console for Sabi learner/call QA."""

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
  <style>
    :root {
      color-scheme: light;
      --green: #24933f;
      --green-dark: #1d7432;
      --green-soft: #e8f5ec;
      --ink: #232b27;
      --muted: #68746d;
      --line: #e2e7e4;
      --header: #f6f7f6;
      --row: #f0f0f0;
      --panel: #ffffff;
      --warn: #9b5b00;
      --warn-bg: #fff4dc;
      --bad: #b42318;
      --bad-bg: #fff0ee;
      --good: #147a3f;
      --shadow: 0 18px 45px rgba(31, 43, 35, 0.12);
    }
    * { box-sizing: border-box; }
    body {
      margin: 0;
      font-family: Inter, ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
      background: #f7f9f8;
      color: var(--ink);
      letter-spacing: 0;
    }
    button, input, select {
      font: inherit;
      border: 1px solid var(--line);
      border-radius: 5px;
      background: #fff;
      color: var(--ink);
    }
    button {
      min-height: 38px;
      padding: 8px 12px;
      cursor: pointer;
      display: inline-flex;
      align-items: center;
      justify-content: center;
      gap: 7px;
    }
    button.primary {
      background: var(--green);
      border-color: var(--green);
      color: #fff;
    }
    input { min-height: 38px; padding: 8px 10px; min-width: 260px; }
    h1, h2, h3 { margin: 0; }
    h1 { font-size: 22px; font-weight: 650; }
    h2 { font-size: 18px; font-weight: 650; }
    h3 { font-size: 14px; font-weight: 700; }
    audio { width: 100%; margin-top: 8px; }
    .app {
      min-height: 100vh;
      display: grid;
      grid-template-columns: 250px minmax(0, 1fr);
    }
    .sidebar {
      background: #f1f3f2;
      border-right: 1px solid var(--line);
      padding: 18px 14px;
      position: sticky;
      top: 0;
      height: 100vh;
    }
    .brand {
      display: flex;
      align-items: center;
      gap: 10px;
      padding: 4px 6px 20px;
      border-bottom: 1px solid var(--line);
      margin-bottom: 16px;
    }
    .brand-mark {
      width: 36px;
      height: 36px;
      border-radius: 7px;
      display: grid;
      place-items: center;
      background: var(--green);
      color: white;
      font-weight: 800;
    }
    .brand-title { font-size: 19px; line-height: 1.05; font-weight: 750; color: var(--green-dark); }
    .brand-subtitle { font-size: 12px; color: var(--muted); margin-top: 3px; }
    .status-note {
      display: inline-flex;
      width: fit-content;
      padding: 3px 7px;
      border-radius: 5px;
      background: #f4f5f4;
      color: var(--muted);
      font-size: 12px;
      border: 1px solid var(--line);
    }
    .nav { display: grid; gap: 4px; }
    .nav button {
      border: 0;
      background: transparent;
      justify-content: flex-start;
      width: 100%;
      color: #3d4741;
      padding: 10px 12px;
      border-radius: 5px;
    }
    .nav button[aria-selected="true"] { background: var(--green); color: #fff; }
    .content { min-width: 0; }
    .topbar {
      min-height: 78px;
      background: #fff;
      border-bottom: 1px solid var(--line);
      padding: 16px 24px;
      display: flex;
      align-items: center;
      justify-content: space-between;
      gap: 18px;
      position: sticky;
      top: 0;
      z-index: 20;
    }
    .topbar-copy { display: grid; gap: 4px; }
    .subtitle { font-size: 13px; color: var(--muted); }
    .top-actions { display: flex; align-items: center; gap: 10px; flex-wrap: wrap; }
    .workspace {
      padding: 22px 24px 28px;
      display: grid;
      gap: 18px;
    }
    .metrics {
      display: grid;
      grid-template-columns: repeat(4, minmax(150px, 1fr));
      gap: 12px;
    }
    .metric {
      background: #fff;
      border: 1px solid var(--line);
      border-radius: 7px;
      padding: 14px;
      display: grid;
      gap: 4px;
    }
    .metric-label { font-size: 12px; color: var(--muted); }
    .metric-value { font-size: 24px; font-weight: 750; }
    .panel {
      background: #fff;
      border: 1px solid var(--line);
      border-radius: 8px;
      overflow: hidden;
    }
    .panel-head {
      padding: 14px 16px;
      border-bottom: 1px solid var(--line);
      display: flex;
      align-items: center;
      justify-content: space-between;
      gap: 12px;
      flex-wrap: wrap;
    }
    .toolbar { display: flex; align-items: center; gap: 8px; flex-wrap: wrap; }
    .muted-button { background: #a7a7ad; color: white; border-color: #a7a7ad; }
    .range { font-size: 14px; color: #2f3733; margin-left: auto; }
    .table-wrap {
      overflow: auto;
      max-height: calc(100vh - 285px);
      background: #fff;
    }
    table {
      width: 100%;
      min-width: 1060px;
      border-collapse: collapse;
      table-layout: fixed;
    }
    thead th {
      position: sticky;
      top: 0;
      z-index: 2;
      background: var(--green);
      color: #fff;
      text-align: left;
      font-weight: 650;
      padding: 14px 15px;
      border-right: 2px solid #fff;
      font-size: 15px;
    }
    tbody tr:nth-child(even) { background: var(--row); }
    tbody tr { cursor: pointer; }
    tbody tr:hover { background: var(--green-soft); }
    tbody tr.active { outline: 2px solid var(--green); outline-offset: -2px; background: #eaf7ef; }
    td {
      padding: 13px 15px;
      border-right: 2px solid #fff;
      vertical-align: middle;
      overflow-wrap: anywhere;
    }
    .user-cell { display: grid; gap: 3px; }
    .user-name { font-weight: 700; }
    .user-phone { color: var(--muted); font-size: 12px; }
    .pill {
      display: inline-flex;
      align-items: center;
      min-height: 24px;
      padding: 3px 8px;
      border-radius: 5px;
      font-size: 12px;
      line-height: 1;
      border: 1px solid var(--line);
      background: #fff;
      color: var(--muted);
      white-space: nowrap;
    }
    .pill.good { background: #e7f7ee; color: var(--good); border-color: #addcbe; }
    .pill.warn { background: var(--warn-bg); color: var(--warn); border-color: #f0c27c; }
    .pill.bad { background: var(--bad-bg); color: var(--bad); border-color: #f3b6ae; }
    .pill.green { background: var(--green); color: #fff; border-color: var(--green); }
    .action-button {
      width: 34px;
      min-height: 28px;
      border: 0;
      background: transparent;
      font-size: 23px;
      line-height: 1;
    }
    .progress-cell { min-width: 220px; }
    .sparkline { width: 100%; max-width: 260px; height: 52px; display: block; }
    .sparkline text { font-size: 9px; fill: var(--muted); }
    .drawer {
      position: fixed;
      right: 0;
      top: 0;
      width: min(920px, calc(100vw - 260px));
      height: 100vh;
      background: #fbfcfb;
      box-shadow: var(--shadow);
      border-left: 1px solid var(--line);
      transform: translateX(105%);
      transition: transform 180ms ease;
      z-index: 50;
      display: grid;
      grid-template-rows: auto 1fr;
    }
    .drawer.open { transform: translateX(0); }
    .drawer-head {
      padding: 18px 22px;
      border-bottom: 1px solid var(--line);
      background: #fff;
      display: flex;
      align-items: flex-start;
      justify-content: space-between;
      gap: 12px;
    }
    .drawer-body { overflow: auto; padding: 18px 22px 30px; display: grid; gap: 16px; }
    .close-button { border: 0; background: #f0f0f0; width: 36px; padding: 0; font-size: 22px; }
    .detail-grid { display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); gap: 10px; }
    .kv {
      border: 1px solid var(--line);
      border-radius: 7px;
      background: #fff;
      padding: 10px 11px;
      min-width: 0;
    }
    .kv-label { color: var(--muted); font-size: 12px; }
    .kv-value { margin-top: 4px; font-weight: 650; overflow-wrap: anywhere; font-size: 15px; line-height: 1.25; }
    .section { display: grid; gap: 10px; }
    .section-title-row {
      display: flex;
      align-items: center;
      justify-content: space-between;
      gap: 10px;
      flex-wrap: wrap;
    }
    .mini-table {
      display: grid;
      gap: 8px;
    }
    .mini-row {
      display: grid;
      grid-template-columns: minmax(260px, 1fr) 86px 130px 78px;
      gap: 10px;
      align-items: center;
      padding: 12px 14px;
      border: 1px solid var(--line);
      border-radius: 7px;
      background: #fff;
      cursor: pointer;
    }
    .mini-row:hover { background: var(--green-soft); border-color: #b9d9c4; }
    .conversation-date { font-size: 15px; font-weight: 750; }
    .conversation-summary { margin-top: 3px; color: var(--muted); font-size: 13px; line-height: 1.35; }
    .conversation-meta { font-size: 15px; font-weight: 650; }
    .quote {
      background: #f6f8f7;
      border-left: 3px solid var(--green);
      padding: 9px;
      border-radius: 4px;
      white-space: pre-wrap;
      overflow-wrap: anywhere;
      font-size: 13px;
      line-height: 1.45;
    }
    .audio-grid { display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); gap: 10px; }
    .turn-card {
      border: 1px solid var(--line);
      border-radius: 7px;
      background: #fff;
      overflow: hidden;
    }
    .turn-head {
      padding: 11px 12px;
      background: #f7f8f7;
      border-bottom: 1px solid var(--line);
      display: flex;
      align-items: center;
      justify-content: space-between;
      gap: 10px;
    }
    .turn-body { padding: 12px; display: grid; gap: 12px; }
    .turn-columns { display: grid; grid-template-columns: 1fr 1fr; gap: 12px; }
    .curriculum-card {
      border: 1px solid var(--line);
      border-radius: 7px;
      background: #fff;
      padding: 13px;
      display: grid;
      gap: 10px;
    }
    .curriculum-card.compact { padding: 16px; }
    .curriculum-map { width: 100%; height: 112px; display: block; }
    .map-caption {
      display: flex;
      align-items: center;
      justify-content: space-between;
      gap: 10px;
      flex-wrap: wrap;
      padding-top: 2px;
    }
    .map-caption strong { font-size: 15px; }
    .module-grid { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 10px; }
    details.module {
      border: 1px solid var(--line);
      border-radius: 7px;
      background: #fff;
      overflow: hidden;
    }
    details.module summary {
      cursor: pointer;
      padding: 11px 12px;
      font-weight: 700;
      display: flex;
      justify-content: space-between;
      gap: 10px;
    }
    .module-body {
      border-top: 1px solid var(--line);
      padding: 11px 12px;
      display: grid;
      gap: 8px;
    }
    .lesson {
      display: grid;
      grid-template-columns: 78px minmax(0, 1fr);
      gap: 8px;
      padding: 7px 8px;
      background: #f7f8f7;
      border: 1px solid var(--line);
      border-radius: 5px;
      font-size: 12px;
    }
    .code { font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace; color: var(--green-dark); font-weight: 750; }
    .empty, .error {
      color: var(--muted);
      padding: 24px;
      text-align: center;
      border: 1px dashed var(--line);
      border-radius: 7px;
      background: #fbfcfb;
    }
    .error { color: var(--bad); background: var(--bad-bg); border-color: #f3b6ae; }
    .small { font-size: 12px; color: var(--muted); }
    .hidden { display: none !important; }
    @media (max-width: 1100px) {
      .app { grid-template-columns: 1fr; }
      .sidebar { position: static; height: auto; }
      .nav { grid-template-columns: repeat(3, 1fr); }
      .metrics { grid-template-columns: repeat(2, minmax(0, 1fr)); }
      .detail-grid, .turn-columns, .audio-grid, .module-grid { grid-template-columns: 1fr; }
      .drawer { width: 100vw; }
      .mini-row { grid-template-columns: 1fr; }
      .topbar { align-items: flex-start; flex-direction: column; }
      input { min-width: 0; width: 100%; }
    }
  </style>
</head>
<body>
  <div class="app">
    <aside class="sidebar">
      <div class="brand">
        <div class="brand-mark">S</div>
        <div>
          <div class="brand-title">Sabi</div>
          <div class="brand-subtitle">Education for Equality</div>
        </div>
      </div>
      <nav class="nav" aria-label="Sabi admin navigation">
        <button id="nav-learners" aria-selected="true">Learners</button>
        <button id="nav-calls" aria-selected="false">Calls</button>
        <button id="nav-curriculum" aria-selected="false">Curriculum</button>
      </nav>
    </aside>
    <div class="content">
      <header class="topbar">
        <div class="topbar-copy">
          <h1 id="page-title">Learners</h1>
          <div class="subtitle" id="page-subtitle">Students, levels, calls, transcripts, and progress.</div>
        </div>
        <div class="top-actions">
          <input id="search" placeholder="Filter learners or phone numbers" autocomplete="off">
          <button class="muted-button" id="export">Download CSV</button>
          <button class="muted-button" id="refresh">Refresh</button>
        </div>
      </header>
      <main class="workspace">
        <section class="metrics" id="metrics"></section>
        <section class="panel">
          <div class="panel-head">
            <h2 id="panel-title">Learner Database</h2>
            <div class="toolbar">
              <span class="range" id="range">0 - 0</span>
              <button id="prev-page" class="muted-button">Previous</button>
              <button id="next-page" class="muted-button">Next</button>
            </div>
          </div>
          <div class="table-wrap" id="table-wrap"><div class="empty">Loading...</div></div>
        </section>
      </main>
    </div>
  </div>
  <aside class="drawer" id="drawer" aria-live="polite">
    <div class="drawer-head">
      <div>
        <h2 id="drawer-title">Detail</h2>
        <div id="drawer-subtitle" class="subtitle"></div>
      </div>
      <button id="drawer-close" class="close-button" aria-label="Close">x</button>
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
      view: "learners",
      learners: [],
      calls: [],
      curriculum: null,
      selectedLearner: "",
      selectedCall: "",
      page: 0,
      pageSize: 50,
    };
    const moduleNames = {
      1: "Counting",
      2: "Addition",
      3: "Subtraction",
      4: "Multiply",
      5: "Division",
      6: "Problems",
    };
    const search = document.getElementById("search");
    const tableWrap = document.getElementById("table-wrap");
    const metrics = document.getElementById("metrics");
    const drawer = document.getElementById("drawer");
    const drawerTitle = document.getElementById("drawer-title");
    const drawerSubtitle = document.getElementById("drawer-subtitle");
    const drawerBody = document.getElementById("drawer-body");

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
    function displayPhone(record) {
      const phone = record && (record.phone_number || record.phone_number_normalized || (record.calling || {}).last_phone_number);
      return phone || "No phone linked yet";
    }
    function phoneNote(record) {
      const hasPhone = Boolean(record && (record.phone_number || record.phone_number_normalized || (record.calling || {}).last_phone_number));
      return hasPhone ? "" : `<span class="status-note">Web/demo profile</span>`;
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
    async function getJson(path) {
      const res = await fetch(path, { headers });
      if (!res.ok) throw new Error(`${res.status} ${res.statusText}`);
      return res.json();
    }
    async function loadData() {
      tableWrap.innerHTML = `<div class="empty">Loading...</div>`;
      const q = encodeURIComponent(search.value.trim());
      try {
        const [learners, calls, curriculum] = await Promise.all([
          getJson(`/admin/learners?limit=100${q ? `&q=${q}` : ""}`),
          getJson(`/admin/calls?limit=100${q ? `&q=${q}` : ""}`),
          state.curriculum ? Promise.resolve(state.curriculum) : getJson("/admin/curriculum-map"),
        ]);
        state.learners = learners.items || [];
        state.calls = calls.items || [];
        state.curriculum = curriculum;
        state.page = 0;
        render();
      } catch (err) {
        tableWrap.innerHTML = `<div class="error">Could not load Sabi admin data: ${escapeHtml(err.message)}</div>`;
      }
    }
    function setView(view) {
      state.view = view;
      state.page = 0;
      drawer.classList.remove("open");
      document.getElementById("nav-learners").setAttribute("aria-selected", view === "learners");
      document.getElementById("nav-calls").setAttribute("aria-selected", view === "calls");
      document.getElementById("nav-curriculum").setAttribute("aria-selected", view === "curriculum");
      render();
    }
    function render() {
      renderHeader();
      renderMetrics();
      if (state.view === "learners") renderLearnersTable();
      if (state.view === "calls") renderCallsTable();
      if (state.view === "curriculum") renderCurriculumView();
    }
    function renderHeader() {
      const titles = {
        learners: ["Learners", "Students, levels, calls, transcripts, and progress.", "Learner Database"],
        calls: ["Calls", "Recent phone sessions and recording evidence.", "Voice Sessions"],
        curriculum: ["Curriculum", "Structured learning path and bump-down rules.", "Curriculum Map"],
      };
      const [title, subtitle, panel] = titles[state.view];
      document.getElementById("page-title").textContent = title;
      document.getElementById("page-subtitle").textContent = subtitle;
      document.getElementById("panel-title").textContent = panel;
      search.placeholder = state.view === "calls" ? "Filter sessions or phone numbers" : "Filter learners or phone numbers";
    }
    function renderMetrics() {
      const learnerCount = state.learners.length;
      const callCount = state.calls.length;
      const totalMinutes = state.calls.reduce((sum, call) => sum + Number(call.duration_seconds || 0), 0) / 60;
      const flaggedCalls = state.calls.filter(call => (call.quality_flags || []).length).length;
      metrics.innerHTML = [
        metric("Learners", learnerCount),
        metric("Recent calls", callCount),
        metric("Call minutes", totalMinutes.toFixed(1)),
        metric("Needs review", flaggedCalls),
      ].join("");
    }
    function metric(label, value) {
      return `<div class="metric"><div class="metric-label">${escapeHtml(label)}</div><div class="metric-value">${escapeHtml(value)}</div></div>`;
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
    function renderLearnersTable() {
      updateRange(state.learners.length);
      const rows = pageSlice(state.learners).map(learnerRow).join("");
      tableWrap.innerHTML = `<table>
        <thead>
          <tr>
            <th style="width: 230px;">User</th>
            <th style="width: 150px;">Course</th>
            <th style="width: 180px;">Current Level</th>
            <th style="width: 260px;">Progress Map</th>
            <th style="width: 110px;">Sessions</th>
            <th style="width: 130px;">Recent Calls</th>
            <th style="width: 150px;">Learning</th>
            <th style="width: 120px;">Status</th>
            <th style="width: 90px;">Actions</th>
          </tr>
        </thead>
        <tbody>${rows || `<tr><td colspan="9"><div class="empty">No learners found.</div></td></tr>`}</tbody>
      </table>`;
      tableWrap.querySelectorAll("[data-learner]").forEach(row => row.addEventListener("click", () => openLearner(row.dataset.learner)));
    }
    function learnerRow(item) {
      const current = item.effective_state || {};
      const calling = item.calling || {};
      const position = item.curriculum_position || {};
      const numeracy = position.numeracy || {};
      const status = scaffoldDepth(current) ? pill("Bumped down", "warn") : pill("On level", "good");
      const active = state.selectedLearner === item.id ? " active" : "";
      return `<tr class="${active}" data-learner="${escapeHtml(item.id)}">
        <td><div class="user-cell"><span class="user-name">${escapeHtml(item.name || "Unnamed learner")}</span><span class="user-phone">${escapeHtml(displayPhone(item))}</span>${phoneNote(item)}</div></td>
        <td>${pill(current.course || "numeracy", "green")}</td>
        <td>Module ${escapeHtml(current.current_module ?? "?")}<div class="small">${escapeHtml(preview(numeracy.title || current.active_skill || ""))}</div></td>
        <td class="progress-cell">${progressSparkline(current)}</td>
        <td>${escapeHtml(item.total_sessions || 0)}</td>
        <td>${escapeHtml(calling.recent_call_count || 0)} calls<div class="small">${fmtSeconds(calling.recent_call_seconds)}</div></td>
        <td>${escapeHtml(item.total_correct || 0)} correct<div class="small">${escapeHtml(item.total_wrong || 0)} needs help</div></td>
        <td>${status}</td>
        <td><button class="action-button" title="Open learner">...</button></td>
      </tr>`;
    }
    function renderCallsTable() {
      updateRange(state.calls.length);
      const rows = pageSlice(state.calls).map(callRow).join("");
      tableWrap.innerHTML = `<table>
        <thead>
          <tr>
            <th style="width: 180px;">Date</th>
            <th style="width: 170px;">Caller</th>
            <th style="width: 130px;">Duration</th>
            <th style="width: 130px;">Turns</th>
            <th style="width: 170px;">Status</th>
            <th>Review</th>
            <th style="width: 90px;">Actions</th>
          </tr>
        </thead>
        <tbody>${rows || `<tr><td colspan="7"><div class="empty">No calls found.</div></td></tr>`}</tbody>
      </table>`;
      tableWrap.querySelectorAll("[data-call]").forEach(row => row.addEventListener("click", () => openCall(row.dataset.call)));
    }
    function callRow(item) {
      const flags = item.quality_flags || [];
      const hasClips = Number(item.turn_count || 0) > 0;
      const status = flags.length ? pill(flags[0], "warn") : pill(item.end_reason || "Success", "good");
      const review = hasClips ? "Turn audio and transcript ready" : "Full-call recording only";
      const active = state.selectedCall === item.call_uuid ? " active" : "";
      return `<tr class="${active}" data-call="${escapeHtml(item.call_uuid)}">
        <td>${escapeHtml(fmtDate(item.created_at) || item.call_uuid || "")}</td>
        <td>${escapeHtml(item.phone_number || "unknown")}</td>
        <td>${fmtSeconds(item.duration_seconds)}</td>
        <td>${escapeHtml(item.user_turns || 0)} child<div class="small">${escapeHtml(item.turn_count || 0)} clips</div></td>
        <td>${status}</td>
        <td>${escapeHtml(review)}<div class="small">${escapeHtml(item.call_uuid || "")}</div></td>
        <td><button class="action-button" title="Open call">...</button></td>
      </tr>`;
    }
    function renderCurriculumView() {
      updateRange(0);
      const curriculum = state.curriculum || {};
      const numeracy = (curriculum.numeracy || {}).modules || [];
      const literacy = (curriculum.literacy || {}).modules || [];
      tableWrap.innerHTML = `<div style="padding: 16px; display: grid; gap: 16px;">
        <div class="curriculum-card">
          <h3>Full Curriculum Line</h3>
          ${bigCurriculumMap({current_module: 4, scaffold_depth: 0, correct_streak: 0})}
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
          ${policyHtml(curriculum.bump_down_policy || {})}
        </div>
      </div>`;
    }
    function progressSparkline(current) {
      const module = safeModule(current);
      const depth = scaffoldDepth(current);
      const streak = Number(current.correct_streak || 0);
      const x = 24 + (module - 1) * 38;
      const y = depth ? 32 + depth * 4 : (streak >= 2 ? 16 : 24);
      const label = depth ? `support ${depth}` : (streak >= 2 ? "moving up" : `M${module}`);
      const color = depth ? "#9b5b00" : (streak >= 2 ? "#147a3f" : "#24933f");
      return `<svg class="sparkline" viewBox="0 0 240 52" role="img" aria-label="curriculum progress map">
        <line x1="24" y1="24" x2="216" y2="24" stroke="#d7ded9" stroke-width="4" stroke-linecap="round"/>
        ${[1,2,3,4,5,6].map(n => `<circle cx="${24 + (n - 1) * 38}" cy="24" r="4" fill="${n <= module ? "#24933f" : "#cfd8d2"}"/>`).join("")}
        <polyline points="24,24 ${x},24 ${x},${y}" fill="none" stroke="${color}" stroke-width="3" stroke-linecap="round" stroke-linejoin="round"/>
        <circle cx="${x}" cy="${y}" r="6" fill="${color}"/>
        <text x="${Math.max(6, x - 20)}" y="48">${escapeHtml(label)}</text>
      </svg>`;
    }
    function curriculumStatusText(current) {
      const module = safeModule(current);
      const depth = scaffoldDepth(current);
      if (depth) return `Needs extra support in Module ${module}`;
      if (Number(current.correct_streak || 0) >= 2) return `Ready to move up from Module ${module}`;
      return `Currently learning Module ${module}`;
    }
    function curriculumHelpText(current) {
      const depth = scaffoldDepth(current);
      if (depth) return "The line dips because Sabi is using easier scaffolded examples before moving forward.";
      if (Number(current.correct_streak || 0) >= 2) return "The line rises when the child is showing mastery.";
      return "The green line shows how far the child has reached in the numeracy path.";
    }
    function bigCurriculumMap(current) {
      const module = safeModule(current);
      const depth = scaffoldDepth(current);
      const streak = Number(current.correct_streak || 0);
      const x = 50 + (module - 1) * 96;
      const y = depth ? 78 + depth * 8 : (streak >= 2 ? 38 : 58);
      const color = depth ? "#9b5b00" : (streak >= 2 ? "#147a3f" : "#24933f");
      return `<svg class="curriculum-map" viewBox="0 0 580 112" role="img" aria-label="learner curriculum path">
        <line x1="50" y1="58" x2="530" y2="58" stroke="#d7ded9" stroke-width="7" stroke-linecap="round"/>
        ${[1,2,3,4,5,6].map(n => {
          const cx = 50 + (n - 1) * 96;
          const done = n <= module;
          return `<circle cx="${cx}" cy="58" r="10" fill="${done ? "#24933f" : "#cfd8d2"}"/><text x="${cx - 30}" y="100">${escapeHtml(moduleNames[n])}</text>`;
        }).join("")}
        <polyline points="50,58 ${x},58 ${x},${y}" fill="none" stroke="${color}" stroke-width="5" stroke-linecap="round" stroke-linejoin="round"/>
        <circle cx="${x}" cy="${y}" r="12" fill="${color}"/>
      </svg>`;
    }
    async function openLearner(id) {
      state.selectedLearner = id;
      state.selectedCall = "";
      render();
      drawerTitle.textContent = "Learner";
      drawerSubtitle.textContent = "Loading...";
      drawerBody.innerHTML = `<div class="empty">Loading learner...</div>`;
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
      drawerTitle.textContent = student.name || "Unnamed learner";
      drawerSubtitle.innerHTML = `${escapeHtml(displayPhone(student))} ${phoneNote(student)} ${pill(current.course || "course", "green")} ${scaffoldDepth(current) ? pill("bumped down", "warn") : pill("on level", "good")}`;
      drawerBody.innerHTML = `<div class="section">
        <div class="curriculum-card compact">
          <h3>Curriculum Position</h3>
          ${bigCurriculumMap(current)}
          <div class="map-caption">
            <strong>${escapeHtml(curriculumStatusText(current))}</strong>
            <span class="small">${escapeHtml(curriculumHelpText(current))}</span>
          </div>
        </div>
        <div class="detail-grid">
          ${kv("Numeracy", `Module ${current.current_module ?? "?"}, Week ${current.current_week ?? "?"}, Lesson ${current.current_lesson ?? "?"}`)}
          ${kv("Literacy", `Module ${lit.current_module ?? "?"}, Week ${lit.current_week ?? "?"}, Lesson ${lit.current_lesson ?? "?"}`)}
          ${kv("Current numeracy lesson", numeracy.title || "not placed yet")}
          ${kv("Current literacy lesson", literacy.title || "not placed yet")}
          ${kv("Learning evidence", `${student.total_correct || 0} correct · ${student.total_wrong || 0} needs help`)}
          ${kv("Recent practice", `${calling.recent_call_count || 0} calls · ${fmtSeconds(calling.recent_call_seconds)}`)}
          ${kv("Active skill", current.active_skill || "")}
          ${kv("Next step", current.next_step || "")}
          ${kv("Recent struggles", current.wrong_streak ?? 0)}
          ${kv("Support level", scaffoldDepth(current) ? `Level ${scaffoldDepth(current)} support` : "On level")}
        </div>
      </div>
      <div class="section">
        <div class="section-title-row">
          <h3>Recent Conversations</h3>
          <span class="status-note">Newest first</span>
        </div>
        <div class="mini-table">${(student.recent_sessions || []).map(sessionRow).join("") || `<div class="empty">No sessions.</div>`}</div>
      </div>`;
      drawerBody.querySelectorAll("[data-open-call]").forEach(el => el.addEventListener("click", () => openCall(el.dataset.openCall)));
    }
    function sessionRow(session) {
      return `<div class="mini-row" ${session.call_sid ? `data-open-call="${escapeHtml(session.call_sid)}"` : ""}>
        <div><strong class="conversation-date">${escapeHtml(fmtTimestamp(session.created_at))}</strong><div class="conversation-summary">${escapeHtml(preview(session.summary || "", 105))}</div></div>
        <div class="conversation-meta">${fmtSeconds(session.duration_seconds)}</div>
        <div class="conversation-meta">${escapeHtml(session.child_turns || 0)} child turn${Number(session.child_turns || 0) === 1 ? "" : "s"}</div>
        <div>${session.call_sid ? pill("Open", "green") : pill("Saved")}</div>
      </div>`;
    }
    async function openCall(id) {
      if (!id) return;
      state.selectedCall = id;
      state.selectedLearner = "";
      render();
      drawerTitle.textContent = "Call";
      drawerSubtitle.textContent = id;
      drawerBody.innerHTML = `<div class="empty">Loading call...</div>`;
      drawer.classList.add("open");
      try {
        const call = await getJson(`/admin/calls/${encodeURIComponent(id)}`);
        renderCallDetail(call);
      } catch (err) {
        drawerBody.innerHTML = `<div class="error">Could not load call: ${escapeHtml(err.message)}</div>`;
      }
    }
    function renderCallDetail(call) {
      const progression = call.learning_progression || {};
      drawerTitle.textContent = call.phone_number || "Call";
      drawerSubtitle.innerHTML = `${escapeHtml(call.call_uuid || "")} ${pill(call.end_reason || "unknown", (call.quality_flags || []).length ? "warn" : "good")}`;
      drawerBody.innerHTML = `<div class="section">
        <div class="detail-grid">
          ${kv("Duration", fmtSeconds(call.duration_seconds))}
          ${kv("Child turns", call.user_turns || 0)}
          ${kv("Sabi turns", call.assistant_turns || 0)}
          ${kv("Review clips", call.turn_count || 0)}
          ${kv("Quality flags", (call.quality_flags || []).join(", ") || "none")}
          ${kv("Progression evidence", progression.has_turn_evidence ? "turn evidence available" : "full-call audio only")}
        </div>
      </div>
      ${recordingBlock(call.recordings || {})}
      <div class="section">
        <h3>Turn Evidence</h3>
        ${(call.turns || []).length ? (call.turns || []).map(turnBlock).join("") : `<div class="empty">No per-turn clips on this older call. New calls show child audio, STT transcript, lesson text, Sabi audio, and TTS text here.</div>`}
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
    function turnBlock(turn) {
      const user = turn.user || {};
      const assistant = turn.assistant || {};
      const before = turn.learning_state_before || {};
      const after = turn.learning_state_after || {};
      const bump = turn.bump_down || {};
      return `<div class="turn-card">
        <div class="turn-head">
          <strong>Turn ${escapeHtml(turn.turn_index)}</strong>
          <span>${(turn.flags || []).map(flag => pill(flag, flag.includes("low") || flag.includes("retry") ? "warn" : "")).join(" ")} ${bump.detected ? pill("bump-down", "warn") : ""}</span>
        </div>
        <div class="turn-body">
          <div class="turn-columns">
            <div class="section">
              <h3>Child</h3>
              ${user.has_audio ? `<audio controls preload="none" src="${escapeHtml(audioUrl(user.audio_endpoint))}"></audio>` : `<div class="small">No child clip.</div>`}
              <div class="quote">Transcribed: ${escapeHtml(user.stt_transcript || "")}</div>
              <div class="quote">Lesson text: ${escapeHtml(user.normalized_transcript || "")}</div>
              <div class="small">Confidence ${escapeHtml(user.stt_confidence ?? "")} · ${fmtSeconds(user.audio_seconds)}</div>
            </div>
            <div class="section">
              <h3>Sabi</h3>
              ${assistant.has_audio ? `<audio controls preload="none" src="${escapeHtml(audioUrl(assistant.audio_endpoint))}"></audio>` : `<div class="small">No Sabi clip.</div>`}
              <div class="quote">Sabi said: ${escapeHtml(assistant.text || "")}</div>
              <div class="quote">Sent to TTS: ${escapeHtml(assistant.tts_text || "")}</div>
              <div class="small">TTS changed ${assistant.tts_text_changed ? "yes" : "no"} · ${fmtSeconds(assistant.audio_seconds)}</div>
            </div>
          </div>
          <div class="detail-grid">
            ${kv("Before", `M${before.current_module ?? "?"} · scaffold ${before.scaffold_depth ?? 0}`)}
            ${kv("After", `M${after.current_module ?? "?"} · scaffold ${after.scaffold_depth ?? 0}`)}
            ${kv("Bump-down reasons", (bump.reasons || []).join(", ") || "none")}
            ${kv("Teacher move", (bump.to || {}).teacher_move || (after.scaffold_ladder || {}).teacher_move || "")}
          </div>
        </div>
      </div>`;
    }
    function modulesHtml(modules, kind) {
      if (!modules.length) return `<div class="empty">No modules defined.</div>`;
      return modules.map((module, index) => `<details class="module" ${index === 0 ? "open" : ""}>
        <summary><span>Module ${escapeHtml(module.module)}: ${escapeHtml(module.module_name || "")}</span>${pill(`${(module.lessons || []).length} lessons`)}</summary>
        <div class="module-body">
          <div class="small">Skill: ${escapeHtml(module.active_skill || "")} · starts week ${escapeHtml(module.start_week || "?")}</div>
          <div class="quote">${escapeHtml(module.principle || "")}</div>
          ${(module.lessons || []).slice(0, 12).map(lesson => lessonRow(lesson, kind)).join("")}
        </div>
      </details>`).join("");
    }
    function lessonRow(lesson, kind) {
      const code = kind === "literacy" ? (lesson.lesson_code || lesson.script_lesson || "") : `L${lesson.global_lesson || ""}`;
      return `<div class="lesson"><span class="code">${escapeHtml(code)}</span><span>Week ${escapeHtml(lesson.week || "?")}, Lesson ${escapeHtml(lesson.lesson || "?")}: ${escapeHtml(lesson.title || "")}</span></div>`;
    }
    function policyHtml(policy) {
      return `<div class="detail-grid">${Object.entries(policy).map(([label, value]) => kv(label, value)).join("")}</div>`;
    }
    function kv(label, value) {
      return `<div class="kv"><div class="kv-label">${escapeHtml(label)}</div><div class="kv-value">${escapeHtml(value)}</div></div>`;
    }
    function exportCsv() {
      const items = state.view === "calls" ? state.calls : state.learners;
      const keys = state.view === "calls"
        ? ["call_uuid", "phone_number", "duration_seconds", "end_reason", "turn_count", "user_turns", "assistant_turns"]
        : ["id", "name", "phone_number", "total_sessions", "total_correct", "total_wrong", "current_module"];
      const rows = [keys.join(",")].concat(items.map(item => keys.map(key => `"${String(item[key] ?? "").replace(/"/g, '""')}"`).join(",")));
      const blob = new Blob([rows.join("\\n")], { type: "text/csv" });
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = `sabi-${state.view}.csv`;
      a.click();
      URL.revokeObjectURL(url);
    }
    document.getElementById("nav-learners").addEventListener("click", () => setView("learners"));
    document.getElementById("nav-calls").addEventListener("click", () => setView("calls"));
    document.getElementById("nav-curriculum").addEventListener("click", () => setView("curriculum"));
    document.getElementById("refresh").addEventListener("click", loadData);
    document.getElementById("export").addEventListener("click", exportCsv);
    document.getElementById("prev-page").addEventListener("click", () => { state.page = Math.max(0, state.page - 1); render(); });
    document.getElementById("next-page").addEventListener("click", () => { state.page += 1; render(); });
    document.getElementById("drawer-close").addEventListener("click", () => drawer.classList.remove("open"));
    search.addEventListener("keydown", event => { if (event.key === "Enter") loadData(); });
    loadData();
  </script>
</body>
</html>"""
