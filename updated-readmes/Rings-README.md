# Rings

**Status:** 🚀 **Launched**

Personal CRM built around Dunbar's circles.

Concentric rings — 3, 12, 30, 50, 100, 200 — each with a calibrated reminder cadence. Friends sit in a ring; the app reminds you when enough time has passed.

Started as a Python `tkinter` prototype. Currently **Version 2.1** — a multi-device Swift app for iPhone and Mac with CloudKit sync.

---

## 🎯 The Problem

Relationships fade through neglect, not conflict. Modern life is crowded, and:
- Inner-circle friends get lost in the noise
- Outer-ring connections disappear entirely
- Good intentions don't scale
- CRMs feel like sales pipelines, not friendships

---

## 💡 The Solution

**Rings** makes relationship maintenance visible without making friendship feel transactional.

### Dunbar's Circles

Based on anthropologist Robin Dunbar's research on stable relationship group sizes:

| Ring | Size | Cadence | Purpose |
|------|------|---------|---------|
| **Ring 1** | 3 people | Every 3 days | Closest relationships |
| **Ring 2** | 12 people | Weekly | Core friend group |
| **Ring 3** | 30 people | Biweekly | Close friends |
| **Ring 4** | 50 people | Monthly | Regular friends |
| **Ring 5** | 100 people | Quarterly | Acquaintances |
| **Ring 6** | 200 people | Biannual | Extended network |

---

## ✨ Features

### Simple Flow

```
Add friend → Assign ring → App schedules next check-in
  → When you contact them → Tap "marked" → Reschedule
```

### Multi-Device Sync
- iPhone and Mac apps
- CloudKit synchronization
- Shared state across devices

### Smart Reminders
- Push notifications when it's time to reach out
- Respect for your capacity (ring sizes enforce limits)
- Calibrated cadences per ring

### Privacy-First
- No social media integration
- Your data, locally managed (CloudKit private database)
- No tracking, no analytics

---

## 🛠️ Tech Stack

| Component | Technology |
|-----------|-----------|
| **Platform** | iOS, macOS |
| **Language** | Swift |
| **UI** | SwiftUI |
| **Sync** | CloudKit (private database) |
| **Notifications** | UserNotifications framework |
| **Architecture** | MVVM, SwiftData/Core Data |
| **Version History** | v1.0 (Python tkinter) → v2.1 (Swift multi-device) |

---

## 🧠 The Philosophy

> **The Dunbar number is not a budget; it is an attention shape.**

Inner-circle relationships need frequent warmth. Outer rings shouldn't disappear just because life gets crowded. **Rings** makes relationship maintenance visible without making friendship feel like a sales pipeline.

---

## 🎯 Use Cases

**Maintaining close friendships:** Regular check-ins with your inner circles  
**Remembering to reach out:** Outer-ring friends who'd otherwise fade  
**ADHD/executive function:** Structure for relationship maintenance  
**Post-college life:** When default social structures disappear

---

## 🚀 What This Demonstrates

- **iOS/macOS development:** Swift, SwiftUI, multi-device apps
- **CloudKit integration:** Private database, sync, conflict resolution
- **Product research:** Dunbar's number applied to product design
- **UX design:** Simple, non-transactional relationship management
- **Full lifecycle:** Prototype (Python) → Production (Swift v2.1)

---

## 📂 Version History

**v1.0 (2024):** Python tkinter prototype  
**v2.0 (2025):** Swift iOS app, single device  
**v2.1 (2026):** Multi-device (iPhone + Mac), CloudKit sync

---

## 📬 Contact

**GitHub:** https://github.com/thegirwhocodes  
**Portfolio:** https://naomiivie.vercel.app
