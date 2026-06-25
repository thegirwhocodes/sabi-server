"""Protected browser review console for Sabi learner/call QA."""

from __future__ import annotations


def render_admin_review_page() -> str:
    """Return the internal QA page shell.

    The page is intentionally server-hosted by the Sabi API because call audio
    lives on the PBX volume. The existing API-key middleware protects this
    route, and the client reuses the same api_key query param for JSON/audio
    calls when a browser cannot send headers for <audio> elements.
    """
    return """<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Sabi Review Console</title>
  <style>
    :root {
      color-scheme: light;
      --ink: #17211b;
      --muted: #5f6f66;
      --line: #d9e3dc;
      --soft: #f5f8f6;
      --panel: #ffffff;
      --accent: #1f8a4c;
      --accent-soft: #e6f4ec;
      --warn: #a45a00;
      --bad: #b42318;
      --good: #147a3f;
    }
    * { box-sizing: border-box; }
    body {
      margin: 0;
      font-family: Inter, ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
      color: var(--ink);
      background: #eef4f0;
      letter-spacing: 0;
    }
    header {
      position: sticky;
      top: 0;
      z-index: 5;
      background: rgba(255,255,255,0.96);
      border-bottom: 1px solid var(--line);
      padding: 14px 20px;
      display: flex;
      align-items: center;
      justify-content: space-between;
      gap: 16px;
    }
    h1 { font-size: 20px; margin: 0; }
    h2 { font-size: 16px; margin: 0 0 10px; }
    h3 { font-size: 14px; margin: 0 0 8px; }
    button, input, select {
      font: inherit;
      border: 1px solid var(--line);
      border-radius: 6px;
      background: #fff;
      color: var(--ink);
    }
    button {
      cursor: pointer;
      padding: 8px 10px;
      display: inline-flex;
      align-items: center;
      gap: 6px;
    }
    button.primary {
      background: var(--accent);
      color: white;
      border-color: var(--accent);
    }
    input { padding: 8px 10px; min-width: 220px; }
    main {
      display: grid;
      grid-template-columns: minmax(320px, 0.95fr) minmax(460px, 1.45fr);
      gap: 14px;
      padding: 14px;
      max-width: 1500px;
      margin: 0 auto;
    }
    section {
      background: var(--panel);
      border: 1px solid var(--line);
      border-radius: 8px;
      min-width: 0;
    }
    .section-head {
      padding: 12px;
      border-bottom: 1px solid var(--line);
      display: flex;
      align-items: center;
      justify-content: space-between;
      gap: 10px;
    }
    .body { padding: 12px; }
    .toolbar { display: flex; gap: 8px; align-items: center; flex-wrap: wrap; }
    .tabs { display: flex; gap: 6px; }
    .tab[aria-selected="true"] { background: var(--accent-soft); border-color: #a7d8bc; color: var(--accent); }
    .list { display: grid; gap: 8px; }
    .row {
      border: 1px solid var(--line);
      border-radius: 8px;
      background: #fff;
      padding: 10px;
      cursor: pointer;
    }
    .row:hover { border-color: #9bccae; }
    .row.active { border-color: var(--accent); box-shadow: 0 0 0 2px rgba(31,138,76,0.12); }
    .row-title { display: flex; align-items: center; justify-content: space-between; gap: 8px; font-weight: 650; }
    .meta { color: var(--muted); font-size: 12px; line-height: 1.45; margin-top: 4px; }
    .pill {
      display: inline-flex;
      align-items: center;
      min-height: 22px;
      padding: 2px 7px;
      border-radius: 999px;
      font-size: 12px;
      border: 1px solid var(--line);
      background: var(--soft);
      color: var(--muted);
      white-space: nowrap;
    }
    .pill.good { background: #e7f7ee; color: var(--good); border-color: #addcbe; }
    .pill.warn { background: #fff2dd; color: var(--warn); border-color: #f0c27c; }
    .pill.bad { background: #fff0ee; color: var(--bad); border-color: #f3b6ae; }
    .grid {
      display: grid;
      grid-template-columns: repeat(2, minmax(0, 1fr));
      gap: 10px;
    }
    .kv {
      background: var(--soft);
      border: 1px solid var(--line);
      border-radius: 8px;
      padding: 10px;
      min-width: 0;
    }
    .kv-label { color: var(--muted); font-size: 12px; }
    .kv-value { margin-top: 3px; font-weight: 650; overflow-wrap: anywhere; }
    audio { width: 100%; margin-top: 6px; }
    .audio-grid { display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); gap: 8px; }
    .turn {
      border: 1px solid var(--line);
      border-radius: 8px;
      padding: 10px;
      display: grid;
      gap: 8px;
      background: #fff;
    }
    .turn-grid { display: grid; grid-template-columns: minmax(0, 1fr) minmax(0, 1fr); gap: 10px; }
    .quote {
      background: var(--soft);
      border-left: 3px solid #a7d8bc;
      padding: 8px;
      border-radius: 5px;
      white-space: pre-wrap;
      overflow-wrap: anywhere;
      font-size: 13px;
      line-height: 1.4;
    }
    .empty, .error {
      color: var(--muted);
      padding: 18px;
      text-align: center;
      border: 1px dashed var(--line);
      border-radius: 8px;
      background: var(--soft);
    }
    .error { color: var(--bad); background: #fff8f7; border-color: #f3b6ae; }
    .small { font-size: 12px; color: var(--muted); }
    .stack { display: grid; gap: 10px; }
    @media (max-width: 980px) {
      main { grid-template-columns: 1fr; }
      .grid, .audio-grid, .turn-grid { grid-template-columns: 1fr; }
      header { align-items: flex-start; flex-direction: column; }
      input { min-width: 0; width: 100%; }
    }
  </style>
</head>
<body>
  <header>
    <div>
      <h1>Sabi Review Console</h1>
      <div class="small">Learner progression, call recordings, STT evidence, and bump-down review.</div>
    </div>
    <div class="toolbar">
      <input id="search" placeholder="Search name or phone" autocomplete="off">
      <button class="primary" id="refresh">Refresh</button>
    </div>
  </header>
  <main>
    <section>
      <div class="section-head">
        <h2>Review Queue</h2>
        <div class="tabs" role="tablist">
          <button class="tab" id="tab-learners" aria-selected="true">Learners</button>
          <button class="tab" id="tab-calls" aria-selected="false">Calls</button>
        </div>
      </div>
      <div class="body">
        <div id="queue" class="list"><div class="empty">Loading...</div></div>
      </div>
    </section>
    <section>
      <div class="section-head">
        <h2 id="detail-title">Detail</h2>
        <span id="detail-status" class="pill">No selection</span>
      </div>
      <div class="body">
        <div id="detail" class="empty">Select a learner or call.</div>
      </div>
    </section>
  </main>
  <script>
    const params = new URLSearchParams(window.location.search);
    const apiKey = params.get("api_key") || "";
    const headers = apiKey ? {"X-API-Key": apiKey} : {};
    const state = { tab: "learners", learners: [], calls: [], selectedCall: "", selectedLearner: "" };
    const queue = document.getElementById("queue");
    const detail = document.getElementById("detail");
    const detailTitle = document.getElementById("detail-title");
    const detailStatus = document.getElementById("detail-status");
    const search = document.getElementById("search");

    function escapeHtml(value) {
      return String(value ?? "").replace(/[&<>"']/g, ch => ({
        "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;"
      }[ch]));
    }
    function audioUrl(path) {
      if (!path) return "";
      const separator = path.includes("?") ? "&" : "?";
      return apiKey ? `${path}${separator}api_key=${encodeURIComponent(apiKey)}` : path;
    }
    function pill(text, kind = "") {
      return `<span class="pill ${kind}">${escapeHtml(text)}</span>`;
    }
    function fmtSeconds(seconds) {
      const n = Number(seconds || 0);
      if (!n) return "0s";
      const m = Math.floor(n / 60);
      const s = Math.round(n % 60);
      return m ? `${m}m ${s}s` : `${s}s`;
    }
    function preview(text, limit = 150) {
      const clean = String(text || "").replace(/\\s+/g, " ").trim();
      return clean.length > limit ? clean.slice(0, limit - 3) + "..." : clean;
    }
    async function getJson(path) {
      const res = await fetch(path, { headers });
      if (!res.ok) throw new Error(`${res.status} ${res.statusText}`);
      return res.json();
    }
    function setTab(tab) {
      state.tab = tab;
      document.getElementById("tab-learners").setAttribute("aria-selected", tab === "learners");
      document.getElementById("tab-calls").setAttribute("aria-selected", tab === "calls");
      renderQueue();
    }
    async function loadData() {
      queue.innerHTML = `<div class="empty">Loading...</div>`;
      const q = encodeURIComponent(search.value.trim());
      try {
        const [learners, calls] = await Promise.all([
          getJson(`/admin/learners?limit=40${q ? `&q=${q}` : ""}`),
          getJson(`/admin/calls?limit=40${q ? `&q=${q}` : ""}`),
        ]);
        state.learners = learners.items || [];
        state.calls = calls.items || [];
        renderQueue();
      } catch (err) {
        queue.innerHTML = `<div class="error">Could not load review data: ${escapeHtml(err.message)}</div>`;
      }
    }
    function renderQueue() {
      const items = state.tab === "learners" ? state.learners : state.calls;
      if (!items.length) {
        queue.innerHTML = `<div class="empty">No ${state.tab} found.</div>`;
        return;
      }
      queue.innerHTML = items.map(item => state.tab === "learners" ? learnerRow(item) : callRow(item)).join("");
      queue.querySelectorAll("[data-learner]").forEach(el => el.addEventListener("click", () => openLearner(el.dataset.learner)));
      queue.querySelectorAll("[data-call]").forEach(el => el.addEventListener("click", () => openCall(el.dataset.call)));
    }
    function learnerRow(item) {
      const current = item.effective_state || {};
      const calling = item.calling || {};
      const active = state.selectedLearner === item.id ? " active" : "";
      return `<div class="row${active}" data-learner="${escapeHtml(item.id)}">
        <div class="row-title">
          <span>${escapeHtml(item.name || "Unnamed learner")}</span>
          ${pill(`M${current.current_module ?? "?"}`)}
        </div>
        <div class="meta">${escapeHtml(item.phone_number || item.phone_number_normalized || "no phone")} · ${escapeHtml(current.course || "course?")} · ${escapeHtml(current.active_skill || "skill?")}</div>
        <div class="meta">${calling.recent_call_count || 0} recent calls · ${fmtSeconds(calling.recent_call_seconds)} · next: ${escapeHtml(preview(current.next_step || ""))}</div>
      </div>`;
    }
    function callRow(item) {
      const flags = item.quality_flags || [];
      const active = state.selectedCall === item.call_uuid ? " active" : "";
      const flagKind = flags.length ? "warn" : "good";
      return `<div class="row${active}" data-call="${escapeHtml(item.call_uuid)}">
        <div class="row-title">
          <span>${escapeHtml(item.phone_number || "unknown")}</span>
          ${pill(item.end_reason || "unknown", flagKind)}
        </div>
        <div class="meta">${escapeHtml(item.call_uuid)} · ${fmtSeconds(item.duration_seconds)} · ${item.user_turns || 0} child turns · ${item.turn_count || 0} review clips</div>
        <div class="meta">${flags.length ? escapeHtml(flags.join(", ")) : "No quality flags"}</div>
      </div>`;
    }
    async function openLearner(id) {
      state.selectedLearner = id;
      state.selectedCall = "";
      renderQueue();
      detailTitle.textContent = "Learner";
      detailStatus.textContent = "Loading";
      detail.innerHTML = `<div class="empty">Loading learner...</div>`;
      try {
        const data = await getJson(`/admin/learners/${encodeURIComponent(id)}?limit=20`);
        renderLearnerDetail(data.student || {});
      } catch (err) {
        detail.innerHTML = `<div class="error">Could not load learner: ${escapeHtml(err.message)}</div>`;
      }
    }
    function renderLearnerDetail(student) {
      const current = student.effective_state || {};
      const lit = current.literacy || {};
      const calling = student.calling || {};
      detailStatus.innerHTML = `${pill(current.course || "course?")} ${pill(`M${current.current_module ?? "?"}`)} ${pill(`scaffold ${current.scaffold_depth ?? 0}`, current.scaffold_depth ? "warn" : "good")}`;
      detail.innerHTML = `<div class="stack">
        <div class="grid">
          ${kv("Name", student.name || "Unnamed")}
          ${kv("Phone", student.phone_number || student.phone_number_normalized || "")}
          ${kv("Sessions", student.total_sessions || 0)}
          ${kv("Recent call time", fmtSeconds(calling.recent_call_seconds))}
          ${kv("Numeracy position", `Module ${current.current_module ?? "?"}, Week ${current.current_week ?? "?"}, Lesson ${current.current_lesson ?? "?"}`)}
          ${kv("Literacy position", `Module ${lit.current_module ?? "?"}, Week ${lit.current_week ?? "?"}, Lesson ${lit.current_lesson ?? "?"}`)}
          ${kv("Active skill", current.active_skill || "")}
          ${kv("Next step", current.next_step || "")}
          ${kv("Wrong streak", current.wrong_streak ?? 0)}
          ${kv("Scaffold depth", current.scaffold_depth ?? 0)}
        </div>
        <div>
          <h3>Recent Calls And Lessons</h3>
          <div class="list">${(student.recent_sessions || []).map(session => sessionRow(session)).join("") || `<div class="empty">No sessions.</div>`}</div>
        </div>
      </div>`;
      detail.querySelectorAll("[data-open-call]").forEach(el => el.addEventListener("click", () => openCall(el.dataset.openCall)));
    }
    function sessionRow(session) {
      return `<div class="row" ${session.call_sid ? `data-open-call="${escapeHtml(session.call_sid)}"` : ""}>
        <div class="row-title">
          <span>${escapeHtml(session.created_at || "session")}</span>
          ${pill(fmtSeconds(session.duration_seconds))}
        </div>
        <div class="meta">${escapeHtml(session.summary || "")}</div>
        <div class="meta">${session.child_turns || 0} child turns · ${session.sabi_turns || 0} Sabi turns · ${session.has_learning_state_snapshot ? "state snapshot" : "no state snapshot"}</div>
        <div class="meta">Last child: ${escapeHtml(session.last_child_turn_preview || "")}</div>
      </div>`;
    }
    async function openCall(id) {
      state.selectedCall = id;
      state.selectedLearner = "";
      renderQueue();
      detailTitle.textContent = "Call";
      detailStatus.textContent = "Loading";
      detail.innerHTML = `<div class="empty">Loading call...</div>`;
      try {
        const call = await getJson(`/admin/calls/${encodeURIComponent(id)}`);
        renderCallDetail(call);
      } catch (err) {
        detail.innerHTML = `<div class="error">Could not load call: ${escapeHtml(err.message)}</div>`;
      }
    }
    function renderCallDetail(call) {
      const progression = call.learning_progression || {};
      detailStatus.innerHTML = `${pill(call.end_reason || "unknown", (call.quality_flags || []).length ? "warn" : "good")} ${pill(`${call.turn_count || 0} turn clips`)}`;
      detail.innerHTML = `<div class="stack">
        <div class="grid">
          ${kv("Call ID", call.call_uuid)}
          ${kv("Phone", call.phone_number)}
          ${kv("Duration", fmtSeconds(call.duration_seconds))}
          ${kv("Student ID", call.student_id || "")}
          ${kv("Quality flags", (call.quality_flags || []).join(", ") || "none")}
          ${kv("Progression evidence", progression.has_turn_evidence ? "turn evidence available" : "full-call audio only for this older call")}
        </div>
        ${recordingBlock(call.recordings || {})}
        <div>
          <h3>Turn Evidence</h3>
          ${(call.turns || []).length ? `<div class="list">${call.turns.map(turnBlock).join("")}</div>` : `<div class="empty">No per-turn clips on this call. Calls made after this deploy will show child clip, STT transcript, normalized transcript, Sabi text, Sabi audio, and bump-down state here.</div>`}
        </div>
      </div>`;
    }
    function recordingBlock(recordings) {
      const items = [
        ["Caller + Sabi", recordings.mixed],
        ["Caller side", recordings.rx_network],
        ["Sabi side", recordings.tx_sabi],
      ];
      return `<div>
        <h3>Full Call Recordings</h3>
        <div class="audio-grid">${items.map(([label, item]) => audioBox(label, item && item.audio_endpoint, item && item.exists)).join("")}</div>
      </div>`;
    }
    function audioBox(label, endpoint, exists) {
      return `<div class="kv">
        <div class="kv-label">${escapeHtml(label)}</div>
        ${exists ? `<audio controls preload="none" src="${escapeHtml(audioUrl(endpoint))}"></audio>` : `<div class="meta">No audio file.</div>`}
      </div>`;
    }
    function turnBlock(turn) {
      const user = turn.user || {};
      const assistant = turn.assistant || {};
      const before = turn.learning_state_before || {};
      const after = turn.learning_state_after || {};
      const bump = turn.bump_down || {};
      return `<div class="turn">
        <div class="row-title">
          <span>Turn ${turn.turn_index}</span>
          <span>${(turn.flags || []).map(flag => pill(flag, flag.includes("low") || flag.includes("retry") ? "warn" : "")).join(" ")} ${bump.detected ? pill("bump-down/scaffold", "warn") : ""}</span>
        </div>
        <div class="turn-grid">
          <div>
            <h3>Child Audio And STT</h3>
            ${user.has_audio ? `<audio controls preload="none" src="${escapeHtml(audioUrl(user.audio_endpoint))}"></audio>` : `<div class="meta">No child clip.</div>`}
            <div class="quote">STT: ${escapeHtml(user.stt_transcript || "")}</div>
            <div class="quote">Lesson text: ${escapeHtml(user.normalized_transcript || "")}</div>
            <div class="meta">Confidence: ${escapeHtml(user.stt_confidence ?? "")} · Clip: ${fmtSeconds(user.audio_seconds)}</div>
          </div>
          <div>
            <h3>Sabi Response And TTS</h3>
            ${assistant.has_audio ? `<audio controls preload="none" src="${escapeHtml(audioUrl(assistant.audio_endpoint))}"></audio>` : `<div class="meta">No Sabi clip.</div>`}
            <div class="quote">${escapeHtml(assistant.text || "")}</div>
            <div class="meta">TTS text changed: ${assistant.tts_text_changed ? "yes" : "no"} · Clip: ${fmtSeconds(assistant.audio_seconds)}</div>
          </div>
        </div>
        <div class="grid">
          ${kv("Before", `M${before.current_module ?? "?"} · ${before.active_skill || ""} · scaffold ${before.scaffold_depth ?? 0}`)}
          ${kv("After", `M${after.current_module ?? "?"} · ${after.active_skill || ""} · scaffold ${after.scaffold_depth ?? 0}`)}
          ${kv("Bump-down reasons", (bump.reasons || []).join(", ") || "none")}
          ${kv("Teacher move", (bump.to || {}).teacher_move || (after.scaffold_ladder || {}).teacher_move || "")}
        </div>
      </div>`;
    }
    function kv(label, value) {
      return `<div class="kv"><div class="kv-label">${escapeHtml(label)}</div><div class="kv-value">${escapeHtml(value)}</div></div>`;
    }
    document.getElementById("tab-learners").addEventListener("click", () => setTab("learners"));
    document.getElementById("tab-calls").addEventListener("click", () => setTab("calls"));
    document.getElementById("refresh").addEventListener("click", loadData);
    search.addEventListener("keydown", event => { if (event.key === "Enter") loadData(); });
    loadData();
  </script>
</body>
</html>"""
