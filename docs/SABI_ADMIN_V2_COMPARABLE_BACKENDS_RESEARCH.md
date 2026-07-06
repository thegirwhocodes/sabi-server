# Sabi Admin v2 — Comparable-Backend Research (2026-06-29)

**Companion to:** [SABI_SYSTEM_DESIGN_2026-06-29.md](./SABI_SYSTEM_DESIGN_2026-06-29.md)
**Source:** Multi-agent research workflow `wx5qq5dr9` (9 agents, 997K tokens, 518 tool calls)
**Scope:** Twilio Console + Voice Insights, Africa's Talking, Supabase Studio, contact-center QA, learning analytics, AI conversation review, modern ops consoles, African edtech ops
**Status:** Reference — drives the curriculum-app/app/admin/ Next.js implementation

This document has two halves: (1) the **Design Language Brief** (the consolidated Sabi-tailored output that maps directly onto the admin pages we will build), and (2) the **Per-comparable deep dives** (one product family per section — full UI element lists, filter/column rosters, source URLs).

---

# Part 1 — Sabi Admin v2 Design Language Brief

# Sabi Admin v2 — Design Language Brief

## 1. Overall layout

**App shell:** Next.js 16 App Router with route group `app/admin/(shell)/` owning the persistent chrome. Three fixed regions on every authenticated page:

- **Topbar (48px tall, sticky).** Left to right: Sabi spark mark + "Sabi Admin" wordmark (serif, gold), breadcrumb with chevron-dropdowns for sideways navigation (Stripe + Vercel pattern), centered empty space, right cluster: environment pill, global Cmd-K trigger, live-mode toggle, notifications bell, Clerk `<UserButton>`. Environment pill is gold-on-black for production, muted-amber-on-black for staging, neutral grey for sandbox (Stripe's safety pattern, restyled to Sabi gold rather than orange).
- **Left sidebar (240px expanded / 56px collapsed, resizable, hide-able via `[`).** shadcn `sidebar-07` block. Uses scoped `--sidebar-*` tokens so it sits one shade darker than the canvas (Linear "don't compete for attention" move). Items: **Today** (home dashboard), **Calls**, **Learners**, **Curriculum**, **Kids** (low-priority section), **Reports**, **Inbox**, **Settings**. Persists collapse state to a cookie (`sabi-sidebar`).
- **Main canvas.** All pages render here. Detail pages are **full routes** (not drawers) when they're hostable in URL state and shareable; **right Sheet drawers** are used only for transient edits and quick-look row inspection from a list. (Twilio + Stripe rule.)

**Drawer vs page rule (project-wide):**
- Full page = something that has its own URL someone will paste into Slack: `/admin/calls/[id]`, `/admin/learners/[id]`, `/admin/curriculum`.
- Right Sheet drawer = quick row peek that doesn't take you out of the list (`?learnerId=...` URL-keyed so it's still shareable), inline edits ("flag for review", "edit learner metadata"), ratchet-through navigation in QA mode (Helicone pattern: prev/next inside the open drawer).
- Modal = destructive confirmation only.

**Persistent right rail (`/admin/inbox` and `/admin/calls` only):** Optional 320px live activity feed (Duolingo for Schools pattern) — last 50 events streamed via Supabase Realtime, collapsible to icon strip. Off by default outside ops pages.

**Density:** Comfortable default (48px table rows), Compact toggle (32px, `whitespace-nowrap`) stored per-user in Clerk `publicMetadata.density`.

**Responsive:** Sidebar becomes a floating bottom bar on `<sm` (Vercel pattern). Three-pane call-detail collapses to stacked accordion on `<md` with audio player pinned to bottom.

---

## 2. Design tokens

Defined once in `app/globals.css` via Tailwind v4 `@theme` directive, OKLCH-based for perceptual uniformity (Linear LCH pattern).

### 2.1 Color tokens

**Surface stack** (dark mode = canonical, light mode = inverse):

```css
@theme {
  /* Sabi brand */
  --color-sabi-gold: oklch(0.78 0.13 82);          /* #D4A537 */
  --color-sabi-gold-hover: oklch(0.84 0.13 82);
  --color-sabi-gold-active: oklch(0.72 0.13 82);
  --color-sabi-gold-muted: oklch(0.78 0.13 82 / 0.12);
  --color-sabi-ink: oklch(0.13 0 0);               /* near-black canvas */
  --color-sabi-paper: oklch(0.99 0 0);             /* light mode canvas */

  /* Surfaces - dark mode (default for Sabi admin) */
  --background: oklch(0.13 0 0);                   /* page */
  --surface: oklch(0.16 0 0);                      /* card */
  --surface-2: oklch(0.19 0 0);                    /* elevated card / popover */
  --surface-3: oklch(0.22 0 0);                    /* sheet / modal */

  /* Text */
  --foreground: oklch(0.98 0 0);                   /* primary */
  --foreground-2: oklch(0.78 0 0);                 /* secondary */
  --muted-foreground: oklch(0.62 0 0);             /* tertiary / labels */
  --meta-foreground: oklch(0.45 0 0);              /* timestamps, ids */

  /* Borders (depth via ring, not shadow - Supabase pattern) */
  --border-soft: oklch(0.22 0 0);
  --border: oklch(0.27 0 0);
  --border-strong: oklch(0.34 0 0);

  /* Primary = Sabi gold for CTAs and active states ONLY */
  --primary: var(--color-sabi-gold);
  --primary-foreground: oklch(0.13 0 0);

  /* Operational accent = restrained green, never compete with gold */
  --accent-green: oklch(0.72 0.16 152);            /* success / completed */
  --accent-green-muted: oklch(0.72 0.16 152 / 0.12);

  /* Semantic */
  --color-success: oklch(0.72 0.16 152);
  --color-warning: oklch(0.78 0.16 70);
  --color-danger:  oklch(0.65 0.22 27);
  --color-info:    oklch(0.72 0.14 230);

  /* Status palette - shape+color pairs (see §2.6) */
  --status-completed: var(--color-success);
  --status-in-progress: var(--color-info);
  --status-flagged: var(--color-warning);
  --status-failed: var(--color-danger);
  --status-safety: oklch(0.62 0.25 12);            /* deeper red for safety escalations */
  --status-pending: var(--meta-foreground);

  /* Sidebar (dimmer than canvas - Linear) */
  --sidebar: oklch(0.11 0 0);
  --sidebar-foreground: var(--muted-foreground);
  --sidebar-primary: var(--color-sabi-gold);       /* active item */
  --sidebar-primary-foreground: oklch(0.13 0 0);
  --sidebar-accent: oklch(0.18 0 0);               /* hover */
  --sidebar-border: var(--border-soft);

  /* Waveform / speaker tracks */
  --speaker-sabi: var(--color-sabi-gold);          /* gold */
  --speaker-child: oklch(0.88 0 0);                /* off-white */
  --speaker-teacher: oklch(0.72 0.14 230);         /* info-blue, only if joined */
  --speaker-overlap: oklch(0.65 0.22 27 / 0.45);   /* cross-talk = translucent red */
  --speaker-silence: oklch(0.78 0.16 70 / 0.25);   /* >2s silence = translucent amber */

  /* Chart palette */
  --chart-1: var(--color-sabi-gold);
  --chart-2: var(--accent-green);
  --chart-3: var(--color-info);
  --chart-4: var(--color-warning);
  --chart-5: oklch(0.72 0.14 295);                 /* purple for fifth series */
}

/* Light mode = inverse */
:root[data-theme="light"] {
  --background: var(--color-sabi-paper);
  --surface: oklch(0.97 0 0);
  --surface-2: oklch(0.95 0 0);
  --surface-3: oklch(0.93 0 0);
  --foreground: oklch(0.13 0 0);
  --foreground-2: oklch(0.30 0 0);
  --muted-foreground: oklch(0.45 0 0);
  --meta-foreground: oklch(0.58 0 0);
  --border-soft: oklch(0.93 0 0);
  --border: oklch(0.87 0 0);
  --border-strong: oklch(0.78 0 0);
  --sidebar: oklch(0.97 0 0);
  --sidebar-accent: oklch(0.93 0 0);
  --speaker-child: oklch(0.32 0 0);
}
```

**Rules:**
- Gold (`--primary`) appears only on: primary CTA buttons, active sidebar item, current playhead, Sabi speaker waveform, "Mastery Achieved" star badge. Never as a row hover fill (use `--sabi-gold-muted` at 12% if a tint is needed).
- Green is operational (completed, success), never brand.
- Red is reserved for danger + safety escalations. Warnings use amber. No category color is also a status color.
- Status colors must always be paired with a shape (see §2.6).

### 2.2 Typography

```css
@theme {
  --font-serif: "Roca", "Source Serif Pro", Georgia, serif;          /* Sabi wordmark + page H1 */
  --font-sans: "Geist", "Inter", system-ui, sans-serif;              /* UI body */
  --font-mono: "Geist Mono", "JetBrains Mono", Menlo, monospace;     /* IDs, timestamps, JSON */

  /* Sizes - same scale as Geist */
  --text-xs: 12px;
  --text-sm: 14px;     /* default body / table cells / sidebar */
  --text-base: 16px;
  --text-lg: 18px;
  --text-xl: 22px;
  --text-2xl: 28px;
  --text-3xl: 36px;

  --leading-tight: 1.1;
  --leading-snug: 1.3;
  --leading-normal: 1.5;
}
```

**Role assignments:**
- `font-serif` weight 600: page H1 only (each route's title bar). One serif per screen — keeps the "premium official document" feel without going decorative.
- `font-sans` weight 500: H2, sidebar items, button labels, table headers.
- `font-sans` weight 400: body, table cells, descriptions.
- `font-mono` 13/14: phone numbers, call UUIDs, transcript timestamps, learner IDs, JSON viewers.
- All caps + tracking is forbidden except inside `<TimecodeChip>` (e.g., `[02:14]`).

### 2.3 Spacing

8px base. Tokens `--space-1` (4px) through `--space-12` (48px). Form field internal padding `--space-3`, gap between fields `--space-4`, section padding `--space-8`.

### 2.4 Radii

```css
--radius-xs: 4px;     /* badges, chips, pill stems */
--radius-sm: 6px;     /* buttons, inputs */
--radius-md: 8px;     /* cards, popover */
--radius-lg: 12px;    /* sheet, modal */
--radius-pill: 9999px; /* status badges */
```

### 2.5 Elevation

**No drop shadows in dark mode.** Depth via ring borders (Supabase rule).

```css
--elev-flat: none;
--elev-ring: 0 0 0 1px var(--border);
--elev-raised: 0 0 0 1px var(--border-strong), 0 4px 24px oklch(0 0 0 / 0.5); /* modal/popover only */
```

### 2.6 Status glyphs (shape+color, accessibility-grade)

Always paired so colorblind users + printed reports work:

| Status | Color | Lucide icon | Shape |
|---|---|---|---|
| Completed | `--status-completed` | `CircleCheck` | circle |
| In progress | `--status-in-progress` | `CircleDot` | circle |
| Flagged for review | `--status-flagged` | `Triangle` | triangle |
| Failed | `--status-failed` | `Square` | square |
| Safety escalation | `--status-safety` | `Octagon` | octagon |
| Pending / queued | `--status-pending` | `Circle` outline | circle outline |
| Scheduled | `--muted-foreground` | `Diamond` | diamond |

One `<StatusBadge status="…" />` component reused everywhere — list cells, detail headers, timeline events. Forbid raw colors in feature code.

### 2.7 Motion

```css
--motion-fast: 150ms;
--motion-base: 200ms;
--motion-slow: 320ms;
--ease-standard: cubic-bezier(0.2, 0, 0, 1);
```

Allowed motion: drawer slide, modal fade, sidebar collapse, accordion expand, table skeleton shimmer (only when `prefers-reduced-motion: no-preference`). No spring physics. No celebratory animation on the admin surface — that's reserved for the kids' lesson channel.

Focus ring: `0 0 0 2px color-mix(in oklab, var(--primary), transparent 50%)` — translucent gold halo.

---

## 3. shadcn/ui component map

| Sabi page / surface | shadcn primitive | Custom wrapper | Notes |
|---|---|---|---|
| App shell | `sidebar-07` (block) | `<AdminShell>` | Clerk `OrganizationSwitcher` replaces TeamSwitcher header |
| Topbar | `NavigationMenu` + `Breadcrumb` | `<AdminTopbar>` | Breadcrumb segments are `DropdownMenu` for sideways nav |
| Environment pill | `Badge` | `<EnvBadge mode={env}>` | Mode = `production | staging | sandbox` |
| Global search | `CommandDialog` | `<SabiCommandPalette>` | ⌘K, alt ⌘J. Sections: Navigate / Search / Actions / Help |
| Tabs (Activity/Skills/Mastery, Messages/Turns/Details) | `Tabs` | `<SabiTabs>` | Hotkeys M/T/D in QA mode via `useHotkeys` |
| Data tables | `DataTable` (TanStack v8) | `<SabiTable>` | Faceted filters, URL-state via `nuqs`, density via `data-density` attr |
| Filter bar | `Popover` + `Command` chips | `<FilterBar>` | Stripe DSL parser `parseSabiQuery()`; chips render parsed filters |
| Row drawer | `Sheet side="right"` | `<RowSheet>` | Prev/Next ratchet (Helicone); URL-keyed via `?id=` |
| Detail page panels | `ResizablePanelGroup` | `<ThreePane>` | Persists sizes via cookie |
| Status pill | `Badge` | `<StatusBadge>` | See §2.6 |
| Audio waveform | `Card` wrapping `wavesurfer.js` | `<DualWaveform>` | Two stacked tracks, shared scrubber, mute toggles, talk-% labels |
| Transcript turn list | `ScrollArea` + custom rows | `<TranscriptList>` | Auto-scroll-sync with playhead, click-to-seek |
| Evidence cards (per-turn) | `Card` | `<TurnEvidenceCard>` | STT / LLM / TTS columns |
| Annotation row | `Card` + `Toggle` + `Select` | `<AnnotationStrip>` | Keyboard 1-5 + s/c |
| Comments | `Card` + `Textarea` | `<TimestampComments>` | Anchored to playhead, glow on cross |
| Snippet/clip | Radix two-thumb `Slider` over waveform | `<ClipHandles>` | Gold-yellow drag handles |
| Empty state | (none) | `<EmptyState>` | Icon + active-voice title + 1-line desc + primary CTA |
| Inline notifications | `sonner` | global | Top-right, scale dismiss timing to severity |
| Audit log entries | `Collapsible` row | `<AuditRow>` | Click to expand metadata |
| Kebab row actions | `DropdownMenu` | `<RowActions>` | Quick: View, Listen, Copy ID, Flag, Open in new tab |
| Bulk action toolbar | `Card` sticky | `<BulkBar>` | Appears when `selection.length > 0` |
| Filter "saved views" | `Combobox` | `<SavedViews>` | Persists per Clerk user |
| Skeleton loaders | `Skeleton` | per-route `<*Skeleton>` | Match real layout; live in `loading.tsx` |
| Charts | `recharts` via shadcn `Chart` | `<SabiChart>` | Color from `--chart-1..5` only |
| Curriculum map | `@xyflow/react` (React Flow) | `<CurriculumGraph>` | Two side-by-side graphs (literacy / numeracy) |
| Right-rail activity log | `ScrollArea` | `<LiveActivityRail>` | Supabase Realtime, paused-on-hover |
| Audio download buttons | `DropdownMenu` | `<AudioDownload>` | MP3 32kbps / WAV 128kbps (Twilio pattern) |
| Cohort / org context | Clerk `OrganizationSwitcher` | wrapped | Hierarchy label shown as breadcrumb |

---

## 4. Learners page

**Route:** `/admin/learners`

### 4.1 Identity de-dup rules (the most-cited bug)

Backend consumes `GET /admin/learners`. The page applies these display rules **client-side on the returned list** so the API contract is preserved:

1. **One row per `student_id`.** Multiple records with the same `student_id` collapse — display the most recently updated row.
2. **Phone-as-identity:** any two `student_id`s that share a normalized E.164 phone collapse into a single row, the one with `consent_status = 'active'` and the more recent `last_call_at` winning. Show a small `chain` icon in the Phone cell as a tooltip: "2 underlying records merged."
3. **Hide rows with no phone AND no parent contact** — these are stub records the system created but never fully provisioned. Display a dismissible banner at top: "12 incomplete learner records hidden. [Show all]".
4. **Hide rows named "Unnamed learner", "Test", "Demo", and any row where the registered phone matches `+1.*` (Naomi's US demo number) or numbers in the configured `internal_test_numbers` list** — backed by a `Settings → Demo numbers` allowlist. Banner: "3 demo/test learners hidden. [Show all]".
5. **Display name fallback chain:** `preferred_name → first_name + last_name → guardian_name + " (guardian)" → "Learner " + last_4(phone)`. Never display the string "Unnamed learner".

### 4.2 Columns (widths, alignment)

Default 7 columns. Density-aware row height (48 / 32px).

| # | Column | Width | Align | Source | Notes |
|---|---|---|---|---|---|
| 1 | `[ ]` selection checkbox | 40px | center | — | Sticky left |
| 2 | **Name** | 220px | left | display-name chain | Bold; click → `/admin/learners/[id]`; if merged shows `chain` icon |
| 3 | **Phone** | 160px | left mono | `phone_e164` | Format `+234 7012 345 678`; copy-on-hover |
| 4 | **Cohort / Source** | 160px | left | `cohort_name` or `source` | Pill: "Lagos pilot", "CcHub", "Bakame" |
| 5 | **Literacy level** | 110px | center | `current_literacy_level` | Mini level chip (L1–L8) |
| 6 | **Numeracy level** | 110px | center | `current_numeracy_level` | Same |
| 7 | **Last call** | 150px | left | `last_call_at` | Relative ("2 hours ago"); hover for exact |
| 8 | **Calls (7d)** | 90px | right | `calls_last_7d` | With minutes hint: "5 / 23 min" |
| 9 | **Status** | 140px | left | derived | `<StatusBadge>`: Active / Inactive / Flagged / Needs follow-up |
| 10 | **`⋯`** | 56px | center | — | Sticky right |

Columns 8-9 hidden in Compact density. Column visibility menu in toolbar (`Columns` button). Manual reorder via drag handle in column header.

### 4.3 Filter bar

Above the table, single row of chips + DSL search + saved views combobox.

**Default chip filters:**
- Cohort (multi-select)
- Literacy level (range)
- Numeracy level (range)
- Last call (date range; presets: today, 7d, 30d, all)
- Status (multi-select)
- Consent (active / pending / declined)
- School status (in-school / out-of-school / unknown)

**`+ Add filters`** opens a Popover with all filterable columns.

**DSL search bar** (Stripe pattern). Examples:
- `cohort:lagos level:>L3 last_call:<7d`
- `phone:7012345678`
- `status:flagged -cohort:demo`

Operators: `=` implicit, `>`, `<`, `..` (range), `is:`, `-` (negate), quotes for exact.

**Sort UX (this is a feature, not a pill):**
- Click any column header → ascending → descending → none cycle, with chevron `↑ / ↓` glyph on the active column.
- Active sort renders as a dedicated chip *adjacent to the column header*, not inside the filter row. Looks like a real sort, doesn't get confused for a filter.
- Default sort: `last_call_at DESC` (newest first). Default sort chip in column header reads "**Newest first**" as a label with caret, not as a filter pill.

**Saved views combobox** (top-right of toolbar): "My active Lagos kids", "Needs follow-up", "Out-of-school in Kano". Per-user Clerk metadata.

### 4.4 Pagination

Server-side cursor pagination on `(last_call_at, student_id)`. Footer: `Prev` `Next` + "Showing 1-50 of 412 learners" + page size selector (25 / 50 / 100). URL: `?cursor=…&size=50`.

### 4.5 Bulk actions

When ≥1 row selected, sticky `<BulkBar>` slides in above the table:
- **Export selected as CSV** — columns match displayed columns + transcript URLs
- **Tag**: opens combobox to add/remove tags
- **Assign to reviewer** — Clerk org member picker
- **Trigger outbound call** — calls `POST /admin/asterisk/direct-call` per row (with confirm modal)
- **Mark as inactive / safety hold**

### 4.6 Empty state

`<EmptyState>` centered:
- Icon: lucide `Users` 48px in `--muted-foreground`
- Title (serif, 22px): **"No learners yet"**
- Description: "Learners appear here once their first call lands. Your inbound number is `+234 …`. [Copy number]"
- Primary CTA: `Trigger a test call` (opens the direct-call modal)
- Secondary: `View call setup docs →`

When filtered to zero: title **"No learners match these filters"**, description "Try removing a filter or change the date range.", CTA `Clear all filters`.

### 4.7 Density

`Comfortable` default. `Compact` toggle in toolbar (icon-only button, persists to user metadata). Compact drops row to 32px, drops Calls(7d) + Status columns by default.

---

## 5. Calls page

**Route:** `/admin/calls`

Same skeleton as Learners (filter bar + table + drawer/page split) — operators learn it once. Backed by `GET /admin/calls`.

### 5.1 Columns

| # | Column | Width | Align | Notes |
|---|---|---|---|---|
| 1 | `[ ]` | 40px | center | — |
| 2 | **Started** | 160px | left mono | `2026-06-29 14:32` + relative tooltip |
| 3 | **Learner** | 200px | left | Display-name chain + small phone underneath in `--meta-foreground` mono. Two-line cell. Click → learner page. |
| 4 | **Phone** | 150px | left mono | `+234 7012 345 678` |
| 5 | **Lesson** | 220px | left | "Phonics L3 · Letter F" with a tiny lesson-code pill |
| 6 | **Duration** | 80px | right mono | `4:21` |
| 7 | **Status** | 140px | left | `<StatusBadge>` |
| 8 | **STT provider** | 110px | left | Pill: Whisper / Intron / Deepgram |
| 9 | **Quality flags** | 220px | left | See §5.2 — never overflows |
| 10 | **Cost** | 90px | right mono | `₦128` (or `$0.04`) |
| 11 | **`⋯`** | 56px | center | View, Listen, Download MP3/WAV, Re-run STT, Flag, Open in new tab |

**Cell-overflow rule for "Quality flags" column:** the cell renders **at most 2 pills inline**; remainder collapses into a `+N more` chip that opens a Popover with the full list. Each pill is a `<StatusBadge variant="quality">` with `max-w-[180px] truncate`. Long flag strings never break the row.

**Two-line learner cell** keeps the table from needing a separate Phone column to repeat the same identity; columns 3 and 4 are both shown only when DSL search has matched on phone (so the operator can see what they searched for).

### 5.2 Quality flag → human-language map

A single source of truth at `lib/calls/quality-flags.ts` translates backend `quality_flag` codes into operator-friendly text. Every flag carries: `code`, `label` (short, pill text), `description` (tooltip), `severity`, `category`.

| Backend code | Pill label | Severity | Category | Tooltip |
|---|---|---|---|---|
| `stt_low_confidence` | "Hard to hear" | warn | stt | "Speech-to-text was uncertain — listen to confirm." |
| `stt_empty` | "Silent turn" | warn | stt | "STT returned nothing for a child turn." |
| `stt_overlap_detected` | "Talk-over" | info | stt | "Child spoke while Sabi was still speaking." |
| `stt_provider_fallback` | "Backup STT used" | info | stt | "Primary STT failed; switched to backup mid-call." |
| `tts_truncated` | "Cut off" | warn | tts | "Sabi's response was cut short by TTS." |
| `tts_wrong_voice` | "Wrong voice" | warn | tts | "TTS used a fallback voice instead of Sabi." |
| `tts_provider_fallback` | "Backup TTS used" | info | tts | "Primary TTS failed; switched to backup." |
| `latency_first_audio_high` | "Slow to respond" | warn | latency | "Time to first audio over 1.5s." |
| `latency_llm_high` | "Slow thinking" | warn | latency | "LLM took >2s to reply." |
| `audio_packet_loss` | "Bad connection" | warn | network | "Packet loss detected." |
| `audio_one_way` | "One-way audio" | error | network | "Only one side of the call was audible." |
| `guardrail_safety_redirect` | "Safety redirect" | error | safety | "Sabi redirected after a safety guardrail." |
| `guardrail_off_topic` | "Off topic" | info | guardrail | "Conversation drifted from the lesson." |
| `lesson_abandoned` | "Lesson abandoned" | warn | lesson | "Child hung up mid-lesson." |
| `lesson_completed` | "Lesson complete" | success | lesson | "Lesson finished as designed." |
| `child_no_response` | "No response" | warn | engagement | "Child didn't answer prompts." |
| `repeat_correct` | "Repeated correct" | info | engagement | "Child repeated the correct answer 3+ times." |
| `multiple_voices` | "Multiple voices" | info | identity | "More than one voice detected — phone may be shared." |
| `consent_missing` | "Consent missing" | error | compliance | "No consent on record for this learner." |
| `cost_outlier` | "Costly call" | warn | cost | "Cost above the 95th percentile." |

Component: `<QualityFlagPill code="…" />` reads from the map; never accept a raw string.

### 5.3 Filter bar

Same chips/DSL/saved-views pattern as Learners. Default chips:

- Date range (today / 24h / 7d / 30d / custom)
- Status (Completed / In progress / Failed / Flagged / Safety)
- Course / Lesson (combobox grouped by literacy/numeracy)
- STT provider (Whisper / Intron / Deepgram)
- Quality flag (multi-select from the map above)
- Cohort
- Name (free text → DSL `name:`)
- Phone (free text → DSL `phone:`)

DSL examples:
- `lesson:phonics-l3 flag:guardrail_safety_redirect`
- `provider:intron duration:>180`
- `cohort:lagos status:flagged date:7d`

### 5.4 Sort

Default `started_at DESC` — "Newest first" labeled in the column header, not as a filter chip. Sortable columns: Started, Duration, Cost. Quality flags, Status, Lesson are filter-only.

### 5.5 Bulk actions

- Export selected as CSV (includes audio download URLs)
- Re-run STT with provider X
- Mark as reviewed
- Add tag
- Open feedback intake (for cases where a parent reported an issue and you're tagging calls)

### 5.6 Empty state

Title: **"No calls in the last 24 hours"** (when date filter active) or **"No calls yet"** (when truly empty). Body explains how to trigger a test call.

### 5.7 Live mode

Toggle in toolbar: "Live" pill with a pulsing dot. When on, new calls appear with a "(N new) load" pill at top of the table (Helicone anti-jitter pattern) — operator opts in to insert them.

---

## 6. Learner detail — full page

**Route:** `/admin/learners/[student_id]` — **full page**, not drawer. Rationale: this is the page Naomi will paste into Slack to discuss a specific child; bookmarkable, deep-linkable, hostable in audit logs. The drawer-version (`/admin/learners?learnerId=…`) opens a quick-look Sheet when an operator clicks a row in the index, with a "Open full page →" link.

Backed by `GET /admin/learners/{student_id}`. Also calls `GET /admin/learners/by-phone` when the URL is a phone instead of an id.

### 6.1 Header

Sticky, 96px tall, surface `--surface-2`:

- Left: serif 28px display name + small mono phone underneath
- Right cluster: `<StatusBadge>`, `Last call: 2 hours ago`, action buttons: **Call now** (primary, triggers `direct-call`), **Send SMS**, **Flag**, kebab `⋯` (Export profile / Merge with… / Mark inactive / Delete)

### 6.2 Section layout (two-column on `>lg`, stacked on `<lg`)

**Left column (35%):**

- **Identity card**
  - Display name, preferred pronunciation (if collected)
  - Phone (E.164) with copy
  - Other associated phones (if any, with merged-record provenance)
  - Consent status: badge + "Verified by Sonia on 2026-05-14"
  - Parent/guardian: name + phone + relationship
  - School status: In-school / Out-of-school / Unknown — with last-confirmed date
  - Cohort / source pill
  - Age (when collected)
  - Languages: Pidgin / English / Yoruba flags

- **Current placement card**
  - Literacy: Level **L3** · Module 2 · Week 4 · Lesson 3 ("Letter F sounds")
  - Numeracy: Level **L2** · Module 1 · Week 2 · Lesson 2 ("Counting 1–10")
  - Active skill: pill — "Phoneme blending: /f/ + vowel"
  - Next lesson: pill with `Trigger` button — "L3 · M2 · W4 · L4 — Letter F words"
  - Bump-down history: collapsible mini-list of moves (see §8.3)

- **Mastery snapshot card**
  - Correct attempts: 47
  - Needs-help attempts: 12
  - Wrong-streak: current 2 / max 5
  - Scaffold depth: current 2 / max 3 (with tooltip explaining scaffolding model)
  - Mini sparkline of last-30-day accuracy

- **Safety alerts card** (only renders if `alerts.length > 0`)
  - List of alerts with timestamp, code (mapped via quality-flag map), reviewer-acknowledged toggle, "Open call" link

**Right column (65%):**

- **Activity strip** — 7-day bar chart: calls per day with minutes overlaid. Reuses `<SabiChart>`.

- **Calls per week tile + Minutes per week tile** at top — two big numbers with WoW delta.

- **Recent conversations** table — last 20 calls for this learner. Columns: Started, Lesson, Duration, Status, Quality flags (max 1 pill + `+N`), `⋯`. Click row → `/admin/calls/[id]`. "View all calls →" link at footer with pre-applied filter.

- **Curriculum trajectory** — small embedded segment of the curriculum graph (§8) showing this learner's path: completed nodes filled gold, current node ringed gold, next nodes outlined. Click to open full curriculum view with this learner pre-selected.

- **Notes & annotations** — `<TimestampComments>` reused but anchored to the learner, not a call. Coordinator notes ("Sonia spoke to mom on WhatsApp, child has Tuesday/Thursday access only"), `@mention` org members.

### 6.3 Right-side drawer variant (when opened from list)

The Sheet variant collapses to: Identity card (top), Current placement card (middle), `Recent conversations` (bottom 5 only), and a sticky footer with `Open full page →`.

---

## 7. Call detail

**Route:** `/admin/calls/[call_uuid]` — **full page** (the same drawer rule as learners).

Backed by `GET /admin/calls/{call_uuid}`. Audio fetched from `GET /admin/calls/{call_uuid}/audio/{kind}` and `GET /admin/calls/{call_uuid}/turns/{turn_index}/audio/{role}`. Feedback (if present) from `GET /admin/feedback/{call_uuid}` and its audio from `GET /admin/feedback/{call_uuid}/audio`.

### 7.1 Three-pane layout (`<ThreePane>`)

`ResizablePanelGroup` horizontal, persisted sizes:

- **Left pane (28% default):** AI brief (Highlights / Outline / Ask anything placeholder)
- **Center pane (44% default):** Audio player + per-turn transcript and evidence cards
- **Right pane (28% default):** Annotation row + scorecard + comments + share & audit

Each pane has its own scroll. Right pane collapses to icon strip below `<lg`.

### 7.2 Header strip (sticky, full width above the three panes)

- Left: serif "Call · 2026-06-29 14:32" + breadcrumb `Calls / Lagos pilot / Amara O.`
- Middle: `<StatusBadge>` + duration `4:21` + cost `₦128`
- Right cluster: **Replay with edits** (opens prompt-fork sandbox), **Share** (Stripe-style modal with link expiry + audit), **Download** (MP3 / WAV / Transcript / Full JSON), **Flag**, kebab

### 7.3 Center pane — audio player

`<DualWaveform>` Card:

- **Two stacked tracks** (WaveSurfer.js):
  - Top: **Sabi** lane in `--speaker-sabi` (gold). Mute toggle left end, talk-% right end.
  - Bottom: **Child** lane in `--speaker-child` (off-white). Same controls.
- **Shared scrubber + playhead** in `--primary` (gold).
- **Overlay rectangles:**
  - Red translucent (`--speaker-overlap`) where both tracks have signal above threshold (cross-talk).
  - Amber translucent (`--speaker-silence`) where both are silent >2s.
- **Timeline marker rail above the waveform:** small lucide icons for time-stamped events (guardrail trip, correct answer, repeated mistake, long silence, lesson plan deviation, pronunciation flagged). Click marker → seeks.
- **Topic ribbons below the waveform:** color-coded segments per lesson phase (warm-up / introduce / practice / check / close).
- **Control bar:** Play/Pause · ±15s jump · **Speed dropdown 0.5× / 0.75× / 1× / 1.5× / 2×** (5 steps — avoid Twilio's 4-step omission of 0.75×) · scrubber · timecode `02:14 / 04:21` · Copy link with timestamp (URL embeds `?t=134`).
- **Audio source toggle group:** `Mixed | Child only | Sabi only | Per-turn` — switches which `GET /admin/calls/{call_uuid}/audio/{kind}` endpoint feeds the player.

### 7.4 Center pane — transcript + per-turn evidence

Below the waveform, a `<TranscriptList>` of `<TurnEvidenceCard>`s, one per turn. Auto-scroll-sync so the active card is centered as audio plays; click card to seek.

Each `<TurnEvidenceCard>` (collapsed):

- Header row: speaker badge `SABI` (gold) / `CHILD` (off-white), `[02:14]` timecode pill, turn duration, per-turn play button (uses `GET /admin/calls/{call_uuid}/turns/{turn_index}/audio/{role}`).
- Body: one line summary — for CHILD: normalized transcript; for SABI: TTS text.
- Quality flag pills inline (max 1 + `+N more`).
- Right: expand caret.

Expanded `<TurnEvidenceCard>` (the evidence the spec demands):

**For a CHILD turn:**
- **What child said (audio)** — per-turn audio player (`role=child`)
- **STT raw** — exactly what the provider returned (mono font)
- **Normalized transcript** — after Sabi's normalization (mono)
- **STT confidence** — number + visual bar
- **STT provider** — pill (Whisper / Intron / Deepgram), with model version
- **Latency** — `STT 412ms · LLM 1,124ms · TTS 287ms · First-audio 1,823ms` mono strip (with green/amber/red coloring against per-stage SLA)
- **Quality flags** — full pill list, all flags shown when expanded

**For a SABI turn:**
- **Sabi's reply (audio)** — per-turn player (`role=sabi`)
- **Reply rendered text** — what Sabi decided to say
- **Exact TTS text** — the literal string passed to TTS (often differs from reply due to SSML)
- **TTS provider** — pill (Chatterbox / ElevenLabs)
- **TTS voice** — voice name + version
- **Latency** — same mono strip
- **Quality flags** — full list

Expand-all / collapse-all button in the transcript header.

**Three-column "in context" view** (Cognigy pattern) — triggered by right-click `→ Show in context`: opens a modal with `Prior turn | Current turn | Next turn` side-by-side, so reviewers don't lose the surrounding turns.

### 7.5 Left pane — AI brief

Collapsible sections (`Accordion`, defaults all open):

- **Ask anything** — `Textarea` placeholder. (Stub for future Claude-powered Q&A with citations back to turn timestamps.)
- **Highlights** — 1-paragraph recap + bulleted highlights generated post-call by Claude Haiku. Hover bullet → highlights the related turn in transcript.
- **Outline** — lesson phases with durations, click-to-seek.
- **Call info** — caller (last 4 only by default, click reveals full), lesson code, cohort, server/region, AT call SID, build/version of Sabi.
- **Pipeline events** — collapsed by default; expand for a vertical timeline of every step (AT inbound → STT request → LLM request → TTS request → audio out) with timestamps, latencies, HTTP status, and bytes.

### 7.6 Right pane — annotation + scorecard + comments + feedback

**Annotation strip** (always visible at top of right pane, sticky):

- Lesson completion: Yes / Partial / No (segmented control, key `1/2/3`)
- Child engagement: 1–5 stars (keys `1`-`5` when Engagement is focused via `e`)
- Comprehension: Struggled / Normal / Strong
- Safety: None / Redirect / Escalate (key `s` cycles)
- Audio quality: 1–5 stars
- Comment: free-text (key `c` focuses)
- Save state: autosaves with sonner toast; "Last saved 12s ago" in `--meta-foreground`

**Scorecard** (collapsible Card below):

- Sections (e.g., Intro / Phonics accuracy / Engagement check-ins / Error handling / Close)
- Each question rendered per type (`range / yesno / single_select / multi_select / open_ended`)
- AI-suggested answer pre-selected with a small `<Sparkles>` icon and `Why?` link → opens transcript citations
- Per-question mandatory indicator, scoring-guide collapse, free-text "Add more feedback"
- Overall calculated score with weighted snap-to-100
- Status pill at top: `Draft · To do · AI Pending · AI Scored · Acknowledged · Disputed`
- Footer: Save / Submit / Request review

**Comments** — `<TimestampComments>`:

- Anchored to current playhead by default
- `@mention` Clerk org members
- Visibility radio: Workspace / Specific people / Only me
- Comment row glows in `--sabi-gold-muted` when playhead crosses it

**Feedback section** (only renders when `GET /admin/feedback/{call_uuid}` returns):

- Header: "Parent feedback submitted 2026-06-29 19:04"
- Inline audio player (uses `GET /admin/feedback/{call_uuid}/audio`)
- Transcript of feedback if STT'd
- "Mark as addressed" button

**Share & audit** (collapsible Card at bottom):

- Share button → modal with privacy radio (Workspace / Anyone with link / Specific people), link expiry (1d / 7d / 30d / 100d), identification gate toggle, domain allowlist
- Audit log table: who opened / when / from where / which timestamps they jumped to

---

## 8. Curriculum view

**Route:** `/admin/curriculum`

Backed by `GET /admin/curriculum-map`. The current ugly tree (brown branches, dropping ball, overlapping text) is replaced with two side-by-side, professionally laid-out, click-navigable graphs.

### 8.1 Layout

- **Header strip:** title (serif), legend (mastery levels with shape+color), filter bar (Cohort, Learner, Date range, "Show bump-downs"), density toggle, full-screen button, export SVG / PNG.
- **Main canvas** split vertically:
  - **Left half (50%):** Literacy graph — "Literacy"
  - **Right half (50%):** Numeracy graph — "Numeracy"
- **Right rail (320px collapsible):** Inspector — when a node is selected, shows module/week/lesson details, active skill, cohort mastery histogram for that node, list of learners currently at it (top 10), bump-down history.

### 8.2 Graph rendering

`@xyflow/react` (React Flow v12). Custom node + edge components.

- **Nodes:** rounded rectangles, `--surface-2` background, gold border for current cohort focus, label = lesson name in `font-sans`, code (e.g., "L3·M2·W4·L3") in `font-mono` `--meta-foreground` underneath. Inside the node, a small horizontal stacked bar shows cohort mastery split across mastery levels (uses the 5-level shape+color palette). Node size: 200×64px minimum. **Text never overflows** — labels truncate with `…` and full label appears on hover Popover.
- **Edges:** thin (1.5px) curves in `--border-strong`, never brown. Forward-progression edges have a small chevron at midpoint. **Bump-down branches** use a dashed style with a soft amber `--color-warning` and a `↘` chevron — visually distinct from the dropping-ball.
- **Layout algorithm:** elk.js `layered` direction LR (left-to-right scope-and-sequence). Vertical lane per module. Auto-spaces nodes so labels never collide.
- **Color rule:** background uses `--surface` (deep ink); nodes use `--surface-2`. Gold reserved for active node, hovered node, and primary CTA. Green-tinted `--accent-green-muted` fills nodes where the focused learner has mastered. **No brown anywhere.**
- **Bump-down indicator:** when "Show bump-downs" is on, edges where a learner moved backward render dashed amber with a small `↘` icon at midpoint. Hover the edge → tooltip "8 learners bumped down at this gate (last 30 days)."
- **Hold / up / down moves visible** as small dots on the edge (hold = circle, up = chevron-up, down = chevron-down) when a learner is selected.

### 8.3 Per-module drill-down

Click a node → right rail inspector populates:

- **Module / week / lesson** header
- **Active skill** chip
- **Cohort mastery histogram** (small bar chart of the 5 levels with counts)
- **Top 10 learners at this node** — list with name, days at node, last call. Click → learner page.
- **Bump-down history** (when a learner is selected globally) — list of "Was at L3·M2·W4·L3 on 2026-06-15 — bumped down to L3·M2·W3·L2 on 2026-06-22 — back at L3·M2·W4·L3 on 2026-06-28"
- **Open node detail →** full page at `/admin/curriculum/nodes/[code]`

### 8.4 Per-learner trajectory mode

A combobox at the top of the page: "Showing: cohort average" — change to a specific learner. The graph then:

- Fills mastered nodes in `--accent-green-muted`
- Rings the current node in `--primary` (gold)
- Outlines the next node in dashed `--primary`
- Renders the learner's bump-down dashed amber edges at each move

### 8.5 Anti-overlap guarantees

- Auto-layout runs on every cohort/learner change.
- Node text uses `text-overflow: ellipsis` with `max-width: 180px`; full text in Popover.
- Edge labels (when needed) sit on a tiny pill background in `--surface` so they're readable against any underlying edge.
- Minimum 32px vertical gap between any two nodes in the same column.

---

## 9. Kids tab (low priority)

**Route:** `/admin/kids` — distinct from Learners. Same shell, different schema lens.

**Differentiation from Learners:**
- Learners is the **call-pipeline view** — driven by phone-as-identity, dedup-heavy, optimized for QA workflow.
- Kids is the **person-centric profile view** — assumes a researcher / partnership / safeguarding lens, treats each child as the unit of record even when phone is shared.

### 9.1 Columns (same skeleton as Learners, different columns)

| # | Column | Width | Notes |
|---|---|---|---|
| 1 | `[ ]` | 40px | |
| 2 | **Child name** | 200px | Preferred name |
| 3 | **Age** | 60px | |
| 4 | **Guardian** | 180px | Name + relationship |
| 5 | **Phone** | 150px | Shared-phone icon if multiple kids share |
| 6 | **Consent** | 100px | `<StatusBadge>` |
| 7 | **School status** | 130px | In-school / Out-of-school / Unknown |
| 8 | **Cohort / source** | 150px | |
| 9 | **Usage streak** | 100px | "12-day streak" |
| 10 | **Calls done** | 90px | total |
| 11 | **Literacy level** | 110px | |
| 12 | **Numeracy level** | 110px | |
| 13 | **Last lesson** | 200px | name + date |
| 14 | **Next recommended** | 200px | name + `Trigger` button on hover |
| 15 | **Feedback / safety** | 130px | `<StatusBadge>` for any open feedback/safety items |
| 16 | **`⋯`** | 56px | |

### 9.2 Filters

Cohort, Consent, School status, Age range, Streak length, Literacy level, Numeracy level, Has open feedback (toggle), Has safety alert (toggle).

### 9.3 Detail page

`/admin/kids/[child_id]` — same three-panel structure as Learner detail, but with additional sections:

- **Profile** card with photo (if collected), age, languages, relationship to guardian, household notes (free text, RBAC-gated)
- **Consent record** with timestamps, method (WhatsApp / in-person / SMS), reviewer
- **Feedback & safety** dedicated section with timeline of incidents
- **Cohort + source** lineage (e.g., recruited via Sonia 2026-05-12, transferred from CcHub demo cohort)

(Identity, current placement, mastery, recent conversations sections are shared with Learner detail via a common `<LearnerSections>` component.)

### 9.4 Empty state

Same `<EmptyState>` component, copy adapted: "No children registered yet. Children appear here once a guardian completes consent. [Open consent flow →]"

---

## 10. Patterns copied (source → Sabi page → behaviour)

| # | Source | Sabi page | What Sabi does |
|---|---|---|---|
| 1 | Vercel Runtime Logs — filter rail + chronological table + right drawer | Calls page | Same three-region layout; filter rail on left, table center, Sheet drawer for row peek with prev/next ratchet |
| 2 | Vercel — "Logs from your browser" | Calls page | Filter chip "My test calls only" matches caller phone to current user's stored test number |
| 3 | Vercel — breadcrumb with chevron-dropdowns | Topbar everywhere | Each breadcrumb segment is a `DropdownMenu` for sideways nav |
| 4 | Stripe — persistent environment indicator | Topbar | Gold (prod) / amber (staging) / grey (sandbox) pill, always visible |
| 5 | Stripe — search-as-DSL with operators | Filter bars on Calls + Learners + Kids | `parseSabiQuery()` accepts `status:`, `cohort:`, `phone:`, `is:`, `>`, `<`, `..`, `-`, quoted phrases |
| 6 | Stripe — payment detail timeline + metadata + actions | Call detail header + pipeline-events accordion | Chronological event list, metadata panel, refund-style "Re-run STT", "Trigger call back", "Open feedback" |
| 7 | Stripe — Share modal (privacy / expiry / domain / audit) | Call detail Share button | Identical: privacy radio, link expiry, identification gate, domain allowlist, audit log of views |
| 8 | Linear — Cmd-K with Navigation/Actions/Help sections | Global `<SabiCommandPalette>` | Same sections; `G L` `G C` `G K` etc. for navigation |
| 9 | Linear — dimmer sidebar | App sidebar | Scoped `--sidebar-*` tokens make sidebar a step darker than canvas |
| 10 | Linear — Inbox with `J/K/U/H` keyboard shortcuts | `/admin/inbox` for ops notifications | Same keys |
| 11 | Linear — empty-state pattern (monochrome line + active-voice CTA) | All empty states | One reusable `<EmptyState>` component |
| 12 | Linear — `M/T/D` view-mode toggle on threads | Call detail | Three-tab strip on the center pane: Messages (chat), Turns (cards), Details (raw evidence) |
| 13 | Supabase — three-pane (tables left / grid center / row inspector right) | Call detail + Learner detail | `<ThreePane>` ResizablePanelGroup |
| 14 | Supabase — sidebar component composition | `sidebar-07` block | Adopted directly |
| 15 | Supabase — `Esc` closes drawer | Sheet drawer everywhere | Wired |
| 16 | Supabase — tabs across destinations with preview-tab pin-on-edit | Curriculum + Calls QA mode | Tabs row above call detail; preview tab italic until interaction |
| 17 | Supabase — depth via ring border, no shadows | All cards | `--elev-ring` default, no `box-shadow: blur` |
| 18 | Supabase — AI filter bar with NL → chips | Filter bar on Calls and Learners | `Ask` button next to DSL search; Claude returns parsed `{column, op, value}` array |
| 19 | Supabase — AI diff view in Monaco | Replay-with-edits sandbox | Lesson prompt edits render as red/green diff with accept/reject hunks |
| 20 | Twilio Voice Insights — edge-by-edge metrics per call | Call detail pipeline-events accordion | "Cards per hop": Africa's Talking edge / Sabi server edge / Caller edge with shared field labels |
| 21 | Twilio Voice Insights — Conversation Relay AI KPI tiles | `/admin/` Today dashboard | 4 latency tiles: Time-to-first-audio, STT, LLM, TTS + 3 behavioural: Interruption rate, Silent calls, Calls-with-errors |
| 22 | Twilio Voice Insights — event timeline with threshold + measured value | Call detail timeline marker rail | Every warning marker shows `threshold: 800ms, measured: 1340ms` in Popover |
| 23 | Twilio Voice Insights — annotation row at top of call detail | Call detail right pane Annotation strip | Inline-edit completion / engagement / comprehension / safety / audio quality / comment |
| 24 | Twilio Recordings — MP3 32kbps + WAV 128kbps downloads | Call detail Download menu | Two formats per call |
| 25 | Twilio Flex — per-channel waveform with cross-talk red + silence orange | `<DualWaveform>` | Sabi gold / child off-white / red overlap / amber silence |
| 26 | Twilio Flex — segments panel for multi-lesson calls | Center pane topic ribbons | Per-lesson-phase ribbons under waveform, click to seek |
| 27 | Africa's Talking — three-dot kebab → Details | Row kebab on Calls + Learners + Kids | Same pattern, opens full page |
| 28 | Africa's Talking — environment-as-color chrome | Topbar env pill | Sabi adapts to gold/amber/grey not orange/green |
| 29 | Africa's Talking — per-call event timeline with callback HTTP status | Call detail pipeline-events | Each step shows latency + HTTP status |
| 30 | Africa's Talking — hangup cause as first-class field | Call detail header + Calls table | `endCause` enum: child_hung_up / network_dropped / sabi_finished_lesson / sabi_safety_redirect / parent_intervened / idle_timeout / error |
| 31 | Gong — comments anchored to playhead, glow when crossed | `<TimestampComments>` on Call detail | Same behaviour, `--sabi-gold-muted` glow |
| 32 | Gong — yellow drag handles on timeline for snippet + transcript-side anchors | Clip handles | Two-thumb Slider in gold-yellow; floating menu on transcript text-select |
| 33 | Gong — color-coded speakers (purple/pink → Sabi gold/child off-white) | `<DualWaveform>` + `<TranscriptList>` | Sabi gold, child off-white, teacher info-blue |
| 34 | Gong — annotation indicator on AI-suggested rubric answers | Scorecard panel | `<Sparkles>` icon + Why? link → cites transcript passages |
| 35 | Talkdesk QM — status vocabulary | Scorecard status pill | `Draft / To do / Review requested / AI pending / AI scored / Completed / Acknowledged / Disputed` |
| 36 | Talkdesk QM — agent acknowledge + dispute | Scorecard right pane footer | Acknowledge → status change; Dispute → opens thread visible to disputer + supervisor |
| 37 | Observe.ai — synchronized streams (audio + transcript + metadata) | Call detail center pane | Transcript auto-scrolls in sync with playhead |
| 38 | Khan Academy — three-tab cohort overview (Activity / Skills / Mastery) | Cohort detail (`/admin/cohorts/[id]`) | Same three tabs, Sabi-mapped: Calls / Skills / Mastery |
| 39 | Khan Academy — 5-level mastery model with stacked-bar viz | Mastery tab + curriculum nodes | 5 levels: Not Tried / Heard / Repeats-with-prompt / Reads-independently / Generalizes |
| 40 | Khan Academy — star icon for Mastery Achieved | Curriculum nodes + Learner detail | Lucide `Star` in `--primary` (gold) — naturally on-brand |
| 41 | Canvas — shape+color status glyphs | `<StatusBadge>` everywhere | Circle / Triangle / Square / Octagon / Diamond pairing |
| 42 | Canvas — "Message Students Who…" criteria | Bulk action "Trigger outbound calls" | Bulk-bar action that calls `POST /admin/asterisk/direct-call` per matched row |
| 43 | Schoology — gear icon → Mastery Settings / Export Summary / Export Detail | Top-right of every table | `DropdownMenu` with same three items |
| 44 | Moodle — at-risk card stream with 4 actions | `/admin/inbox` (needs-attention surface) | Card per learner: Call now / View profile / Acknowledge / Not at risk |
| 45 | Knewton — knowledge graph for board explainer | Curriculum view | React Flow graph, ovals for objectives, prerequisite arrows |
| 46 | Coursera — "Next step" recommendation card | Today dashboard + Learner detail | "Your next attention call: Amara hasn't picked up in 4 days. [Call now]" |
| 47 | Helicone — request drawer with prev/next ratchet | Sheet drawer on lists | Up/down arrows in Sheet header step through filtered list without closing |
| 48 | Helicone — Live mode toggle with anti-jitter "N new" pill | Calls page | Live toggle in toolbar; new rows surface as a pill, never auto-shift the list |
| 49 | LangSmith — three view modes M/T/D | Call detail center pane | Tabs: Messages (chat) / Turns (cards) / Details (raw JSON) — hotkeys M/T/D |
| 50 | LangSmith — cost breakdown tooltip | Call detail header + cost cell | Hover cost → STT + LLM + TTS + AT breakdown |
| 51 | Voiceflow — bulk evaluation (batch run evals on selected) | Calls bulk-bar | "Batch run scorecard" on selected rows; async with progress |
| 52 | Voiceflow — eval result shows reasoning, not just score | Scorecard | Each AI-suggested answer expands to show citation passages |
| 53 | Cognigy — three-column "Prior / Current / Next" | Right-click on transcript turn | Modal with three sticky columns |
| 54 | Cognigy — right-click context menu on messages | Transcript turn | shadcn `<ContextMenu>` with: Replay this turn / Add to test set / Fork from here / Send to curriculum team / Create regression test |
| 55 | Mteja — three-column inbox (filters / thread / contact) | `/admin/inbox` | Same layout via ResizablePanelGroup |
| 56 | Mteja — live count badges on left-rail filters | Sidebar items | Each NavItem renders `<Badge variant="secondary">` with count |
| 57 | Mteja — inline audio player on each call row in thread | Inbox + recent conversations on Learner detail | `<audio>` inline with transcript collapse |
| 58 | engageSPARK — downloadable multi-sheet spreadsheet report | Export buttons on every list | `.xlsx` with one sheet per channel (Calls / Learners / Feedback / Costs) |
| 59 | engageSPARK — cost decomposition on overview | Today dashboard | Hero strip: total cost / STT cost / LLM cost / TTS cost / AT minutes |
| 60 | Africa's Talking + CDR convention — playback speed dropdown | `<DualWaveform>` controls | 5 steps 0.5×/0.75×/1×/1.5×/2× |
| 61 | Linear — keyboard-first navigation with `G` sequences | Global | `G T` Today, `G C` Calls, `G L` Learners, `G K` Kids, `G U` Curriculum, `G I` Inbox, `G R` Reports, `?` show all shortcuts |
| 62 | shadcn — `--sidebar-*` token set scoped independently | App sidebar | Sabi-tuned sidebar tokens |
| 63 | Linear — Sonner toasts for non-blocking feedback | Global | `toast.promise(action, {loading, success, error})` |
| 64 | Vercel + Stripe — Copy URL on every filter / drawer / detail | All pages | "Copy link" button in toolbar; URL encodes filters/sort/drawer state via `nuqs` |

---

## 11. Patterns rejected (with reason)

| # | Source | Pattern rejected | Reason |
|---|---|---|---|
| 1 | Duolingo for Schools | Decorative gamification (XP, streaks, owls) on admin views | Undermines board credibility. Keep admin serious, premium gold-on-black. Gamification stays on the kids' phone channel. |
| 2 | Cognigy | Right-click as *primary* action surface | Discoverability disaster on web. Always expose right-click actions in a visible `⋯` kebab too. |
| 3 | Anthropic Workbench | Local-only drafts (no persistence) | Catastrophic for an admin console. Persist every annotation to Supabase as typed. |
| 4 | Helicone | 1–2s live polling that jitters the list | Use opt-in "N new — load" pill instead. |
| 5 | Twilio | 4-step speed control (Slow / Normal / Fast / Very Fast) without 0.75× | QA listeners need 0.75× for accent comprehension. Sabi ships 5 steps. |
| 6 | Twilio | CSV export caps without surfacing API alternative | Show "Showing first N rows — use the API for full export" with code snippet. |
| 7 | Twilio | Two parallel call lists (Logs vs Insights Calls) | One Calls list with progressive disclosure (basic filters default, "Advanced" toggle). |
| 8 | Africa's Talking | "Sandbox" as a separate username, not an env in the same app | Sabi keeps the same app shape across envs; only env vars + chrome color swap. |
| 9 | Africa's Talking | No global search, no app switcher inside the app shell | Sabi ships Cmd-K from day one + inline org switcher. |
| 10 | Africa's Talking | No bulk actions on tables | Sabi ships bulk-bar from v1. |
| 11 | Supabase | Studio's "Postgres jargon in user-facing UI" (`int8`, `jsonb`, `timestamptz`) | Use plain labels ("Number", "Object", "Date and time"); toggle to Postgres types only under a "Show technical types" preference. |
| 12 | Supabase | Inline-edit annotations without keyboard shortcuts | Sabi annotation strip supports `1-5`, `e`, `s`, `c`. |
| 13 | Supabase | Multiple AI assistants with different prompt patterns across surfaces | One AI prompt pattern reused: same shortcut (Cmd+I), same diff-acceptance UX. |
| 14 | Talkdesk | Sentiment color (red/amber/green) as the ONLY in-transcript color carrier | Sabi uses speaker color (gold/off-white) as the primary carrier; engagement signal as secondary; safety as accent. |
| 15 | Stripe | Test/live toggle inside user menu | Belongs in topbar where it's permanently visible. |
| 16 | Stripe | Hidden "Workbench" floating pane as primary surface | Sabi keeps the Workbench equivalent (developer pane) optional and gated by role. |
| 17 | Linear | Multiple top-level surfaces (Inbox + Triage + My Issues + Active Cycle + Backlog) | Sabi caps sidebar at 8 top-level items: Today, Calls, Learners, Curriculum, Kids, Reports, Inbox, Settings. |
| 18 | Khan Academy | Hide collapse-by-default everywhere | Default-expand the first 1–2 sections of any list so first-time admins see what data exists. |
| 19 | Canvas | 24-hour data refresh on analytics | Sabi calls dashboard is live or near-live (≤60s polling). |
| 20 | Schoology | Single mastery scale across the whole "district" | Sabi allows per-cohort overrides (CcHub vs Lagos public vs Bakame). |
| 21 | Schoology | "Mastery Settings" buried in a gear icon with consequential defaults (Decaying Average at 75%) | Surface mastery-calculation policy during onboarding, not in a settings panel. |
| 22 | Moodle | Predictive at-risk flags without explanation | Always show "WHY this learner is at risk" with the prediction (Prediction details panel pattern). |
| 23 | Cognigy | Contact profile schema (Gender, Age, Birthday, GDPR fields) for children, possibly shared phone | Use anonymized callerHash + region + age-range only. Sabi treats child PII with explicit consent + minimization. |
| 24 | Botpress | One-click "pass back to bot" without confirm | Sabi requires confirm modal for any escalation back to autonomous mode after safety review. |
| 25 | Voiceflow | Generic "AI-powered insights" empty state with fake mock data | Sabi empty states are honest; never invent activity. |
| 26 | Gong / Coursera | Auto-fill AI without showing it's AI | Every AI-suggested annotation / answer / summary has a `<Sparkles>` indicator and a `Why?` citation link. |
| 27 | Twilio Paste | Sub-account hierarchy bolted on top of single-account UI | Sabi designs for district→school→cohort from v1, not retrofitted. |
| 28 | Africa's Talking | Documentation portal JS-rendered, hostile to crawlers/LLMs | Sabi admin docs are SSR. |
| 29 | Stripe | Hidden agent action buttons that scroll off on narrow screens (Flex CallCanvas) | Sabi per-call action bar is sticky. |
| 30 | All edtech LMSes | "No spreadsheets to interpret" → ship a UI so dense it forces export-to-Excel | Sabi gives a clean UI first; CSV/XLSX export is for evidence, not browsing. |

---

## 12. Open questions for Naomi

1. **Gold-on-black premium identity vs operational green accents — confirm the balance.** Brief assumes gold reserved for CTAs/active/Sabi-speaker/star badges only, with green as the operational accent (success/completed status). Is that the right ratio, or do you want more gold throughout?

2. **Light mode — required or optional?** Brief defaults to dark mode as canonical (matches premium gold-on-black brand and the Supabase/Linear ethos for power-user tools). Light mode tokens are defined as inverse. Do board members ever review during the day on glare-prone screens where they'd want light mode? Should it default to system preference, or hard-default to dark?

3. **Sabi wordmark — serif everywhere in chrome, or only the topbar?** Brief uses serif for the app wordmark + each page H1 only, then `font-sans` for the rest. Confirm — or do you want serif on section headings too?

4. **"Sabi" trademark risk (per memory).** Brief uses the name throughout. If the trademark situation pushes toward a rename, every visible string should be sourced from a single brand config so we can rename in one place. Confirm that's the right hedge.

5. **Curriculum visualization library — React Flow vs custom SVG.** React Flow is the safest choice for click/zoom/pan + auto-layout via elk, and won't repeat the brown-branches mistake. Confirm OK, or do you want a fully custom SVG so the visual language is 100% under our control?

6. **Voice-driven planning hook for Curriculum view.** Memory says voice-driven planning is preferred for the Class on Time project — does the Curriculum view need a voice-input affordance ("show me Amara's path", "compare cohorts on numeracy L2"), or is that scoped to the kids' channel only?

7. **Per-call cost surfacing — show learners or hide?** Twilio/Stripe pattern surfaces cost prominently. Sabi as a nonprofit may want cost de-emphasized on board-facing views and emphasized only on internal ops/funder reports. Brief defaults to "always visible" — confirm.

8. **Kids tab — keep separate from Learners or merge with role-based view toggle?** Brief keeps them separate (Learners = call-pipeline lens, Kids = person-centric lens). Alternative: one route with a toggle. Which feels right?

9. **Live mode default state on Calls page.** Brief defaults `Live: off`. For pilot demos in board meetings you may want it `on` so the room sees calls land. Confirm default.

10. **Annotation taxonomy — who owns the rubric?** Brief assumes the rubric is owned by you + Sonia and editable in `/admin/scorecards`. If Bakame or partner reviewers should be able to define their own scorecards per-cohort, the data model needs `scorecard_org_id` from day one. Confirm scope.

11. **Safety escalation surface — separate red page or just a filter on Calls/Inbox?** Brief threads safety alerts through Inbox + Learner detail + Call quality flags. Alternative: a dedicated `/admin/safety` route with the loudest possible visual treatment (separate red top-bar banner when alerts are open). Which level of separation?

12. **Replay-with-edits sandbox — board-visible or engineer-only?** Brief gates it behind a Clerk role (`admin` or `developer`). Board members shouldn't accidentally edit a live prompt. Confirm that's the right gate.

13. **Server-rendered Python admin (`sabi-server/admin_review.py`) — sunset immediately, or run in parallel during migration?** Recommend running both for ~2 weeks behind a feature flag so any missing endpoint is caught before deletion.

Absolute paths referenced:
- Backend HTTP surface to consume: `/Users/naomiivie/Education for Equality/sabi-server/admin_review.py`
- New admin app target: `/Users/naomiivie/Education for Equality/curriculum-app/app/admin/`
- Brand assets to wire in: `/Users/naomiivie/Education for Equality/assets/sabi-spark.svg` and Roca wordmark (per memory `project_sabi_brand`)
- Quality-flag map to author: `/Users/naomiivie/Education for Equality/curriculum-app/lib/calls/quality-flags.ts`
- DSL parser to author: `/Users/naomiivie/Education for Equality/curriculum-app/lib/filters/parse-sabi-query.ts`
- Brand voice rules to keep aligned with: `/Users/naomiivie/Education for Equality/.claude/brand-voice-guidelines.md`

---

# Part 2 — Per-comparable deep dives


---

## Comparable 1: Twilio Console + Voice Insights + Flex

I have enough deep material to write the full audit. Let me produce the comprehensive response.

# Twilio Console + Voice Insights + Flex

## A) Product overview (1 paragraph)

Twilio Console is the unified web operations layer for every Twilio product, organized after their 2020–2024 rebuild into four top-level zones — **Develop, Monitor, Account, Billing** — with a left dock for pinned products and a topbar housing the AccountSwitcher, ProductSwitcher, search, support, and UserDialog. **Voice Insights** lives under `Monitor > Insights > Voice` and consists of (a) an aggregate **Call Insights Dashboard** with KPI tiles and filterable trend charts, (b) a **Call Logs** list at `Monitor > Logs > Voice > Calls`, and (c) a per-call **Call Summary** detail page with edge-by-edge metrics (carrier_edge, sip_edge, sdk_edge, client_edge), an event timeline, and a 30-day retention window. A separate **Conversation Relay Insights Dashboard** exists specifically for AI voice agents and exposes TTS/STT/network/application latency breakdowns, interruption rates, silent-call rates, and tokens/words/turns per call — which is the closest direct analogue for Sabi. **Twilio Flex** is the contact-center product built on the same design system (Paste), with an Agent Desktop split into a `TaskList` left rail and `TaskCanvas` right region (CallCanvas, MessagingCanvas, NoTasksCanvas, etc.) and a Supervisor "Teams View" data table with inline monitor/coach/barge actions. Flex Insights ships a "Conversation Screen" with a per-channel waveform player, transcript pane, comments, and assessments.

## B) Navigation + topbar pattern (detailed)

**Top-level grouping (left sidebar, in order):**
1. **Develop** — channels and product features the developer ships with. Tailored for discovery/onboarding. Reduced menu depth — deep items collapsed into tabbed pages.
2. **Monitor** — single pane of glass for ops. Cross-product logs, debugger/alarms, and the Insights products (Voice Insights, Messaging Insights, Flex Insights, Conversation Relay Insights).
3. **Account** — users, API keys, auth tokens, Trust Hub (customer trust/compliance), regions.
4. **Billing** — usage, invoices, payment methods, plan upgrade, balance/auto-recharge.

**Specific Monitor sub-tree relevant to Sabi:**
- `Monitor > Logs > Voice > Calls` → flat call log list.
- `Monitor > Logs > Errors / Alarms / Debugger` → "Workbench" page with three tabs: Overview, Debugger, Alarms.
- `Monitor > Insights > Voice > Settings` → toggle Advanced Features on/off.
- `Monitor > Insights > Voice > Dashboard` → aggregate KPIs/charts.
- `Monitor > Insights > Voice > Calls` → call list with the 40+ Voice Insights filter dimensions (richer than the Logs list).
- `Monitor > Insights > Voice > Conversation Relay` → AI-voice-agent dashboard.

**Sidebar mechanics (Paste `SidebarNavigation` component):**
- Built around three composable parts: `SidebarNavigationItem` (single link, requires href), `SidebarNavigationDisclosure` (expandable group, ARIA Disclosure pattern), `SidebarNavigationSeparator` (visual divider). Plus `SidebarBetaBadge` for "beta" pills on items.
- Nesting depth officially capped at **3 levels** — a hard design rule.
- Two width states: expanded and **compact**. `hideItemsOnCollapse` hides labels and keeps only icons in compact mode; disclosure groups are **always hidden** when collapsed.
- Selection state uses `aria-current="page"` (semantic, not just visual).
- "Pin/unpin" affordance on every product — clicking the all-products icon opens the full ProductSwitcher menu; pinned items live in the persistent left dock.
- Each navigation item requires an `aria-label` for screen reader use; action buttons sit as **siblings** of items, never nested inside.

**Topbar (Paste `Topbar` component):**
- **Left zone**: `AccountSwitcher` (project/account dropdown — supports parent + subaccount hierarchy) and product name/logo. Naomi: AccountSwitcher is the right pattern for Sabi's "school district → school → cohort" hierarchy.
- **Right zone**: in this fixed order — `Combobox` global search (results show hit + its place in the nav tree), `ProductSwitcher` (the dot-grid app launcher), `Menu` for help (`SupportIcon`), `StatusMenu` for system status, `UserDialog` (profile + sign-out, uses `UserIcon` + `ChevronDownIcon`).
- Search behavior: returns matches **with their breadcrumb path** so you can jump deep without navigating.

**In-page navigation (page-level, not global):**
- `Breadcrumb` for hierarchy (Account → Voice → Call).
- `InPageNavigation` (tabs) for sibling views within one resource. Voice Insights Call Detail uses tabs like *Summary / Events / Metrics / Annotations*.
- **Drawer vs full page rule (inferred from Twilio's pattern):** lists like Call Logs and Recordings drill to **full pages** with breadcrumbs (because users want to share/bookmark the URL and view dense metrics). Quick actions like "edit task attributes" in Flex use a **side drawer/Modal**. The split is "stateful detail = full page, transient action = overlay."

**Home/dashboard landing:** A "Console Dashboard" with a messaging health score (last 7 days), recently used products grid, trial usage tile, product recommendations. The home screen is **personalized state**, not a fixed dashboard — it changes as you use the product.

## C) List/index pages — columns, filters, sort, search, density, pagination, bulk actions, empty state

### Call Logs (`Monitor > Logs > Voice > Calls`) — the basic list

**Columns** (left to right, in displayed order):
- Date (linked — clicking the timestamp opens Call Detail)
- From (E.164)
- To (E.164)
- Status (badge: queued, ringing, in-progress, completed, busy, failed, no-answer, canceled — failed/busy not billed)
- Duration (m:ss)
- Direction (inbound, outbound-api, outbound-dial, trunking-originating, trunking-terminating)
- Price (with `price_unit` e.g. USD)
- Call Type
- Call SID (32-hex `CA…` identifier)

**Filters** (top-of-list filter bar):
- Date Range (date picker, supports relative ranges)
- Status (multi-select)
- From (phone number)
- To (phone number)
- Call Type
- Plus search bar with page size, level, source, event type modifiers
- Historical trend dropdown showing a histogram of event counts over the selected window

**Pagination & export:** Server-side. **Export CSV** action with a hard cap of **2,500 rows** for the basic Logs page and **2,000 rows** for the Voice Insights filtered list (use the API beyond that). Retention: **90 days** for Console logs, **30 days** for Voice Insights data (GDPR).

### Call Insights Calls list (richer) — filter builder dimensions

**Participant / identity:** To/From Phone Number, Client Name (Voice SDK only), Verified Caller (boolean), Branded Call (boolean), Branded Call Caller name, SIP URI.

**Network / carrier / geography:** To Carrier, From Carrier, To Country Code, From Country Code, Edge Location (Twilio region).

**Device / SDK:** To Device Type, From Device Type, SDK Type, SDK Version, Browser, App Name, App Version, Client Registration Region.

**Call metadata:** Call Direction, Call State, SIP Response Code, Codec, Silence Detected.

**Quality flags:** Network Affected — Carrier, Network Affected — SDK, Packet Loss Detected, Jitter Detected, High RTT, Low MOS, ICE Failure, High PDD.

**Annotations (user-applied tags):** Answered By (machine vs human), Spam (boolean), Call Score (1–5), Connectivity Issue, Quality Issues taxonomy (one-way audio, choppy, robotic, dropped, audio-latency, garbled-audio, echo, static, volume).

**Sort/density:** Sortable by every column; default sort is date desc. Tabular density (Paste tables are medium density by default — about 56px row height in the standard theme).

**Bulk actions:** Limited in the public docs — primarily Export CSV; bulk annotate isn't documented for Console UI.

**Empty state:** Not documented in public-facing docs, but Paste's pattern is an illustration + headline + 1-line description + primary CTA.

### Recordings list (Programmable Voice → Recordings)

**Columns shown:** SID (RE…), Date Created, Start Time, Duration (seconds), Channels (1 = mono, 2 = dual-channel agent/customer), Source (DialVerb, Conference, RecordVerb, OutboundAPI, Trunking, StartCallRecordingAPI, StartConferenceRecordingAPI), Status (in-progress, paused, stopped, processing, completed, absent, deleted), Track (inbound, outbound, both), Price, Price Unit, Encryption Details.

**Row interaction:** Click → opens recording detail, which has the audio player + **download buttons in two formats**: `.wav` (128 kbps) and `.mp3` (32 kbps). Dual-channel uses `?RequestedChannels=2`.

**Retention nuance:** Recording metadata persists 40 days after delete even though media is unrecoverable — the row stays visible with a "deleted" status badge.

## D) Detail/drawer pages — layout, sections, audio player, transcript, drilldown

### Voice Insights — Call Summary detail page

Layout reads **top to bottom, two columns**:

**1. Header strip** — Call SID, direction badge, status, total duration, timestamp, "Who Hung Up" (caller / callee / error). Annotations row: Answered By, Spam, Call Score (1–5 stars), Connectivity Issue, Quality Issues, Comment, Incident — all editable inline.

**2. Two-column "From" / "To" metadata cards** (mirror layout):
- From: caller, carrier, country_code, country_subdivision, city, location, ip_address, number_prefix, connection type
- To: same fields
- Plus SDK-specific (when applicable): User Agent, SIP Call ID, Signaling IPs, Media IPs, Region, Operating System (OS), Engine (JS only), Browser, SDK Version, Selected Region, Client Name, Client IP Address, Client Location

**3. Properties section:**
- Who Hung Up, Last SIP Response, Twilio RTP Latency (average + max), Post-dial Delay, Call State, Silence Detected (yes/no with timeline)

**4. Metrics section per edge** — one card per edge present on the call (Carrier Edge, SIP Edge, SDK Edge, Client Edge):
- Codec (name + RFC code)
- Packet Loss Detected (boolean + percentage value)
- Jitter Detected (avg + max ms)
- Low MOS (SDK only — score 0–5)
- High Round Trip Time (SDK only)
- ICE Failure (SDK only)
- Plus the underlying counters: packets_received, packets_sent, packets_lost, packets_loss_percentage, latency.avg/max, packet_delay_variation, bytes_received, bytes_sent, audio_in/audio_out (mic/speaker levels)

**5. Time-series charts** — line/area plots with the event timeline overlaid:
- Jitter (ms over time)
- Received packet loss (% over time)
- MOS (Voice SDK) — with an **ITU-T threshold dotted orange line** at MOS 4.0 as the "acceptable" floor
- Round Trip Time
- Audio input level / Audio output level
- Sampling rate: every 1 second for SDK calls, every 10 seconds for SIP/carrier calls

**6. Event Stream / Event List timeline:**
- Two view modes: horizontal time-axis stream and a chronological list
- Event categories: `network-quality`, `audio-level`, `ice-connection`, `pc-connection-state`, `signaling-state`, `connection`, `feedback`
- Severity levels: ERROR, WARNING, INFO, DEBUG — each color-coded
- Example event names: `high-rtt`, `low-mos`, `high-jitter`, `high-packet-loss`, `high-packets-lost-fraction`, `low-bytes-received`, `low-bytes-sent`, `ice-connectivity-lost`, `constant-audio-input-level`, `constant-audio-output-level`, `incoming`, `accepted-by-local`, `disconnected-by-remote`, `muted`, `reconnecting`, `reconnected`, ICE states (`checking`, `connected`, `disconnected`, `completed`, `failed`), signaling (`stable`, `have-local-offer`, `have-remote-offer`), feedback (`received`, `received-none`), `network-change`
- Warning events carry `sdk_edge.metric.threshold` and `sdk_edge.metric.values` so the user sees *what the threshold was and what the measured value was* — not just "warning."
- Each event has timestamp, name, group, level — the timeline highlights both the *start* and the matching *clear* event (e.g., "high-rtt" raised at 00:03, INFO "high-rtt cleared" at 00:09)

**7. Trust block** (if branded calling enabled): `branded` boolean, caller name, use case, business_sid, brand_sid, `verified_caller.verified`.

**8. Conversation Relay agent session summaries** — when present (this is the most Sabi-relevant block):
- `session_id`, `tts_latency_ms`, `stt_latency_ms`, `network_latency_ms`, `time_to_first_audio_ms`, `application_latency_ms`
- `tokens.total`, `tokens.tokens_per_second`
- `words.total`, `words.words_per_minute`
- `turns`
- `interruptions.customer_to_agent`, `interruptions.agent_to_customer`
- `session_state`

### Flex Insights — Conversation Screen (call playback UI)

Layout from top:
- **Header:** Agent Name / Handling Team / Customer / Reflection Score / Recording Duration (single horizontal info bar, left → right)
- **Segments panel (top right):** lists every segment in chronological order with the talk time per segment, click to jump that segment into the player (this is the pattern for handling transferred / multi-leg calls)
- **Player panel (main):**
  - Per-channel waveform — **green = customer, blue = agent** (color-coded by speaker, two stacked tracks)
  - **Red highlight** where waveforms overlap = cross-talk
  - **Orange highlight** = long silence
  - Click anywhere on the timeline to start playback at that position
  - Playback speed control: **Slow / Normal / Fast / Very Fast** (four discrete steps, not a continuous slider)
  - "Copy Link" share — shares the URL with the playhead position embedded
  - Timestamps row below the waveform for navigation
  - HIPAA mode: waveform is **disabled** for privacy (you can't see when each party is speaking)
  - Recordings stored externally also have no waveform
- **Chat transcript pane** (for messaging conversations from 2019-11-15 forward)
- **Comment section:** free-text field + category dropdown (Good, Neutral, Poor, Good for Training, others)
- **Assess section:** structured QA form (compliance + script questions, each scored)
- **Agent Feedback pane:** chronological feedback received by the agent (most recent first)

### Flex Agent Desktop (live call view)

`AgentDesktopView` uses a `Splitter` (resizable) with two children:
- **Panel 1 (left): `TaskList`** — `TaskListContainer` → `TaskListItem`s → `TaskListButtons`. Each item shows task name, type icon (phone/chat/SMS), queue, time-in-queue.
- **Panel 2 (right): `TaskCanvas`** — header (`TaskCanvasHeader`) with caller ID + queue + elapsed time, `TaskCanvasTabs` to switch between Info / Notes / History, then one of:
  - `NoTasksCanvas` — empty state with agent's current availability
  - `IncomingTaskCanvas` — Accept / Reject buttons
  - `CallCanvas` — live call with `CallCanvasActions` toolbar:
    - Mute yourself
    - Put on hold (caller hears hold music)
    - Transfer (to Queue or Agent)
    - Consult (warm transfer / 3-way)
    - Keypad/DTMF
    - Hang up
  - `MessagingCanvas` — message history + composer + attachment icon + "End Chat" top-right
  - `ParticipantCanvas` — multi-party
  - Wrap-up canvas — "Complete" button to release and become available again
- **CRMContainer** — right of the splitter when CRM is enabled, side-by-side with the task

**MainHeader (topbar) carries**:
- App menu icon (hamburger)
- Microphone control
- Agent name + status pill (status options: **Offline / Available / Unavailable / Break** — user picks from a dropdown). The status pill is the most-clicked element in the entire UI.

**Incoming task notification** appears as a banner at the top of the Flex UI; agent can Accept from the banner OR navigate to Agent View and accept there.

### Flex Supervisor — Teams View data table

- Up to 200 agents at a time
- Per-agent row shows: Activity status, Time spent on the status, Individual task information, Email, Assigned skills, Teams the agent belongs to
- Filter by team membership; teams the supervisor owns appear under a "Teams" tab
- Click a voice task in the row → reveals **Call Monitoring** button. Click it → a persistent monitoring bar appears at top of screen with audio. Stop with "Call Monitoring" again or "Stop Monitoring."
- Chat monitoring exists but is **view-only** (no sending)

## E) Visual language — colors, typography, density, iconography, motion, brand voice

**Type system (Paste):**
- Font family: **Twilio Sans** super-family, three cuts — **Twilio Sans Display** (brand moments), **Twilio Sans Text** (UI default), **Twilio Sans Mono** (code). Default web theme falls back to **Inter** ("Inter var experimental" → "Inter var" → "Inter" → system stack).
- Font size scale uses paired tokens: `$font-size-10` through `$font-size-110+`. Tokens use **rem** (1 rem = 16 px).
- Line height tokens **pair by number** with size: `$font-size-40` always uses `$line-height-40`. This is a hard convention — designers do not mix-and-match.
- Four weights only: **400 Regular / 500 Medium / 600 Semibold / 700 Extrabold**. "Light" and "Bold" tokens exist but resolve to 400 and 600 — meaning the team intentionally rejects very-thin and very-heavy display weights for UI.
- Component-level type roles: `DisplayHeading` = Extrabold + Display family (brand only), `Heading` = Semibold + Text family (UI), `Paragraph` = 400 + Text family (body), `Detail Text` = 500 + Text family (captions/labels).
- Paste components: Anchor, DescriptionList, DetailText, DisplayHeading, Heading, InlineCode, Label, HelpText, List, Paragraph.

**Color system (Paste):**
- Architecture: **primitive aliases → semantic tokens**. Designers never reference raw hex codes — they reference tokens like `$color-background-primary` which point to an alias which points to hex. This is what makes their dark mode swap clean.
- Every hue has at least **10 steps** (lighter → darker), and the team explicitly leaves room to add more.
- Hue palette: Gray (neutrals), Blue (primary interactive + neutral information), Green (success), Orange (warning), Red (destructive + error), plus Twilio Red as a brand-only color "reserved for moments of impact" — illustrations, logos, iconography — never used as a UI background or button color.
- Semantic background tokens: `$color-background-primary`, `$color-background-success`, `$color-background-warning`, `$color-background-error`, and neutrals (body, weak, weakest, strong, strongest).
- Semantic text tokens: `$color-text`, `$color-text-link`, `$color-text-error`, `$color-text-success`, `$color-text-warning`.
- The product environment is intentionally **subdued** — most pages are gray + blue. Red appears only when something is wrong.

**Density:** Comfortable-to-medium. Sidebar items have generous padding; tables use single-line rows in lists with a 56-ish px row height; detail pages use generous section spacing because they're scanned, not skimmed.

**Iconography:** Single icon library (`@twilio-paste/icons`), 1.5-px stroke, geometric, monochrome. Every icon must have a `title` (not decorative) when used in a collapsed sidebar.

**Motion:** Disclosure expansion is the dominant motion (sidebar groups, in-page collapsibles). Modals and drawers slide in. No flashy transitions — motion is functional.

**Brand voice (relevant for Sabi to mimic the *feel*):** Direct, second-person, action-oriented. Help text is short, factual, no marketing copy in-product. Labels are nouns ("Recordings") not phrases ("Your call recordings").

## F) Specific patterns Sabi should copy

1. **Four-zone left sidebar (Develop / Monitor / Account / Billing → for Sabi: Curriculum / Calls / Roster / Billing)**
   - *What it does:* groups every product page into ≤4 top-level buckets, capped at 3 levels of nesting.
   - *Where it lives:* persistent left rail in the admin shell.
   - *Sabi mapping:* In Next.js 16, use a root `(admin)` route group with a `<Sidebar>` from shadcn/ui that mirrors the four buckets. Top-level items use Lucide icons + label; sub-items use Collapsible/Disclosure. Persist collapsed/expanded state to a cookie (shadcn pattern). Cap nesting at 3 levels — exactly Paste's rule. Use Tailwind v4's `@theme` to define semantic tokens (`--color-sidebar-bg`, `--color-sidebar-fg-active`) so dark mode is a single token swap.

2. **AccountSwitcher in topbar-left for school/district/cohort hierarchy**
   - *What it does:* a left-topbar dropdown that lets ops users switch the current scope (parent account → subaccount in Twilio's case).
   - *Sabi mapping:* Sabi has districts/schools/cohorts. Put `<AccountSwitcher>` (shadcn Command + Popover) in the topbar-left with breadcrumb-style "District > School > Cohort" labeling. Clerk's `<OrganizationSwitcher>` is the closest off-the-shelf — but wrap it so the displayed label is the hierarchy path, not just the current org name.

3. **In-page search with breadcrumb hits**
   - *What it does:* global search where every result shows its location in the nav, so users teleport to deep pages.
   - *Sabi mapping:* shadcn `<CommandDialog>` (Cmd-K) indexed over your sitemap. Result rows: `Curriculum > Lessons > "Letter F – sounds"`. Index calls (by phone number / parent name / lesson code) the same way so support staff can jump straight to a call detail.

4. **List vs Detail = full-page navigation, not drawer**
   - *What it does:* Twilio uses **full pages with breadcrumbs** for detail (Call Summary), reserving drawers for transient actions only.
   - *Sabi mapping:* Call Detail = its own URL (`/calls/[id]`). Annotating a call = drawer over the list. This makes deep-linked support tickets ("look at this call") work and keeps URLs shareable.

5. **Edge-by-edge call metrics on the detail page**
   - *What it does:* Voice Insights presents the same metric set (codec, jitter, packet loss, latency, MOS) *per edge* — carrier_edge, sip_edge, sdk_edge, client_edge — so engineers can localize the problem to a hop.
   - *Sabi mapping:* For each call, render a card-per-edge: **Africa's Talking edge** (carrier metrics: jitter, packet loss as ATC reports it), **Sabi server edge** (Hetzner: STT latency, LLM latency, TTS latency, audio bytes in/out), **Caller edge** (signal estimate from packet timing). Side-by-side cards with the *same field labels* so ops can scan left-to-right. This is the single highest-value pattern to steal — it forces you to think of the pipeline as discrete hops.

6. **Conversation Relay-style latency KPI tiles (TTS / STT / Network / Application / Time-to-first-audio)**
   - *What it does:* surfaces the four latency components that determine "does the AI sound natural" with a 1200ms target.
   - *Sabi mapping:* Dashboard hero row = 4 tiles: **Time to first audio (ms)** (target < 1200), **STT latency (ms)**, **TTS latency (ms)**, **LLM application latency (ms)**. Plus three behavioral KPIs Twilio invented for AI calls: **Interruption rate by callers (kids talking over Sabi)**, **Silent calls (% with no speech)**, **Calls with errors**. Use shadcn `<Card>` with a sparkline (Recharts) under each number.

7. **Event timeline with severity-colored events + threshold values inline**
   - *What it does:* every warning event shows *the threshold* and *the measured value* — not just "warning."
   - *Sabi mapping:* Build a `<CallTimeline>` Tailwind component: horizontal time axis at top, events as colored pills below. Hover = popover with `threshold` and `values`. Event groups for Sabi: `network`, `stt`, `llm`, `tts`, `safety_guardrail`, `lesson_state`. Severities: info/warning/error with `--color-status-*` tokens. When a "high-stt-latency" event fires, show "threshold: 800ms, measured: 1340ms" — never just "STT slow."

8. **Annotation row at the top of every call detail (Answered By, Score 1–5, Spam, Connectivity Issue, Quality Issues, Comment)**
   - *What it does:* lets ops/QA users tag calls in place, building a labeled dataset for later training.
   - *Sabi mapping:* Critical. Render an inline-editable annotation row: **Lesson completion (yes/partial/no)**, **Child engagement (1–5)**, **Comprehension (struggled/normal/strong)**, **Safety flag (none/redirect/escalate)**, **Audio quality (1–5)**, **Free-text comment**. Persist to Supabase; export to JSONL for model fine-tuning. This is how Sabi turns its phone calls into training data without a separate annotation tool.

9. **Per-channel waveform player (green = customer, blue = agent; red = cross-talk; orange = silence)**
   - *What it does:* a glance tells you the conversation shape — long silences, interruptions, who talked more — without listening.
   - *Sabi mapping:* Use **WaveSurfer.js** (MIT) inside a shadcn `<Card>`. Two stacked tracks: child waveform (color e.g. emerald-500) on top, Sabi waveform (sky-500) on bottom. Overlay red rectangles where both channels have signal > threshold (cross-talk = kid interrupting Sabi); orange rectangles for silence runs > 2s. Speed control = **0.5x / 1x / 1.5x / 2x** dropdown (mirror Twilio's 4-step). "Copy link with timestamp" share button (URL encodes `?t=00:34`). Click anywhere on the waveform to seek.

10. **Segments panel for multi-leg / multi-lesson calls**
    - *What it does:* a single call may have multiple segments (transfer, hold-and-resume, multi-agent). The Segments panel top-right lists each with talk time and lets you jump.
    - *Sabi mapping:* A kid often does multiple lessons in one phone call. Top-right list: "Lesson 1 — Letter F • 4:21," "Lesson 2 — Counting 1–10 • 3:08," each clickable to scrub player to that section. Reuses the same panel pattern for transferred calls (e.g., escalated to a human teacher).

11. **40+ dimension filter builder on the call list**
    - *What it does:* lets ops drill into "all calls from MTN Nigeria where MOS was low and answered_by = machine in the last 7 days" in one query.
    - *Sabi mapping:* `<FilterBuilder>` component with predicate chips (`carrier IN [MTN, Airtel]`, `audio_quality < 3`, `lesson_completion = partial`, `state = Lagos`, `safety_flag IS NOT NULL`). Save filters as named views ("MTN Lagos churn risk," "Safety escalations this week"). Backed by a TanStack-Table-style column model.

12. **Recordings list with `.wav` and `.mp3` download in two formats**
    - *What it does:* gives bandwidth-poor reviewers a small file and quality-focused QA a hi-fi file.
    - *Sabi mapping:* Two download buttons per row — "MP3 (32 kbps)" and "WAV (128 kbps)." Naomi's pitch reviewers / partners on slow networks get the MP3; internal QA gets the WAV.

13. **Inline status badge with the exact same color across list, detail, and timeline**
    - *What it does:* a "completed" call looks identical everywhere — your eye learns the color once.
    - *Sabi mapping:* Define ONE `<StatusBadge status="completed|in-progress|failed|safety_escalated|incomplete">` component with semantic tokens. Forbid raw colors in feature code.

14. **"Who Hung Up" tile + chart on the dashboard**
    - *What it does:* one of the most useful blame-localization metrics: did the caller or callee disconnect, and how often was it a SIP error?
    - *Sabi mapping:* "Who hung up" tile with three slices: **Child hung up** (expected at lesson end), **Sabi hung up** (lesson completion), **Disconnect / error** (network drop). When the third slice grows week-over-week, you know infrastructure regressed.

15. **Paste's token-driven theming for Tailwind v4**
    - *What it does:* every visible color/font goes through a token → alias → value chain so dark mode is a one-line swap and brand customization is centralized.
    - *Sabi mapping:* In Tailwind v4, define `@theme` with semantic tokens (`--color-background-primary`, `--color-text-error`, `--color-status-warning`). Reference them from components via `bg-[var(--color-background-primary)]` or extend `theme.colors`. Never use raw `slate-700` etc. in feature components.

16. **"Beta" pill on sidebar items**
    - *What it does:* signals new/experimental features without hiding them.
    - *Sabi mapping:* `<SidebarBetaBadge>` equivalent — useful for "Lesson Authoring (beta)" before it's stable.

17. **Drawer for editing single-resource attributes**
    - *What it does:* lets ops edit a small set of fields without leaving the list.
    - *Sabi mapping:* shadcn `<Sheet>` from the right edge for "edit cohort," "edit number assignment." Reserve full pages for detail viewing.

18. **`StatusMenu` in topbar-right for system health**
    - *What it does:* always-visible pill showing the platform's current incident state (operational / degraded / outage).
    - *Sabi mapping:* topbar status pill linked to Sabi's own status page. Goes red when Hetzner GPU is down or AT inbound is failing — saves support tickets.

## G) Anti-patterns to avoid

1. **Twilio's deep menu legacy** — pre-2020 Console buried features 4–5 clicks deep. Their rebuild explicitly **reduced menu depth** and flattened deep items into tabbed pages. Sabi should ship flat from day one; if a feature needs >3 levels, it's mis-organized.
2. **CSV export caps with no API hint in-context** — Twilio caps Logs export at 2,500 and Insights export at 2,000 but doesn't surface the API alternative in the UI. Sabi should show "Showing first N rows — use the API for full export" with a code snippet.
3. **30-day Voice Insights retention without warning on the dashboard** — GDPR pressure made Twilio cap retention, but the limitation is buried in docs, not on the dashboard. Sabi should show "Showing the last 30 days. Archive older data to keep it searchable."
4. **Two parallel call lists (Logs vs Insights Calls)** — same data, two pages, different filter sets. Confusing. Sabi should ship **one** call list with progressive disclosure (basic filters by default, "Advanced filters" toggle reveals the rest).
5. **Disabling waveform in HIPAA mode without explanation** — Twilio just hides it. Sabi should show "Waveform hidden — privacy mode enabled" so the operator knows it's intentional, not broken.
6. **Hidden agent action buttons in the canvas** — Flex's CallCanvas action bar can scroll off on narrow screens. Sabi's per-call action bar (escalate / flag / re-listen) must stay sticky.
7. **Speed control as 4 discrete steps (Slow/Normal/Fast/Very Fast)** — fine, but no 0.75x option. Many QA listeners want 0.75x for accent comprehension; ship at least 5 steps (0.5 / 0.75 / 1 / 1.5 / 2).
8. **Status pill as the only place to change availability** — Flex puts agent status only in the topbar. Sabi should also expose it via Cmd-K so power users don't mouse.
9. **No empty-state docs in Paste** — Twilio's empty-state pattern isn't formally documented. Sabi should standardize a `<EmptyState icon label description cta>` component up front; otherwise every list invents its own.
10. **Sub-account hierarchy bolted on top of single-account UI** — Twilio's AccountSwitcher works but feels grafted. Sabi should design for the district→school→cohort hierarchy from v1, not retrofit.
11. **Conversation Relay dashboard separate from Voice Insights** — Twilio shipped a parallel dashboard for AI agents. Sabi shouldn't fork; AI metrics belong inline with regular call metrics, toggleable by a "Show AI-only KPIs" switch.
12. **Inline-edit annotations without keyboard shortcuts** — Flex lets you set call_score by clicking stars. Sabi should support `1–5` keys + `s` for safety flag + `c` for comment when a call detail page is focused — annotators churn through hundreds per session.

## H) Source URLs

Primary docs — Voice Insights:
- https://www.twilio.com/docs/voice/voice-insights/call-summary
- https://www.twilio.com/docs/voice/voice-insights/api/call/details-call-summary
- https://www.twilio.com/docs/voice/voice-insights/api/call/details-sdk-call-quality-events
- https://www.twilio.com/docs/voice/voice-insights/advanced-features
- https://www.twilio.com/docs/voice/voice-insights/call-insights-dashboard
- https://www.twilio.com/docs/voice/insights/dashboards
- https://www.twilio.com/docs/voice/voice-insights/conversation-relay-insights-dashboard
- https://www.twilio.com/docs/voice/voice-insights/frequently-asked-questions
- https://www.twilio.com/docs/voice/voice-insights/api/call/call-events-resource
- https://www.twilio.com/docs/voice/voice-insights/event-streams/call-insights-events
- https://www.twilio.com/en-us/changelog/voice-insights-call-summary-and-events-updates
- https://www.twilio.com/docs/events/event-types/voice-insights/voice-sdk-metrics

Primary docs — Console / navigation / Paste:
- https://www.twilio.com/docs/usage/new-twilio-console
- https://www.twilio.com/en-us/blog/products/launches/introducing-the-new-twilio-console-html
- https://www.twilio.com/en-us/blog/developers/bringing-cohesion-to-the-twilio-product-suite-part-ii
- https://www.twilio.com/en-us/changelog/new-navigation-experience-in-twilio-console
- https://help.twilio.com/articles/27885350503195-Twilio-Console-and-Help-Center-UI-Updates
- https://paste.twilio.design/
- https://paste.twilio.design/experiences/navigation
- https://paste.twilio.design/components/sidebar-navigation
- https://paste.twilio.design/components/sidebar
- https://paste.twilio.design/foundations/colors
- https://paste.twilio.design/foundations/typography
- https://paste.twilio.design/tokens
- https://paste.twilio.design/tokens/list
- https://paste.twilio.design/customization/creating-a-custom-theme

Primary docs — Flex:
- https://www.twilio.com/docs/flex/admin-guide/core-concepts/flex-ui
- https://www.twilio.com/docs/flex/onboarding-guide/explore-the-built-in-flex-ui-views
- https://www.twilio.com/docs/flex/developer/ui
- https://www.twilio.com/docs/flex/developer/ui/components
- https://www.twilio.com/docs/flex/onboarding-guide/handle-incoming-voice-and-sms-tasks
- https://twilio.com/docs/flex/supervisor-desktop-agents-data-table-and-call-monitoring
- https://www.twilio.com/docs/flex/admin-guide/setup/voice/dialpad/enable
- https://www.twilio.com/docs/flex/end-user-guide/dialpad-use
- https://www.twilio.com/docs/flex/end-user-guide/insights
- https://www.twilio.com/docs/flex/end-user-guide/insights/player
- https://www.twilio.com/docs/flex/end-user-guide/insights/conversation-screen
- https://www.twilio.com/docs/flex/end-user-guide/insights/conversation-assessments
- https://www.twilio.com/docs/flex/end-user-guide/insights/metrics/agent-copilot
- https://www.twilio.com/docs/flex/developer/insights/playback-recordings-custom-storage
- https://assets.flex.twilio.com/docs/releases/flex-ui/1.21.0/AgentDesktopView.html

Primary docs — Recordings & Call Logs:
- https://www.twilio.com/docs/voice/api/recording
- https://www.twilio.com/docs/voice/api/recording-transcription
- https://www.twilio.com/docs/voice/twiml/record
- https://help.twilio.com/articles/223132947
- https://support.twilio.com/hc/en-us/articles/360002588893-Downloading-and-Deleting-Twilio-Call-Recordings
- https://www.twilio.com/docs/voice/tutorials/how-to-retrieve-call-logs
- https://support.twilio.com/hc/en-us/articles/14890707708059-How-to-View-and-Export-SIP-Voice-Call-Logs-from-Twilio-Console
- https://help.twilio.com/articles/223183588-Exporting-SMS-and-Call-Logs
- https://www.twilio.com/docs/voice/resolve-call-log-usage-discrepancies
- https://www.twilio.com/docs/voice/troubleshooting
- https://www.twilio.com/docs/usage/troubleshooting/debugging-your-application

Secondary / pattern references:
- https://www.tatvasoft.com/blog/how-do-i-integrate-crm-into-twilio-flex/
- https://symbl.ai/developers/blog/integrating-conversation-intelligence-with-twilio-flex/
- https://hamming.ai/resources/real-time-voice-analytics-dashboards-customer-service
- https://thelevel.ai/blog/call-center-recording-solutions
- https://ui.shadcn.com/examples/dashboard
- https://www.freecodecamp.org/news/build-an-admin-dashboard-sidebar-with-shadcn-ui-and-base-ui/


---

## Comparable 2: Africa's Talking dashboard

Empty. I have enough source data. Composing the final report now.

# Africa's Talking dashboard

## A) Product overview (1 paragraph)

Africa's Talking (AT) is a pan-African CPaaS that exposes five product families through one shared web console at `account.africastalking.com`: **SMS** (one-way, two-way short codes, Bulk, Premium subscriptions), **Voice** (inbound IVR on virtual numbers, outbound calls, SIP trunking, recordings, queues, conferences), **USSD** (session-based menu apps over service codes), **Airtime** (programmatic top-ups across telcos with reseller-style billing), and **Payments / Mobile Data / WhatsApp** as adjacent products. The console exists in two parallel modes — **Sandbox** (orange chrome, no charges, traffic terminates in a browser-based **Simulator** at `simulator.africastalking.com:1517` instead of a real handset) and **Live** (green chrome, real money, real telcos). Per the help center: *"On account.africastalking.com the Sandbox dashboard is orange while the live dashboard is green."* Every developer gets the same SDK; sandbox vs live is just a different app whose `username` is literally the string `sandbox`. The Live side is organized as a **Team** (org) → **Apps** (the actual integrations, each with its own username, API key, stash balance, and dashboard) → **Products** (SMS / Voice / USSD / Airtime / Payments tabs inside each app). Status page (`status.africastalking.com`) lists the surface area cleanly: SMS, Bulk, Premium, Airtime, Chat, Insights, Voice, USSD, Mobile Data, Echo, Sandbox, Web, Docs, Website, Dashboard — 15 components, each with 90-day uptime and historical incidents.

## B) Navigation + topbar pattern (detailed)

**Two-layer hierarchy.** AT's nav is unusual and deliberate: it doesn't put product tabs in the topbar. Instead the topbar is for **environment / org / app context**, and the sidebar is for **product surfaces inside that one app**.

**Topbar (post-login, account portal):**
- Brand mark "Africa's Talking" (links home)
- Team dropdown (each user can belong to multiple Teams = orgs)
- A primary orange CTA button labeled **"Go To Sandbox App"** when you're in the account/teams view. The button is the only way into the sandbox dashboard and is colored to match the sandbox chrome. (*"Log into your account, click on the orange Go To Sandbox App button"* — help center, API key article.)
- "Create App" button — opens a modal: **App Name**, **Username**, **Country** dropdown. Username becomes the API username and is permanent.
- Live apps list cards on the home: each card shows the app name, username, country flag, and a tile/avatar; click → enter that app's dashboard.
- Account/profile menu top-right (Settings, Logout, Billing).
- "Quick Guide" / Docs link.

**Sidebar (inside a single app's dashboard):** vertical, fixed-left, persistent. Product groups are top-level items; each expands into product-specific subroutes. Confirmed sidebar nodes from official + tutorial sources:

- **Dashboard / Overview** (home for that app — shows stash balance, recent activity, app username)
- **SMS**
  - Bulk → Outbox (sent messages list, per-recipient delivery status), Analytics, Send (composer)
  - Inbox (incoming SMS to your short codes)
  - Short Codes (list + Create)
  - Alphanumerics / Sender IDs (list + "Request Alphanumeric Sender ID")
  - Premium (subscription products, keywords)
  - Callback URLs (delivery report URL, incoming SMS URL)
- **Voice**
  - Phone Numbers (list of your virtual/regular/toll-free/premium/SIP numbers; per-row "Actions" → change callback URL — confirmed: *"voice → phone Numbers → actions"*)
  - Request (request a new number; selector for Toll-Free / Premium / Regular / SIP / Virtualized Physical Line)
  - Calls (call log)
  - Recordings (MP3 list)
  - Queues
  - Conferences
  - SIP (credentials, trunk config)
  - Callback URL settings
- **USSD**
  - Service Codes (list of channels; "Create a channel" button directly above the table)
  - Sessions (per-session log; each row has an "Actions" column with a three-dot more menu → "Details")
  - Callback URLs
- **Airtime**
  - Send Airtime (composer)
  - Transactions (status: SENT → SUCCESS → FAILED), filter by date/telco
  - Callback URL (optional)
- **Payments**
  - Products (list + Create payment product)
  - Wallet (separate from app stash — this is the float for mobile money)
  - Transactions
  - Callback URLs
- **Mobile Data**
  - Bundles, Transactions
- **WhatsApp** (newer collection)
- **Settings**
  - API Key (gated by password re-prompt; "Generate" button; one-time copy modal: *"you will not see it from the dashboard on subsequent visits"*; ~3-minute propagation warning)
  - App profile
  - Webhooks / Callback URLs (consolidated)
  - Team members & roles
- **Billing**
  - Stash (the AT API balance used to pay for SMS/Voice/USSD/Airtime/Payments transaction fees — *"AT Stash is the application balance displayed on your App dashboard"*)
  - Payment Methods (M-Pesa, M-Pesa B2B, Card, Bank — different per country)
  - Invoices / Statements

**Topbar color is the environment indicator.** Sandbox = orange; Live = green. This is the single biggest visual cue and is repeated in every screenshot in third-party tutorials. The button to enter sandbox is also orange, so the visual language is consistent end-to-end.

**App switcher.** Switching apps means going back to `account.africastalking.com`, seeing the Live Apps list/cards plus the Sandbox tile, and clicking the target app. There is **no** global "currently viewing: APP X ▾" dropdown inside the per-app dashboard — switching context = leaving and re-entering. (This is an anti-pattern; see G.)

## C) List/index pages — columns, filters, sort, search, density, pagination, bulk actions, empty state

AT uses a recurring **list page pattern** across products. Same skeleton, different columns. The skeleton:

- Page header: product/sub-product name (e.g. "USSD Sessions", "Voice Phone Numbers", "Airtime Transactions"), with a primary CTA in the top-right corner (e.g. "Create a channel" appears *"directly above the empty table of currently configured codes"* — Medium tutorial). Buttons are blue for primary action (e.g. "Create Channel"); orange is reserved for the global sandbox toggle.
- Tabular body with row-level actions in a final "Actions" column = a three-dot/kebab `⋯` menu. Confirmed pattern across USSD Sessions and Voice Phone Numbers: *"select the three dots at the far right"* → "Details", "Edit callback URL", etc.
- Empty state: a centered prompt to create the first resource (e.g. when no short codes exist, the Create button still appears above the empty table).
- Date-based filters on transaction-style tables (Airtime transactions, SMS Outbox, Calls).

**Per product, confirmed columns and statuses:**

**SMS → Bulk → Outbox** (sent messages list)
- To (msisdn), From (sender ID / short code), Message body (truncated), Cost, Status, Date/time
- Statuses (delivery report values, verbatim): **Sent** (handed to telco), **Submitted** (telco accepted), **Buffered** (telco queued), **Success** (handset delivered), **Rejected** (telco rejected), **Failed** (did not reach handset)

**Voice → Calls** (call log) — fields shown on the dashboard for each call (compiled from billing article + parameter article + events URL article):
- sessionId (unique per call, e.g. `ATVId_0496051a90c295c4fa62fac955555a6b`)
- callerNumber (E.164 with `+`)
- destinationNumber
- direction (Inbound / Outbound)
- callerCountryCode
- callStartTime
- callSessionState — values: **Active, Dialing, Ringing, Bridged, Completed, NotAnswered, Enqueued, Dequeued, Expired** (Expired = couldn't reach after 6-hour retry window)
- duration (seconds)
- cost (charged from stash; SIP→SIP = KES 1/min, regular/virtual = KES 5/min, varies by country)
- isActive (1/0)
- hangupCause (e.g. USER_BUSY, NO_ANSWER, NO_USER_RESPONSE — distinct codes)
- recordingUrl (link to MP3 if recorded)
- amount + currencyCode (billing fields)

**USSD → Sessions**
- sessionId, phoneNumber, serviceCode, text (running concat of user input), date, status, error message field (visible per session)
- Row Actions kebab → **Details** (full transcript of the back-and-forth, response codes from your endpoint, latency)

**Airtime → Transactions**
- Recipient msisdn, Amount, Currency, Telco, Status (**SENT → SUCCESS / FAILED**), Date, Request ID, Discount earned
- *"Africa's Talking relays the final status of the airtime request to the client by posting it to the dashboard or a callback"*

**Voice → Phone Numbers**
- Number, Type (Toll-Free 0800 / Premium 0900 / Regular / SIP / Virtualized Physical Line), Country, Callback URL, Events URL, Actions kebab → Edit callback, Edit events URL, View calls on this number

**Bulk actions:** Limited. Bulk SMS composer is the closest thing — paste/import recipients, send to many at once. There's no documented multi-select on list tables (e.g. you can't multi-select call recordings and bulk delete them through the public docs).

**Pagination + search:** Standard paginated tables; date filter is the primary filter on transaction-type lists. Search on free text (e.g. msisdn) is implied by tutorials but not documented as global.

**Density:** Default comfortable density; the tables are not Stripe-tight. Each row has visible padding so a sandbox session table with 5 rows fills most of a viewport.

## D) Detail/drawer pages — layout, sections, audio player, transcript, drilldown

AT's detail surface is **a dedicated page reached via the row kebab → "Details"**, not a side drawer (unlike Twilio). The detail page structure is consistent:

**USSD Session Detail page:**
- Header: session ID, phone number, service code, total duration, final status
- Timeline / transcript table: each step in the menu (request `text` from telco, response `CON ...` or `END ...` from your endpoint, timestamp, latency in ms, HTTP status of your callback)
- Error block: if the callback failed or returned malformed response, the **error message field** is rendered prominently
- Raw request/response payload (collapsible)

**Voice Call Detail page:**
- Header: sessionId, caller/destination, duration, cost, status (Completed / NotAnswered / Expired etc.), hangupCause
- Audio player (if recordingUrl present) — inline MP3 player with play/seek
- Recording metadata: duration, file size, retention window
- Event timeline: every callback POST to your callback URL + every events URL POST (Active → Dialing → Ringing → Bridged → Completed) with timestamps, HTTP status of your endpoint, latency
- DTMF digits captured (from `<GetDigits>`)
- Action history: which voice actions (Say, Play, GetDigits, Record, Dial, Enqueue, Dequeue, Conference, Redirect, Reject) were executed in order
- Raw XML response your server returned (collapsible)

**SMS Message Detail:**
- Recipient, body, cost, status with full delivery-report ladder (Sent → Submitted → Buffered → Success), MCC/MNC telco breakdown, retry count

**Airtime Transaction Detail:**
- Recipient, amount, telco, request payload, status ladder (SENT → SUCCESS / FAILED), discount earned, delivery report timestamp, error message if failed

**The "Drilldown" loop is the killer pattern.** From product analytics → list of transactions → individual transaction → raw callback log. You can always get from a high-level number ("12 failures today") down to the exact HTTP exchange that failed, with the timestamp, the error code, and the request body. No "this is opaque, contact support" dead-ends.

## E) Visual language — colors, typography, density, iconography, motion, brand voice

- **Brand palette is owned by environment, not by the brand mark.** Orange = sandbox; Green = live. Primary action button inside dashboards is a distinct blue (e.g. "Create Channel"). This is a 3-color functional palette: orange (env: dev), green (env: prod), blue (action). Black/dark text on white surface; grey for secondary info.
- **Typography:** Standard sans-serif (Lato / system stack feel), no exotic font. Headings are bold, larger, no all-caps. Field labels are sentence-case ("Service Code", "Callback URL", "Channel Number"). Documentation site uses a slightly different sans (closer to Inter / docs theme).
- **Density:** Comfortable, not dense. Tables have meaningful row height. The console reads as an admin tool for developers in low-bandwidth environments — it loads fast, doesn't over-animate, and works well on slow connections (an explicit AT design constraint given their market).
- **Iconography:** Sparse. Three-dot kebab `⋯` for row actions. Standard pencil/edit, trash/delete in some places. Country flags on app cards. Telco logos (MTN, Safaricom, Airtel, Glo, etc.) appear in analytics breakdowns.
- **Motion:** Minimal. Pages load, modals fade in for create flows, copy-to-clipboard confirmation for the API key. No transitions for transitions' sake. This is deliberate — fast networks aren't a given for AT's users.
- **Brand voice (in console copy + docs):** Plain, direct, transactional. "Generate", "Create Channel", "Top up", "Send Airtime". Help center voice is friendly-conversational ("How do I…", "What is my…", "Why am I getting…") with first-person questions as article titles. Marketing voice (#WeLoveNerds tagline on the Airtime page) is dev-affectionate.

## F) Specific patterns Sabi should copy (numbered)

1. **Environment-as-color dashboard chrome.** WHAT: The entire dashboard chrome (topbar, primary CTA color, app card border) changes color based on whether you're in sandbox or production. WHERE: Topbar + sidebar accent. SABI MAPPING: Sabi's board console will run in two modes — **staging** (curriculum changes not yet live to phone callers) and **production** (changes immediately affecting real children calling in). Use a stripe across the topbar: muted gold/grey for staging, full Sabi gold for production. In Tailwind v4, expose `--chrome-env` as a CSS variable that the layout reads. Clerk org metadata + a `dataMode` cookie can drive this. Makes "am I about to push this to real kids?" impossible to miss.

2. **Application switcher = leave-and-re-enter via a top-level apps grid.** WHAT: AT doesn't put a "switch app" dropdown inside the app shell; it puts the apps grid at the org root. WHERE: `account.africastalking.com` home. SABI MAPPING: For Sabi, each **partner school / pilot site / region** could be its own "app". Inverse-AT here: also offer an inline `⌘K` switcher (AT's lack is an anti-pattern). Use shadcn `Command` palette with each Clerk Organization as an entry. The grid at the org root stays as the canonical home.

3. **Three-dot row kebab → Details page.** WHAT: Every list-page row ends in a kebab; primary action is "Details" which opens a dedicated page (not just a drawer) with raw payload, timeline, audio. WHERE: USSD Sessions, Voice Calls, Airtime Transactions. SABI MAPPING: For Sabi's **call log**, **session transcript**, and **lesson attempt** tables, end every row in a `DropdownMenu` (shadcn) with at minimum: View Details, Copy Session ID, Listen to Recording, Re-run with same input, Flag for review. Keep the detail view as a full route (`/calls/[id]`) not a drawer — easier to share, deep-link in Sentry, and bookmark.

4. **Per-call event timeline with HTTP status of your callback.** WHAT: AT's call detail shows every callback POST AT made to your server, the timestamp, the HTTP code your server returned, and the latency. WHERE: Voice Call Detail page. SABI MAPPING: For each Sabi call, log every transition (caller dials in → Whisper STT request → Claude Haiku request → Chatterbox TTS request → audio streamed back) with timestamp, ms latency, HTTP status, and the request/response bytes. Store in Supabase, render as a vertical timeline component (shadcn `Card` per row, lucide `Circle` / `CheckCircle` / `XCircle` for status). Critical for the moment a child says "Sabi didn't understand me" — you need to see exactly which step broke.

5. **Audio player inline in detail page.** WHAT: AT's call detail embeds an HTML5 audio player for the recording. WHERE: Voice Call Detail. SABI MAPPING: Trivial but huge — every Sabi session row needs an inline `<audio controls>` for both the caller's voice and Sabi's response audio (two tracks, side-by-side). Use shadcn-style `audio` wrapper with waveform (wavesurfer.js). Listening to actual children's audio is the only way to QA the curriculum; don't make Naomi or Sonia download MP3s.

6. **Status ladder for async operations.** WHAT: AT models async delivery as a status ladder (SMS: Sent → Submitted → Buffered → Success / Rejected / Failed; Airtime: SENT → SUCCESS / FAILED). The dashboard shows the *current* rung and the *highest* rung reached. WHERE: SMS Outbox, Airtime Transactions. SABI MAPPING: Use the same pattern for **lesson assignments** (queued → played → completed / abandoned / errored) and **enrollment / consent flows** (collected → verified → activated → onboarded). shadcn `Badge` with a tooltip showing the ladder; the badge color changes based on the current rung.

7. **Hangup cause as a first-class field.** WHAT: AT exposes `hangupCause` (USER_BUSY, NO_ANSWER, NO_USER_RESPONSE, etc.) as a distinct enumerated column on the call log. WHERE: Voice Calls list + Detail. SABI MAPPING: For Sabi, expose `endCause` as: child_hung_up, network_dropped, sabi_finished_lesson, sabi_safety_redirect, parent_intervened, idle_timeout, error. This makes the difference between "kid hung up bored" and "audio quality killed the call" visible in aggregate. Drives content iteration.

8. **One-time API key reveal with timing caveat.** WHAT: AT generates the API key once, shows it in a modal, warns it will never be shown again, and adds a ~3-minute propagation warning. WHERE: Settings → API Key. SABI MAPPING: For any board-issued credentials (school admin tokens, partner API keys), use shadcn `Dialog` with a copy-to-clipboard button, an obvious "Save this now — we can't show it again" warning, and store only a hash server-side (Clerk handles this for user tokens; do it ourselves for service tokens). Wait, propagation isn't a Sabi issue, but the one-time reveal is the right pattern.

9. **Callback URL config lives at the resource level, not globally.** WHAT: AT lets you set a callback URL per phone number (Voice → Phone Numbers → row → Actions → Edit callback). Different numbers can point at different endpoints. WHERE: Per-resource Actions menu. SABI MAPPING: Per-school webhook URLs for "lesson completed", "child enrolled", "consent received". Each pilot site can wire their own LMS / Google Sheet / Zapier without Sabi having to maintain a global router. shadcn `Sheet` for the edit, with URL validation (must be HTTPS in prod, can be ngrok in staging).

10. **Voice actions as primitives.** WHAT: AT's Voice API is a small composable XML set (Say, Play, GetDigits, Record, Dial, Enqueue, Dequeue, Conference, Redirect, Reject). The dashboard's call detail shows which actions ran in order. WHERE: Call Detail action history. SABI MAPPING: Model Sabi lesson steps as named primitives — `SpeakLesson`, `AskQuestion`, `WaitForAnswer`, `RepeatIfUnclear`, `Encourage`, `MoveOn`, `EndLesson`. Render the action sequence per call in the detail page. Naomi can scan "Sabi went Speak → Ask → Wait → (silence) → Repeat → Wait → (silence) → MoveOn" and immediately see the kid checked out.

11. **Status page with per-component uptime is part of the trust story.** WHAT: AT's `status.africastalking.com` lists 15 separate components (SMS, Bulk, Premium, Airtime, Chat, Insights, Voice, USSD, Mobile Data, Echo, Sandbox, Web, Docs, Website, Dashboard) each with 90-day uptime %. WHERE: External public domain. SABI MAPPING: When Sabi has partner schools / NGOs / funders, ship a public `status.sabi.education` (or similar) showing: Phone Pipeline, Whisper STT, Claude Haiku, Chatterbox TTS, Admin Console, Reports. Use a hosted statuspage service or roll your own with Next.js + Vercel cron pinging each subsystem. Builds trust faster than any pitch deck.

12. **Per-app stash with low-balance behavior.** WHAT: AT shows the app stash balance prominently on the app dashboard home; failed transactions when the stash hits zero are visible immediately. WHERE: App Dashboard home + Billing → Stash. SABI MAPPING: Show **per-school cost-to-date** (Whisper tokens + Haiku tokens + Chatterbox seconds + telephony minutes) on each school's dashboard home. Even though Sabi is free to kids, partner schools / funders care about unit economics. This is also where you'd surface "this school used 47% more compute this week — check if a kid is calling repeatedly."

13. **Simulator parallel to production.** WHAT: AT runs `simulator.africastalking.com` — a browser-based phone that simulates real calls/SMS/USSD against the same sandbox app. Developers test without burning credit or holding a handset. WHERE: Separate subdomain, same auth. SABI MAPPING: Build a `/simulator` route in the board console that lets a board member "place a call" to Sabi from the browser using WebRTC into the same pipeline that real phones hit. Lets Naomi demo Sabi in a board meeting without dialing a Nigerian number, and lets Sonia QA new lessons before they ship to real kids.

14. **Help center articles titled as user questions.** WHAT: Every AT help article is titled as the question a user types into search ("How do I generate an API Key?", "Why am I getting the error 'Supplied Authentication is Invalid'?", "What is my Username and API Key?"). WHERE: `help.africastalking.com`. SABI MAPPING: Sabi's docs and inline help tooltips should follow the same convention. Helpful for SEO when partners search, and forces the writer to think from the user's POV. Use `?` next to any non-obvious field in the console — onclick opens a popover with the matching help article snippet.

15. **Country selection is a first-class app property.** WHAT: When you create an AT app, country is a required field; it determines which products, pricing, and telco integrations are available. WHERE: Create App modal. SABI MAPPING: When provisioning a new Sabi partner site, country is required and drives: TTS voice (Nigerian English vs Pidgin), pedagogy localization (UK vs US phonics, Naija age 6–12 vs other), pricing tier (which telco's per-minute rate), and which Africa's Talking number/short-code pool the site uses. Don't let users pick country later.

## G) Anti-patterns to avoid

- **App switcher requires leaving the app.** AT has no inline `⌘K`/header dropdown to jump between apps. To switch from "Sabi Lagos" to "Sabi Abuja" you'd go back to `account.africastalking.com`, find the tile, click in. Painful with 5+ apps. **Sabi must add an inline app/org switcher** (shadcn `Command` palette + Clerk Organizations).
- **API key shown exactly once with no rotation UX.** AT's "copy now or generate again" is hostile when a key is rotated under emergency. The "wait ~3 minutes before testing" is mystery delay. **Sabi: show last 4 chars + rotation history + "tested OK at X timestamp" indicator.**
- **No bulk actions on tables.** Can't multi-select recordings to delete, can't bulk re-trigger failed SMS, can't bulk export. **Sabi: add multi-select + bulk export CSV / bulk re-run from day one** — pilot QA workflows live and die on this.
- **No global search.** Can't type a phone number in a topbar search and jump to that caller's full history across SMS + Voice + USSD. **Sabi: ship `⌘K` search across all sessions/calls/children/schools** — critical when a teacher calls and says "a child named Amara called this morning and it didn't work."
- **No real-time updates on list pages.** Dashboards require manual refresh. **Sabi: use Supabase realtime channels on list pages** so a teacher demoing in a board meeting sees the call land.
- **Sandbox is a separate username (`sandbox`), not a separate env in the same app.** Means staging code paths diverge from prod. **Sabi: keep the same app shape across envs, only swap env vars + the chrome color.**
- **Detail pages are routes, not drawers (good for sharing, bad for fast triage).** AT forces a full page load to see details. **Sabi: shadcn `Sheet` drawer for the 80% case + a "Open as full page" link for share/deep-link.**
- **No call analytics dashboard out of the box.** AT shows raw counts ("messages successfully sent per telco") but no funnel, no retention, no time-to-resolution. **Sabi: ship a charts tab from v1** (lesson completion rate, drop-off heatmap, repeat-call rate, telco audio quality) using Recharts or Tremor.
- **Voice dashboard color cue can be lost on colorblind users.** Orange/green env cue fails red-green colorblindness. **Sabi: pair color with an explicit "Production" / "Staging" pill** in the topbar.
- **Documentation portal is JS-rendered and fails for crawlers / archive tools.** Hurts SEO + makes LLMs miss the docs. **Sabi: SSR all docs (Next.js App Router + `generateStaticParams`)** so search engines and AI assistants can crawl.
- **Three-dot kebabs hide too much.** Critical actions like "Edit callback URL" are buried in the row kebab. New users hunt for them. **Sabi: surface the 1–2 most common actions inline; put rest in kebab.**

## H) Source URLs

- https://account.africastalking.com/apps/sandbox
- https://account.africastalking.com/
- https://simulator.africastalking.com:1517/
- https://simulator.africastalking.com/simulator/ussd
- https://developers.africastalking.com/docs/voice/overview
- https://developers.africastalking.com/docs/voice/make_call
- https://developers.africastalking.com/docs/voice/actions/say
- https://developers.africastalking.com/docs/voice/SIP
- https://developers.africastalking.com/docs/voice/handle_calls
- https://developers.africastalking.com/docs/ussd/overview
- https://developers.africastalking.com/docs/ussd/handle_sessions
- https://developers.africastalking.com/docs/ussd/notifications
- https://developers.africastalking.com/docs/sms/sending/bulk
- https://developers.africastalking.com/docs/airtime/query/find_transaction_status
- https://developers.africastalking.com/docs/payments/topup_stash
- https://developers.africastalking.com/simulator
- https://help.africastalking.com/en/
- https://help.africastalking.com/en/collections/150795-quick-guide-to-africa-s-talking
- https://help.africastalking.com/en/collections/150771-voice
- https://help.africastalking.com/en/collections/150764-sms
- https://help.africastalking.com/en/collections/150775-ussd
- https://help.africastalking.com/en/collections/150760-airtime
- https://help.africastalking.com/en/collections/150790-payments
- https://help.africastalking.com/en/collections/150837-sender-ids-alphanumerics
- https://help.africastalking.com/en/articles/1170660-how-do-i-get-started-on-the-africa-s-talking-sandbox
- https://help.africastalking.com/en/articles/1361037-how-do-i-generate-an-api-key
- https://help.africastalking.com/en/articles/2189460-what-are-the-sandbox-and-the-live-environments
- https://help.africastalking.com/en/articles/2258771-what-is-a-team-an-app-and-analytics
- https://help.africastalking.com/en/articles/2298182-what-is-my-stash-and-my-wallet
- https://help.africastalking.com/en/articles/1981959-how-do-i-top-up-my-account
- https://help.africastalking.com/en/articles/2948521-understanding-parameters-used-in-a-call
- https://help.africastalking.com/en/articles/1160521-what-does-hangupcause-parameter-mean
- https://help.africastalking.com/en/articles/1163069-what-is-an-events-url
- https://help.africastalking.com/en/articles/2282146-what-types-of-voice-phone-numbers-are-available
- https://help.africastalking.com/en/articles/2900658-what-you-need-to-build-a-call-center
- https://help.africastalking.com/en/articles/2900701-implementing-an-interactive-voice-response-ivr-system
- https://help.africastalking.com/en/articles/1152209-how-does-voice-billing-work
- https://help.africastalking.com/en/articles/1035338-why-does-it-say-sent-on-my-dashboard-but-the-airtime-hasn-t-reached-the-recipient
- https://help.africastalking.com/en/articles/11462686-how-to-view-ussd-sessions
- https://help.africastalking.com/en/articles/4427018-what-is-a-team-an-app-and-analytics
- https://help.africastalking.com/en/articles/3954086-how-do-i-top-up-my-africa-s-talking-account-using-b2b
- https://help.africastalking.com/en/articles/407085-how-do-i-set-up-my-sender-id-in-kenya-or-uganda
- https://help.africastalking.com/en/articles/4885295-airtime-api
- https://help.africastalking.com/en/articles/2255714-how-do-i-top-up-my-mobile-data-wallet
- https://help.africastalking.com/en/articles/1399787-how-do-i-know-if-my-airtime-has-been-sent
- https://help.africastalking.com/en/articles/6151516-what-is-the-flow-for-an-airtime-request
- https://help.africastalking.com/en/articles/9915125-how-do-i-go-live-with-ussd
- https://help.africastalking.com/en/articles/6049012-what-do-i-need-to-set-up-a-sip-trunk-connection
- https://help.africastalking.com/en/articles/1163043-how-do-i-set-up-my-sip-phone
- https://status.africastalking.com/
- https://africastalking.com/
- https://africastalking.com/voice
- https://africastalking.com/voice-api
- https://africastalking.com/voice/conference
- https://africastalking.com/airtime
- https://africastalking.com/messaging-bulk
- https://africastalking.com/messaging-api
- https://africastalking.com/pricing
- https://africastalkingltd.gitbooks.io/mobile-communication-apis/content/sandbox-set-up.html
- https://dev.to/arseytech/from-code-to-conversation-mastering-africas-talking-voice-api-4aa8
- https://dev.to/supamodo/transactional-sms-setup-with-africas-talking-sdk-for-single-and-bulk-messages-16fg
- https://medium.com/f4life/serverless-ussd-with-africas-talking-62c97ef91fdd
- https://bfaglobal.com/insights/serverless-ussd-with-africas-talking-part-1/
- https://bfaglobal.com/insights/serverless-ussd-with-africas-talking-part-2/
- https://medium.com/@chegemaimuna/africas-talking-node-js-express-application-for-sending-sms-f735ef5592c9
- https://medium.com/@chegemaimuna/africas-talking-node-js-express-ussd-application-7e10aa400b98
- https://medium.com/@antonriziki/how-to-make-automated-calls-using-africas-talking-voice-api-in-python-bbdb7a5f5c46
- https://medium.com/@franciskisiara/getting-started-with-africas-talking-bulk-sms-api-for-php-developers-3e7e7f13aa90
- https://helloduty.com/blogs/getting-started-with-the-africas-talking-ussd-api
- https://anthonylimo.hashnode.dev/build-an-interactive-voice-response-ivr-application-with-africas-talking-flask-docker-and-heroku-ck2ncufc8001cfcs1p8h5ifn0
- https://workdo.io/documents/africas-talking-detailed-documentation/
- https://learn.microsoft.com/en-us/connectors/africastalkingsms/
- https://learn.microsoft.com/en-us/connectors/africastalkingvoice/
- https://learn.microsoft.com/en-us/connectors/africastalkingairtime/
- https://learn.microsoft.com/en-us/connectors/africastalkingpayments/
- https://github.com/AfricasTalkingLtd/africastalking.Net
- https://github.com/AfricasTalkingLtd
- https://www.postman.com/africastalking/workspace/africa-s-talking-apis/
- https://www.capterra.com/p/10002327/Africas-Talking-Voice/
- https://www.softwareadvice.com/voip/africas-talking-voice-profile/
- https://docs.communityhealthtoolkit.org/building/messaging/gateways/africas-talking/
- https://docs.novu.co/platform/integrations/sms/africas-talking
- https://documentation.proto.cx/aicx/aicx-modules/ai-agents/publishing/africas-talking


---

## Comparable 3: Supabase Studio

No prior research on Supabase Studio in agent-research. Synthesizing now.

---

# Supabase Studio

## A) Product overview (1 paragraph)

Supabase Studio is the browser-based admin/QA console for a Supabase project — a hosted Postgres database plus auth, storage, edge functions, realtime and logs. Studio is the workbench developers and project admins use to manage schemas, query data, inspect users, browse files, debug logs, and configure infrastructure. It is open source (lives in the `supabase/supabase` monorepo under `apps/studio`, runnable locally and self-hosted), is built on Next.js + Tailwind + a shadcn/ui–compatible component library (Radix + Geist–inspired), and uses Monaco for SQL editing, TanStack Table for data grids and React Data Grid for the spreadsheet-like Table Editor. The product wraps seven service health endpoints (Database, PostgREST, Auth, Realtime, Storage, plus Edge Functions and Logs) behind a single `ProjectLayout` shell, with routing that adapts to project lifecycle states (active, building, paused). The defining ethos: dark-mode-native, terminal-minded, brand-green used only for CTAs, hierarchy through size and border contrast rather than weight or shadow, and Postgres-first muscle memory (SQL is a first-class action, not buried). Recent versions (Studio 2.0 in 2024, 3.0 in 2025, plus the 2026 "Tabs" update) layered on tabbed editing, inline SQL from anywhere in the dashboard, AI-assisted query writing with diff-view, schema visualizer, shared snippets, and AI-powered filter bars.

## B) Navigation + topbar pattern (detailed)

**Two-level shell.** Studio is built on a `ProjectLayout` wrapper that owns global state (project health, lifecycle transitions, sidebar collapse state). Above the project level, an organization-scoped layer lets you switch between organizations and projects. The 2026 nav refactor (rolled out behind a feature-preview flag, see Discussion #33670) hardened this into: **organizations are the primary hub; one org at a time; projects under that org are what populates the project picker; account settings live in a separate top-right dropdown that is always visible regardless of which org you are in**.

**Top header (project context):**
- Left: Supabase logo / home (collapses sidebar when hovered/clicked)
- Organization picker (dropdown — "click the Organization picker on the top header" — to swap orgs; switching orgs filters the project list)
- Project picker (within the selected org)
- Branch selector (for projects with Supabase Branching)
- Center/inline: contextual breadcrumb / page title
- Right: Inline SQL Editor trigger (new in 2026 — "run SQL from anywhere in the Dashboard … query and modify tables, add triggers, functions, RLS policies, and anything else you can do from the main SQL Editor")
- Right: AI Assistant trigger (multiple chats per project, switchable without losing history, stored locally)
- Right: Feedback button
- Right: Notifications bell
- Right: Help / Docs link
- Right: User avatar dropdown (account-level — moved out of org context in the redesign; contains profile, preferences, theme, **Feature Previews** toggle list, logout)

**Left sidebar (primary nav).** Implemented with the Supabase design system `Sidebar` component (composed of `SidebarProvider`, `Sidebar`, `SidebarHeader`, `SidebarContent`, `SidebarGroup`, `SidebarMenu`, `SidebarMenuItem`, `SidebarMenuButton`, `SidebarMenuAction`, `SidebarMenuSub`, `SidebarFooter`, `SidebarTrigger`). The user-facing primary items, top to bottom:

1. **Table Editor** (`/editor`)
2. **SQL Editor** (`/sql`)
3. **Database** (schema visualizer, functions, triggers, extensions, indexes, replication, migrations, roles, webhooks)
4. **Authentication** (Users, Policies, Providers, Email Templates, URL Configuration, Rate Limits, Hooks, MFA)
5. **Storage** (Buckets, Policies, Settings, S3 connection)
6. **Edge Functions** (functions list, secrets, deployment, invocation logs)
7. **Realtime** (Inspector, settings)
8. **Advisors** (Security advisor, Performance advisor, Linter)
9. **Reports** (customizable, with resizable/reorderable chart blocks and SQL blocks)
10. **Logs** (Postgres, API edge, Auth, Storage, Realtime, Function, Function edge)
11. **API Docs**
12. **Integrations** (Marketplace, Wrappers — Stripe, Firebase, S3, ClickHouse, BigQuery, Logflare; webhooks; partner integrations)
13. **Project Settings** (General, Compute & Disk, Infrastructure, Network Restrictions, API, Database, Auth settings, Storage settings, Functions settings, Vault, Billing, Add-ons, Usage, Team)

**Collapsible behavior.** PR #21550 (merged Feb 28, 2024) shipped a `Feat/collapsible nav bar`. Three modes: `offcanvas` (slides in from edge — mobile), `icon` (collapses to icon-only rail with truncated labels hidden), `none`. Users can "lock in collapsed or expanded sidebar." Active item gets `isActive` styling via `data-active=true` attribute. Collapsible groups wrap `SidebarGroup` in a `Collapsible` for progressive disclosure. The `useSidebar()` hook exposes `state`, `open`, `setOpen`, `openMobile`, `setOpenMobile`, `isMobile`, `toggleSidebar()`. Styling responds to collapse state with `group-data-[collapsible=icon]:hidden` selectors so labels disappear cleanly when iconized.

**Command Menu (⌘K).** Always available. Implemented as the design-system `cmdk` component with `CommandProvider`, `CommandMenuInput`, `CommandMenuList`, `CommandMenuTrigger`, and a `useRegisterCommands` hook. Commands fall into two architectures: **Action commands** (execute a callback) and **Route commands** (navigate to a URL). Organized into named sections ("Action commands", "Route commands", "Docs", etc.). Features: experimental badges on items, icons per command, items hidden until matched by search query, force-mount option to bypass filtering, conditional commands tied to state via dependency arrays, **subpages** for hierarchical command organization (e.g., a "SQL operations" subpage with create-table, create-function, create-policy commands), and direct docs search ("search the Docs directly from the menu" — Studio 2.0). Naomi shortcut alternates `cmd-j` to dodge browser conflicts in dev mode.

**Keyboard shortcuts (global + table editor — Discussion #234):**
- `⌘/Ctrl + K` — open command palette
- `Shift + /` — help / show all shortcuts
- `Shift + F` — open filter side panel
- `Shift + S` — open sort side panel
- `Esc` — close side panel editor
- Table editor: `Shift + Enter` add row, `Enter` edit cell, `⌘/Ctrl + E` edit row in side panel, `⌘/Ctrl + Backspace` delete row, `⌘/Ctrl + C/V` copy/paste cells, `⌘/Ctrl + Shift + Enter` add column, `⌘/Ctrl + Shift + E` edit column, `⌘/Ctrl + ↑/↓/←/→` scroll to extents

## C) List/index pages — columns, filters, sort, search, density, pagination, bulk actions, empty state

Studio's data lists fall into three escalating patterns from the design system:

1. **Table** — presentational wrapper around `<table>`, for static lists with no sort/filter
2. **Data Table** — built on TanStack Table; sorting, filtering, column visibility, row actions, selection, pagination
3. **Data Grid** — built on React Data Grid; virtualization, column resizing, cell editing, spreadsheet-like (this is what the Table Editor uses for live row data)

Common Data Table elements visible on a Studio list page:
- **Top filter bar** with: a search input (e.g., "Email" filter), filter chips, column-visibility dropdown (toggles which columns render), an action button cluster on the right (Refresh, Filter, Sort, plus a planned/feature-flagged "Columns" toggle)
- **Three-state sortable column headers** (ascending → descending → none, indicated by a chevron)
- **Row-selection checkboxes** plus a select-all checkbox in the header
- **Per-row action dropdown** (kebab/⋯ menu) for individual operations
- **Pagination** at the bottom: Previous / Next buttons, plus a "X of Y row(s) selected" label
- **Density**: compact rows by default; small text (`text-sm` = 14px), single-line ellipsis for long cells

### Table Editor (the headline list page)

**Layout, left to right:**
- **Schema selector** at the top of the inner sidebar (dropdown — `public`, `auth`, `storage`, plus any custom schemas)
- **Table list sidebar** — every table in the selected schema, searchable, with primary-key/FK icons next to names
- **Tabs row** above the grid — multiple tables open simultaneously; italicized tab titles indicate preview mode that pins on first edit/interaction (per the 2026 Tabs update: "A new tab will only be dedicated to that file when you start editing or simply click into it"). New Tab page surfaces create-table CTA + recently opened tables.
- **Top toolbar** above the data grid: **Refresh**, **Filter**, **Sort**, **Insert** (split button — Insert row, Insert column, Import data via CSV), **Definition** tab (shows the SQL DDL for the table), **API Docs** tab (auto-generated SQL + supabase-js snippets per CRUD op), TypeScript types download
- **Filter bar (new AI version, GA Apr 2026)**: filter blocks rendered as chips with three slots — column dropdown → operator dropdown (`=`, `<>`, `<`, `<=`, `>`, `>=`, `~~` (LIKE), `~~*` (ILIKE), `NOT LIKE`, `NOT ILIKE`, `IS NULL`, `IS NOT NULL`, `in`) → value input. Keyboard-driven: backspace to select values, arrows to navigate, Enter to apply. **AI prompt** at the top of the bar that emits filter blocks from natural language ("orders from last 30 days where status is not paid"). Filter state is shareable via URL.
- **Sort panel** (Shift+S): list of order-by clauses with column + direction, drag-reorderable
- **Data grid** itself: virtualized rows; column headers show name + type badge (e.g., `int8`, `text`, `timestamptz`, `jsonb`, `uuid`) with PK and FK icons; nullable columns render `NULL` in muted gray; resizable columns; click cell to inline edit; double-click or Enter to commit; foreign-key cells have a "view referencing record" button that jumps to that row in the related table; foreign-key insert flow opens a row picker rather than forcing a manual value paste

**Empty/zero-row state in Table Editor:** centered overlay with a lucide-react icon, an active-voice title ("Create a vector bucket" rather than "No vector buckets found"), description, and a primary CTA. The overlay sits outside the grid so it does not shift during scroll (PR #35031). Table headers in the empty state get dulled `text-foreground-muted`, hover bg on cells removed (`[&>td]:hover:bg-inherit`).

**Pagination:** Previous / Next at the bottom with rows-selected label and total row count (Postgres `COUNT(*)` triggered on demand to avoid blocking large tables).

**Bulk actions:** select rows via checkboxes → action bar appears with **Delete selected**, **Export selected as CSV**, **Copy as SQL INSERT**.

### Auth → Users page

**Layout:** Data Table over the `auth.users` table with cursor-based pagination ("Improved Search") for large datasets, falling back to offset-based for smaller projects.

Columns shown by default:
- Selection checkbox
- **User UID** (truncated with copy-on-hover)
- **Email** (with verified checkmark icon)
- **Phone** (with verified checkmark icon)
- **Provider(s)** — pill badges (email, google, github, apple, phone, anon, etc.)
- **Created at**
- **Last sign in at**
- Per-row kebab menu

**Filters (search bar at top):**
- Free-text search (prefix-indexed against email, phone, and metadata)
- Toggle filters: **Verified**, **Unverified**, **Anonymous**, **Banned**, by **Provider**
- "Filters and search keywords are shareable via URL" — explicit Supabase design choice
- Sort by created-at and last-sign-in (recently requested filter-by-UID is the documented gap, Discussion #27536)

**Row drilldown / detail panel** (right-side drawer): User UID + copy button; Email + verification status + resend verification; Phone + verification; **Provider identities** list (each identity with provider + provider_id); **User metadata** (`raw_user_meta_data`) rendered as a collapsible JSON viewer; **App metadata** (`raw_app_meta_data`) same; Sessions; Sign-in history. Action footer: **Send magic link**, **Send password recovery**, **Send OTP**, **Edit metadata**, **Ban user**, **Delete user** (delete is blocked if user owns Storage objects, with an explicit error explaining why). Invite-by-email lives on a top-right primary button outside the drawer.

### SQL Editor

**Layout (three-pane):**
- **Left rail: snippets explorer** — `Your snippets` (account-level) and `Project snippets` (shared with team) sections; folder tree (RFC: SQL Editor 2.0); sortable alphabetically / by recency / by creation date; **History** tab below snippets (execution history — every query you've run, with timestamp and snippet name)
- **Center: Monaco editor** with syntax highlighting, autocomplete (table names, column names, functions, keywords aware of your schema), error squigglies, linter; **tabs row** at top for multiple open queries (preview-tab pattern like Table Editor); font size independent of UI zoom
- **Bottom: Results panel** — virtualized result table with resizable columns, "Copy row as SQL INSERT" action, CSV export, collapse indicator showing a single-line summary when collapsed; supports cancelling a running query

**Toolbar:**
- **RUN** button (or `⌘/Ctrl + Return`; runs selection if any, else full snippet)
- **Save** snippet
- **Share** snippet (project-shared vs private)
- **Run as role** dropdown (test RLS by impersonating a Postgres role)
- **Pass JWT** input (impersonate a user for RLS testing — wraps in `BEGIN; SET LOCAL ROLE …; SET LOCAL request.jwt.claim …; …`)
- **Timeout** override
- **EXPLAIN ANALYZE** with history of past plans
- **AI Assistant** docked on the right of the editor — chat box; suggestions are applied as a **diff view** in the snippet itself ("a diff view for changes that Supabase AI makes to your SQL snippet" — accept/reject per hunk). AI is **schema-aware** — knows tables, columns, FKs, RLS policies — and can auto-name snippets from their content.

**Saved queries / sharing:** snippets can be **private (your account)**, **project shared** (visible to everyone on the team in a Project Snippets list), or **local** (when running `supabase start` locally, snippets are written to `supabase/snippets/` on disk so they commit to git and appear in both local Studio and the hosted Dashboard).

### Logs Explorer

**Sources picker** at top (dropdown / segmented control) — choose one of:
- `auth_logs` (GoTrue auth/authorization activity)
- `edge_logs` (Cloudflare edge request/response metadata)
- `function_edge_logs` (edge network for edge functions)
- `function_logs` (`console.log` from inside edge functions)
- `postgres_logs` (Postgres database logs — queries, errors)
- `realtime_logs` (Realtime client connections)
- `storage_logs` (Storage upload/retrieval)

**Top bar:**
- Time range picker (last 5 min, 1 hr, 24 hr, 7 days, custom)
- Source button (upper-right) toggles between databases and load balancers for API logs
- **Search input** (free text, regex-aware via BigQuery `regexp_contains`)
- Status code filter (200, 4xx, 5xx pills)
- Path filter
- "Add property/value from the detail panel to search and filter results" — clicking a metadata key in the drill-down injects it as a filter chip

**Templates** — a `Templates` tab (and a dropdown in the `Query` tab) of pre-built queries (e.g., "errors in the last hour", "top 10 slowest endpoints").

**Log row list:**
- Timestamp (left, mono)
- Severity icon / status code badge (color-coded — 2xx green, 3xx neutral, 4xx amber, 5xx red, error severity from postgres_logs in red)
- `event_message` (single-line, mono, truncated)
- Method + path (for API logs)
- Latency (mono, ms)

**Drilldown panel** (right side or bottom drawer): full unnested metadata tree (since fields like `metadata.parsed.user_name`, `metadata.parsed.error_severity` are arrays-of-objects that need `cross join unnest()`, the UI expands them automatically for browsing); every key has a one-click "Add as filter" affordance; copy-as-JSON button; permalink to the log entry. Query editor below the log stream lets you write raw BigQuery SQL with autocomplete; results capped at **1000 rows per run**.

### Storage Browser

**Left rail: bucket list** — each bucket shown with a **Public** / **Private** badge, file count and size, plus a per-bucket settings cog. **+ New bucket** button at top opens a modal: name input, Public toggle, restricted file types (MIME multi-select), max file size input.

**Main area: column-based Finder-style miller-column explorer** (default; "we've defaulted to using the column-based explorer in Finder as it allow us to quickly drill into nested folders … miller-based column view, allowing you to get to deeply nested folders quickly"). Each column is a folder level; clicking a folder pushes a new column to the right. Alternative: **List view** toggle (per blog post, "If you're a fan of List Views though, don't worry! We have that option available too").

**Top of explorer:**
- **Path / location bar** (paste a path to jump directly — "if you already know the location of a file but want to save a few clicks, you can paste the path into the location bar and navigate to it directly")
- Search by filename
- Sort dropdown
- View toggle (columns ↔ list)
- **Upload file** button + drag-and-drop everywhere ("Files upload to the current folder")
- **New folder** button

**File detail panel** (rightmost column, when a file is selected):
- **Rich preview** for "a wide set of file types including images, audio, and videos"
- File name + extension
- File size
- Last modified
- MIME type
- Public URL (copy button)
- Bucket + path
- Permissions / ownership
- Actions: Download, Rename, Copy URL, Move, Delete

**Folders are virtual** — created implicitly by uploading a file at a path prefix (e.g., `avatars/user-123/profile.png` creates `avatars/` and `user-123/`).

**Storage Policies** sub-page — RLS policies scoped to bucket + path, with templates ("Allow authenticated read", "Allow user to manage own files").

## D) Detail/drawer pages — layout, sections, audio player, transcript, drilldown

Studio leans on **right-side slide-out drawers (side panels)** for editing context rather than dedicated detail routes. The pattern:

**Side panel anatomy** (used for Edit Row, Edit Column, Edit Table, Edit User, Edit Bucket, Edit Webhook, Edit Policy):
- Header: object title + close (Esc closes — `Esc → close side panel editor`)
- Body: stacked form fields with section headers (`Configuration`, `Permissions`, `Foreign Keys`, `JSON metadata`, etc.)
- Each field has label + input + helper text + validation; foreign-key fields are pickers (row selector across the referenced table) not raw text
- JSON fields render in a Monaco-style editor with syntax highlighting; for JSON cells, an `Expand` button blows the JSON out into the full side panel for a "more spacious editing experience"
- Cascade-delete configuration for FK constraints lives **inside the side panel**, not in a separate modal
- Footer: secondary `Cancel` (left), primary `Save` (right, brand green)

**Row inspector (Table Editor)** opened by clicking a row's expand icon or pressing `⌘/Ctrl + E`. It shows every column as label + value, with type badge, primary-key/FK indicator, FK navigation links, and inline edit on each field. Datetime columns display in ISO with a copy button (Issue #5877 surfaced a bug where `timestamp` without `z` rendered blank — illustrative of how strictly the panel parses types).

**User drilldown drawer (Auth → Users)** — covered above in §C; the same right-side pattern with JSON viewers for metadata, an Action footer, and identity sub-cards per provider.

**Log row drilldown** — right-side metadata tree (covered in §C), with "add as filter" inline.

**SQL diff drawer (AI assistant)** — when AI proposes changes to a snippet, the diff appears inline in the Monaco editor (red removed lines, green added lines) with `Accept` / `Reject` buttons either globally or per hunk.

**Schema Visualizer (Database)** — full-canvas zoomable graph (think dbdiagram/drawSQL): tables as cards with column lists, lines for FKs, color-coded by schema. Pan/zoom controls bottom-right; minimap.

**There is no audio player / transcript pattern in Supabase Studio** — Studio is a database/auth/storage console with no built-in media tooling. Storage's file preview supports inline audio and video via the browser's native `<audio>`/`<video>`, but no transcript view, waveform, or scrub-bar custom UI. (Naomi note for the Sabi mapping: for Sabi's call transcripts you'll need a custom drawer; the Studio side-panel chrome is the right shell, but the player + transcript + tool-call timeline are net-new.)

## E) Visual language — colors, typography, density, iconography, motion, brand voice

### Colors (dark-mode-native; light mode supported but inverted secondary)

Background hierarchy:
- `#0f0f0f` — deepest (page surface for hero sections)
- `#171717` — primary canvas (`--bg`)
- `#1c1c1c` — surface / cards (`--surface`)

Text:
- `#fafafa` — primary text (`--fg`)
- `#b4b4b4` — secondary text (`--fg-2`)
- `#898989` — muted (`--muted`)
- `#4d4d4d` — meta (`--meta`)

Border (depth via borders, not shadows):
- `#242424` — subtle (`--border-soft`)
- `#2e2e2e` — standard (`--border`)
- `#363636` / `#393939` — prominent

Brand:
- `#3ecf8e` — accent green (`--accent` — the Postgres-green nod)
- `#00c573` — accent hover (`--accent-hover`)
- `#0f0f0f` — accent-on (text on green CTA)
- Used **sparingly** — primary CTAs, links, success states, brand mark; "use brand green only for CTA" is an explicit team mantra

Semantic:
- `#16a34a` — success
- `#eab308` — warn
- `#dc2626` — danger

Color tokens are HSL-based with alpha channels for almost every color, enabling layered translucency.

### Typography

Families:
- Display + body: **Circular** (geometric sans-serif, rounded terminals) with fallbacks `"custom-font", "Helvetica Neue", Helvetica, Arial, sans-serif`
- Mono: **Source Code Pro** with fallbacks `"Office Code Pro", Menlo, Monaco, Consolas`

Type scale:
- `--text-xs` 12px
- `--text-sm` 14px (default body for dense UI — table cells, sidebar items)
- `--text-base` 16px
- `--text-lg` 18px
- `--text-xl` 24px
- `--text-2xl` 32px
- `--text-3xl` 36px
- `--text-4xl` 72px (marketing hero only)
- Line heights: body `1.5`, tight `1.00` (hero, terminal-like)

Weights: **400 (regular) almost everywhere; 500 only on nav links and button labels; no 700 bold in the detected token set — hierarchy comes from size and color, not weight**.

Mono in uppercase with `1.2px` letter-spacing is the only place tracking is loosened.

### Density

- 8px base spacing unit (`--space-1` 4, `--space-2` 8, `--space-3` 12, `--space-4` 16, `--space-5` 20, `--space-6` 24, `--space-8` 32, `--space-12` 48)
- Table rows are compact (around 36–40px tall, single-line)
- Sidebar items are 32–36px tall, `text-sm`, weight 500
- Form fields use `--space-3` (12px) internal padding; gaps between fields `--space-4` (16px)
- Section padding: `--section-y-desktop` 128px, `--section-y-tablet` 80px, `--section-y-phone` 48px (marketing surfaces; in-app is much tighter)

### Radius

- `--radius-sm` 6px (secondary buttons, badges, inputs)
- `--radius-md` 8px (cards, panels)
- `--radius-lg` 16px (modals, large cards)
- `--radius-pill` 9999px (primary marketing CTAs; in-app uses 6/8)

### Elevation

- `--elev-flat` `none`
- `--elev-ring` `0 0 0 1px var(--border)` — most cards (a ring, not a shadow)
- `--elev-raised` `0 0 0 1px var(--border), 0 4px 12px rgba(0, 0, 0, 0.4)` — modals/popovers
- **No shadows in dark mode** — depth is communicated by border contrast (`#242424 → #2e2e2e → #393939`)

### Focus + motion

- Focus ring: `0 0 0 2px color-mix(in oklab, var(--accent), transparent 50%)` (a translucent green outer ring — accessible without being shouty)
- Motion fast: 150ms
- Motion base: 200ms
- Easing: `cubic-bezier(0.2, 0, 0, 1)` (standard "Material out", not bouncy)
- Sidebar collapse, drawer slide-in, modal fade all use 150–200ms

### Iconography

- **lucide-react** is the icon system (Users, Plus, ChevronDown, MoreHorizontal, etc., shown in PR #35031 and the design system); icons sit at 16px in dense UI, 20px in section headers
- Custom Supabase brand mark is the only non-lucide glyph
- Provider logos in Auth (google, github, apple, etc.) come from official wordmarks

### Brand voice (in-app copy)

- Empty states: **active voice** ("Create a vector bucket", not "No vector buckets found")
- Errors are explanatory, not blame-y ("The bucket 'user_avatars' doesn't seem to exist." — an Admonition with a navigation button)
- Microcopy is terse, lowercase, developer-direct (no marketing fluff inside the product)
- Dieter-Rams-inflected design mantras: "be more subtle, simplify simplify simplify, use brand green only for CTA"

## F) Specific patterns Sabi should copy

1. **Three-pane Table Editor (left tables list / center grid / right side-panel inspector)**
   - *What it does:* Lets an admin browse every Postgres table, edit cells inline, and use a right-side drawer for richer row editing without leaving context.
   - *Where it lives:* `apps/studio/components/grid/*` and `SidePanelEditor`. UI built on React Data Grid for the spreadsheet; TanStack Table everywhere else.
   - *Sabi mapping:* Sabi's board console will have analogous heavy tables (callers, calls, schools, donors, lessons-completed). Use **shadcn/ui `Sidebar` + a `Data Table` (TanStack Table) for index pages + a right-side `Sheet` (Radix) for the row inspector**. Map each Sabi resource to a "table" in the left rail (Callers, Calls, Schools, Donors, Lessons, Audit Log). Cell-level inline edit for short fields (notes, tags), drawer for everything else. Use the same `Esc closes drawer` and `⌘/Ctrl + E opens drawer` shortcuts.

2. **Tabs across destinations (Table Editor + SQL Editor)**
   - *What it does:* Lets you keep multiple tables / queries / call records open without losing context; preview tabs (italic) auto-pin once you interact.
   - *Where it lives:* Tabs row above the editor body.
   - *Sabi mapping:* For board-facing review of recorded calls (transcript drilldowns, lesson playback), implement tabs so a reviewer can keep three calls open across schools. Use `shadcn/ui Tabs` plus a custom preview-tab state machine. Persist tab state in URL (each tab = a `?tab=callid_123` query slot) so reviewers can share links.

3. **AI filter bar with natural-language chip generation**
   - *What it does:* User types "calls from MTN where the child dropped off mid-lesson last week" → AI converts to filter chips (provider=MTN, drop_off=true, started_at > now()-'7d').
   - *Where it lives:* Top of the Data Table.
   - *Sabi mapping:* This is *huge* for a board console — board members are not query-writers. Wire a Tailwind v4 + Clerk-secured Next.js Server Action that takes the prompt + the current resource's schema (column list with types) and asks Claude Haiku to emit a JSON array of `{column, op, value}` blocks, which the client renders as chips. Reuse Sabi's existing Anthropic key; the schema-aware filter is a 200-line component.

4. **Inline SQL anywhere ("Run SQL from any page")**
   - *What it does:* A global `Inline SQL Editor` button in the topbar opens a Monaco overlay so the user can poke at the DB from any page without leaving context.
   - *Where it lives:* Top header, right side.
   - *Sabi mapping:* For Naomi/board *advanced* users only (gate via Clerk role `admin` or `developer`), expose an "Ask Sabi data" floating button that opens a similar overlay — except instead of raw SQL, it's a natural-language box (Claude → tool-call → server-side parameterized Postgres). For non-technical board members, hide entirely. The pattern of "the power tool follows you around the app" is what to copy.

5. **AI diff view for query suggestions / config changes**
   - *What it does:* AI proposes changes to a SQL snippet as a red/green diff inline in Monaco; accept/reject per hunk.
   - *Where it lives:* SQL Editor right-side AI panel.
   - *Sabi mapping:* When Sabi AI suggests changes to a lesson prompt or guardrail config, render the change as a diff against the current value (Monaco's diff editor is one component import; or use `react-diff-viewer-continued`). Critical for admin trust — never have AI silently overwrite child-facing copy.

6. **Cursor-based pagination + URL-shareable filter state on the Users page**
   - *What it does:* `auth.users` page filters and search are serialized to the URL; cursor pagination scales to millions of rows.
   - *Where it lives:* `apps/studio/pages/project/[ref]/auth/users.tsx`.
   - *Sabi mapping:* Sabi's Callers list will balloon (every phone number that has ever dialled). Use the exact same pattern: Next.js `searchParams` as the source of truth for filters, cursor pagination via `created_at + id` composite cursor. Share a link to "callers from Kano with >3 lessons" by URL.

7. **Right-side drawer with sections + JSON viewer for metadata**
   - *What it does:* User detail panel renders `raw_user_meta_data` and `raw_app_meta_data` as collapsible JSON, with an "Expand" affordance to blow JSON into the full drawer.
   - *Where it lives:* `SidePanelEditor` row inspector.
   - *Sabi mapping:* For each caller, render their phone metadata, last-known school, language/dialect detected, raw STT transcript JSON as collapsible sections in a Sheet. Use a JSON viewer (e.g., `@uiw/react-json-view`) styled with the design tokens below.

8. **Action commands + Route commands in a ⌘K palette**
   - *What it does:* `⌘K` opens a command menu with sectioned route-jumps ("Go to Callers", "Go to Lessons") and action-callbacks ("Export caller list as CSV", "Trigger fresh sync from AT").
   - *Where it lives:* Top-level, persistent.
   - *Sabi mapping:* Ship a ⌘K palette using `cmdk` (the same library Supabase uses; already a shadcn/ui component). Register Sabi-specific actions: "Replay call …", "Mark caller as flagged for review", "Send WhatsApp follow-up", "Open guardrail stress test report". Use Action vs Route command distinction — board members navigate, ops triggers actions.

9. **Logs Explorer pattern: source picker → time range → free-text search → drilldown drawer with "add as filter"**
   - *What it does:* For each log source pick a time window, search free-text, click any nested metadata key in the drilldown to add it as a filter chip.
   - *Where it lives:* `/project/[ref]/logs/*`.
   - *Sabi mapping:* This is the *exact* model for Sabi's "Calls" page (which is really a log explorer). Source picker = AT inbound vs Twilio outbound vs WhatsApp; time range; search by phone/transcript; drill into a single call → see metadata tree (ASR confidence, TTS latency, guardrail trips, lesson_id, tool_calls) → click any field to add as a filter on the index. Pre-built **Templates** ("All calls where guardrail tripped today", "Top 10 longest calls", "Calls with <70% ASR confidence") match the Supabase Templates pattern.

10. **Side panel for FK editing — pick a referencing row instead of typing a UUID**
    - *What it does:* When editing a FK column, opens a row picker against the referenced table (search + paginated grid) so admins don't paste UUIDs.
    - *Where it lives:* `SidePanelEditor` foreign-key field.
    - *Sabi mapping:* When assigning a caller to a school, a lesson to a curriculum, a transcript to a reviewer — never show a raw UUID input. Always open a row picker. (Use a Radix `Command` inside a `Popover` over a paginated Server Action.)

11. **Empty states with active-voice CTA + lucide icon + Admonition for missing routes**
    - *What it does:* "Create a vector bucket" not "No buckets found"; missing routes get an `Admonition` with a navigate-back button.
    - *Where it lives:* Across every empty list and 404.
    - *Sabi mapping:* Wire shadcn `EmptyState` (or a small custom component) with the same convention. For Sabi: "Add the first donor", "Configure your first school", "Invite your first reviewer".

12. **Collapsible icon-rail sidebar with `useSidebar()` hook + ⌘K to navigate without ever expanding it**
    - *What it does:* User can lock sidebar collapsed; nav still works via icons + ⌘K.
    - *Where it lives:* `Sidebar` component.
    - *Sabi mapping:* Use shadcn/ui `Sidebar` (collapsible="icon"); ship pinned + unpinned states; persist preference in `localStorage` + Clerk user metadata.

13. **Definition tab + auto-generated docs tab on the Table Editor**
    - *What it does:* For each table, a tab shows the SQL DDL; another shows generated `supabase-js` snippets per CRUD op.
    - *Where it lives:* Above-grid tabs.
    - *Sabi mapping:* For each Sabi resource, ship a "Schema" tab (the source DDL) and an "API" tab (the Next.js Server Action / route handler snippet for that resource). Helps the board understand "what data are we actually storing on each caller" without reading code.

14. **Templates dropdown on the SQL/Logs editors**
    - *What it does:* Pre-canned starter queries reduce empty-editor anxiety.
    - *Where it lives:* SQL Editor + Logs Explorer Templates tab.
    - *Sabi mapping:* Ship a "Common reports" library: "Active callers this week", "Lesson completion rate by school", "Avg call duration by language", "Guardrail trips last 30 days". One-click to load + run.

15. **`Feature Previews` toggle list under the user avatar**
    - *What it does:* Roll out new UI behind opt-in flags ("New Table Filter Bar", "Tabs in dashboard"); users can disable.
    - *Where it lives:* Avatar dropdown → Feature previews.
    - *Sabi mapping:* For the board console, ship a "Feature previews" submenu under Clerk user dropdown. Lets Naomi roll out experimental dashboards (new dialect metric, new caller-cohort view) to herself + a few board members without affecting the rest.

16. **Customizable Reports page with resizable/reorderable chart blocks + inline SQL blocks**
    - *What it does:* Users assemble dashboards by dragging chart blocks and pinning SQL snippets as visualizations.
    - *Where it lives:* `/project/[ref]/reports`.
    - *Sabi mapping:* Board members want their own snapshot dashboards. Ship a "My Dashboard" page where each board member can add cards (lesson completion, donor count, calls-this-week, etc.). Use `react-grid-layout` for the drag-resize and persist layout per-user in Clerk metadata.

17. **Border-based depth, not shadows**
    - *What it does:* All cards and panels use a 1px ring (`box-shadow: 0 0 0 1px`) in dark mode rather than blurred shadows; depth read from border-color steps (#242424 → #2e2e2e → #393939).
    - *Sabi mapping:* In Tailwind v4, use `outline` or `ring` utilities for cards. Configure tokens `--border-soft`, `--border`, `--border-strong` and use them on `Card`, `Sheet`, `Popover`, `Dialog`. Resist shadow-heavy shadcn defaults — replace the default `shadow-sm` on cards.

18. **Brand color used only on CTAs and active states; everything else neutral**
    - *Sabi mapping:* If Sabi keeps the gold/black premium identity (per memory), apply gold *only* to primary CTAs, brand mark, and `data-active=true` sidebar items. Use neutral gray for all other interaction states. Mirror Supabase's "be more subtle" discipline.

19. **Per-row action kebab + bulk-action bar on selection**
    - *What it does:* Single-row actions hidden in `⋯`; multi-row actions appear in a sticky toolbar above the grid when ≥1 row checked.
    - *Sabi mapping:* For callers list: per-row "Replay last call", "Open transcript", "Block this number"; selection bar: "Export selected as CSV", "Send WhatsApp re-engagement to all", "Mark as reviewed".

20. **Inline cell type badges in column headers (`text`, `int8`, `jsonb`)**
    - *What it does:* Every column header shows its Postgres type as a tiny mono badge so editors know what they're typing into.
    - *Sabi mapping:* For Sabi's data grids that surface mixed-type fields (`metadata jsonb`, `created_at timestamptz`), copy the badge convention — orients board members who don't know Postgres.

## G) Anti-patterns to avoid

1. **Don't over-rely on raw SQL as the only escape hatch.** Supabase Studio's Logs Explorer makes you write BigQuery SQL (no `with`, no subqueries, no `ilike`) to do anything non-trivial — that's appropriate for a dev tool, terrible for a board of nonprofit reviewers. Sabi must always have a no-code path before exposing SQL.
2. **Don't ship "Storage policies" as raw RLS SQL.** Supabase exposes Storage policies as SQL `CREATE POLICY` statements with templates — fine for devs, gibberish for nonprofit ops. Sabi should ship guarded forms ("Only school admins can read their school's transcripts") that compile to policies under the hood.
3. **Don't gate critical actions behind nested drawers.** Supabase's "delete user blocked because they own Storage objects" surfaces as an error mid-action. Better UX: show ownership state in the drawer header so you know before you click Delete. Apply to Sabi's "delete school" / "delete caller" flows.
4. **Don't shrink CTAs into icon-only buttons without tooltips.** Some Studio toolbar buttons collapse to icons (Refresh/Filter/Sort) without labels; this is fine for power users but causes hover-hunt for new users. Sabi should keep labels visible until the toolbar runs out of width, then collapse with tooltips.
5. **Don't bury org/account switching in deep nav.** The 2026 refactor explicitly fixed this — they moved the user dropdown to top-right and made it always visible. Sabi: keep the Clerk user dropdown top-right from day one.
6. **Don't lean on `display: none` for empty states inside virtualized grids.** PR #35031 explicitly shifted loading/error/empty states *outside* the DataGrid so they don't shift on scroll. Sabi's empty states must be siblings of the grid, not children.
7. **Don't make column visibility a hidden setting.** Supabase's "hide columns" lives in a Columns dropdown in the toolbar; users routinely forget where it is (Discussion #18197). Sabi should make column visibility a more prominent surface — e.g., a settings cog at the top-right of each Data Table that opens a side panel with column toggles, frozen-column choice, density, and saved views.
8. **Don't have multiple AI assistants with different prompt boxes.** Supabase's AI shows up in the SQL editor, in the filter bar, in the assistant chat — three different surfaces with three different prompt patterns. Pick ONE AI input style for Sabi and reuse it everywhere (consistent shortcut, consistent diff-acceptance pattern).
9. **Don't surface Postgres jargon directly in board-facing UI.** Type badges like `int8`, `jsonb`, `timestamptz` are correct but alienating. For board members, show "Number", "Object", "Date and time"; toggle to Postgres types under a "show technical types" preference.
10. **Don't make the SQL Editor the default landing page.** Supabase Studio drops you on Table Editor or a project home; that's correct. For Sabi: land on a "Today" dashboard (recent calls, recent flags, recent donors), not on a list.
11. **Don't use brand color as a hover/active background fill.** Supabase rule: green is for CTAs only. Hover/active states use border or muted bg. Sabi's gold should follow the same rule — `bg-amber-500/10` on hover-active, never `bg-amber-500` on a full row.
12. **Don't ship a Realtime Inspector style debugger as the only way to verify live data.** Devs love it; board members want a "is anyone on a call right now" widget. Build the high-level view first.

## H) Source URLs

- [Supabase Studio 2.0: help when you need it most — Supabase blog](https://supabase.com/blog/supabase-studio-2.0)
- [Supabase Studio 3.0: AI SQL Editor, Schema Diagrams, and new Wrappers — Supabase blog](https://supabase.com/blog/supabase-studio-3-0)
- [Keeping Tabs on What's New in Supabase Studio — Supabase blog](https://supabase.com/blog/tabs-dashboard-updates)
- [How design works at Supabase — Supabase blog](https://supabase.com/blog/how-design-works-at-supabase)
- [Supabase Design System root](https://supabase.com/design-system)
- [Supabase Design System — Sidebar component](https://supabase-design-system.vercel.app/design-system/docs/components/sidebar)
- [Supabase Design System — Command Menu (cmdk) component](https://supabase.com/design-system/docs/components/commandmenu)
- [Supabase Design System — Tables UI pattern](https://supabase.com/design-system/docs/ui-patterns/tables)
- [Supabase Design System — Empty states UI pattern](https://supabase-design-system.vercel.app/design-system/docs/ui-patterns/empty-states)
- [Supabase Design System — Typography](https://supabase-design-system.vercel.app/design-system/docs/typography)
- [SQL Editor — Supabase Features](https://supabase.com/features/sql-editor)
- [Logs & Analytics — Supabase Features](https://supabase.com/features/logs-analytics)
- [Tables and Data — Supabase Docs](https://supabase.com/docs/guides/database/tables)
- [Users — Supabase Docs](https://supabase.com/docs/guides/auth/users)
- [User Management — Supabase Docs](https://supabase.com/docs/guides/auth/managing-user-data)
- [Logging — Supabase Docs](https://supabase.com/docs/guides/telemetry/logs)
- [Advanced Log Querying and Filtering — Supabase Docs](https://supabase.com/docs/guides/telemetry/advanced-log-filtering)
- [Storage Quickstart — Supabase Docs](https://supabase.com/docs/guides/storage/quickstart)
- [Storage Buckets — Supabase Docs](https://supabase.com/docs/guides/storage/buckets/fundamentals)
- [Storage is now available in Supabase — Supabase blog (column-Finder explorer)](https://supabase.com/blog/supabase-storage)
- [Introducing the Supabase UI Library — Supabase blog](https://supabase.com/blog/supabase-ui-library)
- [Supabase UI Library](https://supabase.com/ui)
- [SQL snippets can now be saved in local Studio — Changelog](https://supabase.com/changelog/42031-sql-snippets-can-now-be-saved-in-local-studio)
- [RFC: SQL Editor 2.0 — GitHub Discussion #14206](https://github.com/orgs/supabase/discussions/14206)
- [Keyboard Shortcuts for our Dashboard — GitHub Discussion #234](https://github.com/orgs/supabase/discussions/234)
- [Upcoming breaking change to Dashboard Navigation — GitHub Discussion #33670](https://github.com/orgs/supabase/discussions/33670)
- [New Filter bar w/ AI — GitHub Discussion #42461](https://github.com/orgs/supabase/discussions/42461)
- [Advanced filtering in the log explorer — GitHub Discussion #22640](https://github.com/orgs/supabase/discussions/22640)
- [Auth — search/filter by user id inside Auth table — GitHub Discussion #27536](https://github.com/orgs/supabase/discussions/27536)
- [Feat/collapsible nav bar — PR #21550](https://github.com/supabase/supabase/pull/21550)
- [Table Editor: shift loading/error/empty states outside DataGrid — PR #35031](https://github.com/supabase/supabase/pull/35031)
- [Studio Feature Reference — DeepWiki for supabase/supabase](https://deepwiki.com/supabase/supabase/7-studio-feature-reference)
- [Supabase Design Tokens — design-extractor / DesignMD analysis](https://www.designmd.co/d/supabase)
- [Supabase design system palette + typography tokens (Open Design extraction)](https://open-design.ai/plugins/design-system-supabase/)
- [Supabase design analysis — Hagicode design.md gallery](https://design.hagicode.com/designs/supabase/)
- [Supabase Table Editor UI — SaaSFrame](https://www.saasframe.io/examples/supabase-table-editor)
- [Supabase Storage Explorer — Makerkit Supamode docs](https://makerkit.dev/docs/supamode/features/storage-explorer)
- [Explore Table Editor in Supabase — Onebite](https://onebite.dev/explore-table-editor-in-supabase-database/)


---

## Comparable 4: Contact-center QA — Observe.ai, Gong, Chorus, Five9 Insight, Talkdesk QA

I now have very rich material. Let me write the comprehensive audit.

# Contact-center QA — Observe.ai, Gong, Chorus, Five9 Insight, Talkdesk QA

## A) Product overview

These five products belong to the same product category — "evaluate a recorded interaction between an agent and a customer against a scoring rubric, surface coachable moments, and roll the scores up into trends" — but they cluster into two cultural camps. Gong and Chorus (ZoomInfo) come from sales conversation intelligence — they assume the "agent" is a quota-carrying rep and the "customer" is a prospect, so they lean into deal-board context, snippet-sharing, talk-ratio coaching, and a richly editorial "call page" with AI summaries, outlines, trackers, and at-mention comments. Observe.ai, Talkdesk QM (with QM Assist), and Five9 QM come from the contact-center QA tradition — they assume thousands of calls per day, a small QA team that can only ever review a sliver manually, statuses like "AI Pending / AI Scored / Acknowledged / Disputed," and a strict three-tier scoring hierarchy (Sections > Categories > Questions) with weights and base percentages. All five converge on a single canonical detail screen: a three-pane layout with a media player + waveform/timeline at the top or center, a paragraph-per-turn diarized transcript on one side, and an AI summary / scorecard / scoring form on the other side — with the timeline, transcript, and scorecard answers all click-synchronized to the same playhead. ([Gong intro to the call page](https://help.gong.io/docs/intro-to-the-call-page), [Talkdesk QM Overview](https://www.talkdesk.com/cloud-contact-center/wem/quality-management/), [Observe.ai post-interaction](https://www.observe.ai/post-interaction-ai))

## B) Navigation + topbar pattern

**Gong's global nav** is a thin left rail of section labels — *Home, Conversations (Calls/Meetings/Search/Streams), Deals, Accounts, Forecast, Library, Coaching, Insights, Assets (where Scorecards live under Assets > Scorecards), Admin center*. Calls are reached via *Conversations > Search* and scorecards are reached via *Assets > Scorecards* — i.e. "stuff that runs on calls" lives separately from "the call viewer itself." The call viewer's own topbar carries: the call title (top left), the account name underneath it, the call timestamp, a "listened" indicator, then five right-side action icons — *Add to library, Listen later, Share call, Generate email follow-up*, plus the universal Gong Assistant chat. ([Intro to the call page](https://help.gong.io/docs/intro-to-the-call-page))

**Chorus's global nav** (post-make-over) is a top tab bar: *Recordings, Library, Coaching, Analytics, Cold Call Central, Trackers*, with a search magnifying glass for keyword/customer/rep/meeting-title lookup. Filters live on the **left rail** of the Recordings page, grouped as *Recording Info, Deal Info, Cold Call Central, CRM*. The detail view replaces the global nav with a returning "back to recordings" link plus a per-call action row. ([Chorus Recordings overview](https://www.spekit.com/templates/chorus-getting-started-guide))

**Talkdesk QM** uses an app launcher to enter QM; once inside, the QM dashboard splits into *Forms* and *Evaluations* as two top-level areas, with subareas *Calibrations*, *Agent View*, *Reports*, *QM Assist > Configurations*. Talkdesk Interaction Analytics is its own sibling app that contributes the transcript + sentiment annotations the QM screen pulls in. ([QM overview](https://www.talkdesk.com/cloud-contact-center/wem/quality-management/), [Evaluations in QM](https://support.talkdesk.com/hc/en-us/articles/13053603142555-Evaluations-in-QM), [Interaction Analytics dashboards](https://support.talkdesk.com/hc/en-us/articles/360061348931-Using-Dashboards-with-Interaction-Analytics))

**Observe.ai** organizes nav as functional pillars rather than chronological sections: *Conversation Intelligence, Auto QA, Manual QA, Coaching (Coaching Copilot), Insights (Insights Copilot), Agent Copilot, Real-time Agent Assist, Screen Recording, Reports/Dashboards*. The interaction detail screen merges audio + transcript + screen recording + metadata "on one interface" — Observe explicitly markets the synchronized four-stream player as its core view. ([Observe platform overview](https://www.observe.ai/), [Screen recording](https://www.observe.ai/agent-screen-recording), [Coaching workflows](https://www.observe.ai/blog/introducing-agent-performance-coaching-workflows))

**Five9 QM** lives inside the Five9 cloud desk; the nav is a sectioned launcher pointing into *Quality Management (Forms, Evaluations, Coaching), Interaction Analytics, Performance Dashboard, WFM*. Five9's design language is real-time-dashboard heavy: KPI tiles ("visual attention to important metrics") sit at the top of every screen, and the evaluator drills from a tile into a list into an evaluation. ([Five9 QM page](https://www.five9.com/products/capabilities/contact-center-quality-management-monitoring-tools), [Performance Dashboard](https://www.five9.com/products/capabilities/performance-management-dashboard))

The **common pattern** for the topbar across all five: brand mark + global nav + search + a workspace selector + a notifications/inbox bell + a user avatar with role-based switcher (Agent View vs Supervisor View vs Admin in Talkdesk; Scored-Me vs Scored-Others in Gong). Sabi's board console should crib this: a left rail for the verbs (*Sessions, Lessons, Children, Teachers, Schools, QA, Curriculum, Reports, Admin*), a topbar with workspace switcher (school/district), search, notifications, and a profile menu that explicitly says "Viewing as: Board / Coordinator / Reviewer."

## C) List/index pages — columns, filters, sort, search, density, pagination, bulk actions, empty state

**Gong's Conversations > Search list page** — the canonical "list of recorded interactions" — has these confirmed elements:

- **Five default filters** rendered as inline chips at the top: *Participants* (with sub-roles: hosted / attended / invited / email sender / email recipient), *Account name* (multi-select), *Words or phrases* (full-text with operators), *Trackers* (phrase-based concept trackers with mention scope), *Call title or email subject*.
- **Search operators**: exact phrase `"term"`, OR `term1 | term2`, AND `term1 + term2`, NOT `-"term"`.
- **Filter expansion options**: contains/excludes term; mentioned-by (team / customer / anyone); said-anytime / said-in-question / said-in-specific-part / said-about-topic.
- **+ Add filters** opens drawer of *Call data, Email data, CRM data* fields.
- **Per-row quick actions**: Share externally, Share internally, Generate follow-up email, Add to Listen later, Download media, Download transcript, Toggle privacy, Move workspace, Delete.
- **Bulk actions**: select multiple calls and run bulk operations via the toolbar that appears.
- **Saved searches + Streams**: any filter combination saves as a "Stream" that auto-updates and notifies.
- **Reorderable/customizable filter row** so each user has their own default working set.
- **CSV export of the result set** via *Download call data* (date, participants, duration — not transcript text).
- **Drill-in**: clicking a row opens the call's preview panel inline, then full page. ([Gong search-for-calls](https://help.gong.io/docs/search-for-calls), [Download call data](https://help.gong.io/docs/download-call-data))

**Chorus's Recordings list page** has filters on the left rail in four groups:
- *Recording Info*: stage at time of call, team, rep, recording date, duration, and more.
- *Deal Info*: current stage, amount, close date.
- *Cold Call Central*: connected / phone tree / gatekeeper / voicemail.
- *CRM*: any field from the linked Salesforce/HubSpot record.
- **Columns**: the table is column-customizable via a "+" icon adjacent to *Cold Call Central* and *Trackers*, so a user can pin tracker hit counts as columns.
- **Search**: magnifying glass for customer name, prospect name, rep name, meeting title.
- **Smart Playlists** behave like a saved search — auto-fill criteria are Account Name, Current Deal Stages, Deal Stages at Time of Call, Reps, Teams, Trackers/Themes. New calls matching automatically join. ([Spekit Chorus guide](https://www.spekit.com/templates/chorus-getting-started-guide), [Smart Playlists](https://docs.chorus.ai/hc/en-us/articles/1260806120190-Using-Smart-Playlists))

**Talkdesk QM Evaluations list** has these confirmed columns and statuses:
- **Columns**: *Evaluator* (supervisor who started/completed it), *Evaluation form* (form name), *Interaction* (call recording date), *Evaluation date* (when draft initiated), *Created on*.
- **Status pill values** (this is the most useful piece for Sabi): `Draft` · `To do` · `Review Requested` · `AI Pending` · `AI Scored` · `Completed` · `Acknowledged`. `AI Pending` = QM Assist couldn't fill confidently and needs human review; visible only to supervisors. `AI Scored` = fully filled, editable by supervisor.
- **Filters**: *Queues* (all / specific) and *Teams* (all / multiple specific).
- **Bulk action**: assign to evaluator, recall, calibrate. ([Evaluations in QM](https://support.talkdesk.com/hc/en-us/articles/13053603142555-Evaluations-in-QM), [Agent View in QM](https://support.talkdesk.com/hc/en-us/articles/4402963554203-Agent-View-in-QM))

**Five9 QM Forms list**: hierarchical browser of Forms > Sections > Categories > Questions, with form-level columns *Form name, Channel, Status, Last modified, Owner*. Five9 also exposes *Average score* with a *trend arrow icon* comparing to the previous period — a pattern Sabi should mirror at the top of any list. ([Five9 scoring methods](https://five9verint.five9-wfo.com/onlinehelp/en_us/qm/QM/Scoring_methods.htm), [Five9 QM datasheet](https://www.five9.com/en-uk/products/capabilities/contact-center-quality-management-monitoring-tools))

**Observe.ai's Interactions list** is filterable by team, individual agent, location, channel, product category, and talk time, with bulk assign-to-evaluator and bulk export to coaching modules. AI-evaluated rows carry an "AI auto-suggested / AI auto-filled / AI auto-submitted" indicator so reviewers know what level of human attention is needed. ([Observe reporting & analytics](https://www.observe.ai/blog/reporting-analytics-from-observe-ai), [Observe post-interaction](https://www.observe.ai/post-interaction-ai))

**Density**: all five use medium-density tables (about 48–56px row height) with truncated text + tooltip overflow. None use a card grid for the index — list density wins.

**Empty state**: from observed product screenshots, the empty state typically shows an illustration + one-sentence explanation + a single primary CTA ("Connect a call source" or "Import your first form").

## D) Detail/drawer pages — layout, sections, audio player, transcript, drilldown

The five products converge on a **three-pane interaction detail layout** that Sabi should adopt almost wholesale:

### D.1 Gong call page — the most detailed layout we have hard documentation on

- **Top header bar** — call title (top-left), account name underneath, call timestamp, "listened" status indicator. Right side carries five icon buttons: *Add to library, Listen later, Share call, Generate email follow-up*, Gong Assistant chat trigger.
- **Left panel (the AI brief)** — vertical stack of collapsible sections:
  - **Ask anything** (free-text Q&A bar at top of the panel — answers come from the transcript and link back to source moments).
  - **Highlights / Briefs** — 1-paragraph recap + bulleted summary + next steps. Hover any bullet to jump to that moment in the call.
  - **Outline** — call broken into named topic sections, each with a duration. Each section has a timestamp link that jumps the player, plus a "copy text" icon on hover in the top right of the section.
  - **Transcript** — synced highlight as audio plays. Translate icon top-right. Search box for words/phrases. Click any line to jump the player. Select text to open a floating action menu (snippet / share / comment / library / scissors icon for snippet). Download menu in the options dot-dot-dot.
  - **Call info** — duration, participants, source system, recording quality.
  - **Points of interest** — playbook mentions, *questions* (color-coded: **purple = your side, pink = customer**), trackers (concept-detection chips), filler words flagged when above average. Click any chip to view its snippet list and jump.
  - **Slides** — if a screen share was detected, slide thumbnails with start time and duration.
- **Center — the player**:
  - **Call screen** (video / shared content area).
  - **Action bar** below — play/pause, 15-second jump, speed, scrubber, expand-to-full-screen arrow.
  - **Pointer** — the **purple timeline point** that you drag to scrub.
  - **Soundtrack** — horizontal per-speaker lanes (one row per participant). Your-company speakers' lanes render **in purple**. Click a speaker name to jump to their next utterance. Each lane has a **mute/unmute toggle at the left end** and a **talk-percentage label at the right end** ("32%"). This is the canonical "per-channel agent+customer waveform" pattern Sabi asked about.
  - **Topics section** at the bottom of the player — color-coded ribbons across the timeline so you can scrub to a specific topic.
- **Right panel** — vertical icon rail (collapsible). Stack:
  - **Comments icon** (with a numeric notification badge) — comments thread; each comment can be timestamped to a transcript line. @mentions tag up to 50 people; hashtags work. Visibility picker is *anyone at your company / specific people / only you*. Emoji picker. If a comment isn't bound to a timestamp it defaults to 0:00. Comments highlight in yellow when the playhead crosses their timestamp.
  - **Scoring/Scorecards section** (star icon) — opens the rubric panel (see E below).
  - **Stats section** — talk:listen ratio, longest monologue, patience (silence after customer turn), interactivity, question count.
  - **Feedback / whistle icon** with a *REQUEST FEEDBACK* button — pings a manager to score the call.
  - **Shares & Views** — log of who shared the call, who viewed it, what timestamps they jumped to, how many times an emailed link was opened.
  - **AI to-dos icon** — action items auto-extracted from the conversation.

Source: [Gong intro to the call page](https://help.gong.io/docs/intro-to-the-call-page), [Review a call](https://help.gong.io/docs/review-what-happened-in-a-call), [Add a comment](https://help.gong.io/docs/add-a-comment), [Create a snippet](https://help.gong.io/docs/create-a-call-snippet), [Score a call](https://help.gong.io/docs/score-a-call).

### D.2 Snippet/clip-a-moment interaction (Gong-style, used by Chorus too)

Two entry points produce the same artifact:

- **Timeline method**: click the scissors-style icon below the call screen. **Yellow drag handles** appear on the timeline. You drag the two handles to set the in/out points; the transcript on the side highlights the corresponding text with synced anchor pointers — drag either side and both stay in sync.
- **Transcript method**: select text in the transcript; a floating action menu appears adjacent to the selection; click the scissors icon.

Either method produces a snippet you can **Share** (internal or external), **Comment**, **save to Library**, **Download**, or **Embed** in a third-party tool. The original call is unaffected and any number of snippets can spin off one call. ([Gong snippets](https://help.gong.io/docs/create-a-call-snippet), [Chorus snippets/library](https://www.spekit.com/templates/chorus-getting-started-guide))

### D.3 Share modal pattern (Gong, mirrored across the rest)

- Share icon top-right of the call page opens a single dialog with three tabs/sections: *Email to Gong users*, *Slack channel* (preview shows "AI-generated call brief"), *Microsoft Teams notification* for internal; *copyable customer-facing link* + *embed link* for external.
- **Privacy radio**: "Anyone with the link" vs "Only specific people."
- **Link expiration** (up to 100 days).
- **Toggle**: include AI summary in share.
- **Toggle**: require identification via Google or LinkedIn before viewing.
- **Domain allowlist** field: "Also allow anyone from these company domains" (rejects personal-domain entries).
- After share: a **Shares & Views panel** logs share count, timestamps, viewer identity (when identification was required), specific playback points jumped to, and email-forward counts for unidentified links. ([Share a call](https://help.gong.io/docs/share-a-call))

### D.4 Talkdesk QM detail screen (the more "QA-shaped" cousin)

- **Side panel = full call transcript** (paragraph-per-turn).
- **Keyword search box** above the transcript for word/phrase lookup.
- **Sentiment summary chip at the top of the transcript** — single value, customer perspective: **Positive / Neutral / Negative**.
- **Per-utterance sentiment** — each turn carries an agent-sentiment and customer-sentiment annotation.
- **Recording timeline** sits with the audio player. Talkdesk Interaction Analytics adds **time-stamped intent annotations** that appear as **positive or negative icons** on the timeline — clickable jump points to where each intent was matched.
- **Screen + audio** play simultaneously (the agent's screen capture syncs to the call audio).
- **Evaluation form panel** with multi-select / range / yes-no / free-text questions, sectioned by category.
- **Drilldowns**: each transcript turn can be clicked to scrub; intent bubble in the dashboard view links into the conversations carrying that intent. ([Talkdesk QM Overview](https://www.talkdesk.com/cloud-contact-center/wem/quality-management/), [QM Assist overview](https://support.talkdesk.com/hc/en-us/articles/4402964008987-Talkdesk-QM-Assist), [Interaction Analytics dashboards](https://support.talkdesk.com/hc/en-us/articles/360061348931-Using-Dashboards-with-Interaction-Analytics))

### D.5 Observe.ai detail screen

- Single canvas that **synchronizes four streams**: audio waveform, transcript, agent screen recording, and metadata (queue/disposition/channel) — drag the timeline and all four scrub together.
- **PCI / PII redaction** is applied automatically to browser and desktop streams (the field shows as an obscured rectangle).
- **Per-stream multi-monitor display** — if the agent had two screens, both stack side-by-side under the player.
- **Evaluation form** to the right with **auto-suggest / auto-fill / auto-submit** colored highlight states so the reviewer can see at a glance which answers AI populated vs which still need a human.
- **Time-stamped comments** ("highlight a coachable moment and leave a time-stamped comment") that double as anchors for scheduled coaching sessions.
- **Agent acknowledgement** + **dispute** controls at the bottom of the form — when an agent disagrees with a score, they file a dispute that opens a side conversation visible to the supervisor. ([Observe screen recording](https://www.observe.ai/agent-screen-recording), [Observe Auto QA](https://www.observe.ai/post-interaction/auto-qa), [Observe coaching workflows](https://www.observe.ai/blog/introducing-agent-performance-coaching-workflows))

### D.6 Scorecard/rubric panel — combined detail across all five products

Gong's scoring panel sits on the **right rail** of the call view, opened by a **star icon**. The header says "Includes answers by Gong AI" if AI scoring is on. The form contains:

- **One question per row**, each rendered according to **question type**: *Range (0–50)*, *Multi-select* (checkboxes), *Single-select* (radio), *Yes/No*, *Open-ended* (free text).
- An **AI-suggested answer** is pre-selected and tagged with a small AI icon. Clicking the icon expands a "Why the AI chose this answer" explanation showing the source transcript passages.
- A **scoring guide** drawer collapses under each question with instructions from the scorecard author.
- An **"Add more feedback"** free-text field per question.
- A **mandatory** indicator on questions where required.
- **Overall score question** at the bottom — *Manual* or *Calculated*. Calculated uses per-question weights that snap to 100% (auto-recalibrating slider). Answers normalize to 0–1, weighted, then rescaled to 1–5. Skipped questions = lowest value; N/A excluded.
- **Visibility radio**: Public (company-wide), Private (scorer only), Collaborators (specific recipients notified).
- **Submit** → counts as feedback given (unless you're the call owner scoring yourself).
- **Learning resources block** — links to Gong calls, external URLs, or AI Trainer content. Can be set to display only when below a score threshold, with an optional context message.
- **Edit / Delete** own scorecards; admins edit others' with both names shown. ([Score a call](https://help.gong.io/docs/score-a-call), [Create scorecards](https://help.gong.io/docs/create-and-manage-scorecards))

Five9's scoring model is more elaborate and worth borrowing structurally: **Forms > Sections > Categories > Questions**, with each level independently configurable as *Sum / Average / Percentage* and weighted via a *Base Percentage*. **Null scores aren't counted** in calculations. ([Five9 scoring methods](https://five9verint.five9-wfo.com/onlinehelp/en_us/qm/QM/Scoring_methods.htm))

Talkdesk QM forms allow **optional questions** that evaluators can skip without blocking submission, and each form is tied to a queue/team filter so the right form auto-loads for the right call. AI Pending evaluations are partially filled and routed to supervisor inboxes. ([Forms in QM](https://support.talkdesk.com/hc/en-us/articles/360051607831-Forms-in-QM))

Observe.ai's form supports the Gong-style answer types plus **agent acknowledge / dispute** at the bottom, with the dispute opening a thread visible only to the supervisor and the disputing agent. ([Observe.ai evaluation forms](https://www.observe.ai/contact-center-glossary/call-center-agent-evaluation-form), [Observe.ai performance coaching](https://www.observe.ai/blog/introducing-agent-performance-coaching-workflows))

## E) Visual language — colors, typography, density, iconography, motion, brand voice

**Gong** uses a saturated brand palette of **bright purple flanked by pink**, with **shades of gray** to modulate. The product UI specifically uses **purple for your-company speakers and pink for customers** in question tags and speaker lanes — this is a meaningful in-product use of brand color (not decorative). The brand typography is a "bold, whimsical" block-form display face, paired with a clean text sans for the product UI. Gradient treatments (deep indigo → vibrant purple) carry into product surfaces. Tone of voice: confident, energetic, slightly playful — "celebration / conversation / individuality" are the explicit brand drivers. Comments highlight in **yellow** when the playhead crosses their timestamp; snippet selection handles on the timeline are also **yellow** — yellow is the in-product "user-generated marker" color. ([Gong visual identity](https://www.gong.io/blog/introducing-gongs-new-visual-identity), [Review a call](https://help.gong.io/docs/review-what-happened-in-a-call))

**Talkdesk** uses a calmer enterprise palette (white canvas, dark navy nav, teal/green accents, with sentiment-specific reds/greens/grays for negative/positive/neutral). Sentiment is the only color carrier inside the transcript — green = positive, red = negative, gray = neutral. Time-stamped intent annotations on the recording timeline render as small positive (green up) or negative (red down) icons. ([Talkdesk QM Assist transcript](https://support.talkdesk.com/hc/en-us/articles/4402964008987-Talkdesk-QM-Assist-Overview), [Talkdesk Interaction Analytics](https://support.talkdesk.com/hc/en-us/articles/360058760372-Interaction-Analytics-Overview))

**Five9** leans toward a real-time-dashboard aesthetic: red/amber/green KPI tiles, big animated trend arrow icons next to averages, a darker chrome to read at a glance from across an ops floor. ([Five9 Performance Dashboard](https://www.five9.com/products/capabilities/performance-management-dashboard))

**Observe.ai** has a clean white-and-dark-blue product surface with green for positive sentiment, red for risk, and a soft purple as a third accent on AI-generated content. AI-filled answers in the eval form carry a soft purple "AI" badge so the human always knows what was machine-suggested. ([Observe.ai brand site](https://www.observe.ai/))

**Chorus** uses a ZoomInfo-aligned blue + dark theme with red/green sentiment ticks, and yellow "highlight" callouts on the transcript that mark tracker hits.

**Density**: all five use **medium row density** for lists (≈48px row), **comfortable density** for detail screens (transcript paragraphs separated by ≈12–16px), and **small density** for inline filter chip rows. Iconography is universally outline-style (Material/Phosphor/Lucide family), 20–24px in toolbars, 16px in inline chrome. Motion is minimal — the only animated affordances are the **purple/yellow scrubber playhead glide** and the **scorecard answer highlight bounce** when AI auto-fills.

## F) Specific patterns Sabi should copy (numbered)

**Sabi tech reminder**: Next.js 16 App Router + Tailwind v4 + shadcn/ui + Clerk. Audio = WaveSurfer.js (per-channel) + lucide-react icons. Tables = TanStack Table v8. Drag handles = `@radix-ui/react-slider` for in/out points. Comments = Supabase Realtime channel.

1. **Three-pane interaction detail layout (transcript left / player center / scorecard+comments right).** Lives at `/sabi/sessions/[id]`. Build with shadcn `ResizablePanelGroup`; collapse the right rail to an icon strip on narrow widths like Gong does. The left rail uses an `Accordion` of collapsible sections: *Ask anything (placeholder for future AI Q&A), Highlights, Outline, Transcript, Lesson info, Points of interest, Pages of the workbook*. Persist open/closed state in `localStorage` per user (Clerk userId scoped). Why it works: the same screen serves three audiences without context switches — a coordinator scoring, a board member reviewing, an agent (teacher) acknowledging.

2. **Per-channel audio lanes with mute toggles and talk-percentage.** Render two WaveSurfer instances stacked vertically — **Sabi voice (top lane, gold per the approved brand)** and **Child voice (bottom lane, off-white)**. Each lane gets a mute toggle on the left end and a talk-percentage label on the right end (`"32%"`). Both lanes share a single scrubber. Why: Gong's evidence — talk-ratio is the #1 scoreable signal evaluators look at; surfacing it inline removes a whole tab.

3. **Synchronized highlight transcript with paragraph-per-turn diarization.** One paragraph per speaker turn, speaker label (`SABI` / `CHILD-{id}`) in a small caps badge at the left, timestamp pill `[02:14]` after the badge. Currently-playing turn gets a left border in `--color-sabi-gold` and a subtle background tint. Click any turn = `wavesurfer.setTime(turn.startMs/1000)`. Search box at the top with `Ctrl/Cmd+F` shortcut.

4. **Color-coded utterance roles (Gong's purple/pink).** Use the Sabi palette: **gold tint = Sabi turns, off-white tint = child turns, soft red tint = guardrail-triggered moments, blue tint = teacher voice if a coordinator joined.** Pin to CSS variables so any QA color change cascades.

5. **Topic ribbons under the player.** Gong's "topics section" — render per-lesson-segment ribbons (Phonics warm-up / Letter sound / Blend practice / Read-the-word / Closing). Click a ribbon = scrubs to that segment. Color them via the curriculum-app phase palette already in use. shadcn `ScrollArea` horizontal.

6. **Snippet/clip with yellow drag handles + transcript-side anchors.** Two-handle range slider that sits directly on top of the waveform (Radix Slider with two thumbs, gold-tinted yellow `#F5C145`). Selecting transcript text opens a floating menu (use `@radix-ui/react-popover` anchored to the selection) with *Clip, Comment, Share, Save to Library*. Storing as a `clips` row keyed by `sessionId + startMs + endMs + createdBy`. Why: Sabi's clips become the raw material for the parent-comms loop and partner reports.

7. **Comment system with timestamp anchoring, @mention, hashtag, visibility scope, and yellow playhead highlight.** Steal Gong wholesale: comments default to the current playhead, `@mention` up to N people, `#tag` for hashtag-style filtering, visibility radio (Workspace / Specific people / Only me), and the comment row glows yellow when the playhead crosses its timestamp. Use Clerk org members for `@mention` resolution. Persist as `comments(session_id, t_ms, body, mentions[], hashtags[], visibility)`. The "comments-as-bookmarks" pattern means clips and comments share the same primitive.

8. **AI brief at the top of the left panel ("Highlights / Outline / Ask anything").** Generate at session-end via Anthropic + cache to Supabase. Surface a one-paragraph recap + bulleted highlights + next steps for the parent. The Outline is the lesson plan with per-segment durations; hover bullet = jump. The Ask-anything bar is a `Textarea` whose answer cites transcript ranges (use Claude's tool-use to return `{answer, citations:[{start_ms,end_ms}]}`) — answer chunks are clickable to scrub.

9. **Scorecard panel as right-rail star-icon drawer.** Sections + categories + questions in a Five9-style tree. Question types: `range`, `yesno`, `single_select`, `multi_select`, `open_ended`. Each question has a mandatory toggle, a scoring-guide collapsible drawer, an "AI suggested" pill with a "Why?" link that opens transcript citations. Calculated overall scoring with weights that auto-snap to 100%. Skipped = lowest; N/A = excluded. For the lesson rubric concretely: *Intro / Phonics accuracy / Engagement check-ins / Error handling / Close & next-lesson hook*.

10. **Status pill vocabulary borrowed from Talkdesk QM.** `Draft · To do · Review requested · AI pending · AI scored · Completed · Acknowledged · Disputed`. Render as shadcn `Badge` variants with distinct colors per status. `AI Pending` rows are visible only to coordinators (Clerk role gate).

11. **Agent (teacher / coordinator) acknowledge + dispute flow.** After a session is scored, the teacher sees an *Acknowledge* button; clicking transitions status to `Acknowledged`. A *Request review* button opens a dispute thread bound to the evaluation, visible only to the disputer and supervisor. This is how Talkdesk + Observe.ai keep agents bought-in.

12. **Index page with chip filters + saved searches ("Streams").** Default filter chips: *Pupil, School/Cohort, Lesson, Date range, Phone number, Sabi voice version, Score range, Status*. `+ Add filters` opens a side drawer of every column. Save any filter combo as a *Stream* that auto-includes new sessions and notifies the creator (Supabase Realtime + Clerk email). Search bar supports operators: quotes for exact, `|` for OR, `+` for AND, `-` for NOT.

13. **Per-row quick-action set on the list page**: *Listen later, Add to library, Share (internal/external/embed), Generate parent SMS, Download audio, Download transcript, Mark privacy, Move workspace, Delete.* Use shadcn `DropdownMenu` triggered by the row's `…` icon.

14. **Bulk actions toolbar** that appears when ≥1 row checked: *Assign to reviewer, Export CSV, Bulk tag, Bulk share to library, Bulk apply scorecard, Bulk soft-delete*. Mirror Gong's "Download call data" CSV — date, child id, lesson, duration, score, status, evaluator.

15. **Share modal with privacy radio + link expiration + identification gate + domain allowlist + share/views audit log.** Even at small scale this matters for Sabi because board members will forward links; the audit log lets you see who opened what, jumped to what timestamp, and forwarded the link. Persist as `shares(id, session_id, scope, expires_at, require_identification, allowed_domains[], created_by)` + `share_views(share_id, viewer, opened_at, jumped_to_ms[])`.

16. **Per-utterance sentiment + overall sentiment chip at the top of the transcript** (Talkdesk pattern). For Sabi, replace generic sentiment with **child engagement signal**: `engaged / hesitant / frustrated / silent`. Run cheap classifier per turn; render colored dot in the left margin and a single chip at the top showing the modal value.

17. **Time-stamped intent / moment icons on the timeline** (Talkdesk's "positive/negative icons on the recording timeline"). For Sabi: render small icons above the waveform for *Guardrail tripped, Correct answer, Repeated mistake, Long silence, Lesson plan deviation, Pronunciation flagged*. Click = scrub. Use lucide icons sized 14px, color-mapped to category.

18. **Auto-fill / auto-suggest / auto-submit indicators on AI-generated rubric answers.** Three visual states: `AI-suggested` (faint purple ring, pending human approval), `AI-filled` (solid purple dot, human can override), `AI-submitted` (gray check, auto-locked at high confidence). Inline `Why?` reveals the transcript citations.

19. **Library + Smart Playlists (Chorus pattern).** A `/sabi/library` page where saved clips live. Smart Playlists auto-fill from criteria: *all guardrail-tripped moments this week, all sessions where a child read 3+ words correctly, all sessions where Sabi mispronounced a Pidgin word*. The board can subscribe and the playlist updates daily. This becomes the highlight reel for grant reports.

20. **Calibration mode (Talkdesk pattern).** Two or more coordinators score the same session blind, then the system reveals each other's scores side-by-side with a per-question delta. This is critical for Sabi because the team is distributed (Naomi + Sonia in Lagos + future reviewers) — calibration keeps the rubric reliable.

21. **Coaching tab linked from any session.** Borrowed from Observe.ai's coaching workflows: from a scored session, click *Create coaching plan* → opens a form that converts low-scoring rubric answers into action plan items with a follow-up date. Track completion. Connect to a per-teacher dashboard.

22. **AI summary at top is editable + cite-back.** Don't ship a raw LLM blob. Show the summary in a `Card` with an Edit pencil for the reviewer + footnote-style citations (Gong's "click AI answer to see why" pattern) that anchor to transcript ranges. This is what builds board trust.

23. **Density + iconography**: shadcn defaults are fine but pin **row height 48px** for lists, **transcript paragraph spacing 16px**, **icon size 20px in toolbars, 16px in inline chrome**. Lucide icons everywhere. Sabi gold (`#D4A537`-ish per the brand kit) for the active speaker / current playhead / "in-progress" states, off-white for inactive content, deep navy/black for surface chrome — matching the approved premium-gold-on-black brand direction.

## G) Anti-patterns to avoid

- **Don't render audio + transcript on separate pages or behind tabs.** Every product converged on a single canvas with both visible. Tabbing kills the eye-darting motion that makes QA fast.
- **Don't put scoring on its own page.** Gong, Observe, and Talkdesk all keep the scorecard pinned to the right rail of the same screen as the audio + transcript. Routing away breaks the "score-as-you-listen" loop.
- **Don't auto-fill AI answers without a visible "AI suggested" indicator and a citation link.** Reviewers stop trusting the tool the moment they realize they can't tell what a human did vs what the model did. Talkdesk's `AI Pending` status exists specifically because confidence is variable.
- **Don't gate the @mention or comment thread behind a separate "Discussion" page.** Inline timestamp-anchored comments are the killer feature. Standalone discussion threads die.
- **Don't ship a free-text-only tagging system.** Free text rots. Use a **preset taxonomy + free text** combo: a controlled vocabulary of categories (Guardrail trip, Pronunciation, Engagement, Lesson deviation, Compliance) plus an optional hashtag field. Mirror Gong's hashtags-with-autosuggest pattern — previously used hashtags surface as suggestions.
- **Don't omit the share audit log.** If you ship sharing without "who viewed when," boards will forward links to funders and you'll never know which ones converted.
- **Don't let the AI summary be the only summary.** Make it editable + citable; otherwise it's just a fancy-looking liability.
- **Don't build a list page with no bulk actions.** A QA reviewer needs to multi-select and assign / export / tag in one move — the Talkdesk-style status pills only earn their keep when paired with bulk transitions.
- **Don't show waveforms as one mixed mono channel.** The whole point of per-channel waveforms (Gong's speaker lanes, Observe's synchronized streams) is to see overlapping talk, dead air, and interruptions at a glance. A mixed waveform tells you nothing about who.
- **Don't use color decoratively.** Gong uses purple/pink for speaker role, Talkdesk uses red/green/gray for sentiment, and that's it — color carries meaning. If Sabi paints rubric sections in random brand pastels, color stops being information.
- **Don't put "Acknowledge" and "Dispute" only in email.** Putting them in-app inside the scorecard panel (Observe + Talkdesk pattern) is what makes the loop close.
- **Don't allow snippet creation only from the timeline OR only from the transcript.** Gong's dual-entry (timeline scissors + transcript-selection scissors) is what makes clipping feel native to whichever surface the reviewer is currently looking at. Build both.
- **Don't let scoring weights drift away from 100%.** Gong's auto-recalibration when an admin changes a weight is the right behavior; manual sum-to-100 math is a usability bug.

## H) Source URLs

- https://help.gong.io/docs/intro-to-the-call-page
- https://help.gong.io/docs/review-what-happened-in-a-call
- https://help.gong.io/docs/view-a-call-transcript
- https://help.gong.io/docs/score-a-call
- https://help.gong.io/docs/create-and-manage-scorecards
- https://help.gong.io/docs/faqs-automatic-review-scorecards
- https://help.gong.io/docs/scorecard-faqs
- https://help.gong.io/docs/gong-ai-for-scoring
- https://help.gong.io/docs/capture-and-analyze-calls
- https://help.gong.io/docs/search-for-calls
- https://help.gong.io/docs/add-a-comment
- https://help.gong.io/docs/review-a-comment
- https://help.gong.io/docs/share-a-call
- https://help.gong.io/docs/create-a-call-snippet
- https://help.gong.io/docs/download-a-call-or-snippet
- https://help.gong.io/docs/download-call-data
- https://help.gong.io/docs/make-bulk-changes-via-a-csv-file
- https://help.gong.io/docs/how-to-create-and-manage-deal-boards
- https://help.gong.io/docs/integration-patners-hub-embed-a-call-in-third-party-software
- https://www.gong.io/blog/introducing-gongs-new-visual-identity
- https://www.gong.io/blog/how-gong-uses-gong
- https://docs.chorus.ai/hc/en-us/articles/360050825334-New-UI-Chorus-Got-a-Make-Over
- https://docs.chorus.ai/hc/en-us/articles/115009183547-Tips-on-Getting-Started-with-Chorus
- https://docs.chorus.ai/hc/en-us/articles/360007464874-Recordings-Review-all-your-team-s-meetings-at-a-glance
- https://docs.chorus.ai/hc/en-us/articles/360007562893-Playlists-Curated-content-for-you-to-review
- https://docs.chorus.ai/hc/en-us/articles/1260806120190-Using-Smart-Playlists
- https://docs.chorus.ai/hc/en-us/articles/360036206813-How-to-Create-Trackers
- https://docs.chorus.ai/hc/en-us/articles/360007562973-Indepth-Analytics-Page-Gain-Insight-into-Your-Team-s-Conversations
- https://docs.chorus.ai/hc/en-us/articles/115009169648-Advanced-Tracker-Setup
- https://www.chorus.ai/
- https://www.spekit.com/templates/chorus-getting-started-guide
- https://www.claap.io/blog/chorus-ai-call-recording
- https://www.observe.ai/
- https://www.observe.ai/post-interaction-ai
- https://www.observe.ai/post-interaction/auto-qa
- https://www.observe.ai/post-interaction/contact-center-performance-management
- https://www.observe.ai/agent-screen-recording
- https://www.observe.ai/blog/introducing-agent-performance-coaching-workflows
- https://www.observe.ai/blog/reporting-analytics-from-observe-ai
- https://www.observe.ai/contact-center-glossary/call-center-agent-evaluation-form
- https://support.talkdesk.com/hc/en-us/articles/360051136152-Talkdesk-Quality-Management-QM-Overview
- https://support.talkdesk.com/hc/en-us/articles/360051226552-Performing-Evaluations-in-QM
- https://support.talkdesk.com/hc/en-us/articles/13053603142555-Evaluations-in-QM
- https://support.talkdesk.com/hc/en-us/articles/4402964008987-Talkdesk-QM-Assist-Overview
- https://support.talkdesk.com/hc/en-us/articles/4441539319835-Talkdesk-QM-Assist-Best-Practices
- https://support.talkdesk.com/hc/en-us/articles/4405382004251-Configurations-in-QM-Assist
- https://support.talkdesk.com/hc/en-us/articles/4413116984475-Calibrations-in-QM
- https://support.talkdesk.com/hc/en-us/articles/4402963554203-Agent-View-in-QM
- https://support.talkdesk.com/hc/en-us/articles/360051607831-Forms-in-QM
- https://support.talkdesk.com/hc/en-us/articles/360058760372-Interaction-Analytics-Overview
- https://support.talkdesk.com/hc/en-us/articles/360061348931-Using-Dashboards-with-Interaction-Analytics
- https://support.talkdesk.com/hc/en-us/articles/360060227612-Using-Search-with-Interaction-Analytics
- https://support.talkdesk.com/hc/en-us/articles/10465887798555-Release-Notes-Talkdesk-QM-Assist
- https://support.talkdesk.com/hc/en-us/articles/10465889498651-Release-Notes-Talkdesk-Quality-Management
- https://www.talkdesk.com/cloud-contact-center/wem/quality-management/
- https://www.talkdesk.com/cloud-contact-center/customer-experience-analytics/interaction-analytics-sentiment/
- https://www.talkdesk.com/modals/talkdesk-interaction-quality-analytics/
- https://data-dictionary.talkdesk.com/docs/qm-evaluation-analysis
- https://www.five9.com/products/capabilities/contact-center-quality-management-monitoring-tools
- https://www.five9.com/products/capabilities/interaction-analytics
- https://www.five9.com/products/capabilities/performance-management-dashboard
- https://www.five9.com/blog/how-create-contact-center-scorecard
- https://www.five9.com/faq/what-is-an-agent-scorecard
- https://www.five9.com/resources/datasheet-five9-performance-dashboard
- https://www.five9.com/resources/datasheet/enterprise-quality-management
- https://www.five9.com/blog/future-quality-management-enhancing-call-recording-speech-analytics
- https://five9verint.five9-wfo.com/onlinehelp/en_us/qm/QM/Scoring_methods.htm


---

## Comparable 5: Edtech learning analytics — Duolingo Schools, Khan Academy teacher, Coursera instructor, Canvas, Moodle, Schoology, Knewton

I have substantial material. Let me now write the comprehensive audit.

# Edtech learning analytics — Duolingo Schools, Khan Academy teacher, Coursera instructor, Canvas, Moodle, Schoology, Knewton

## A) Product overview (1 paragraph)

These seven products cover the full range of stakeholder dashboards Sabi will need to design around: **Duolingo for Schools** is the closest analogue to Sabi (gamified language/literacy learning with phone-style engagement loops), giving teachers a "control center" with rosters, assignments, real-time activity log, XP/accuracy/time-on-task metrics, and "missed"/"late" assignment labels. **Khan Academy Teacher / Districts** is the gold standard for mastery visualization: a five-level mastery model (Not Started → Attempted → Familiar → Proficient → Mastered) with color-coded progress bars, three-tab Activity Overview (Activity / Skills / Mastery), Individual Student Reports, and a district-level Administrator Homepage with Activation Summary, Skills-to-Proficient summary, and grade-level segmentation. **Coursera instructor** popularized "Google-Analytics-style" course dashboards with vital-stats + three interactive charts + itemized question table, and proved that surfacing a "Next step" recommendation lifts completion 10%+. **Canvas New Analytics / Course Analytics** is the most opinionated about "needs attention" — a Submissions graph with green-circle / yellow-triangle / red-square / diamond glyphs, plus the canonical "Message Students Who…" flow scoped by Missing count, Late count, or score range. **Moodle** ships a Completion Progress block (red/blue/yellow/green segments per activity) and an Insights/Inspire predictive engine that emits "Students at risk of dropping out" cards with four standard actions (Send a message / View / Accept / Not applicable). **Schoology (PowerSchool)** is the strongest reference for standards-based mastery with light-green "Meets Expectations" / dark-green "Exceeds Expectations" cells, star-icon "Mastery Achieved" badge, and six exception flags (Absent, Exempt, Incomplete, Late, Missing, Collected) reachable by hovering a cell. **Knewton (Alta + Enterprise)** is the reference for the knowledge-graph mental model — ovals = learning objectives, arrows = prerequisites, color = chapter/assignment grouping — with a per-assignment Mastery Progress ring/bar that updates after every question and "circular progress icons next to learning objectives."

## B) Navigation + topbar pattern (detailed)

**Khan Academy Teacher Dashboard — primary nav (per-class left sidebar):**
- **Assign** (default landing after picking a class)
- **Course Mastery**
- **Activity** (a.k.a. "Activity overview")
- **Students** (roster + manage)
- **Settings** (where "Download student data" → "Download CSV" lives)
- Top-level switcher: **Classes** tab → list of all classes you've created + "add a new class" CTA
- Khan Academy Districts adds an **Administrator Homepage** at the top with cards: *Activation Summary* (rostered / activated / started an activity counts), *Skills to Proficient and Above Summary*, school/grade/class drill-down, and *Khanmigo Usage* report.

**Duolingo for Schools — primary nav:**
- **Classes** (cohort list)
- **Assignments** (XP Assignments creation + tracker)
- **Reports** tab (per-assignment student data, click student to see their unique data)
- A **persistent right-rail Activity Log sidebar** that updates in real time — shows which Duolingo Unit each student is on, XP earned, lesson completions, streaks. This is the unique pattern: the log is always visible alongside whatever main view you're on.
- Gamification overlays on roster cells: XP, leaderboards, streak counts, achievement badges.

**Canvas — course-level nav (left rail per course):**
- Home, Announcements, Assignments, Discussions, **Grades**, People, Pages, Files, Syllabus, **New Analytics** (button on Home Sidebar; visible only to instructors/admins/TAs), Modules, Quizzes
- Inside New Analytics: tabs for **Grades**, **Weekly Online Activity**, **Communication**, **Resources**
- An **Options icon** (kebab) on each chart toggles between interactive chart graph and data table view.

**Moodle — dashboard:**
- Personal **Dashboard** with stackable blocks: **Course overview block** (filters: *All / In progress / Future / Past / Starred / Term / Removed from view*), **Timeline block** (upcoming deadlines), **Calendar block**, **Completion Progress block** (segment grid, one segment per activity)
- Each course has a left/sidebar nav → **Course administration > Reports > Insights** (predictive at-risk notifications) and **Course administration > Reports > Course completion**.

**Schoology (PowerSchool) — course nav:**
- **Materials**, **Updates**, **Gradebook**, **Mastery** (the primary mastery tab/section), **Members**, **Analytics**, **Workload Planning**
- District/admin overlay: **District Mastery** with shared library of learning objectives and one mastery scale across the district.

**Coursera instructor (legacy + current):**
- **Course Dashboard** ("Google Analytics"-style top-level view) → vital stats + three interactive charts + itemized table
- Sub-dashboards: **Quiz dashboard** (per-quiz, per-question), **Peer assessment dashboard** (bootstrap sampling visual)
- Learner home page now leads with a **progress bar per active certificate course** and a **"Start" button on the next recommended item** (last left-off, failed-assignment retry, or upcoming practice).

**Knewton Alta:**
- Course view → Assignments list with per-assignment **Mastery progress bar** that updates after each answered question
- Instructor view: Gradebook with mastery percentage, time-per-question, mastery progression velocity, performance patterns; at-risk identification surfaced via class trends.

**Common topbar conventions across all seven:** logo top-left → product switcher → role indicator (Teacher / Admin / Instructor) → notifications bell → user avatar with menu → help. Schoology's custom-branded top nav requires a 4.5:1 contrast ratio with text on chosen hex.

## C) List/index pages — columns, filters, sort, search, density, pagination, bulk actions, empty state

### Khan Academy — Activity Overview (Activity tab, the canonical cohort view)
**Columns (rows are students):**
- Student name (clickable → Individual Student Report)
- Total learning minutes
- Skills worked on (count)
- Skills leveled up (count)
- Skills reached Proficient
- Skills reached Mastered

**Filters:**
- Checkbox: **"Only show my class's courses"**
- Checkbox: **"Only show assigned skills"**
- Time range filter (date picker)

**Sort:**
- Click **Total**, **Average**, or **Proficiency** column header → reverses high-low / low-high.

**Skills tab columns:** skill name × per-student mastery-level cell (color-coded by mastery level). Click `>` symbol next to a unit to expand and reveal individual skills in that unit.

**Mastery tab:** purple bar graph per unit — click bar to drill into per-student mastery percentage; click skill name or colored chart to see student distribution at each mastery level for that skill.

**Export:** Settings tab → "Download student data" section → **"Download CSV" button**. Three CSV options: **Scores**, **All student skills data**, **Class skills data**. Scores CSV: columns = each assignment (with type: exercise/quiz/unit test/video/article), rows = student display name (or nickname). Optional **"Include the average score"** checkbox adds an Average score column. District admin CSV adds: *Skills Mastery Points* (0-100), *Total Learning Minutes on Khan Academy*.

### Duolingo for Schools — Roster / Assignment Tracker
**Real-time data columns per student:** XP earned, lesson completions, streak count, accuracy, time on task, current Duolingo Unit, assignment completion status. Late assignments are flagged "**missed**" if not started, "**late**" if completed after due date.

**Activity Log sidebar (right-rail, real-time):** running feed of "what student X just did, when" — used as the always-on situational awareness pane.

**Roster joining model:** students join a class by link or code.

### Canvas — Gradebook (cohort index)
**Filter menu options (multi-select):**
- Assignment groups
- Sections
- Modules
- Student groups
- Assignment status (late, missing, resubmitted, dropped, excused)
- Submission type
- Grading period
- Assignment due dates

**Search:** "Search Students" field with **as-you-type filtering**; supports name or SIS ID.
**Display options:** sort name by **first name / last name / SIS ID / Integration ID / Login ID**.
**Column arrangement:** by assignment name / due date / points / modules; manually resize and rearrange.
**Per-column sort:** by grade and by assignment status.
**Color customization:** instructor can pick the color for each status — late / missing / resubmitted / dropped / excused.

### Canvas — New Analytics (Course Analytics)
**Reports panel options:**
- **Missing Assignments**
- **Late Assignments**
- **Excused Assignments**
- **Class Roster**
- **Course Activity**

**Downloaded CSV columns (per institution):** student's name, Canvas user ID, email, student ID, **overall course grade**, **percent of assignments on time**, **last page view time**, **last participation time**, **last logout time**.

**Comparison toggles:** chart graph comparison or data table comparison between course average vs. an individual student or section.

### Schoology — Mastery (cohort index)
**Layout:** list of all students with overall mastery scores per learning objective; items ordered as they appear in the course folder structure.
**Color cells:**
- **Light green** = "Meets Expectations" (minimum score set by instructor)
- **Dark green** = "Exceeds Expectations" (minimum score set by instructor)
- **Star icon** = "Mastery Achieved"
- Below thresholds = uncolored / default

**Gear icon menu (top-right of report):**
- **Mastery Settings**
- **Export Summary**
- **Export Detail All Students**

**Mastery Settings configuration fields:** Achievement Levels (min score for "Meets" and "Exceeds"), Mastery (numeric demonstrations required), **"Grade Overall Learning Objectives" dropdown** with options: *Average*, *Highest Score*, *Decaying Average* (default 75% decay), Mastery Scale selector (existing or create new).

### Schoology — Gradebook cell exceptions
Hover a cell → flag icon appears → click it to assign one of six exceptions:
- **Absent**
- **Exempt**
- **Incomplete** (visualized as half-filled orange hexagon)
- **Late**
- **Missing** (empty orange hexagon; equivalent to zero score)
- **Collected** (submitted but not yet graded)
- "Excused" = full green hexagon

### Moodle — Completion Progress block (cohort overview page)
Grid: rows = students, columns = activities. Each cell is a small **segment colored red / blue / yellow / green** by default (color is theme-customizable). "Expected by date" drives segment ordering. Layout modes: **squeeze / wrap / scroll**; "When wrapping, limit rows to…" default = 16 segments per row. **Overview page** ("View course overview of Completion Progress for all students" capability) is the cohort view — designed to help find students at risk. Toggle: show/hide inactive students.

### Moodle — Insights at-risk feed
Cards in a stream — one per at-risk learner. Each card has four buttons: **Send a message**, **View** (opens student Outline report), **Accept**, **Not applicable** (the last two feed back into the model). Plus **"View Prediction details"** opens a panel showing which indicator values fed the prediction (low ones are highlighted).

### Pagination & density
None of the products surface heavy custom pagination — Canvas, Schoology, Moodle, Knewton all use traditional gradebook-style virtualized scrolling rows. Khan Academy paginates classes. Density choices: Schoology is the densest (hexagon icons in tight cells); Khan Academy is the most spacious (large progress bars, generous whitespace). Duolingo for Schools is mid-density with chunky rounded buttons (Feather Bold typeface vibe carries through).

### Bulk actions
- Canvas Gradebook: bulk grade edit, "Message Students Who…" applied across criteria-matched set.
- Khan Academy: bulk assign (whole-class assignment), bulk roster import via Clever/Google Classroom.
- Schoology: bulk exception flagging via right-click on column header; bulk export.
- Duolingo: bulk-assign XP assignments to class or individuals.

### Empty states
Khan Academy's classes page shows an **"add a new class"** CTA when empty. Moodle Course overview shows "no courses to display" with a hint to enroll. Canvas New Analytics requires up to 24 hours initial population — empty state explicitly says data refreshes every 8 hours.

## D) Detail/drawer pages — layout, sections, audio player, transcript, drilldown

### Khan Academy — Individual Student Report (the canonical per-learner page)
Reached by clicking student name from Activity Overview. Layout has the same three-tab pattern as the cohort view (Activity / Skills / Mastery), but scoped to one student:
- Top section: student name, class, time range filter
- **Activity tab:** total learning minutes, count of skills worked, skills leveled up, skills proficient, skills mastered, daily activity sparkline
- **Skills tab:** scrollable list of every skill in the course with the student's current mastery level for each one, color-coded (Not Started / Attempted / Familiar / Proficient / Mastered)
- **Mastery tab:** per-course / per-unit mastery breakdown showing distribution of student's skills across mastery levels
- Drilldown: click a skill → see attempted questions, time, attempts to proficient

**Individual Student Activity Log:** separate report showing time-stamped chronology of every action; note: minutes here may differ from Activity Overview because of how "active time" is calculated.

### Schoology — per-student mastery detail
Click a student from Mastery tab → opens that student's mastery report: list of every learning objective with color-coded box for each course material aligned to that objective, in folder-structure order. **Hover over a course material** → tooltip with individual score on that item. **Box plot visualization** showing average, high, low scores (hover-enabled tooltip details). **Info icon** on a test/quiz profile opens aligned learning objectives. **Rubric view** appears conditionally when instructor aligned rubric criteria to objectives.

### Canvas — per-student detail in New Analytics
Click a student name in the chart → comparison overlay drawn on top of the course-average chart (student line vs. average line). Same Options-icon kebab to flip between chart and table. Drilldown: click an assignment in the Submissions graph → assignment detail with green-circle (on-time), yellow-triangle (late), red-square (missing), diamond (due date), with bar extending from due date to actual submission date.

### Knewton Alta — assignment / per-objective drilldown
Inside an adaptive assignment: top bar shows **Assignment Mastery progress bar** that updates after every question. Side panel: **separate indicators of learning objective progress** (circular progress icons / rings), one per objective in the assignment. **Topic work remaining estimates** — explicit "X minutes of work remaining" so students can time-budget. Instructor view of same shell: time-per-question, mastery-progression velocity, performance patterns per student per objective.

### Duolingo for Schools — per-student / per-assignment detail
From Reports tab, pick an assignment, then any student in roster → **unique assignment data** view: XP earned on that assignment, accuracy, time on task, which lesson within the unit they completed, granular per-skill breakdown.

### Moodle — Student Outline report
From an Insight card → **View** button → student's Outline report: activity-by-activity grades, last-access timestamps, completion status icons. Plus the **Prediction details panel** showing the actual indicator values that drove the at-risk prediction, with low-performing indicators highlighted.

### Coursera — Quiz drilldown
Quiz Dashboard top: vital stats + 3 interactive charts (overall performance). Below: **itemized table sortable by "First attempt average score"**, each row expandable to a **details pane** showing per-option answer-choice counts (which wrong answer most students picked → instructor can spot a confusing distractor).

### Audio player / transcript (relevant for Sabi)
None of these seven products has a first-class audio player. The closest analogues: Coursera has its lecture player with **inline transcript panel**, clickable timestamps that scrub the video, and a "Next step" recommendation banner below the player. Canvas embeds media via the rich content editor with captions/transcript. For Sabi's call recordings, the strongest pattern would be a Coursera-style player with: scrubber, speed (0.75×/1×/1.5×/2×), inline transcript with sentence highlight that auto-scrolls in sync, and a "jump to where the learner struggled" marker overlay (this maps to Canvas's diamond/triangle/square glyphs on the timeline).

## E) Visual language — colors, typography, density, iconography, motion, brand voice

### Duolingo
- **Feather Bold** (headlines) — custom display sans-serif from Fontsmith (Krista Radoeva), commissioned 2019, rounded terminals, "wing-tipped stem junction" on uppercase, distinctive flick on lowercase "g".
- **DIN Next Rounded** (in-app body / UI).
- Color tokens:
  - **Feather Green / Duo Green**: `#58cc02` (primary CTA, brand)
  - **Sky Blue**: `#1cb0f6`
  - **Sunshine Yellow**: `#ffc700`
  - **Grape Soda**: `#a570ff`
  - **Bubblegum Pink**: `#cc348d`
- Density: low — chunky rounded buttons, generous padding, big celebratory animations after lesson completion. Heavy use of blob-like character illustrations (Duo the owl + cast).
- Motion: bouncy spring transitions on streak fire, XP fill, confetti on level up.
- Voice: encouraging, slightly cheeky, second-person ("You're on fire!"), short.

### Khan Academy
- Color-coded mastery: stacked bars where each segment is a mastery level. Klein blue / teal accents. "Purple bar graph" used in Mastery tab.
- Mastery levels in order: **Not Started → Attempted → Familiar → Proficient → Mastered**.
- Point values: Familiar = 50, Proficient = 80, Mastered = 100 (per skill).
- Click a proficiency level in the legend → hides that segment from progress bars (legend doubles as filter).
- Typography: friendly humanist sans-serif (Lato historically; product now uses a custom-leaning stack). Generous line-height.
- Voice: warm, encouraging, never punitive. "Skills to proficient" framing as core outcome metric.

### Canvas (Instructure)
- Brand: deep red/coral primary historically (#C82828-ish for Instructure red), navy / blue-grey UI chrome.
- Status icons (canonical and oft-copied):
  - **Green circle** = on time
  - **Yellow triangle** = late
  - **Red square** = missing
  - **Diamond** = due date
- Instructor can override status colors in Gradebook (late / missing / resubmitted / dropped / excused).
- Typography: Lato historically.
- Density: high in Gradebook, moderate in New Analytics charts.
- Voice: neutral, professional, instructional.

### Schoology (PowerSchool)
- Schoology classic: gray "school" + blue "ogy" wordmark, modern sans-serif.
- PowerSchool brand (parent co.): **PowerSchool Cyan `#00B6EF`** on light or white background, Navy as grounding contrast, bright accent colors for energy.
- Custom branding requirement: any custom top-nav color must meet **4.5:1 contrast ratio** with text.
- Mastery color scale: **light green = Meets**, **dark green = Exceeds**, **star icon = Mastery Achieved**, **orange hexagons for Incomplete (half-filled) and Missing (empty)**, **green hexagon = Excused**.
- PowerSchool grade-scale color set: **dark green, green, yellow, orange, red** — 2 to 5 color groups depending on scale.
- Density: highest of the group (gradebook cells are tight).
- Voice: enterprise, district-administrator-friendly, dispassionate.

### Moodle
- Brand orange (`#F98012`-ish) historically, but each install themes itself.
- Completion block default palette: **red / blue / yellow / green** — fully customizable to match institutional theme.
- Boost theme (default since 4.x): clean, Bootstrap-based, neutral grays, blue accents.
- Density: medium; very text-heavy by default.
- Voice: open-source, neutral, descriptive.

### Knewton
- Brand: blue/teal palette historically. Now Wiley-owned (Alta), inherits Wiley's blue brand.
- Knowledge graph visualization: ovals (objectives), arrows (prerequisites pointing A → B meaning "must know A before B"). Different colored objectives represent different chapters/assignments/levels.
- Mastery indicators: progress bar (per assignment) + circular progress icons (per objective) + "X minutes remaining" text.
- Voice: data-driven, neutral, slightly academic.

### Coursera
- Brand: Coursera Blue (`#2A73CC`-ish), white space, clean.
- Typography: Open Sans historically; product now uses a custom stack.
- Progress bars: linear, blue fill, paired with **bold "Start" CTA** for next-step recommendation.
- Density: low-medium; Apple-influenced clean layouts.
- Voice: aspirational, certificate-oriented, second-person.

## F) Specific patterns Sabi should copy (numbered)

**1. Three-tab cohort overview (Activity / Skills / Mastery)**
What it does: One screen, three lenses on the same cohort — Activity (effort: minutes, sessions), Skills (granular skill-by-skill grid), Mastery (rolled-up unit/course progress).
Where it lives: Khan Academy Activity Overview report.
**Sabi mapping:** `/admin/cohorts/[id]` → three `<Tabs>` (shadcn): "Calls" (minutes on phone, calls completed, last-call timestamp), "Skills" (per-phoneme / per-letter mastery for each learner — phonics-aligned to Sabi's curriculum), "Mastery" (unit-level percent stacked bar). Build as Next.js parallel routes so each tab is independently streamable.

**2. Real-time right-rail Activity Log (Duolingo)**
What it does: Persistent sidebar that streams "student X just did Y at time Z," visible regardless of what main view you're on. Lets a teacher glance over and know who's actively engaged right now.
**Sabi mapping:** A persistent right `<Sheet>` (shadcn) or fixed sidebar on `/admin/*` showing live Sabi call events: "Amara picked up at 14:32 — Lesson 3, Letter B." Built on Next.js + a SSE/WebSocket stream from the Africa's Talking webhook handler. Especially valuable for board members watching a pilot in real time.

**3. Five-level mastery model with stacked-bar visualization (Khan Academy)**
What it does: "Not Started → Attempted → Familiar → Proficient → Mastered" — five visually distinct states, each with a color, point value, and concrete advancement rule (e.g., 70-85% → Familiar; 100% on first try at Familiar → Proficient).
**Sabi mapping:** Define Sabi's own five-level scale for phonics: e.g., *Not Tried → Heard → Repeats with prompt → Reads independently → Generalizes to new words*. Show as stacked horizontal bars in the cohort Mastery tab. Legend doubles as filter (click "Familiar" to hide it from the bars). Critical for parents/board who don't know what "75%" means but instantly grasp a colored bar.

**4. Color-coded status glyphs (Canvas)**
What it does: green circle / yellow triangle / red square / diamond = on-time / late / missing / due-date — instantly readable at a distance.
**Sabi mapping:** Adapt to call patterns: green circle = "completed lesson on time," yellow triangle = "started but abandoned," red square = "missed entirely," diamond = "scheduled call slot." Use Lucide icons in shadcn `<Badge>` components. Shape-coded (not just color-coded) for accessibility and for parents printing black-and-white report cards.

**5. "Message Students Who…" criteria flow (Canvas)**
What it does: Single dropdown to pick a cohort segment (Missing count, Late count, score range), single composer, sends via in-product inbox + email/SMS/push.
**Sabi mapping:** `/admin/outreach` → "Call Learners Who…" picker: missed last call / score below X% on last skill / no activity in N days / parent hasn't logged in. Pipe to an SMS via AT or trigger a Sabi outbound call. This is THE pattern that lets a board member personally reach a struggling learner.

**6. Predictive at-risk card stream with four actions (Moodle Insights)**
What it does: One card per at-risk learner, four buttons: Send a message / View report / Accept / Not applicable. "Accept" and "Not applicable" feed back into the model.
**Sabi mapping:** `/admin/needs-attention` as a card grid (shadcn `<Card>`) — each card = one at-risk learner with the prediction reason ("3 missed calls + accuracy dropped 40%"). Four actions: "Call now" (trigger Sabi call), "View profile," "Acknowledge" (mark as seen), "Not at risk" (correct the model). Eventually plug into a real classifier; start with simple rules.

**7. Star-icon "Mastery Achieved" badge (Schoology)**
What it does: Universally legible symbol that crosses language barriers — a gold star on the cell when a learner has mastered a standard.
**Sabi mapping:** Gold star on the skill cell when a learner masters a phoneme. Aligns with Sabi's existing premium gold-serif brand. Use a single `<Star fill="#D4AF37" />` Lucide icon — same gold as the Sabi spark mark.

**8. Knowledge-graph visualization for board explainer (Knewton)**
What it does: Ovals = learning objectives, arrows = prerequisites. Colors group objectives by chapter. Shows the structural logic of the curriculum.
**Sabi mapping:** A read-only static SVG/React Flow diagram on `/admin/curriculum-map` showing the phonics scope-and-sequence: each letter/phoneme as a node, prerequisite arrows (consonants before blends before digraphs), color-grouped by unit. Hover a node → tooltip with "% of cohort mastered." This is the board-meeting visual that proves Sabi has a real curriculum, not a black box.

**9. CSV export with sensible columns + optional aggregates (Khan Academy)**
What it does: A "Download CSV" button under Settings → "Download student data," with three pre-built reports (Scores / All skills / Class skills) and an optional "Include the average score" checkbox.
**Sabi mapping:** `/admin/exports` page (or button on every list view) → three canned reports: *Call logs CSV* (one row per call: learner, lesson, duration, accuracy, completion), *Skill mastery CSV* (one row per learner × skill), *Cohort summary CSV* (one row per learner, columns = each unit + average). Checkbox "Include average accuracy across all calls." Implement via a Next.js route handler that streams CSV.

**10. Gear-icon export menu (Schoology)**
What it does: Top-right gear opens three export options: **Mastery Settings / Export Summary / Export Detail All Students**.
**Sabi mapping:** shadcn `<DropdownMenu>` with `<Settings />` trigger in the top-right of every report — items: Settings, Export Summary (PDF, 1 page for the board), Export Detail (CSV, every row).

**11. Three CSV options at one click (Khan Academy)**
What it does: Doesn't make you build a custom export — gives 3 well-named canned ones.
**Sabi mapping:** Always offer the 3 most-asked reports as one-click downloads, then a separate "Custom export" for power users.

**12. Filter checkbox row above the table ("Only show my class's courses" / "Only show assigned skills")**
What it does: Two opinionated toggles that solve 80% of filtering needs without overwhelming.
**Sabi mapping:** Above every cohort table, a row of 2-3 `<Switch>` (shadcn) toggles: "Only active learners," "Only assigned lessons," "Only learners with a guardian phone." Save defaults per user.

**13. Click column header to flip sort + click student name to drill in (Khan Academy)**
What it does: Standard but worth noting because all seven do it the same way.
**Sabi mapping:** Standard TanStack Table column sort + clickable name cell with `next/link` to `/admin/learners/[id]`.

**14. Comparison overlay: student vs. cohort average (Canvas)**
What it does: Same chart, one line for cohort average, second line for the selected student.
**Sabi mapping:** On `/admin/learners/[id]`, the mastery / activity chart has a faint cohort-average line behind the learner's line. Add a `<Combobox>` to compare against a different cohort or against the same learner one month ago (week-vs-week).

**15. "Next step" recommendation card with bold CTA (Coursera, +10% completion lift)**
What it does: One card on the dashboard: "Your next lesson: Letter D. Last attempt 3 days ago" + "Start" button.
**Sabi mapping:** For staff: "Your next attention call: Amara hasn't picked up in 4 days. [Call now]." For learner-facing parent app: "Your child's next lesson: Letter D. [Trigger call]."

**16. Completion Progress segment grid with customizable colors (Moodle)**
What it does: One small color segment per activity per learner — a wall of color you can scan at a glance to spot a row of red.
**Sabi mapping:** A heatmap component on `/admin/cohorts/[id]/heatmap` — rows = learners, columns = lessons, cells = colored squares (green = mastered, yellow = familiar, red = struggled, gray = not started). Implement with shadcn + custom CSS grid. Limit to 16 segments per row before wrapping (Moodle's default).

**17. Box-plot visualization for cohort distribution per objective (Schoology)**
What it does: Per-objective box plot showing average, high, low — with hover tooltips for exact values.
**Sabi mapping:** On the Mastery tab, per-skill mini box-plots so a board member sees not just the cohort average but the spread. Use recharts or visx.

**18. Two progress bars: one for whole certificate, one for current course (Coursera)**
What it does: Sets context at two scales — "you're 30% through the whole program, 60% through this course."
**Sabi mapping:** On learner detail: two stacked progress bars at top — "Course mastery: 42%" and "Current unit (Vowels): 80%."

**19. Voice-friendly cohort summary card for parents/board (synthesis pattern)**
What it does: Where teachers see grids, parents/board see plain-language sentences: "12 of 15 learners completed lesson 3 this week. 2 are at risk."
**Sabi mapping:** A dedicated `/admin/cohorts/[id]/summary` "Board view" — full-page sentences with one big number per card, no tables. Print-friendly Tailwind `@media print` styles. Sabi's gold-serif brand naturally lends itself to this "official report" aesthetic.

**20. "Send the right person the right message" — Canvas's Message Students Who fused with Moodle's Insight card actions**
What it does: From either a list filter or an at-risk card, one click to message.
**Sabi mapping:** Every list row and every Needs Attention card has the same action menu: Call now / Send SMS / Open profile / Snooze.

## G) Anti-patterns to avoid

1. **Five-tab navigation explosion** — Schoology (Materials / Updates / Gradebook / Mastery / Members / Analytics / Workload Planning) overwhelms first-time users. Cap Sabi at 4 primary nav items per role. Push secondary actions into menus, not tabs.

2. **Color-only encoding (failing parents printing on black/white)** — Canvas's green-circle / yellow-triangle pattern works because it's also shape-coded. Schoology's "light green vs dark green" relies purely on hue and is harder for colorblind users and printed reports. Always pair color with shape or label.

3. **"Mastery Settings" buried under a gear icon** — Schoology's "Decaying Average at 75%" is a hugely consequential setting that almost no teacher will discover. Surface mastery-calculation policy in onboarding, not a settings panel.

4. **Numeric percentages with no context** — Canvas surfaces "average course grade" as a raw percentage. Without a cohort distribution next to it, parents can't tell if 65% is good or bad. Always show a number + a context (cohort average / target / trend arrow).

5. **Real-time activity feeds with no filter** — Duolingo's right-rail log is great until you have 200 learners; then it's noise. Build the live feed with mandatory filters (this cohort only, this lesson only) and a default "pause on hover."

6. **"Click to expand" hidden by default everywhere** — Khan Academy hides per-skill detail behind a `>` chevron on every unit row. Powerful, but if everything's collapsed, first-time admins can't tell what data exists. Default expand the first 1-2 units.

7. **Predictive at-risk with no explanation** — Moodle's early Inspire model emitted flags without the reasoning, which teachers ignored. Always show "WHY this learner is at risk" alongside the flag (the Prediction details panel pattern). Sabi should always show: "Flagged because: 3 missed calls in 7 days + accuracy fell from 80% to 45%."

8. **24-hour data refresh** (Canvas) — for a real-time voice-AI product, batched analytics will feel broken. Sabi should make the cohort dashboard live (SSE/WebSocket) or near-live (60-second polling).

9. **Skill trees with hundreds of nodes** — Knewton's full knowledge graph is unreadable. Use the graph as a board-explainer overview at low zoom; use lists/tables for actual operational work.

10. **Decorative gamification on admin views** — XP, streaks, owls are right for learners but undermine credibility on a board-member view. Keep Sabi's admin chrome serious (gold serif, dense data, no confetti); keep the learner-facing pieces playful.

11. **CSV export buried in Settings** (Khan Academy) — board members will not find a download button under "Settings." Put export on every list view's header.

12. **"Message Students Who" sends through in-product inbox only** — Canvas defaults to Canvas Conversations, requiring students to log in. Sabi's outreach must default to SMS (Africa's Talking) or outbound Sabi call, not a logged-in product inbox most users won't have.

13. **Single mastery scale for the whole district** (Schoology) — over-rigid. Allow per-cohort overrides for Sabi pilots (CcHub vs. Lagos public-school cohort may need different thresholds).

14. **No "as of" timestamp** — Canvas's "data refreshes every 8 hours" is documentation-only; the UI doesn't show last-refreshed. Always render "Last updated: 14:32" on dashboards so admins trust the data.

15. **Duolingo's planned 2027 shutdown of Schools tier** — a reminder that admin/teacher tooling is a long-term commitment, not a side feature. Sabi must commit to a multi-year admin-tooling roadmap or board members will not trust it.

## H) Source URLs

Khan Academy
- https://support.khanacademy.org/hc/en-us/articles/360031052391-How-do-I-use-the-Activity-Skills-and-Mastery-tabs-on-the-Activity-overview-report
- https://support.khanacademy.org/hc/en-us/articles/5548760867853--How-do-Khan-Academy-s-Mastery-levels-work
- https://support.khanacademy.org/hc/en-us/articles/360031123551-How-can-I-view-my-students-progress-towards-their-Mastery-goals
- https://support.khanacademy.org/hc/en-us/articles/7263187791373-How-do-I-use-the-Individual-Student-Report
- https://support.khanacademy.org/hc/en-us/articles/360031129891-What-reporting-options-are-available-on-Khan-Academy-for-teachers-to-track-student-performance
- https://support.khanacademy.org/hc/en-us/articles/360031099511-What-can-I-do-from-the-classes-page
- https://support.khanacademy.org/hc/en-us/articles/10743880066957-How-do-I-download-my-students-assignment-scores-and-skills-data
- https://support.khanacademy.org/hc/en-us/articles/17720742489357-What-data-is-included-on-the-Administrator-Homepage
- https://support.khanacademy.org/hc/en-us/articles/17754502730381-How-do-I-use-the-different-Progress-reports-for-administrators
- https://support.khanacademy.org/hc/en-us/articles/17718729129741-What-reports-does-Khan-Academy-offer-to-administrators
- https://support.khanacademy.org/hc/en-us/articles/4407513378957-How-do-I-export-a-CSV-file-for-Khan-Academy-Districts-administrator-reports
- https://www.khanacademy.org/khan-for-educators/khan-for-educators-advanced-course/x2e5750eab575b791:khan-for-educators-advanced/x2e5750eab575b791:using-ka-reports-to-personalize-learning/a/review-student-progress-toward-mastery-a9
- https://www.khanacademy.org/khan-for-educators/k4e-us-demo/xb78db74671c953a7:using-assignments-on-khan-academy/xb78db74671c953a7:strategies-for-using-assignments-with-students/a/using-khan-academys-mastery-progress-reports
- https://blog.khanacademy.org/why-khan-academy-will-be-using-skills-to-proficient-to-measure-learning-outcomes/

Duolingo for Schools
- https://schools.duolingo.com/
- https://duolingoschools.zendesk.com/hc/en-us/articles/6894350549773-What-is-the-Duolingo-for-Schools-activity-log
- https://duolingoschools.zendesk.com/hc/en-us/articles/11167849068941-A-teacher-guide-to-the-new-Duolingo-for-Schools
- https://duolingoschools.zendesk.com/hc/en-us/articles/7708551934477-New-ways-to-view-student-performance
- https://duolingoschools.zendesk.com/hc/en-us/articles/6893917651469-How-do-late-assignments-work
- https://duolingoschools.zendesk.com/hc/en-us/articles/6893968429965-What-are-XP-assignments
- https://aiflowreview.com/duolingo-schools-review-2025/
- https://linguasteps.com/languages/duolingo-for-schools-explained-a-teacher-s-guide
- https://www.classcentral.com/report/duolingo-for-schools-shutting-down/
- https://design.duolingo.com/identity/color
- https://design.duolingo.com/identity/typography

Coursera
- https://medium.com/coursera-engineering/bringing-data-to-teaching-20bb77ba0c00
- https://blog.coursera.org/new-progress-tracking-features-on-coursera/
- https://blog.coursera.org/whats-new-on-coursera-dashboard-and-course-home/
- https://www.coursera.org/business/products/skillsdashboard

Canvas / Instructure
- https://learn.canvas.cornell.edu/canvas-course-analytics/
- https://teacherscollege.screenstepslive.com/a/1173150-view-weekly-online-activity-analytics-in-canvas-new-analytics
- https://community.canvaslms.com/t5/Instructor-Guide/How-do-I-send-a-message-to-all-students-based-on-specific-course/ta-p/1162
- https://community.canvaslms.com/t5/Instructor-Guide/How-do-I-view-and-download-reports-in-New-Analytics/ta-p/409936
- https://community.canvaslms.com/t5/Instructor-Guide/How-do-I-filter-columns-and-rows-in-the-Gradebook/ta-p/1016
- https://it.umn.edu/services-technologies/how-tos/canvas-arrange-columns-in-gradebook
- https://infocanvas.upenn.edu/instructors/analytics-in-canvas/
- https://www.instructure.com/resources/blog/better-together-unlocking-learning-analytics-with-canvas-lms-and-intelliboard
- https://www.instructure.com/about/brand-guide/canvas

Moodle
- https://docs.moodle.org/502/en/Tracking_progress
- https://docs.moodle.org/33/en/Learning_analytics
- https://docs.moodle.org/502/en/Completion_Progress_block
- https://docs.moodle.org/502/en/Analytics_quick_guide
- https://docs.moodle.org/en/Course_overview
- https://moodle.com/functionality-with-moodle/learning-analytics-for-moodle/
- https://edwiser.org/blog/7-best-moodle-reporting-plugins-for-learning-analytics/

Schoology / PowerSchool
- https://uc.powerschool-docs.com/en/schoology/latest/student-mastery-reporting-enterprise
- https://uc.powerschool-docs.com/en/schoology/latest/mastery-student-overview
- https://uc.powerschool-docs.com/en/schoology/latest/assessment-reports-evaluating-student-mastery-resu
- https://uc.powerschool-docs.com/en/schoology/latest/district-mastery-and-the-standards-based-gradebook
- https://uc.powerschool-docs.com/en/schoology/latest/use-exceptions-in-the-gradebook
- https://uc.powerschool-docs.com/en/schoology/latest/courses-gradebook
- https://uc.powerschool-docs.com/en/schoology/latest/custom-branding
- https://www.powerschool.com/products/classroom/learning-management/
- https://www.powerschool.com/wp-content/uploads/2025/09/PowerSchool_Brand-Guidelines_2025.pdf

Knewton
- http://www.zhanjunlang.com/resources/paper/knewton-adaptive-learning-whitepaper.pdf
- https://dev.knewton.com/
- https://dev.knewton.com/implementation/api-overview/
- https://dev.knewton.com/implementation/tracking-goal-progress/
- https://medium.com/knerd/what-are-knewtons-knowledge-graphs-f6a118acc722
- https://support.knewton.com/s/article/Monitoring-Student-Progress-in-Knewton-Alta
- https://support.knewton.com/s/article/Viewing-Mastery-Progress-in-an-Adaptive-Assignment-as-a-Student-in-Knewton-Alta
- https://support.knewton.com/en/s/article/Assignment-Mastery-in-Knewton-Alta
- https://www.wiley.com/en-us/grow/teach-learn/teacher-resources/courseware/knewton-alta/features/

Cross-reference / framing
- https://enji.ai/glossary/rag-status/ (Red-Amber-Green status convention referenced for at-risk indicators)
- https://www.solvedconsulting.com/dashboard (cohort/grade-filter pattern in K-12 dashboards)
- https://backpackinteractive.com/insights/education-dashboards-best-practices/
- https://ui.shadcn.com/docs/components/radix/data-table (Sabi tech stack: shadcn data table)


---

## Comparable 6: AI conversation review — Voiceflow, Cognigy, Botpress, OpenAI Realtime playground, Anthropic Claude Console, LangSmith, Helicone

I have enough material. Let me synthesize the audit now.

# AI conversation review — Voiceflow, Cognigy, Botpress, OpenAI Realtime playground, Anthropic Claude Console, LangSmith, Helicone

## A) Product overview (1 paragraph)

These seven tools all answer the same core question — "what actually happened in this conversation?" — but from different angles, and that variance is exactly what Sabi needs to study. **Voiceflow** and **Cognigy** are conversational-agent platforms whose admin consoles are explicitly designed for non-engineers (QA leads, operations managers, contact-center supervisors) to read transcripts, filter by business metadata, score interactions against rubrics, and bulk-evaluate retroactively. **Botpress** sits between dev tool and ops tool — channel-aware conversation lists with HITL handoff. **OpenAI's Realtime/Agents Traces dashboard** and the **Anthropic Claude Console Workbench** are developer-facing playgrounds that emphasize prompt iteration, side-by-side comparison, and raw request/response inspection, with eval-tool extensions for structured scoring. **LangSmith** is the most thread-aware of the developer tools — it treats multi-turn conversations as first-class objects with three view modes (Messages, Turns, Details) and Insights Agent for clustering thousands of conversations into usage patterns. **Helicone** is a proxy-first observability tool that flips the request log into a session tree, with a redesigned Request Drawer that lets reviewers ratchet through requests without closing the panel. Across all seven, three patterns recur: (1) a filterable conversation list as the entry point, (2) a right-side drawer or split-pane detail view with role-tagged messages plus a metadata panel, (3) inline drill-down from any turn into the raw prompt/response and tool calls. The board-facing console Sabi is redesigning needs all three, plus the audio-replay primitive that none of these chat-text tools have native equivalents for.

## B) Navigation + topbar pattern (detailed)

**Voiceflow** — Left rail with project switcher at top, then primary nav: Design, Knowledge Base, Transcripts, Evaluations, Analytics, Settings. Transcripts is the tab E4E should care most about because it is the operational review surface. Top bar carries environment toggle (Development/Production), date range, share/export, account avatar.

**Cognigy Insights** — Left rail organized into three meta-groups: Dashboards (Overview, Engagement, NLU Performance), Explorers (Step Explorer, Transcript Explorer, Message Explorer), and Tools (Intent Trainer, Conversation Analyzer). Top bar has a horizontal filter bar that can be toggled hide/show via icon in upper-right; "Reset" appears when filters are active. Inside an explorer, the layout is split-pane: filter bar (top), session list (left), transcript detail (right).

**Botpress** — Left sidebar shows the bot dashboard pattern: Conversations, HITL, Events, Logs, Webchat, Analytics, plus Studio link. Inside Studio, the right sidebar is the inspector for whichever node is selected (instructions, attached actions). Conversations tab is filter-on-top, list-below.

**OpenAI Platform Traces** — Top-level dashboard nav: Chat, Realtime, Logs → Traces, Evals, Files, Assistants, Storage, Usage. Inside Logs/Traces you select a workflow, then a trace list, then a trace detail with span tree.

**Anthropic Claude Console** — Top navigation: Dashboard, Workbench, Evaluate (tab inside Workbench), Logs, Usage, Limits, Billing, API Keys. The Workbench itself has an inner topbar with model selector dropdown, parameter settings gear, "Run" button, "Code" toggle (export request as snippet), Save/Share, and an "Open in Workbench" template loader. The Evaluate tab adds: + Add Row, Generate Test Case (with dropdown arrow → Show generation logic), Generate Prompt button, version selector, and side-by-side comparison toggle.

**LangSmith** — Left rail: Tracing Projects, Datasets & Experiments, Prompts, Annotation Queues, Deployments, Settings. Inside a project: tabs for Runs, Threads, Monitor, Setup, Rules. Threads tab has "Add filter" button, "Save view" option, and three view-mode buttons at top with keyboard shortcuts: **M** (Messages), **T** (Turns), **D** (Details). Top-right of project is "+ New" which surfaces "New Insights Report" among other actions.

**Helicone** — Left sidebar grouped into sections: top group is Dashboard, Requests, Segments, Sessions, Properties, Users, Cache, HQL; an "Improve" group with Prompts, Datasets, Playground; a "Monitor" group with Rate Limits, Alerts; and a bottom group with Docs, Support, Credits ($0.00), Configure. Top bar carries the time-range picker ("Pick a date and time" dropdown), Filter chip area, "Start Live" toggle for real-time refresh (1-2 sec intervals), and a unified filter component with URL sharing and persistent filters across pages.

## C) List/index pages — columns, filters, sort, search, density, pagination, bulk actions, empty state

### Voiceflow Transcripts table
**Default columns**: Date, Platform, User ID, Environment, Credits consumed, Duration. **Optional via table settings icon**: evaluation result columns (per evaluation), custom properties (defined via Set step in workflows under "Properties to set"). **Filter chips on top**: date range, platform, user ID, environment, credits consumed, duration, evaluation results, custom properties. **Column controls**: Table settings icon → add/remove default fields, evaluation results, and custom properties. **Bulk actions**: select multiple transcripts then "Batch run evaluation" button (lets you retroactively score historical conversations and pick which evals to apply). **Settings toggles** under transcript settings: "Save tests to transcripts" and "Save transcripts with no interaction".

### Cognigy Transcript Explorer session list
**Columns**: Endpoint (channel like Cognigy Webchat), Session ID (with copy button), User ID (with copy button), Messages (total count), Last Message (timestamp), Analysis (Conversation Analyzer status). All columns sort via ascending/descending arrow icons. **Local filters** (revealed by "more filters"): Message Rating (Positive/None/Negative), Source (AI Agent/User/Agent Messages), Goals Completed, Flow (specific flow selection), Contains Step (analytic step), Message count From, Message count To. **Global filters** in the top filter bar with a Reset button. **Search**: upper-right field filters by message text, Session ID, or User ID with real-time list updates.

### Cognigy Message Explorer
Initial view shows "Top Messages" — frequently sent messages in descending order with occurrence counts during the selected timeframe (default: Last 7 Days). Local filters add: Message Rating, Source, Flow, "Show payload data" checkbox, "Negate" toggle for exclusion logic. Empty state: top messages list with counts even when no filter applied.

### Helicone Requests page
**Columns** (compact rows for more density): timestamp, model, latency, cost, input tokens, output tokens, status, user, session. **Filter UI** (March 2025 unified filter component): persistent across pages, URL-shareable, includes country-based filtering (July 2025), automatic timezone detection showing requests in local timezone. **Sorting**: server-side backend sorting by column. **Drawer pattern**: a redesigned Request Drawer with quick toggle between requests without closing the drawer for faster review and comparison. Loading: skeleton UI matching content structure for fast perceived performance (6x render improvement on large tables).

### LangSmith threads table
**Columns**: thread identification, first input, last output, start times, turn count, latency (P50/P99), token usage, cost, feedback score. **Add filter** button creates custom filters; **Save view** preserves frequently used configurations. "Thread filters look through all runs and surface a thread if at least 1 run matches" — important semantic for Sabi.

### LangSmith runs table (inside a project)
Run name column (clickable to open trace), latency, status, total tokens, cost, time, tags, feedback. Filter by trace name, model, status, latency, time range, feedback, tags. Search across input/output content.

### Anthropic Console Logs
Per Anthropic Workbench docs, the refreshed Workbench does NOT store prompts/conversations on Anthropic servers (drafts live in your browser); the Logs view at the Console level does show request logs scoped to your API key with timestamp, model, input/output token counts, and cost. No bulk actions on logs.

### Botpress Conversations
Filter by channel, status, date range. Inspect individual bot interactions across deployment channels. HITL tab adds "assign to me" / "assign to teammate" / "resolve" / "pass back to bot" actions per conversation. Events tab filters by event type, conversation ID, user ID, or message ID.

### Empty states
Helicone's onboarding shows realistic mock data demonstrating request volumes, cost patterns, latency samples across multiple LLM providers, error distributions, and temporal trends — the dashboard is never literally empty even for a fresh account. Voiceflow shows zero-state copy directing users to install the agent / start a conversation.

## D) Detail/drawer pages — layout, sections, audio player, transcript, drilldown

### Voiceflow transcript detail
Split layout: **right side** shows the full conversation (chat-style, user/agent role tags); **left side** shows metadata panel (Date, User ID, Platform, Duration, Credits consumed) and a "Previous conversations" link to user history. **Evaluation results panel** displays below metadata — each evaluation shows its result plus model reasoning explaining how the score was determined. **Logs section at the bottom** is the deepest debug surface: a timestamped breakdown of every step including inputs, outputs, warnings, debug information, and credit consumption per step. This is the dev-grade view embedded under the ops-grade view — same page, scroll down.

### Cognigy session transcript viewer
Right panel shows the full transcript when a session is selected. **Right-click context menu on a message** opens: Open Flow, Open in Message Explorer, Create Scenario, Create Playbook, Create Playbook with Assertions. **Debug mode toggle** in the transcript window reveals intent triggers, slot fills, connection events, and xApp details. **Upper-right ellipsis menu** → Evaluation Details (detected topics, basic analysis, custom evaluations). **User-menu icon upper-left** opens session details: Session ID, First/Last Message timestamps, User/AI Agent/Agent Message Counts, Flow Name, user feedback ratings with comments. **Contact profile expansion** shows First Name, Last Name, Email, Gender, Age, Birthday, Location, GDPR acceptance status, Tasks Completed records.

### Cognigy Message Explorer drill-down
Selecting a message splits the page into **three columns**: Prior (preceding message context), Current Message (with X-icon for return navigation), Following (subsequent message context). Each column has blue scroll bars when multiple messages are present. This is brilliant for understanding "what made the agent say that?" without leaving the message view.

### Helicone Sessions detail
Hierarchical visualization of agent workflows. Sessions organize requests using path-based structure: `/abstract`, `/abstract/outline`, `/abstract/outline/lesson-1` represent parent-child relationships (paths create the hierarchy within your session, showing how requests relate to each other). Tracks LLM calls (OpenAI, Anthropic, etc.), vector database queries and embeddings, tool calls and function executions, and custom logged requests in one unified view. Session-level metrics show average latency and total cost.

### Helicone Request Drawer
Redesigned to allow quick toggle between requests without closing the drawer. Shows request body, response body, key metrics in compact format. Reviewers can ratchet through a list without ever returning to the parent table.

### LangSmith trace detail
**Two-panel layout**: left panel shows full run tree (e.g., the `assistant` function with the `get_context` tool call and the OpenAI call nested inside it); right panel is the inspector showing nested spans with parent/child relationships. **Tabs in detail view**: Messages tab (conversation as sent to model), Details tab (complete run hierarchy with all nested operations). Each node in the tree shows total usage for that subtree plus per-child token/cost breakdown. Hover cost section → tooltip with input/output/other breakdown. From any ChatPromptTemplate child run: **"Open in Playground"** button moves you to interactive editing of that exact step.

### LangSmith Threads detail
Three view modes (M/T/D shortcuts):
- **Messages view (beta)**: chat-style thread with user and assistant messages, tool calls, subagent activity inline
- **Turns view**: each turn rendered as an expandable card; **per-turn metadata visible at a glance**
- **Details view**: drill into a specific run to inspect inputs, outputs, metadata, timing, errors, and child runs
**Right panel**: stats for the thread — turn count, first and last start times, P50/P99 latency, cost breakdown by input/output tokens. Feedback column in the threads table is clickable from Messages view via the "LLM call" link in turn metadata.

### Anthropic Workbench
Three-zone layout: **left** = system prompt textarea (always visible), **center** = message list with user/assistant role tags and a "Run" button at bottom, **right** = parameters panel (model selector, temperature, max tokens, top-p, top-k, extended thinking toggle, tools definitions). Response panel shows full message structure, stop reason, and usage (input tokens, output tokens, cached tokens). **Code toggle** in top bar exports current request as a code snippet (curl, Python, TypeScript). **Open in Workbench** template loader brings example prompts in pre-filled.

### Audio player
None of the seven tools have a native audio-replay UI as the centerpiece — even Voiceflow's "voice and chat" transcripts are text-first. The Conversations tab in Voiceflow exposes audio playback only when the conversation came through a voice channel; the audio appears inline with the transcript. **For Sabi, this is white space**: a properly designed waveform player with per-turn anchors is genuinely original work.

## E) Visual language — colors, typography, density, iconography, motion, brand voice

**Helicone** — Clean utilitarian: black/white with cyan accent, supports light and dark mode (skeleton loaders adapt to both). Built on Tremor chart library (StyledAreaChart, AreaChart, BarChart, BarList, QuantilesGraph). Layout system uses react-grid-layout with responsive breakpoints (lg: 12 cols at 1200px, md: 12 cols at 996px, sm: 12 cols at 600px, xs: 4 cols at 360px, xxs: 2 cols), row height fixed at 96px, panels bounded but non-draggable. Dense rows on Requests table are deliberate ("compact row design" for "more data visible at a glance").

**LangSmith** — Modern developer-tool aesthetic, dark mode default, tight monospaced fonts for trace/JSON content, sans-serif for chrome. Different run types trigger different icons or groupings in the trace tree (e.g., `retriever` icon vs `prompt` icon vs `tool` icon vs `llm` icon). Color-codes spans by type: prompts purple-ish, retrievers blue, tool calls green-ish, errors red. Tailwind 4.x + shadcn/ui supported in their generative UI features, suggesting their design system aligns with those primitives.

**Voiceflow** — White card-based design, purple primary brand color, generous spacing. Chat-style message bubbles in transcript view (user right-aligned, agent left-aligned). Filter chips are rounded pills. Evaluation results shown as colored badges (green pass, red fail, numeric scores in pill format). Audio playback uses a horizontal waveform when present.

**Cognigy** — Enterprise dense; blue/grey palette, more form-driven than card-driven. Heavy use of icons for context menu actions. Right-click context menus are a defining interaction pattern (most other tools avoid them). Three-column drill-down in Message Explorer with blue scroll bars when columns overflow.

**Botpress** — Dark navy/black sidebar, light canvas. Studio uses node-based flow editor; conversation/log views are more conventional tables. Card inspector UI moved to right panel (was previously a modal that obstructed workflow).

**Anthropic Workbench** — Anthropic's signature warm sand/orange (the "orange 'Generate Prompt' button at the bottom" mentioned in eval-tool docs); serif headings, sans-serif body. Generous whitespace. Designed to look like a writing tool more than an admin tool — fits the prompt-engineering audience.

**OpenAI platform** — Clean black/white with green accent; tight typography; treats the dashboard as a generic developer surface (less personality than Anthropic Console).

**Motion** — Helicone uses skeleton loaders that match content structure (light + dark mode aware). LangSmith uses subtle expand/collapse on trace tree nodes. Most tools use the React Spring / Framer Motion pattern of fading content in. None lean heavily on animation — these are reference tools and speed of comprehension wins over delight.

## F) Specific patterns Sabi should copy

1. **Three view modes for the same conversation, switched by keyboard shortcut (M/T/D)** — LangSmith. Messages view is chat-style for product/board readers, Turns view is per-turn cards with latency/tokens/cost visible at a glance for ops review, Details view is the raw run tree for debugging. **Sabi mapping**: The board needs Messages view ("did Sabi sound right?"); ops needs Turns view ("how long did each turn take, did STT or TTS run hot?"); engineering needs Details view (raw Whisper output, Claude prompt, Chatterbox audio file URL). Implement with a `<Tabs>` from shadcn/ui at the top of `/admin/calls/[callId]` with hotkeys via `useHotkeys`. Lives at the conversation detail page.

2. **Right-side drawer with "ratchet" navigation between rows without closing** — Helicone Request Drawer. Reviewer hits arrow keys (or up/down buttons in drawer header) to step through the filtered list. **Sabi mapping**: When a coordinator is auditing 20 calls flagged for review, they should never have to go back to the list. Use shadcn/ui `<Sheet>` with prev/next buttons wired to the parent table's filtered state. Lives at the calls index page.

3. **Inline metadata panel left, transcript right, expandable Logs section at bottom of same page** — Voiceflow. The metadata panel doubles as the place where evaluation results render with reasoning. **Sabi mapping**: Left = caller phone (last 4), call duration, region detected, lesson level, total cost (STT + Claude + TTS + AT minutes), Sabi version. Right = transcript with role tags and audio anchors. Bottom = collapsible "Pipeline Logs" with timestamped Whisper/Claude/Chatterbox events including timing, token count, and any guardrail trips. Lives at `/admin/calls/[callId]`.

4. **Filter chips on top of the table with a "Saved views" dropdown** — Voiceflow + LangSmith. Filters persist across navigation and are URL-shareable. **Sabi mapping**: Saved views like "Lagos region, English, flagged", "Pidgin, lesson L4, last 24h", "Calls with guardrail trip". URL-shareable means coordinators can paste a link in WhatsApp/Slack and the recipient sees the same filter. Build with `nuqs` for URL state + a `<Combobox>` for the saved-views dropdown. Lives above the calls table.

5. **Three-column drill-down for "what came before and after"** — Cognigy Message Explorer. Clicking a turn opens Prior / Current / Following columns side by side, with the current turn pinned in the middle. **Sabi mapping**: When a reviewer flags a Sabi response as wrong, they need to instantly see what the child said before it and how Sabi recovered after. This avoids "open transcript, scroll, lose context" cycles. Implement as a triple-pane drawer or a modal with three sticky columns. Lives in the transcript view, triggered by clicking any turn.

6. **Per-turn cards showing latency, tokens, cost, eval score at a glance** — LangSmith Turns view. **Sabi mapping**: For a voice call, each card shows: turn timestamp, child utterance (STT text + confidence), Sabi response (text + TTS file), per-turn latency (STT ms + Claude ms + TTS ms — three components), per-turn cost (in fractional pennies, broken down), eval flag (e.g., "stayed in scope ✓", "guardrail trip ✗"). Use `<Card>` with a grid of small stat blocks. Lives in the Turns view tab.

7. **Right-click context menu on any message → "Open Flow / Open in Message Explorer / Create Scenario / Create Playbook / Create Playbook with Assertions"** — Cognigy. **Sabi mapping**: Right-click on any Sabi turn → "Replay this exact prompt", "Add to test set", "Fork conversation from here", "Send to curriculum team for review", "Create regression test". Lives inline in any transcript. Implement with shadcn/ui `<ContextMenu>`.

8. **Bulk evaluation: select multiple transcripts → "Batch run evaluation" → pick which evals to apply** — Voiceflow. **Sabi mapping**: Coordinator selects 200 yesterday's calls, clicks "Batch run guardrails check" or "Batch run pronunciation rubric", and the eval runs async with progress UI. Critical for retroactive QA when you ship a new safety rule and want to backfill. Lives above the calls table with a sticky action bar that appears on selection.

9. **Built-in eval rubric types: Rating (1-5), Binary (pass/fail), Options (categorical), Text (free-form)** — Voiceflow eval creation form. With per-eval metadata: Name, Model dropdown (default GPT-4o mini), Metric type, Criteria text area, "Test on last transcript" preview button. **Sabi mapping**: Sabi-specific rubrics — "Did Sabi stay in tutor scope?" (binary), "Pronunciation accuracy" (1-5), "Cultural appropriateness" (binary), "Lesson alignment" (1-5), "Guardrail behavior" (options: Trip-correct, Trip-false-positive, No-trip-needed, Missed-trip). Save as templates so coordinators don't redefine each time. Lives at `/admin/evals` with a "Test on last call" button mirroring Voiceflow.

10. **Evaluation result rendered with model reasoning, not just a score** — Voiceflow. Every eval shows score AND why. **Sabi mapping**: Critical for board trust. Don't display "Pronunciation: 4/5". Display "Pronunciation: 4/5 — Sabi correctly pronounced 'photosynthesis' but elongated the second syllable in 'Yoruba'. Reasoning generated by Claude Sonnet against rubric v3." Use a `<Collapsible>` from shadcn/ui so the reasoning is one click away but not visually noisy by default.

11. **Insights Agent for clustering thousands of conversations into patterns** — LangSmith. Natural-language question → "Group by usage patterns" or "Group by poor interactions" → 15-min processing → executive summary with percentages and clickable trace references (#1, #2, #3) → top-level categories with distribution bars → subcategories → traces table per cluster → "Add to dataset" / "Add to annotation queue" actions. **Sabi mapping**: Eventually critical. When Sabi handles 10,000 calls/month, no one reads them all. Coordinator types "What are the most common confusions with the L3 lesson on subtraction?" → gets clustered output. Phase 2 feature; for now, design the empty state so the slot exists. Lives at `/admin/insights/new`.

12. **Open in Playground / Fork conversation from a specific turn** — LangSmith and Helicone. **Sabi mapping**: Critical for curriculum debugging. From any Sabi turn, "Replay with edits" loads the exact system prompt, conversation history up to that point, model params, and tool configs into an editable surface. Reviewer changes the prompt or the rubric and re-runs. The new run is logged under the same session-name with a `replay-` prefix so it shows up grouped (Helicone's pattern: reusing session-name, session-path, prompt-id and request path so replayed sessions are logged under the same session metadata). Lives at a `/admin/calls/[callId]/replay` route.

13. **Conversation Analyzer-style category scoring: predefined criteria sets + up to 10 custom criteria** — Cognigy. Four predefined dimensions (Customer Sentiment, Containment & Success, AI Behavior Quality, AI Agent Experience Quality) plus user-defined custom. **Sabi mapping**: Predefined = (Safety, Pedagogical correctness, Engagement, Pronunciation). Custom = anything the board wants this quarter (e.g., "Did Sabi correctly handle the Ramadan greeting?"). Show as a horizontal "scorecard" strip above the transcript with one tile per dimension.

14. **Topic discovery dashboard with rising-issue spike detection** — Cognigy. Automatically identified customer discussion clusters without manual configuration, AI-powered topic suggestions, conversation count per topic, spike highlights. **Sabi mapping**: "Today: 47 callers asked about 'multiplication tables' (↑320% vs 7-day avg)". Lets the board see what kids actually want to learn without reading transcripts. Lives at `/admin/topics` as a dashboard widget.

15. **Cost breakdown panel with input/output/other tooltip on hover** — LangSmith. **Sabi mapping**: Per-call cost panel showing STT (Whisper API minutes × rate), Claude (input tokens × rate + output tokens × rate, plus cached tokens line), TTS (Chatterbox GPU seconds × rate or ElevenLabs chars × rate), AT (toll-free minutes × rate). Hover any sub-cost for the breakdown. Critical for grant reporting — every CcHub/UNICEF check-in asks "what did this cost".

16. **Skeleton loaders that match content structure, light + dark aware** — Helicone. **Sabi mapping**: Build skeleton variants of the call card, metadata panel, and transcript bubbles. With 6x perceived-performance improvement on large tables, this is cheap engineering effort with high ops payoff.

17. **Live mode toggle for real-time refresh** — Helicone "Start Live" with 1-2s intervals. **Sabi mapping**: Coordinators monitoring an active campaign want a live tail of calls coming in. Implement with Supabase realtime subscriptions on the calls table. Lives as a toggle next to the time-range picker.

18. **5-point quality grading scale on eval rows** — Anthropic Console eval tool. **Sabi mapping**: For human-in-the-loop annotation, 5-point is the right granularity — finer than binary but not so fine that annotators waste time deciding 6 vs 7. Use a row of 5 clickable circles. Lives in the annotation queue page.

19. **Side-by-side prompt comparison** — Anthropic Console. **Sabi mapping**: When testing two versions of Sabi's system prompt, render two transcript columns side by side, scrollable independently, with diff highlights on the model output. Lives at `/admin/prompts/compare`.

20. **"Generate Test Case" with editable generation logic dropdown** — Anthropic Console eval tool. **Sabi mapping**: Coordinator clicks "Generate Test Case" → Claude generates a plausible child utterance based on edited generation logic (e.g., "Generate utterances from a 7-year-old in Lagos asking about division, varying levels of pidgin/English mixing"). Lives in the test set builder.

## G) Anti-patterns to avoid

- **Cognigy's right-click-only context menu for primary actions** is a discoverability disaster on the open web — board members will never right-click to find "Create Playbook". Always expose right-click actions as a visible "..." kebab menu too.
- **Anthropic Workbench's no-persistence default** (drafts live in browser only) is fine for a developer playground but **catastrophic for an admin console**. Sabi's reviewers WILL lose work if the browser closes. Persist every annotation to Supabase the moment it's typed.
- **Helicone's "1-2 second live polling"** sounds good but if you actually use it on the Requests page, the table jitters as rows shift. Better: a "(3 new) Click to load" pill at the top, like Twitter.
- **Voiceflow's "Logs section at the bottom"** can require deep scroll on long conversations. Better: keep Logs in a sticky right rail or as a permanently-pinned bottom drawer with its own scroll.
- **LangSmith's three view modes** with M/T/D shortcuts are powerful but discoverability is poor — most users don't notice them until shown. Add a one-time tooltip-tour on first visit.
- **Cognigy's contact profile fields (Gender, Age, Birthday, GDPR acceptance)** assume a level of identification that is wrong for Sabi — these are children, often anonymous, often phone-shared. Do NOT replicate this schema. Use anonymized callerHash + region detection only.
- **Botpress's HITL "pass back to bot"** button is single-click; one misclick and the human agent loses the conversation. For Sabi, any escalation back to autonomous mode needs a confirmation modal.
- **OpenAI Playground's lack of saved conversation history** in chat mode means reviewers can't return to a previous experiment — replicate LangSmith's persistent threads instead.
- **Cognigy's "deprecated as of 2026.4.0, removal in 2026.17.0"** notice ON the Message Explorer page is jarring for users currently relying on it. Do not ship features without a deprecation plan and a clearly-named successor.
- **Helicone's hard-coded fixed row height of 96px** on dashboard panels is fine for charts but breaks for variable-content cards. Make dashboard tiles content-driven heights with a min-height floor.
- **Generic "AI-powered insights" empty states** that show fake mock data (Helicone onboarding pattern) can confuse non-developer board members into thinking real activity has happened. Use clearly-labeled "Sample data" watermarks or honest zero states.
- **Dense table rows with 9+ columns at default** (Helicone Requests) overwhelm non-technical users. Default Sabi tables to 4-5 high-signal columns with "Customize columns" as the escape hatch.

## H) Source URLs

- [Voiceflow Transcripts documentation](https://docs.voiceflow.com/docs/transcripts)
- [Voiceflow Transcripts (measure) documentation](https://docs.voiceflow.com/documentation/measure/transcripts)
- [Voiceflow Evaluations documentation](https://docs.voiceflow.com/documentation/measure/evaluations)
- [Voiceflow Analytics](https://docs.voiceflow.com/docs/analytics)
- [Voiceflow Test Platform (Experimental)](https://docs.voiceflow.com/docs/voiceflow-test-platform)
- [Cognigy Transcript Explorer](https://docs.cognigy.com/insights/explorers/transcript)
- [Cognigy Message Explorer](https://docs.cognigy.com/insights/explorers/message)
- [Cognigy Conversation Analyzer product update](https://www.cognigy.com/product-updates/conversation-analyzer-automated-quality-evaluation-for-enterprise-ai-agents)
- [Cognigy Conversation Workflow](https://docs.cognigy.com/live-agent/conversation/conversation-workflow/)
- [Cognigy Insights](https://docs.cognigy.com/ai/analyze/insights/)
- [Botpress Conversations academy lesson](https://botpress.com/en/academy-lesson/conversations)
- [Botpress Logs academy lesson](https://botpress.com/academy-lesson/logs)
- [Botpress Events academy lesson](https://botpress.com/academy-lesson/events)
- [Botpress Conversation History API](https://www.botpress.com/docs/learn/guides/advanced/exporting-data/getting-the-conversation-history-from-within-your-bot)
- [Botpress Changelog](https://botpress.com/docs/changelog)
- [OpenAI Realtime conversations](https://platform.openai.com/docs/guides/realtime-conversations)
- [OpenAI Agents SDK Tracing](https://openai.github.io/openai-agents-python/tracing/)
- [OpenAI Trace grading](https://developers.openai.com/api/docs/guides/trace-grading)
- [OpenAI Traces dashboard](https://platform.openai.com/traces)
- [Anthropic Workbench help center](https://support.claude.com/en/articles/8606378-how-do-i-use-the-workbench)
- [Anthropic Console Evaluation Tool](https://platform.claude.com/docs/en/docs/test-and-evaluate/eval-tool)
- [Anthropic Console news post](https://www.anthropic.com/news/upgraded-anthropic-console)
- [Anthropic Prompt Improver news post](https://www.anthropic.com/news/prompt-improver)
- [Anthropic Evaluate Prompts news post](https://www.anthropic.com/news/evaluate-prompts)
- [LangSmith Threads documentation](https://docs.langchain.com/langsmith/threads)
- [LangSmith Insights documentation](https://docs.langchain.com/langsmith/insights)
- [LangSmith Cost tracking](https://docs.langchain.com/langsmith/cost-tracking)
- [LangSmith Observability quickstart](https://docs.langchain.com/langsmith/observability-quickstart)
- [LangChain Insights Agent + Multi-turn Evals blog](https://www.langchain.com/blog/insights-agent-multiturn-evals-langsmith)
- [LangSmith Playground edit-in-playground cookbook](https://github.com/langchain-ai/langsmith-cookbook/blob/main/hub-examples/runnable-prompt/edit-in-playground.ipynb)
- [LangSmith Run evaluation from prompt playground](https://docs.langchain.com/langsmith/run-evaluation-from-prompt-playground)
- [LangSmith tracing deep dive](https://medium.com/@aviadr1/langsmith-tracing-deep-dive-beyond-the-docs-75016c91f747)
- [Helicone Sessions documentation](https://docs.helicone.ai/features/sessions)
- [Helicone replaying LLM sessions blog](https://www.helicone.ai/blog/replaying-llm-sessions)
- [Helicone Dashboard live](https://us.helicone.ai/dashboard)
- [Helicone Dashboard & Analytics views (DeepWiki)](https://deepwiki.com/Helicone/helicone/5.2-dashboard-and-analytics-views)
- [Helicone Changelog](https://www.helicone.ai/changelog)
- [Helicone Header Directory](https://docs.helicone.ai/helicone-headers/header-directory)
- [Helicone User requests guide](https://docs.helicone.ai/use-cases/getting-user-requests)
- [shadcn/ui Data Table](https://ui.shadcn.com/docs/components/radix/data-table)


---

## Comparable 7: Modern ops consoles — Vercel, Linear, PlanetScale, Stripe

I have comprehensive primary-source data. Now let me synthesize the deep audit.

---

# Modern ops consoles — Vercel, Linear, PlanetScale, Stripe

## A) Product overview (1 paragraph)

These four consoles are the gold standard for operator-facing admin tooling on the web today, and each one earned that status by solving a different problem that Sabi's board-facing admin also has to solve. **Vercel** (Geist design system; relaunched Feb 2026) is a deployment and observability console for engineers — its dashboard is a list/index of projects and deployments, with a runtime-logs view that is structurally almost identical to what Sabi needs for a "calls" view (left filter rail + chronological main feed + right detail drawer). **Linear** is the engineering-team workflow console — it set the modern bar for keyboard-first navigation, command palette (Cmd-K), inbox/triage queues, and minimum-chrome visual hierarchy ("don't compete for attention you haven't earned"). **PlanetScale** is the database ops console — its branch/deploy-request UI is the canonical example of operational diff-and-approve workflows, and its Query Insights view is a textbook case of a metrics-table-with-drilldown that Sabi can lift directly for a "lessons performance" view. **Stripe** is the financial ops console — it owns the canonical pattern for the topbar environment indicator (test mode = orange, live = blue), search-as-command-bar with rich operators (`is:`, `amount:>`, `created:<`, etc.), and a payment-detail drilldown page that is structurally what a "call detail" page should look like. Sabi's stack (Next.js 16 + Tailwind v4 + Clerk + shadcn/ui) maps cleanly onto all four because shadcn/ui is itself a near-clone of Vercel's Geist primitives and supports every component these consoles use.

---

## B) Navigation + topbar pattern (detailed)

### Vercel (post-Feb-2026 redesign)

**Topbar (left to right):**
- Vercel logo (left).
- Breadcrumb trail with slash separators: `Team / Project / Section` — clicking any segment navigates; each segment has a dropdown chevron so you can jump sideways inside that scope (e.g. switch projects without leaving the deployments tab).
- Project filter: "projects as filters so you can switch between team and project versions of the same page in one click" — meaning the topbar's project breadcrumb segment turns into a scope toggle.
- Center: empty (intentional whitespace).
- Right: command palette trigger (⌘K), feedback, help/docs, notifications bell, user avatar menu.

**Sidebar (the redesigned chrome):**
- "Horizontal tabs moved to a resizable sidebar that can be hidden when not needed."
- "Unified sidebar navigation with consistent links across team and project levels" — meaning the sidebar's item set is the same whether you're at team scope or project scope; only the data underneath changes.
- "Navigation items prioritized the most common developer workflows" — Projects, Deployments, Analytics, Speed Insights, Logs, Observability, Storage, Firewall, Settings.
- Resizable width; can be fully hidden.
- Mobile: replaced by a "floating bottom bar optimized for one-handed use."

**Command palette (⌘K, also ⌘ Shift K when the deployment itself has a ⌘K palette to avoid collision):**
- Three categories: **Navigation**, **Actions**, **Help**.
- Fuzzy search with typo tolerance and partial matching.
- Recent commands surface at top.
- Each command shows its own keyboard shortcut on the right.
- Capabilities: navigate to specific Projects or Deployments inside a project, search docs, invite team members, create new Projects from Git or Templates.

### Linear

**Top chrome ("inverted L-shape"):**
- Workspace switcher + workspace icon at top of sidebar (not in a separate topbar).
- Tab bar (desktop app): compact, rounded corners, smaller icons/text, icon-only pills for the first items, each tab has its own history stack, pinned tabs persist across sessions, right-click for context menu, ⌘W to close, bracket keys `]` and `[` to open/close sidebars (fixed for Nordic keyboards).
- Header per view: filters, sort, view options, "+ New issue" (`C` shortcut), display toggle.

**Sidebar:**
- Workspace header (workspace name + avatar).
- **Inbox** (`G I`) — global queue with unread count badge that the user can hide if desired.
- **My Issues** (`G M`).
- **Active Cycle** (`G V`).
- **Backlog** (`G B`).
- Favorites (`O F`), Projects (`O P`), Cycles (`O C`), Views, Documents (`O T`).
- **Per team:** team name, then nested: Triage (`G T`), Issues, Cycles, Projects, Views, Docs.
- Reviews tab with focus-ordered notifications (added recently, prioritizes work closest to shipping).
- Team icons (no longer have colored backgrounds — the team identifier alone).
- Dimmed compared to main content area: "Don't compete for attention you haven't earned" — smaller icons, muted inactive text, increased vertical padding, overall brightness reduced.
- Borders rounded; separators reduced in count and contrast.

**Command palette (⌘K):**
- Create issues, search anything (now includes past agent chat conversations), change views, run any action, paste a GitHub PR URL to open it inside Linear.
- Full keyboard map: `?` to see all shortcuts. Key ones: `C` create, `X` select, `Shift+↑/↓` multi-select, `Esc` back, `G` then letter for navigation, `J`/`K` to scroll, `U` mark read, `H` snooze, `Shift S` unsubscribe, `Backspace` delete, `Shift Backspace` delete all read.

### PlanetScale

**Top chrome:**
- Logo / org switcher (left).
- Breadcrumb: `Organization / Database / Branch`.
- Branch selector dropdown is prominent because it is the operational primitive — like environment switching in Stripe.
- Region badge (Production branches display region next to table sizes).
- Web Console session button (one-click open SQL console for the current branch).
- Right: notifications, user avatar.

**Sidebar / page tabs:**
- Per-database tabs (page-level navigation, not sidebar): Overview, **Branches**, Deploy requests, **Console**, **Insights**, Backups, Audit log, Settings, Integrations.
- Per-branch sub-nav: Schema (with collapsible/searchable table list), Data (web console), Insights, Deploy requests (sidebar within branch view shows the deploy request you can open from a development branch), Backups, Settings.

### Stripe

**Topbar (the canonical reference):**
- Stripe logo + account/organization picker (left).
- **Test/Live mode toggle:** "always visible regardless of which page you're on." Pill or segmented switch labeled "Test mode" / "Live mode". When test mode is enabled, an **orange banner** persists; live mode uses a **blue color scheme**. Many pages render a notification box and disable live-mode settings in the test sandbox.
- **Global search bar** in the center/right — see Section C below.
- Right: developers shortcut, help center, notifications bell, account menu (avatar).

**Sidebar (post-2024 simplification):**
- **Section 1 (core resources):** Home, Balances, Transactions, Customers, Product catalog.
- **Shortcuts section:** pinned pages + recently visited pages. After you visit any Products page, it appears in Shortcuts; you click the pin icon to keep it. This is Stripe's solution to the "huge product surface, only 5 things you use daily" problem.
- **Products section:** Connect (connected accounts), Payments (card auth rates, fraud, dispute, Radar, payment links, Terminal), Billing (invoices, subscriptions, discounts, revenue reports), Reporting (transactions export, custom reports, financial reports, Sigma SQL, data management, revenue recognition).
- **More button:** Workflows, Tax, Identity, Atlas, Issuing, Financial connections, Capital, Climate.
- **Workbench** as a floating taskbar pane (see Section D).
- Help shortcut: `?` opens keyboard shortcuts.

### Twilio Paste (reference for telephony consoles)

- Topbar with three zones: left = account/workspace switcher; center = In-Page Navigation (product features like Messaging, Voice, Serverless); right = Search, Product Switcher, Support Menu, User Dialog, Status Menu.
- Sidebar: Header (product logo + label), hierarchical NavigationDisclosure for collapsible sections, Separator between groups, Footer (collapse button), max 3 levels of nesting.
- Two wrapper modes: `SidebarPushContentWrapper` (content shifts when sidebar opens) vs `SidebarOverlayContentWrapper` (overlay).

---

## C) List/index pages — columns, filters, sort, search, density, pagination, bulk actions, empty state

### Vercel Runtime Logs (the closest analog to a Sabi "calls" list)

**Layout:** Left filter rail (sidebar), main center table (one row per request), right detail drawer (when a row is clicked).

**Columns visible per row:** execution timestamp, domain name, HTTP status, function type, RequestId. Severity color coding: 4xx = amber "Warning", 5xx = red "Error", everything else = info.

**Filters in the left rail (every Sabi-relevant filter type is here):**
- **Timeline:** past hour, last 3 days, custom timespan, plus a **Live mode** option for real-time tailing.
- **Level:** Warning, Error, Fatal (and Info implicit).
- **Route:** route pattern (e.g. `/blog/[slug]`).
- **Host:** domain/subdomain with sub-search "Search hosts...".
- **Deployment:** filter by deployment URL.
- **Resource:** Vercel Functions, Routing Middleware, Vercel CDN Cache, Rewrite, Redirect.
- **Request Type:** api, ssr, isr, ppr, rsc, cron.
- **Request Method:** GET, POST, etc.
- **Request Path:** actual URL path.
- **Cache:** HIT, MISS, STALE, PRERENDER.
- **Status Code:** specific HTTP codes.
- **Environment:** production, preview.
- **Branch:** git branch name.
- **"Logs from your browser"** button: filter to requests matching your own IP + User Agent (huge for debugging your own activity in high-traffic prod).

**Search field (top of table):** typed values double as filter chips. Searchable keys: `route`, `requestPath`, `requestType`, `level`, `resource`, `host`, `deployment`, `deploymentId`, `method`, `cache`, `status`, `requestId`, `environment`, `branch`, `sessionId`, `traceId`, `invocationId`. Full-text search is limited to the `message` and `requestPath` fields.

**Sort:** chronological, most recent first when search is active.

**Pagination:** "Show New Logs" button at end of results (default loads past 30 min). Continuous scroll.

**Sharing:** copy URL to share a specific filtered log view with teammates (URL contains filter state).

### Stripe global search bar (the canonical command-bar pattern)

**Location:** topbar, always visible.
**Behavior:** type → top results appear immediately, then "View all results" button or `Enter` to expand.

**Searchable object types** (an exhaustive list — Sabi should mirror this density for its own domain):
Connected accounts, customers, invoices, payouts, products, charges/payments, checkout sessions, coupons, credit notes, disputes, documents, invoice items, orders, payment intents, payment links, payment methods, plans, prices, promotion codes, quotes, refunds, setup intents, sources, subscriptions, transfers.

**Filter operators (exact syntax):**

| Filter | Example |
|---|---|
| `amount:` | `amount:149.99` |
| `brand:` | `brand:visa` |
| `country:` | `country:GB` (ISO 3166-1) |
| `created:` | `created:2020/07/12` |
| `currency:` | `currency:EUR` |
| `date:` | `date:yesterday` |
| `email:` | `email:jenny.rosen@example.com` |
| `exp:` | `exp:08/22` |
| `flow:` | `flow:redirect` |
| `last4:` | `last4:4080` |
| `metadata:` | `metadata:order_id=xyn712` |
| `name:` | `name:jenny` |
| `number:` | `number:06b2b1a642-0023` |
| `postal:` / `zip:` | `postal:12345` |
| `receipt:` | `receipt:3330-2392` |
| `risk_level:` | `risk_level:elevated` |
| `status:` | `status:canceled` |
| `type:` | `type:ideal` |
| `usage:` | `usage:single_use` |
| `profile:` | `profile:rocket_rides` |

**Comparison operators:** `>` greater than, `<` less than, `..` range (`amount:50.00..99.99`).
**Boolean `is:`:** `is:customer`, `is:active`, `is:captured`, `is:disputed`, `is:paid`, `is:recurring`, `is:refunded`, plus every object type.
**Combining:** multiple terms narrow; hyphen prefix negates (`-exp:08/22`); quotes for exact phrases (`"Stripe Shop"`) and for values with spaces (`name:"John Doe"`).
**Date phrases accepted:** `08/22`, `2020-07-12`, `last week`, `yesterday`.
**Multi-account:** searches all accounts in the org by default; dropdown lets you scope to one.
**URL-encoded state:** every search is bookmarkable and shareable.

### PlanetScale Query Insights (the canonical metrics-table-with-drilldown)

**Top controls:** Branch selector, Server selector (primary/replicas), Date navigation (past 7 days), Time range selection (click + drag on graph to zoom), Screenshot save button.

**Graphs above the table:** Query latency (with p50/p95/p99/p99.9 toggles), Queries per second, Rows read/second, Rows written/second.

**Columns in the queries table (exhaustive):** Query, Keyspace, Qualified table, Table keyspace, Table, % of runtime, Count, Total time, p50/p99 latency, Max latency, Rows returned, Rows read, Rows read/rows returned ratio, Rows affected, Tablet calls per query, Last run.

**Table features:**
- **"View options" dropdown** to customize which columns are visible.
- **Sortable columns** — click header to sort by that metric.
- **Sparklines toggle** — when enabled, every numeric column shows a tiny time-series chart inline within the cell over the selected time period.
- **Column-preset tabs** in the top-right of the table — e.g. a "Resources" tab pre-configures columns relevant to CPU/memory analysis. Sabi can use this pattern for "Lessons", "Engagement", "Errors" preset column sets in a call list.
- **Row drilldown** — click any query → full per-query deep-dive page.

**Search bar above the table:** filter syntax supports SQL text, keyspace, table name, query count, query latency, multisharded queries, index name, indexed status.

### Linear list views (display options model)

**Layout options:** List, Board (cards), Timeline (projects/initiatives only).

**Grouping (issue views):** Status, assignee, project, priority, cycle, label, parent issue, team, customer, release, SLA status, Focus.

**Grouping (project/initiative views):** Lead, member, status, health, start date, target date, initiative.

**Ordering (issues):** Status, manual, priority, last created, last updated, due date, link count. Reverse sort supported except manual.

**Sub-grouping:** swim lanes with sticky headers in lists and boards.

**Property toggles (each one can be shown/hidden per view):** ID, status, assignee, priority, SLA, project, due date, milestone, cycle, release, estimate, labels, links, customers, customer revenue, time in status, created/updated dates, pull requests, commits, Sentry issues.

**Display toggles:** show/hide sub-issues, show/hide empty groups, show empty milestones, completed-projects filter (last week / month / year / all / none).

**Save behavior:** every display option can be saved as workspace default or personal preference.

### Bulk actions

- Linear: `X` to select, `Shift ↑/↓` to multi-select, `Backspace` to delete, contextual property updates on selection.
- Stripe sidebar invite, bulk export from any list page.
- Vercel: bulk redeploy from deployments list.

### Empty states (the most-stolen pattern)

**Linear's pattern:** monochrome line illustration (blends into chrome, no color blob) + headline + one-line description + primary CTA + (optional) secondary "Learn more" link. Restrained warmth, no jokes, no mascot.

**Stripe's "tutorial as empty state":** the empty integrations page literally walks the developer through the first integration step-by-step, with **inline code snippets** that mutate based on the language tab selected. The empty state IS the onboarding.

**Vercel's pattern:** "Connect a Git repo" buttons live where projects would, with secondary "Browse templates" — the empty state never tells you the page is empty; it tells you the next action.

**The universal pattern (do this):** illustration + headline + 1-sentence description + primary CTA + (optional) secondary link. Skip the illustration if it doesn't carry weight — a clean text+button outperforms a beautifully illustrated one with unclear copy.

### shadcn/ui data-table primitives (what Sabi will actually build with)

- TanStack Table v8 under the hood; `ColumnDef` for column definitions.
- Sort via `getSortedRowModel()`, `ArrowUpDown` icon in header.
- Filter via `getFilteredRowModel()` with input above table.
- Pagination: 10 per page default, Previous/Next, disabled at boundaries.
- Row selection: header checkbox + per-row checkboxes; tracks "0 of 5 row(s) selected" text.
- Column visibility: dropdown menu with `DropdownMenuCheckboxItem` per column (`VisibilityState`).
- Row actions: `DropdownMenu` on each row.
- Sticky header, virtualization, faceted filters, toolbar, empty state are not in the canonical docs but are in community extensions like `tablecn` (which adds server-side sort + faceted filters per column + URL-based state + bulk-action toolbar + advanced query builder).

---

## D) Detail/drawer pages — layout, sections, audio player, transcript, drilldown

### Vercel runtime-log detail (right-side drawer triggered by clicking a row)

When a row is clicked, the right sidebar shows:
- Request Method (GET/POST etc.).
- Request Path.
- Time (UTC).
- Status Code.
- Host.
- Request Id.
- Request User Agent.
- Search Params.
- Region (edge region where the request was processed).
- Firewall (whether request was allowed).
- Vercel Cache (x-vercel-cache status).
- Middleware metadata (location + duration).
- Function metadata (name, location, runtime, duration, memory usage, start type).
- Deployment metadata (id, environment, branch).
- **Events** — timeline of events during the request with timing info.
- **Outgoing Requests** — sub-requests made during the function execution.
- **Log Messages** — bottom panel, list of `console.log` output in chronological order.

The URL updates so the drawer view is shareable as a deep link.

### Stripe payment detail (full-page drilldown)

- **Timeline section** with chronological events (authorization, capture, refund initiation, dispute, etc.).
- "View Details" link on each Timeline entry expands the metadata for that event (refund details, dispute reason, etc.).
- **Metadata panel** showing the `metadata` key-value object attached to the payment (up to 50 keys, 40-char names, 500-char values) — operators can pin business identifiers here.
- **Refund button** with reason picker + amount selector.
- **PaymentAttemptRecord** with multiple PaymentAttemptRecordEntries — initiation, authentication, authorization, capture — forming an append-only event log that reconstructs the full lifecycle.
- "Edit metadata" inline form.
- "Send receipt" / "View receipt" actions in overflow menu.

### Stripe Workbench (floating pane that overlays the dashboard)

Workbench is a resizable/maximizable taskbar pane available across every Dashboard page (`~` tilde to toggle). Inside it:

**Tabs:** Overview, Errors, Inspector, Logs, Health, Events, Webhooks, Shell.

**Logs tab filters:** Date, HTTP status (200/etc.), HTTP method, API endpoint, IP address, Source (API or Dashboard), Account (connected or organization), API version, Error code, Error type, Error parameter.

**Inspector tab:** Data map (left pane = hierarchy of related API objects), Overview tab (JSON view), Logs tab (related request logs), Events tab (related events), "Edit in API Explorer" button (sandbox only), Auto-inspect toggle (updates as you browse the Dashboard).

**Events tab:** filter by date, delivery status, event type (wildcard like `customer.*`), API resource. Per-event: payload, attempted deliveries with Succeeded/Failed tabs, "View webhook endpoint" overflow, "Resend" button.

**Webhooks tab:** destinations list (URL endpoints, AWS EventBridge, Azure Event Grid, local Stripe CLI), Overview, Event deliveries with full history, "Retry now" per delivery.

**Shell tab:** terminal pane (minimal always-available + full-screen option), "New pane" to split, "API Explorer" button → resource selector + method + parameters + Headers tab + Run + "Print SDK request" + language selector.

**Layout features:** top handle to drag-resize, maximize/minimize/expand/collapse icons, taskbar notification tray for API errors and event activity, "Copy link" for sharing the exact Workbench view, "Send feedback", "Refresh logs", "Refresh events".

### Linear issue detail (full-page or side-panel via `O O`)

- Title (H1, large), ID badge (e.g. `ENG-123`).
- Property rail (right side): Status, Priority, Assignee, Labels, Project, Cycle, Estimate, Due date, Parent issue, Sub-issues, Customers, Releases.
- Description editor (Markdown, inline code, slash commands).
- Activity log (chronological) with comments interleaved.
- Sub-issues list with progress.
- Linked PRs/commits/Sentry issues.
- Right-click any property for context menu; keyboard shortcuts for every action.

### PlanetScale query deep-dive page

- Query pattern display (the SQL itself).
- **"Summarize query"** button (likely AI).
- **"Show explain plan"** button.
- **"Open query in web console"** link — round-trip to the SQL editor with the query pre-filled.
- Metric tabs: Query latency, Queries, Rows read, Rows written, Errors, Indexes.
- Notable queries table with Tags column.
- Time-window adjustment (click/drag or day icons).

### PlanetScale audit log entry expansion

- Row collapsed: who + action + when.
- Click row → expands inline to show full metadata (target resource, IP, user agent, before/after values, etc.).
- Filters: Actor, Action.

### Sabi-specific: audio player + transcript pattern (from CDR-tooling research)

The standard pattern (used by Voiso, VoIPmonitor, Tata Tele Smartflo, Cisco CUCM):
- **Audio player anchored at bottom of detail page** — play/pause, scrubber, time elapsed/total, **playback speed control** (1x/1.25x/1.5x/2x), volume slider, download (.mp4) if role-permitted.
- **Transcript on the main canvas above the player** with timestamps per speaker line; **clicking a timestamp scrubs the audio** to that point.
- **Tabs at top of detail:** Summary (with quality graphs + DTMF data), SIP History (packet/SDP inspection), Legs (call correlation across systems).
- **Comprehensive timeline** of the call journey with time breakdowns per leg.
- **Searchable transcript** so admins can find moments inside long lessons.

---

## E) Visual language — colors, typography, density, iconography, motion, brand voice

### Vercel Geist

**Color philosophy:** "one of the strictest stark systems on the web." Near-white `#fafafa` body, ink-near-black `#171717` for type, 200-step gray scale where every divider/border/disabled state lives on its own deliberate step. **Dark mode is treated as the canonical surface; light is the alternate** — the inverse of how most systems treat this.

**Color scales (10 total):** backgrounds, gray, gray-alpha, blue, red, amber, green, teal, purple, pink. Each non-background scale runs 10 steps (100–1000) where the step **encodes intent, not lightness**:
- 100 = default background
- 200 = hover background
- 300 = active background
- 400 = default border
- 500 = hover border
- 600 = active border
- 700 = high-contrast background
- 800 = hover high-contrast background
- 900 = secondary text and icons
- 1000 = primary text and icons

**Semantic role of accent scales:** blue for success/links/focus, red for errors, amber for warnings, plus green/teal/purple/pink for chart and category color. **Gray-alpha tokens are translucent** for borders/dividers/overlays/hover states; solid gray for text and opaque fills.

**Typography:** Geist Sans (body) + Geist Mono (headings, code, all-caps display). Tailwind classes pre-set `font-size + line-height + letter-spacing + font-weight`:
- Headings: `text-heading-72` down to `text-heading-14` (72/56/48/40 for marketing heroes, 32/24/20/16/14 with Subtle modifier via `<strong>`).
- Buttons: `text-button-16` / `text-button-14` (default) / `text-button-12` (input-specific).
- Labels: `text-label-20` down to `text-label-12` + mono variants `text-label-14-mono`, `text-label-13-mono`, `text-label-12-mono`.
- Copy: `text-copy-24` down to `text-copy-13` + `text-copy-13-mono` for inline code, higher line-height than labels.

### Linear

**Color philosophy:** dimmer chrome ("don't compete for attention you haven't earned"), warmer crisp gray (recently shifted from cool/blue-ish), Inter Variable (510/590 weights with custom stylistic sets), Inter Display introduced for headings to add expression, Berkeley Mono for code, near-black canvas, single high-contrast accent per screen (the rest in a tight monochrome cool-gray scale).

**Theme system:** Uses **LCH color space** (closer to human perception than HSL). Themes are generated from **three variables — base color, accent color, contrast** — instead of 98 hand-tuned variables per theme. The contrast variable auto-generates super-high-contrast themes for accessibility. Custom themes preserved across UI elements (toolbars, etc.).

**Surface stack:** 4-step range from canvas to elevated (background → panel → dialog → modal). Cards get presence through `1px` inset borders + soft drop shadows rather than fills.

**Density:** instrument-panel density. Every pixel earns its place. Engineering-native voice. Reduced icon proliferation (smaller icons, removed colored team-icon backgrounds). Rounded separator edges, reduced separator count, lowered contrast on dividers.

### Stripe

**Color philosophy:** purple-ish blurple `#635bff` as the brand accent, but the dashboard chrome is restrained gray-on-white. Strong reliance on semantic banner colors:
- **Test mode = orange persistent banner** across the top.
- **Live mode = blue color scheme** indicating real money is in play.
- **Notification boxes** on most pages reinforcing the current mode and disabling live-only settings while in sandbox.

### PlanetScale

Dark-friendly engineering aesthetic, lots of mono in code/keyspace identifiers, status badges for branch state (production/development/promoted/deployable), schema-diff coloring (additions green, deletions red, unchanged neutral).

### shadcn/ui (Sabi's effective baseline)

**Tokens (semantic, OKLCH-based in v4):**
- `--background` / `--foreground` (app surface + text).
- `--card` / `--card-foreground` (elevated surfaces).
- `--popover` / `--popover-foreground` (floating surfaces).
- `--primary` / `--primary-foreground` (high-emphasis actions, brand).
- `--secondary` / `--secondary-foreground` (lower-emphasis filled).
- `--accent` / `--accent-foreground` (hover/focus/active).
- `--muted` / `--muted-foreground` (subtle surfaces, lower-emphasis content).
- `--destructive` (errors, destructive actions).
- `--border`, `--input`, `--ring`.
- **Sidebar-specific:** `--sidebar`, `--sidebar-foreground`, `--sidebar-primary`, `--sidebar-primary-foreground`, `--sidebar-accent`, `--sidebar-accent-foreground`, `--sidebar-border`, `--sidebar-ring` — sidebar gets its own complete token set so it can be themed independently (dimmer than canvas, à la Linear).
- `--chart-1` through `--chart-5`.
- `--radius` base with derived `sm`, `md`, `lg`, `xl`, `2xl`, `3xl`, `4xl`.
- Tailwind v4 uses `@theme` directive in CSS, no JS config; dark mode overrides the same tokens inside `.dark` selector.

### Density toggle

The pattern (Salesforce Lightning, Cloudscape, Material React Table):
- **Comfortable** (default): standard spacing, optimizes readability and cross-device experience.
- **Compact**: reduces space between elements, `white-space: nowrap` on table rows to keep them short, sets labels to left of fields instead of above. For data-intensive views.
- (Cloudscape stops at 2; Salesforce splits into "Comfy" with top-aligned labels vs "Compact" with left-aligned labels; Material React Table cycles spacious → comfortable → compact.)
- Stored as user preference per session.

### Loading states (the rule)

- **Spinners** for short backend actions under 2 seconds. Single-module scope (one card, one button).
- **Skeleton screens** for full-screen content loads, content-heavy views, lists, profiles. Skeleton should mirror the actual layout — same row heights, same column widths, same heading sizes.
- **Shimmer** (animated gradient over skeletons) for media-rich content; **respect `prefers-reduced-motion`** because constant shimmer is uncomfortable for motion-sensitive users.
- Above 5 seconds, plain spinners feel broken; skeletons still feel acceptable.
- **Always have an error state** — never leave a skeleton spinning indefinitely if the fetch fails.

### Motion

- Linear emphasizes "polishing micro-interactions" but keeps motion subtle and non-decorative.
- Sonner toasts: non-blocking, slide-in animation, auto-dismiss timing scaled to importance (success faster, errors longer).
- All consoles avoid bouncy or playful easing in the operator chrome — animations are short, linear/ease-out, functional.

---

## F) Specific patterns Sabi should copy

1. **Persistent topbar environment indicator (Stripe orange/blue model).** What it does: an always-visible mode badge or banner that makes Sabi sandbox vs. production unmistakable, even when an operator scrolls deep into a page. Where it lives: topbar left, immediately after the org/breadcrumb. Sabi mapping: render a `<EnvironmentBadge mode={env}>` in the Clerk-aware app shell that pulls from a `NEXT_PUBLIC_SABI_ENV` value and Clerk's org metadata; orange `bg-amber-100 text-amber-900` border for sandbox/staging, neutral (no banner) for production. Persist a banner across the page when sandbox is active, and disable destructive production-only actions inside sandbox with inline "this only affects sandbox data" notes — exactly how Stripe handles it.

2. **Command palette as the universal entry point (Linear/Vercel ⌘K).** What it does: one keystroke opens a fuzzy-searchable launcher with Navigation, Actions, and Help categories, recent-commands at top, keyboard shortcut hints on the right. Where it lives: invoked from anywhere via ⌘K; trigger button in the topbar right side for discoverability. Sabi mapping: `npx shadcn add command` ships `cmdk` under the hood. Categories for Sabi: **Navigate** (Lessons, Learners, Calls, Sessions, Cohorts, Reports), **Actions** (create cohort, send test call, publish lesson, export CDR), **Search** (learners, calls, lessons by ID or phone), **Help** (docs, support). Index Navigation items in a typed array, Actions as functions, Search via API. Include the "paste an ID/phone number to jump" behavior Linear has for GitHub PR URLs.

3. **Icons-only-collapsed sidebar with `sidebar-07` (shadcn).** What it does: full-height sidebar with workspace/org switcher at top, primary nav with icons + labels expanded, collapses to 48–64px icons-only with tooltips on hover; "NavMain" + "NavProjects" + "NavUser" footer + "TeamSwitcher" header. Where it lives: left edge of every authenticated page. Sabi mapping: `npx shadcn add sidebar-07` directly. Replace TeamSwitcher with a Clerk `<OrganizationSwitcher>`. NavMain = Calls, Lessons, Learners, Cohorts, Reports, Insights. NavProjects = pinned cohorts/programs. NavUser = `<UserButton>` from Clerk. Use the dedicated `--sidebar-*` token set so the sidebar can be dimmer than the main canvas (Linear's "don't compete for attention" move).

4. **Stripe-style search-bar-as-filter-DSL.** What it does: a single search field that accepts both free text and `key:value` operators (`status:`, `from:`, `lesson:`, `cohort:`, `country:`, `duration:>120`, `created:yesterday`), with comparison operators (`>`, `<`, `..`), boolean prefixes (`is:answered`, `is:completed`, `-status:failed`), quoted phrases, and a URL-encoded state. Where it lives: topbar global search + top of every list page. Sabi mapping: build a Zod-typed parser (`parseSabiQuery(input): SabiFilter`) that normalizes the DSL into a Supabase query. Bookmark/share URLs by stringifying the filter object back into the DSL in `searchParams`. Searchable types: learner phone, learner ID, lesson code, cohort code, call ID, error code, language.

5. **Filter rail + table + detail drawer (Vercel runtime logs).** What it does: left rail with categorical filters (each filter group is a `Collapsible` section), main center table with sortable columns and chronological default sort, right drawer that opens when a row is clicked and updates the URL so it's shareable. Where it lives: every operational list page (Calls, Errors, Webhooks). Sabi mapping: this is your call-history page. Use `sidebar-08` (inset sidebar with secondary navigation) for the layout, `tablecn` for the data table with faceted filters per column, and `Sheet` from shadcn for the right drawer. Mirror Vercel's "Logs from your browser" pattern with a "My test calls only" filter that matches the operator's Clerk userId.

6. **Pinned shortcuts + recent visits in sidebar (Stripe pattern).** What it does: a "Shortcuts" section in the sidebar that auto-fills with recently-visited pages and lets the operator click a pin icon to keep one. Solves the "large product surface, only 5 things daily" problem. Where it lives: between primary nav and product nav in the sidebar. Sabi mapping: track route visits in `localStorage` (most-recent 5) and store pins in a `user_preferences` table keyed by Clerk userId. Render as a `NavSecondary` group above the main navigation.

7. **Sparkline columns + column-preset tabs (PlanetScale Insights).** What it does: every numeric column in a table can render a tiny time-series line inline within the cell ("Show sparklines" toggle); preset tabs in the table's top-right swap to predefined column sets (Resources, Latency, Errors). Where it lives: any time-series-heavy list (lessons, learners-by-engagement, calls-by-hour). Sabi mapping: use `recharts` `<Sparkline>` inside the cell renderer; gate behind a single toggle in the table toolbar. Define column presets in a `lessonsTablePresets` array (`Engagement` = completion %/duration/replays + sparklines; `Errors` = error rate/last-error/dropoff-point; `Reach` = unique learners/cohorts/regions).

8. **Inbox + Triage queue (Linear).** What it does: an Inbox of in-app notifications grouped by type with `J/K` keyboard scroll, `U` to mark read, `H` to snooze, `Shift S` to unsubscribe; a Triage queue for items from integrations/external sources that need accept/decline/dedupe. Where it lives: sidebar top, with unread badge (cap at "99+", user can hide). Sabi mapping: build `/inbox` for operator notifications (failed calls, content review requests, partner alerts) and `/triage` for inbound items from Africa's Talking webhooks (new partner registrations, content suggestions from teachers). `1` = accept, `2` = mark duplicate, `3` = decline, `H` = snooze (Linear's exact keys). Add Triage Intelligence later: use an LLM to suggest assignees/labels/duplicates.

9. **Empty state = next-step CTA, not decoration (Stripe + Linear).** What it does: every empty list page renders a short headline, a one-line description, a primary CTA button, and (when relevant for onboarding) inline code or a step-by-step walkthrough as Stripe does on empty integrations. Monochrome line illustration only if it earns the space. Where it lives: every list page when `rows.length === 0`. Sabi mapping: build a reusable `<EmptyState title description action illustration?>` component. Examples: "No calls yet — your sandbox number is +1-XXX. Make a test call from your phone to see it appear here. [Copy number]"; "No cohorts — create your first cohort to start enrolling learners. [Create cohort]".

10. **Sonner toasts for non-blocking feedback + persistent activity log for the audit trail.** What it does: ephemeral Sonner toasts (success/info/warning/error/promise variants) for the immediate action; a persistent `/activity` log for the auditable record (Actor / Action / Resource / Time / IP / Metadata, expandable rows). Where it lives: toasts overlay top-right (or bottom-right per Sonner config); activity log is a sidebar item or a tab under Settings → Audit. Sabi mapping: `npx shadcn add sonner`. Use `toast.promise(saveLesson(), { loading, success, error })` for async ops. For the activity log, write every state change to a Supabase `audit_log` table with the Linear/PlanetScale schema: `id, actor_user_id, actor_email, action, resource_type, resource_id, ip, user_agent, metadata jsonb, created_at`. Render as a paginated table with filters for Actor + Action, expandable rows for metadata.

11. **Theme tokens scoped to sidebar (shadcn's `--sidebar-*` set).** What it does: lets the sidebar use a slightly different palette than the main canvas without polluting the global tokens — the Linear move where the sidebar is dimmer than the content. Where it lives: `globals.css`. Sabi mapping: set `--sidebar` to one step darker than `--background` in light mode and one step lighter in dark mode; set `--sidebar-foreground` to `--muted-foreground` so labels read as receded; only `--sidebar-primary` (the active item) gets full contrast.

12. **OKLCH color tokens with Tailwind v4 `@theme` (the modern way).** What it does: defines colors in perceptually-uniform OKLCH so dark mode "accent equivalents" actually feel like the light-mode versions; one CSS file (no JS config). Where it lives: `app/globals.css`. Sabi mapping: copy the shadcn default OKLCH theme as a starting point; convert Sabi gold (#D4AF37 in the gold-on-black brand) to OKLCH for `--primary`; mirror Linear's 3-variable model where you only customize base/accent/contrast for any sub-brand themes (e.g. partner-branded portals).

13. **Density toggle in settings (Salesforce + Cloudscape pattern).** What it does: a user-preference toggle in Settings → Appearance that switches table row heights between Comfortable (default 48px) and Compact (32px with nowrap). Where it lives: Settings → Appearance, also as a button in any data table's toolbar for in-context use. Sabi mapping: store as `density` enum in user preferences; apply via a `data-density` attribute on the table root; Tailwind variants `data-[density=compact]:py-1` vs `data-[density=comfortable]:py-3`.

14. **Skeleton-that-matches-layout for full-page loads, spinner only for sub-actions.** What it does: when a page is fetching its initial data, render a skeleton with the same number of rows, same column widths, same heading sizes; when an inline action (save, refresh) is running, use a small spinner on the button. Where it lives: every page-level loading state. Sabi mapping: leverage Next.js 16 `loading.tsx` boundaries — write a `<CallsListSkeleton>`, `<LessonDetailSkeleton>`, etc., that the framework auto-renders during navigation. Respect `prefers-reduced-motion` and disable shimmer when set.

15. **Keyboard-first navigation with `G` then letter (Linear).** What it does: a global key handler that listens for `G` followed by a letter to navigate (`G I` = Inbox, `G L` = Lessons, `G C` = Calls, `G H` = Home), and `?` to show all shortcuts. Where it lives: app-shell-level key handler. Sabi mapping: install `react-hotkeys-hook`; bind the sequence handler in a `<KeyboardShortcuts>` component mounted in the root layout; render a shortcut-cheatsheet `Dialog` on `?`. Critically: also wire `Esc` to close any open modal/drawer (the universal expectation).

16. **Vercel-style breadcrumb-with-dropdowns.** What it does: every breadcrumb segment has a chevron-dropdown that lets you switch sideways inside that scope (switch project without leaving the deployments tab). Where it lives: topbar breadcrumb. Sabi mapping: build a `<BreadcrumbSegment value options href>` component where each segment is a `DropdownMenu` listing siblings (other cohorts when on a cohort page, other lessons when on a lesson page). Hugely faster than navigating up and back down.

17. **Shareable URL state everywhere (Vercel logs, Stripe search, Workbench).** What it does: every filter, sort, drawer-open state, density, and selected row encodes into `searchParams` so the URL is the canonical state — operators paste URLs into Slack to escalate. Where it lives: every list, every detail drawer. Sabi mapping: use `nuqs` (next-usequerystate) for typed URL state; build a "Copy link" button in the table toolbar that copies the current URL (Stripe Workbench's exact pattern).

18. **Workbench-style floating taskbar pane (Stripe).** What it does: a developer pane that floats over the dashboard, toggled with `~`, containing Logs / Events / Webhooks / Inspector, resizable, maximize/minimize/collapse to icon — so a partner-success operator can debug a Sabi API call without leaving the cohort they were on. Where it lives: bottom of every page, toggled. Sabi mapping: build a `<DeveloperPane>` using shadcn `Sheet` with `side="bottom"` and resizable behavior; tabs for Webhook attempts, AT call logs, Twilio status, recent API errors. Lower priority than the rest but huge for partner-facing technical staff.

---

## G) Anti-patterns to avoid

1. **Don't decorate empty states.** A beautifully illustrated empty state with unclear copy underperforms a clean text+button every time. Skip the mascot.
2. **Don't put the topbar environment indicator anywhere other than persistent + top-left.** Stripe's whole safety argument depends on the orange banner being unmissable. A tucked-away dropdown that says "Sandbox ▾" fails the "oh god is this prod" test at 11pm.
3. **Don't build a sidebar with more than 3 nesting levels.** Twilio Paste explicitly caps at 3. Anything deeper becomes unscannable. If you have more, you need page-level navigation (tabs, breadcrumbs) instead.
4. **Don't gate icons-only collapse on a setting.** Just make the sidebar resizable + collapsible from a button. Stripe and Vercel both let users hide the sidebar entirely; Linear lets you `[` / `]` toggle it. Forcing a "compact mode" preference is friction.
5. **Don't use spinners for full-page loads.** Above 5 seconds they feel broken. Use a skeleton that mirrors the eventual layout. Reserve spinners for sub-actions under 2 seconds.
6. **Don't use shimmer indiscriminately.** Constant shimmer is uncomfortable for motion-sensitive users — gate it behind `prefers-reduced-motion: no-preference`.
7. **Don't use red as a category color and as the destructive color.** Reserve red for errors and destructive confirmations only. Use amber for warnings, blue for info/links, green for success. Stripe and Vercel both keep these semantic.
8. **Don't ship a command palette without recent + keyboard hints.** The 80% value of ⌘K is "fuzzy match → enter" and "I see the shortcut, I'll learn it next time." Skip those and you have a worse search bar.
9. **Don't put numeric badges everywhere.** Cap at "99+" and let the user hide them (Linear added that toggle for a reason). A sidebar with 7 unread badges screams instead of informing.
10. **Don't redesign the sidebar shape per-product.** Vercel's redesign moved horizontal tabs into the sidebar to unify team vs. project navigation. Sabi will have multiple scopes (partner, cohort, lesson) and they should all use the same sidebar shape with consistent items — only the data changes.
11. **Don't let the sidebar compete with content.** Linear's "dimmer sidebar" is the single most-imitable visual move. Use the `--sidebar-*` token set, set `--sidebar-foreground` to muted, only give the active item full contrast.
12. **Don't build custom toast components.** Use Sonner. It already handles position, variants, promise pattern, auto-dismiss timing, and is what shadcn/ui recommends.
13. **Don't store table column visibility / density / sort in component state only.** Persist to URL (shareable) AND user preferences (sticky across sessions). All four consoles do this.
14. **Don't bury the activity log.** It should be a top-level Settings → Audit page with Actor + Action filters and expandable rows — not a paginated text dump.
15. **Don't expose internal IDs in the UI when natural identifiers exist.** Linear uses `ENG-123`, not a UUID. Stripe uses `pi_3M...` but always pairs it with the human context (customer name, amount). Sabi should generate human-readable IDs (`COHORT-LAGOS-2026-Q1`, `LESSON-PHONICS-001`) and use those everywhere the operator reads.
16. **Don't put the test/live toggle inside the user menu.** It belongs in the topbar where it's permanently visible — burying it inside a dropdown is exactly the failure mode Stripe's design exists to prevent.
17. **Don't ship without a "Copy URL" button on every filtered list and detail drawer.** Operators paste URLs into Slack — this is the dominant collaboration channel. If your URL doesn't encode state, the URL is useless.

---

## H) Source URLs

- https://vercel.com/changelog/dashboard-navigation-redesign-rollout
- https://vercel.com/changelog/new-dashboard-navigation-available
- https://vercel.com/changelog/quickly-navigate-the-dashboard-with-shortcuts
- https://vercel.com/changelog/command-menu-now-available-in-deployments
- https://vercel.com/docs/projects/project-dashboard
- https://vercel.com/docs/logs/runtime
- https://vercel.com/docs/concepts/dashboard-features/command-menu
- https://vercel.com/docs/vercel-toolbar
- https://vercel.com/geist/colors
- https://vercel.com/geist/typography
- https://vercel.com/geist/introduction
- https://vercel.com/try/new-dashboard
- https://linear.app/docs/conceptual-model
- https://linear.app/docs/inbox
- https://linear.app/docs/triage
- https://linear.app/docs/display-options
- https://linear.app/now/how-we-redesigned-the-linear-ui
- https://linear.app/now/behind-the-latest-design-refresh
- https://linear.app/changelog
- https://linear.app/changelog/2020-12-04-themes
- https://linear.app/changelog/2022-01-20-linear-preview-new-sidebar-and-team-icons
- https://planetscale.com/blog/improvements-to-database-branch-pages
- https://planetscale.com/docs/vitess/monitoring/query-insights
- https://planetscale.com/docs/security/audit-log
- https://planetscale.com/changelog/deploy-request-ui-updates
- https://planetscale.com/changelog/insights
- https://planetscale.com/docs/vitess/schema-changes/deploy-requests
- https://planetscale.com/blog/introducing-planetscale-insights-advanced-query-monitoring
- https://docs.stripe.com/dashboard/basics
- https://docs.stripe.com/dashboard/search
- https://docs.stripe.com/workbench/overview
- https://docs.stripe.com/development/dashboard
- https://docs.stripe.com/development/dashboard/request-logs
- https://docs.stripe.com/api/metadata
- https://docs.stripe.com/refunds
- https://ui.shadcn.com/blocks
- https://ui.shadcn.com/blocks/sidebar
- https://ui.shadcn.com/docs/theming
- https://ui.shadcn.com/docs/tailwind-v4
- https://ui.shadcn.com/docs/components/radix/sidebar
- https://ui.shadcn.com/docs/components/radix/sonner
- https://ui.shadcn.com/docs/components/radix/data-table
- https://paste.twilio.design/patterns/navigation
- https://paste.twilio.design/components/sidebar-navigation
- https://www.twilio.com/blog/bringing-cohesion-to-the-twilio-product-suite-part-ii
- https://www.nngroup.com/articles/skeleton-screens/
- https://www.onething.design/post/skeleton-screens-vs-loading-spinners
- https://cloudscape.design/foundation/visual-foundation/content-density/
- https://www.material-react-table.com/docs/guides/density-toggle
- https://developer.salesforce.com/blogs/2018/08/new-density-settings-for-the-lightning-experience-ui-in-winter-19
- https://www.enterpriseready.io/features/audit-log/
- https://www.averagedevs.com/blog/audit-logs-saas-compliance-trust
- https://docs.voiso.com/docs/supervisor-workflows-using-the-cdr
- https://www.voipmonitor.org/doc/Call_Detail_Record_-_CDR


---

## Comparable 8: African mobile-first edtech ops — Eneza, Viamo, M-Shule, MomConnect, Ubongo, Rori AI

I have plenty. Let me now produce the audit report.

# African mobile-first edtech ops — Eneza, Viamo, M-Shule, MomConnect, Ubongo, Rori AI (+ adjacent: engageSPARK, Mteja, RapidPro, Turn.io, EIDU, U-Report, DDD)

## A) Product overview (1 paragraph)

This comparable set spans seven user archetypes that overlap heavily with what Sabi's board-facing admin console must serve. **Eneza Education / Shupavu291** (Kenya, Ghana, Côte d'Ivoire — 6M+ learners, $3.5M ARR 2023) runs USSD `*291#` + SMS shortcode `20851`, with a teacher-facing portal at `mwalimoo.com/m/login` ("TeachMobile") for assigning homework, monitoring class performance, and "Ask-a-Teacher" SMS Q&A. **M-Shule** (Kenya, 23K+ learners across 30 counties) sells itself explicitly as "the platform Africa's organizations run learning programs on" — multi-tenant, branded, three-tier pricing (educator → org → government), per-cohort billing and analytics, "10 purpose-built AI tools" including AnalyticsInsight (natural-language Q&A over program data), CourseGenerator, MatchmakingAgent, ModerationAgent. **Viamo** (formerly 3-2-1, 35M+ users, 66 languages, 100M+ minutes/month) is the closest peer to Sabi's voice channel: IVR decision trees with games/quizzes/airtime, real-time partner dashboards for campaign monitoring, audience demographic segmentation. **MomConnect / NurseConnect** (built by Praekelt on Vumi+Junebug, 700K+ active mothers, 95% of SA clinics) shows the helpdesk + reporting pattern — pregnancies registered facility-side, monthly reports to provincial/district MCH coordinators, OpenHIM-routed data into DHIS2 Tracker. **Ubongo** is the soft case — their partner-reporting dashboard is in pilot via Impact Track. **Rori AI** (Rising Academies, 100K+ students, 11pp RCT effect) keeps the consumer side bare (WhatsApp `+1 206 590 6259`) but EBM built them "a dedicated management platform" for lifecycle/analytics/content. **engageSPARK + Mteja + RapidPro + Turn.io** are the dashboard archetypes the research literature and active deployments most resemble — engageSPARK is the closest functional twin (IVR/SMS/WhatsApp/Airtime campaigns with downloadable spreadsheet reports, segment/group contact management, project-arm randomization). Across this set the common thread: low-bandwidth audience, multi-tenant ops, real-time monitoring, downloadable evidence-grade reports, and dashboards designed for non-technical NGO program managers — not engineers.

## B) Navigation + topbar pattern (detailed)

The dominant pattern across this peer set is a **left rail / persistent sidebar** with a slim top utility bar, because these tools serve power users (program managers) who live in the product for hours.

**Mteja (Team Inbox layout — most exhaustively documented):**
- **Three-column layout** explicitly documented: left = "Inbox Summary and Contact Information," middle = "Conversation threads and interaction management," right = "Contact details, groups, and custom fields."
- **Left rail** (Inbox Summary section) has four pinned filters with live numeric counts: "Unassigned" / "Assigned to me" / "All" / "Status." Each shows a count of messages.
- **Top of conversation thread** has assignment dropdown ("Assign the conversation to yourself or another team member") and status setter.
- Channel toggle inside reply composer (SMS vs WhatsApp).
- Right rail = phone number + saved contact name + group memberships + custom field key/value list.
- Global product nav (separate from inbox): CRM, Call Center, Chatbots, USSD, Campaigns, Integrations — six top-level surfaces.
- Call-monitoring buttons in supervisor view: **Listen, Whisper, Barge** (industry-standard call-center triplet).

**engageSPARK:**
- Top utility nav: Solutions, Products, Customers, Pricing, Resources, **Login, Sign up.**
- Inside the app: page-level navigation is feature-named — **Contacts**, **Campaigns**, **Reports**, **Settings**.
- The Contacts page has a **"New" button** that opens a dropdown menu containing "Add Group" and "Add Segment" — this dropdown-as-create-affordance is a heavily reused pattern.
- Inside Contacts, a **left panel hosts Groups and Segments tabs** with the segments listed underneath, auto-updating counts beside each.
- Each campaign card in the list has a right-side **"Actions" button** that opens a menu containing "Download Campaign Report" and "View Analytics" among others.
- Campaign creation is a **three-step wizard**: (1) Content, (2) Contacts, (3) Confirm — a recurring African-edtech UI pattern.

**Turn.io (Inbox / WhatsApp ops):**
- Top product menu: **Product, Solutions, Community, Resources, Pricing**; language toggle (English/Portuguese).
- Product submenu names the surfaces — **Inbox, People & reminders, Playbooks, Journeys, Insights, Calling, Telehealth** (the last marked **NEW**).
- Account actions: "Log in" + "Book a Call" CTA in topbar.

**RapidPro (UNICEF):**
- The product is built around **Workspaces** (per-country, per-org). 284 active workspaces is the bragged-about scale.
- Inside a workspace the navigation is feature-named: Flows, Contacts, Channels, Campaigns, Triggers, Messages, Tickets, Analytics.
- The Flow designer is the **canvas-as-main-surface** pattern — drag-and-drop blocks for "Send Message," "Wait for Response," "Split by Expression," "Call Webhook," etc.

**U-Report (UNICEF, on top of RapidPro):**
- Public site nav: **Opinions, Stories, About, Engagement, Bots, Reports**, plus "Login" → **"Enter Dashboard"** CTA.
- Per-country subdomains (`ureport.in`, with sub-sites for 95 countries).

**Topbar conventions across the set:**
- Workspace switcher / org switcher (M-Shule explicitly: "every school, NGO, corporate team, or government program gets a fully branded environment").
- Channel filter pills (SMS / Voice / WhatsApp / USSD) appear on dashboards.
- Live count badges on left-rail items are universal — counts are a status signal, not decorative.

## C) List/index pages — columns, filters, sort, search, density, pagination, bulk actions, empty state

### Contacts list (engageSPARK + Mteja + RapidPro)

**Required columns** documented:
- **Phone number** (this is the primary key, always present; engageSPARK errors out hard if absent).
- **First Name, Last Name**.
- **Group(s)** — multi-value (a contact can be in many).
- **Custom fields** — engageSPARK uploads support `Age`, `Gender`, "Participant ID" (NOT `ID` — that collides with system IDs and throws "Please correct or remove the ID."), plus arbitrary org-defined fields.
- **Last interaction / Status** in conversation-style inboxes.
- **Carrier prefix** (used internally, surfaced when "No carrier found" upload error fires).

**Filters and segmentation:**
- **Groups** = manual assignment, sticky ("Once a contact is added to a Group it will stay there until you choose to remove it"). Either pre-create groups then assign, or specify group in the CSV upload itself.
- **Segments** = auto-computed from conditions: AND/OR logic over custom fields. Example documented: "Female contacts aged between 25 to 35 who opted into the program." Counts auto-update on upload, on manual edit, and on `Update Contact` action firing inside a survey.
- **Search bar** — keyword + phone number search (Mteja).
- **Conversation status filter dropdown** in inboxes.
- **Tabs in left panel**: "Unassigned / Assigned to me / All / Status."

**Bulk actions (engageSPARK):**
- Select individual contacts → "Actions" dropdown → "Add Contact to Group" → select target group → confirm.
- Contact upload supports `.xlsx` or `.csv`.
- "Multiple countries" toggle during upload (forces international `+CC` format).

**Upload error catalog (engageSPARK — uniquely detailed):**
1. "Please correct or remove the ID." (column-name collision)
2. "Please update the number and try again." (length/format invalid)
3. "No carrier found." (unknown prefix; manual support fix)
4. "Duplicated phone number." (in-file OR existing)
5. "No headers as the first row." (missing headers)
6. "International / national numbers mix up." (mix of formats)
7. "No phone number column"
8. "Phone number error" (Excel scientific-notation truncation `1.11E+10` from `>11`-digit numbers)

**Campaigns list (engageSPARK):**
- Each row has channel-type badge (SMS Blast / Drip / SMS Survey / WhatsApp / Voice IVR Survey / Airtime / CATI), status, name, date, and right-side **Actions** dropdown.
- Actions include: edit live campaign, duplicate, delete, archive, "Download Campaign Report," "View Analytics."
- Live campaigns can be edited in place.

**Tickets list (Mteja):**
- Columns: Status, Priority, Assignee, Customer, Channel, Last update.
- Status: default Open / In Progress / Resolved / Closed, plus custom statuses.
- Priority: Low / Medium / High / Urgent, plus custom levels.
- SLA fields visible: time-to-respond, time-to-closure.
- Auto-escalation rules apply at row level when SLA breaches.

**Empty state pattern (inferred from doc voice):** explicit "no data yet" prompts paired with the next action (e.g., "Add Segment" CTA right where the empty list would render). M-Shule's "real-time completion data that tells you who needs a follow-up before they fall behind" implies row-level "needs follow-up" badges as well.

### Cohort / Program list (M-Shule specifically)

- "Run multiple programs, cohorts, and communities simultaneously — each with its own members, content, analytics, and billing."
- Each cohort row exposes: name, member count, content set, analytics snapshot, billing tier.
- AI tool: **MatchmakingAgent** pairs peers inside a cohort — this implies a per-cohort detail page with a "peer pairs" tab.

## D) Detail/drawer pages — layout, sections, audio player, transcript, drilldown

### Conversation detail (Mteja, dense documentation)

When a row in the inbox is clicked, **the middle column becomes the conversation thread** while the right column populates with contact metadata.

- **Conversation thread (middle column)**:
  - Messages displayed chronologically — calls, SMS, and WhatsApp all interleaved in one history.
  - Each call row shows **a play button for the call recording** ("shows the call recording allowing you to listen to the recording in the same interaction thread"). This is the audio-player drilldown pattern Sabi needs.
  - **Missed/incomplete inbound calls float to the top of the inbox** with an unread count badge — natural visual prioritization.
  - **Returned calls log who returned them** ("indicates which agent made the return call").
  - **Notes** are a first-class object — "agents can take notes directly on the interaction thread… visible to the entire team."
  - **@mentions** of other agents inside notes.
  - **Channel switcher** in composer: SMS / WhatsApp toggle.
  - **Assign dropdown** at top of thread.
  - **Status setter** at top of thread.

- **Right column (contact profile)**:
  - Phone number + saved name.
  - Group memberships (list).
  - Custom field key-value table.

### Learner / Participant detail (extrapolated from M-Shule, EIDU, RapidPro)

- M-Shule: per-learner page shows course title, course progress, summarized content; teacher's view aggregates "number of active learners, new registrations and overall learners."
- EIDU per-learner: Teachers create learner profile in classroom; profile collects "extensive usage data" — gamified EGMA, EGRA, and other assessment scores; usage uploads in real-time when online, peer-to-peer when offline; teacher dashboard shows "learners' weekly usage time."
- RapidPro: contact detail shows full interaction history, flow runs, scheduled messages, group memberships, contact fields.

### Campaign / Flow detail (engageSPARK, RapidPro)

- engageSPARK Campaign Analytics has **three pages: Overview, Analytics, Subscriptions.**
- Overview metrics explicitly listed: "how many contacts were subscribed, contacts engaged, SMS sent, calls made, total cost of campaign, message cost, voice calls cost, WhatsApp cost, and airtime topup cost."
- Analytics page hosts charts of response distributions.
- Subscriptions page is the per-contact roster with their state in this campaign.
- Each campaign has retry rules, time windows (e.g., "M-F, 9 to 6"), caller-ID masking toggle, language selector for personalization, quota stop conditions ("automatically stop once reaching a target number of completed surveys per campaign or per project arm").

### Pilot / RCT reporting (engageSPARK is the documented model)

- **"Per project arm"** is a first-class concept — quotas, segments, and reports filter by arm.
- Random assignment of incoming contacts to arms is supported.
- Skip logic, conditional questions ("only ask if conditions are met"), and contact-profile updates from responses (`Update Contact` action) form the toolkit.
- Forwarding to a live agent is one of the triggered actions — handy for distress detection in a Sabi context.

### Audio-specific drilldown patterns

- Mteja: inline `<audio>`-style playback on each call row in the thread.
- engageSPARK voice IVR: keypress capture, **spoken-response recording**, **speech recognition** in 100+ languages, **ranges** (numeric input), **personalised TTS** in 44 languages.
- Africa's Talking voice dashboard: recordings stored as MP3, retrievable via the dashboard, with **retention and size limits documented in help articles**.
- Africa's Talking call records: source phone, date, time, duration, caller type, hangup cause — the article on hangup causes specifically distinguishes `NO_ANSWER` from `NO_USER_RESPONSE`, which is the kind of granular call-status taxonomy Sabi will need.

### Transcript drilldown (closest analog: Africa's Talking + engageSPARK)

- engageSPARK records spoken responses **and** offers transcription as an option.
- Africa's Talking distinguishes call status transitions (connected/ended) via callback events, and `play` actions can stream audio from any URL — meaning recording playback is universally a hosted-URL `<audio>` element.

## E) Visual language — colors, typography, density, iconography, motion, brand voice

The web-facing marketing surfaces of these tools tell us a lot about how the apps look — design systems tend to leak across.

- **Rori AI**: purple-branded; circular purple logo treated as the brand mark; uppercase navigation labels (`HOME, ABOUT, LEARNING OUTCOMES, PARTNERS, AWARDS & RECOGNITION, GET RORI`); shopping-cart icon in topbar (`[0]/cart`); four testimonial cards in card grid; CTA "Try Now" buttons all link directly to a WhatsApp `wa.me` URL — high color saturation, friendly-for-kids tone.
- **Turn.io**: clean, healthcare-leaning visual language; left-rail product menu with descriptive subtext under each item (e.g., "Inbox: Manage real-time conversations with customers through WhatsApp chat"); `NEW` badge on Telehealth; partner logo strip (Meta, WHO, OpenAI) on home; comparison table contrasting "fragmented" vs "unified"; metric callouts ("567% Improvement," "50+ million people reached").
- **engageSPARK**: utilitarian; documentation-heavy; three-step wizard is the dominant interaction primitive; emphasizes "No tech skills or training required."
- **Mteja**: explicit three-column inbox layout; numeric counts on every left-rail filter; pragmatic call-center skin (Listen/Whisper/Barge buttons).
- **RapidPro/U-Report**: UNICEF blue brand; flow canvas is the hero surface; per-country branding overlays (e.g., U-Report DRC).
- **DDD (Data Driven Districts) South Africa**: emphasis on "easy-to-read dashboards" — explicit anti-overload stance.
- **Density**: dashboards described in this peer set lean **medium-density** — not Bloomberg-terminal, not Notion-airy. Counts and badges are everywhere; long tables are uncommon — drilldowns are. M-Shule explicitly markets "no spreadsheets or dashboards to interpret—just the insight teams need to act."
- **Iconography**: phone, message, recording, group, segment, status. Mteja uses an unread-count dot on missed calls.
- **Motion**: heavy use of real-time updating numbers ("dashboards… updated in real time" — M-Shule; "Real-time data and indicators are automatically reported" — Viamo; "Live Dashboards… instantaneous insights" — Mteja). Implies WebSocket or polling-driven count animations.
- **Brand voice**: directive-imperative ("Run multiple programs," "Reach Millions with Your Message," "Turn WhatsApp into your Health App"). Outcome-first framing ("Cut no-shows by 40%," "doubled learning gains," "22% improvement in academic performance after 3 months").

## F) Specific patterns Sabi should copy

1. **Three-column inbox layout (Mteja).** Left = pinned filters with live counts (`Unassigned / Assigned to me / All / Status`). Middle = chronological conversation thread merging Sabi calls, SMS confirmations, and any future WhatsApp. Right = caller/learner profile with phone, name, cohort, custom fields. **Where it lives**: `/admin/inbox`. **Sabi mapping**: build with shadcn `ResizablePanelGroup` (3 panels, persisted sizes via cookie), Tailwind v4 grid, Clerk org context to scope inbox to current board/org. Each call row = `<Card>` with inline `<audio>` for the Chatterbox-generated session recording + transcript collapsible.

2. **Per-cohort, per-program isolation with own analytics + billing (M-Shule).** Treat every pilot (CcHub demo cohort, Lagos pilot, Bakame pilot, Sonia's regional cohort) as a first-class "Program" with its own learner roster, lesson scope, analytics view, and cost. **Where it lives**: `/admin/programs/[id]`. **Sabi mapping**: Clerk organizations for tenancy; Supabase `programs` table joined to `calls`, `learners`, `lessons`; AnalyticsInsight-style natural-language Q&A box (powered by Claude over Postgres) at the top of each program page.

3. **Three-step campaign wizard: Content → Contacts → Confirm (engageSPARK).** When the board wants to send a new lesson push or SMS reminder, use the same three-step pattern. **Where it lives**: `/admin/campaigns/new`. **Sabi mapping**: shadcn `Stepper` (community component), each step a discrete form, "Confirm" step shows cost preview, scheduled send time, AT short-code/long-code, and audience segment count.

4. **Groups vs Segments as parallel grouping primitives (engageSPARK).** Manual Groups for hand-picked cohorts (e.g., "MIT Hackathon demo kids"), auto-Segments for rule-based cohorts ("Lagos 8-year-olds who completed Lesson 3"). **Where it lives**: `/admin/learners`. **Sabi mapping**: two tabs in left rail; Segment builder with AND/OR over learner fields (county, age, lesson_completed, weeks_active, last_call_at); auto-update counts on every event ingestion.

5. **Quotas per project arm (engageSPARK).** Stop a pilot automatically once N completed sessions are reached per arm. **Where it lives**: program settings + per-experiment configuration. **Sabi mapping**: critical for RCT credibility with EduEvidence and World Bank reviewers — `arm_quotas` table, evaluated on every call completion.

6. **Downloadable, multi-sheet spreadsheet report (engageSPARK Campaign Report + SMS Log + WhatsApp Log + Call (Voice) Log + Airtime TopUp Log).** Board members will ask for this in Excel. **Where it lives**: every program / cohort detail page has a "Download report" button. **Sabi mapping**: server action that generates `.xlsx` with one sheet per channel using `xlsx` or `exceljs`; columns per sheet match the engageSPARK contract (Phone, Status, Duration, Cost, Timestamp, Transcript URL).

7. **Cost decomposition on Overview card (engageSPARK).** Show: contacts subscribed, contacts engaged, calls made, SMS sent, total cost, voice cost, SMS cost, airtime cost. **Where it lives**: program dashboard hero strip. **Sabi mapping**: shadcn `Card` grid; each cost line maps to AT/Twilio CDR aggregation; let the board feel cost-per-learning-minute viscerally.

8. **Call detail row with inline player + transcript collapsible (Mteja + Africa's Talking).** Every Sabi call becomes a thread row with play button, transcript expand, agent-assign dropdown, status, notes box. **Where it lives**: inbox detail. **Sabi mapping**: `<audio controls>` with signed Supabase Storage URL; transcript from Whisper segment-by-segment with timestamps; "Add note" textarea persisting to a `call_notes` table with `mentioned_user_ids[]` for @mention notifications via Clerk.

9. **Workspace / org switcher in topbar (RapidPro pattern).** Sabi will host multiple deployments (E4E pilot, Sonia's Lagos, future partners). **Where it lives**: top-left next to logo. **Sabi mapping**: Clerk `<OrganizationSwitcher>` component, drives all downstream queries via `orgId`.

10. **Live count badges on every left-rail item (Mteja, engageSPARK).** Numbers are status: `New calls (12), Failed (3), No-answer needs retry (45)`. **Where it lives**: every list nav. **Sabi mapping**: Server Components revalidating every 30s, or Supabase Realtime subscriptions on the underlying tables; numbers in shadcn `<Badge variant="secondary">`.

11. **Carrier / MNO performance breakdown by route (Africa's Talking + telco-ops convention).** Show per-carrier ASR (Answer-Seizure Ratio), ACD (Average Call Duration), cost per minute, drop rate. **Where it lives**: `/admin/analytics/carriers`. **Sabi mapping**: Pull from AT CDR webhook → aggregate by `mno_id`; charts via Recharts or shadcn `Chart`; this is THE chart that proves to board "MTN beats Airtel for our segment."

12. **Helpdesk / escalation routing (MomConnect pattern).** A subset of hard questions hit a human helpdesk. **Where it lives**: `/admin/escalations`. **Sabi mapping**: Sabi guardrails already detect safety issues — auto-route those to a board-staffed escalation queue with Mteja-style status (Open / In Progress / Resolved / Closed) and SLA timer.

13. **Real-time monitoring board for active sessions (Viamo + Mteja Live Dashboards).** Right now, who's on a call? Which lesson? Which county? **Where it lives**: `/admin` home, hero panel. **Sabi mapping**: Supabase Realtime subscription on `active_calls`; Mapbox/MapLibre map of Nigeria with pulsing dots per active session; live KPI strip.

14. **"AnalyticsInsight" plain-language Q&A box (M-Shule).** "How many learners in Lagos completed Lesson 5 last week?" → answer in one paragraph + small chart. **Where it lives**: top of every program/dashboard page. **Sabi mapping**: Claude Haiku tool-use against a constrained Postgres query surface — query templates + parameter binding, never raw SQL exec; cache hot answers.

15. **Drilldown drawer instead of new page (LearnDash convention seen in EdTech research).** Click a learner row → side drawer slides in with full attempt history; never lose the list scroll position. **Where it lives**: all list pages. **Sabi mapping**: shadcn `<Sheet>` from `side="right"`, URL-keyed via `?learnerId=...` so the drawer is shareable.

16. **Tier-pricing publicly visible (M-Shule's three tiers: educator → org → government).** Board-facing — make it obvious which tier any given workspace is on, since cost-per-learner is THE board number. **Where it lives**: topbar workspace switcher + Settings → Billing. **Sabi mapping**: Clerk org `publicMetadata.tier`; visual indicator chip in topbar.

17. **Multi-tenant fully branded environments (M-Shule).** Each partner org gets their own logo, color, subdomain. **Sabi mapping**: store `org.branding` JSON in Supabase, swap CSS vars at runtime, Vercel wildcard subdomains.

18. **Three-page Campaign Analytics: Overview / Analytics / Subscriptions (engageSPARK).** Sabi's per-lesson-push analytics should mirror this. **Sabi mapping**: tabs (`<Tabs defaultValue="overview">`), each tab a Server Component.

19. **Numeric NavRail items with status verbs (Mteja: "Unassigned 12 / Assigned to me 3 / All 415").** Verb + count is a richer affordance than label-only. **Sabi mapping**: standardize NavRail items as `<NavRailItem label count variant>`.

20. **Card recordings stored as MP3 with retention surfaced (Africa's Talking).** Don't hide retention. Show on each call row: "Recording expires 2026-09-12." **Sabi mapping**: render relative TTL from Supabase Storage signed-URL expiry; allow "extend" action.

## G) Anti-patterns to avoid

1. **"Open the spreadsheet to find anything" trap.** M-Shule's own marketing pitch is essentially "no spreadsheets" — if Sabi forces board members into Excel to see learner progress, you've lost. Spreadsheets are exports, not browse.
2. **Engineering jargon in the UI.** Several of these tools leak "MSISDN," "CDR," "ASR" into user-facing copy. Board members will not read those. Use "phone number," "call record," "answer rate."
3. **Conflating Groups and Segments (engageSPARK warning).** engageSPARK spends an entire blog post drawing the line — manual vs auto. Sabi should keep them visually distinct (icon + tooltip) from day one or you'll get "why isn't this contact in my segment?" tickets forever.
4. **Login URLs that don't match the brand (Eneza's `mwalimoo.com` for teachers, `enezaeducation.com` for marketing).** Confuses partners. Sabi should put admin behind `admin.sabi.tech` or similar.
5. **No on-platform changelog or product-update path (Eneza has none discoverable).** Board members lose confidence when they can't tell what changed week-to-week. Build a `/admin/changelog` or use a banner.
6. **Free-tier-only with no scaling story (M-Shule starts free but their tier ladder is publicly broken into 3 — Sabi should publish the ladder).** Hiding pricing kills board trust.
7. **Letting upload errors fail silently (engageSPARK's catalog of 8 named errors is best-practice).** If a CSV roster import fails, name the row, name the field, name the fix. Don't show "Upload failed."
8. **Hiding cost.** engageSPARK puts every cost line on the Overview. Hiding cost from the board breaks trust on a cost-conscious project like Sabi.
9. **No multi-cohort isolation (basic edtech LMSes lump everyone together).** Sabi must isolate the MIT-hackathon cohort, the Lagos pilot, and the Bakame pilot from day one. Retrofitting tenancy hurts.
10. **No empty-state CTA (default tables that just say "No data").** Every empty list must have a next-action button — "Add Segment," "Import learners," "Schedule first call."
11. **No retry / no time-window logic (raw Twilio/AT integration without business rules).** engageSPARK exposes "automated retry," "time windows (e.g., M-F, 9 to 6)," "local caller ID masking." Sabi calling kids at 10pm because the cron fired is a brand-killer.
12. **Forgetting the helpdesk loop (MomConnect built CaseProvi specifically for this).** When the AI can't handle a query, route to humans. No human loop = no trust.
13. **Skipping notes + @mentions (Mteja makes them first-class).** Board members + Sonia need to leave context on a call; threadless dashboards don't let them.
14. **Single global feed instead of per-cohort scoping.** Without cohort scoping every chart becomes meaningless aggregate.
15. **Designing for desktop only.** Sonia and field coordinators will look at this on a phone. Every list and detail must collapse cleanly to one column on small screens — Tailwind v4 container queries are the right tool.

## H) Source URLs

**Eneza Education / Shupavu291:**
- https://www.enezaeducation.com/
- https://www.enezaeducation.com/products/
- https://enezaeducation.com/shupavu291-helping-candidates-fulfill-academic-ambitions/
- https://www.engineeringforchange.org/solutions/product/eneza-education/
- https://www.gsma.com/solutions-and-impact/connectivity-for-good/mobile-for-development/blog/eneza-education-making-education-reality-working-hand-hand-mobile-operators/
- https://solve.mit.edu/challenges/teachers-and-educators/solutions/3178
- https://mwalimoo.com/m/login (teacher portal)
- https://mastercardfdn.org/en/articles/edtech-fellow-partners-with-private-sector-to-keep-kenyan-kids-learning/
- https://getlatka.com/companies/eneza-education
- https://hapakenya.com/2016/03/22/safaricom-partners-with-eneza-education-to-launch-shupavu-291/
- https://disruptafrica.com/2016/03/21/kenyas-eneza-education-rolls-out-e-learning-product-with-safaricom/

**Viamo (3-2-1):**
- https://viamo.io/
- https://viamo.io/viamo-platform/
- https://viamo.io/services/campaigns/
- https://viamo.io/services/campaigns/digital-campaigns-dashboard/
- https://viamo.io/services/surveys/
- https://digitalx.undp.org/viamo-3-2-1-platform_1.html
- https://digitalx.undp.org/catalogs/viamo-3-2-1-platform.html
- https://www.engineeringforchange.org/solutions/product/voto-mobile/
- https://viamo.io/viamo-platform/reaching-base-pyramid/

**M-Shule:**
- https://mshule.com/
- https://www.mshule.com/about-us
- https://www.mshule.com/pricing
- https://www.mshule.com/case-studies/our-impact
- https://www.engineeringforchange.org/solutions/product/m-shule/
- https://www.uil.unesco.org/en/litbase/m-shule-sms-learning-training-kenya
- https://ke.linkedin.com/company/m-shule
- https://bera-journals.onlinelibrary.wiley.com/doi/10.1111/bjet.13533

**MomConnect / NurseConnect / Praekelt:**
- https://www.health.gov.za/momconnect-technical-solution/
- https://www.health.gov.za/momconnect/
- https://pmc.ncbi.nlm.nih.gov/articles/PMC5922496/
- https://pmc.ncbi.nlm.nih.gov/articles/PMC5922474/
- https://pmc.ncbi.nlm.nih.gov/articles/PMC5922467/
- https://openhim.org/docs/7.2.x/implementations/momconnect/
- https://github.com/praekeltfoundation/vumi
- https://github.com/praekeltfoundation/junebug
- https://www.praekelt.org/junebug-intro
- https://www.turn.io/
- https://www.turn.io/insights
- https://blog.praekeltfoundation.org/post/95353223077/

**Ubongo:**
- https://www.ubongo.org/
- https://www.ubongo.org/wp-content/uploads/Ubongo-Learning-Report.pdf
- https://www.ubongo.org/partnership/toolkits/
- https://toolkits.ubongo.org/
- https://careers.rippleworks.org/companies/ubongo-org/jobs/58365857-terms-of-reference-social-impact-measurement-of-ubongo-s-educational-content

**Rori AI / Rising Academies:**
- https://rori.ai/
- https://rori.ai/about
- https://rori.ai/get-rori
- https://rori.ai/learning-outcomes
- https://ebm.ai/rising-academies-rori/
- https://arxiv.org/abs/2402.09809
- https://www.risingacademies.com/impact
- https://learning-engineering-virtual-institute.org/rising-academies/

**engageSPARK (closest dashboard analog):**
- https://www.engagespark.com/
- https://www.engagespark.com/support/getting-started/
- https://www.engagespark.com/support/campaigns/
- https://www.engagespark.com/support/voice-ivr/
- https://www.engagespark.com/support/reports/
- https://www.engagespark.com/support/reports-analytics/
- https://www.engagespark.com/support/contact-segments/
- https://www.engagespark.com/support/contact-upload-errors-explained/
- https://www.engagespark.com/blog/organize-your-contacts-with-groups-and-segments/
- https://www.engagespark.com/ivr-call-surveys/
- https://www.engineeringforchange.org/solutions/product/engagespark/

**Mteja (closest call-center inbox analog):**
- https://mteja.io/
- https://help.mteja.io/en/articles/9595210-mteja-s-team-inbox
- https://help.mteja.io/en/articles/9617017-how-to-manage-your-call-center-from-team-inbox
- https://help.mteja.io/en/articles/9827085-maximising-efficiency-assigning-and-tracking-customer-conversations-in-mteja-s-team-inbox
- https://help.mteja.io/en/articles/10398293-what-is-ticketing
- https://help.mteja.io/en/articles/8616952-mteja-s-subscription-plans-basic-business-and-enterprise
- https://help.mteja.io/en/articles/6165940-how-interactive-voice-response-ivr-technology-can-help-organizations-revolutionize-distance-learning-in-africa-s-rural-communities
- https://help.mteja.io/en/articles/4233236-how-mteja-s-call-campaigns-can-scale-sales-and-marketing-for-your-business-via-ivr
- https://www.getapp.com/customer-management-software/a/mteja/

**RapidPro / U-Report (UNICEF stack):**
- https://home.rapidpro.io/
- https://community.rapidpro.io/features/
- https://rapidpro.app/what-is-rapidpro/
- https://www.unicef.org/innovation/rapidpro
- https://www.unicef.org/innovation/U-Report
- https://ureport.in/polls/
- https://en.wikipedia.org/wiki/U-Report
- https://www.unicef.org/evaluation/media/1006/file/U-Report.pdf

**Africa's Talking (telephony backend most Sabi peers use):**
- https://africastalking.com/
- https://africastalking.com/voice
- https://africastalking.com/pricing
- https://help.africastalking.com/en/collections/150771-voice
- https://help.africastalking.com/en/articles/2900658-what-you-need-to-build-a-call-center
- https://help.africastalking.com/en/articles/1170660-how-do-i-get-started-on-the-africa-s-talking-sandbox
- https://help.africastalking.com/en/articles/12318772-consolidated-voice-pricing
- https://developers.africastalking.com/docs/voice/actions/record
- https://developers.africastalking.com/simulator
- https://simulator.africastalking.com/simulator/ussd

**EIDU + Data Driven Districts (dashboard depth references):**
- https://eidu.com/howitworks-for-schools/
- https://dev.eidu.com/
- https://edtechhub.org/2022/03/16/personalised-digital-learning-system-can-it-work-in-kenya/
- https://www.dell.org/ideas/data-driven-districts/
- https://edtechhub.org/wp-content/uploads/2025/10/Sun-et-al.-2025-Designing-Digital-Notifications-to-Support-Teacher-Uptake-of-Data-Dashboards.pdf

**UNICEF Learning Passport:**
- https://www.learningpassport.org/
- https://global.learningpassport.org/
- https://www.unicef.org/partnerships/learning-passport-unicefs-digital-learning-programme-reaches-over-10-million

**FoondaMate (WhatsApp peer):**
- https://peopleofcolorintech.com/front/how-south-african-edtech-startup-foondamate-is-helping-students-study-with-whatsapp/
- https://techpoint.africa/feature/south-african-edtech-foondamate-whatsapp/

**Telco metric references (ASR/ACD):**
- https://blog.kolmisoft.com/answer-seizure-ratio-asr-and-average-call-duration-acd/
- https://www.voip-info.org/asr/
