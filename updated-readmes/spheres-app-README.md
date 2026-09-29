# Spheres

**Status:** 📦 **Archived** — Predecessor to Cortex

Mac SwiftUI predecessor to Cortex: a personal AI brain organized around the areas of a person's life.

> The "spheres" idea: your life is made of areas (sphere of work, sphere of family, sphere of health, etc.). An AI agent that knows you should be aware of all of them and route attention between them.

---

## 🎯 The Concept

Traditional productivity tools are:
- Task-focused, not life-focused
- Siloed by domain (work vs personal)
- Reactive, not proactive
- Unaware of what you're neglecting

**Spheres** organizes your personal AI around **life areas** instead of task lists.

---

## ✨ What It Did

### Life Management
- Creates and manages life spheres (work, family, health, etc.)
- Tracks loops (open questions, ongoing projects)
- Manages inbox items across spheres
- Monitors habits and streaks
- Suggests schedules and priorities

### AI Integration
- Claude-powered classification of inbox items
- Resurfaces neglected work
- Suggests schedules based on sphere balance
- Conversational "Mind" view for planning

### Apple Ecosystem
- EventKit integration (Apple/Google Calendar)
- macOS account system
- SwiftData local storage
- Export/backup flows

### Source Adapters (Experiments)
- Gmail
- Apple Mail
- iMessage
- Notes
- Reminders
- Voice Memos

---

## 🛠️ Tech Stack

| Component | Technology |
|-----------|-----------|
| **Platform** | macOS |
| **Language** | Swift |
| **UI** | SwiftUI |
| **AI** | Claude (Anthropic) |
| **Calendar** | EventKit |
| **Storage** | SwiftData |
| **Architecture** | Service-based (5 core services) |

---

## 🔄 Evolution to Cortex

The architecture here was ported to the web for **Cortex** (https://cortex-web-one.vercel.app).

Five Swift services map to TypeScript modules:

```
SmartSetupService.swift     →   lib/ai/sphere-generator.ts
InboxClassifier.swift       →   lib/ai/inbox-classifier.ts
NeglectDetector.swift       →   lib/ai/neglect-detector.ts
ScheduleSuggester.swift     →   lib/ai/schedule-suggester.ts
MindView.swift              →   lib/ai/mind-view.ts
```

**Why the port?**
- Web > native for rapid iteration
- TypeScript ecosystem for AI tooling
- Easier deployment and sharing
- Cross-platform by default

---

## 🚀 What This Demonstrates

- **macOS development:** Swift, SwiftUI, EventKit
- **AI integration:** Claude API, prompt engineering, streaming
- **System design:** Service architecture, data modeling
- **Product iteration:** Prototype → production port to web
- **Research → product:** Translating life-area theory into software

---

## 📂 Project Status

**Spheres** is archived as a reference implementation. Active development continues in **Cortex** (web).

The repo remains public to show:
- The original Swift architecture
- EventKit and source adapter patterns
- SwiftUI service design
- The path from native prototype to web product

---

## 📬 Contact

**GitHub:** https://github.com/thegirwhocodes  
**Portfolio:** https://naomiivie.vercel.app  
**Cortex (successor):** https://cortex-web-one.vercel.app
