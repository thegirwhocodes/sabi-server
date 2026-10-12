# Education for Equality

**Status:** 🚀 **Launched** | Company Project

Web platform and voice-tutoring infrastructure for Education for Equality, featuring **Sabi** — a phone-accessible AI tutor for foundational literacy and numeracy in Nigeria.

> **Note:** While this repository is public for portfolio purposes, it represents proprietary work for Education for Equality. Sabi is the flagship product: learners can call from a shared feature phone without a smartphone, data plan, or reliable internet.

**Live:** [eduforequality.org](https://eduforequality.org) | [sabi.eduforequality.org](https://sabi.eduforequality.org)  
**Portfolio case study:** [naomiivie.vercel.app/sabi](https://naomiivie.vercel.app/sabi)

---

## 🎯 The Problem

In Nigeria and similar contexts:
- 10+ million children lack basic literacy
- Smartphones and data plans are unaffordable
- Schools are under-resourced
- Existing edtech requires internet connectivity

**Children need tutoring, but they only have access to shared feature phones.**

---

## 💡 The Solution: Sabi

**Phone-accessible AI tutor** that works via voice calls on basic mobile phones.

### How It Works

1. **Call the Sabi number** (no app, no internet)
2. **Voice conversation** with an AI tutor
3. **Curriculum-aligned lessons** (Cambridge Grade 4)
4. **Adaptive pacing** based on student performance
5. **Progress tracking** via phone number (no account needed)

### Design Constraints

- **< 3 second latency** (STT → LLM → TTS)
- **Telephony infrastructure** (Twilio, Africa's Talking)
- **Low-bandwidth optimization**
- **Interrupted call recovery**
- **Shared device handling** (multiple students per phone)

---

## ✨ Features

### Voice Tutoring
- Natural language conversation
- Curriculum-aware scaffolding
- Adaptive difficulty
- Pronunciation feedback (future)

### Telephony Integration
- Twilio for international calls
- Africa's Talking for local Nigerian routes
- Fallback routing for reliability

### Web Platform
- Curriculum content management
- Sabi landing and demo pages
- Learner progress dashboard (future)
- Magic-link authentication (Supabase)

### Curriculum
- Foundational literacy (phonics, reading)
- Numeracy (counting, basic operations)
- Cambridge Grade 4 alignment
- Nigerian context adaptation

---

## 🛠️ Tech Stack

| Component | Technology |
|-----------|-----------|
| **Frontend** | Next.js, TypeScript, React |
| **Backend** | Next.js API routes |
| **Authentication** | Supabase (magic links) |
| **Database** | Supabase (PostgreSQL) |
| **Telephony** | Twilio, Africa's Talking |
| **STT** | Speech-to-text API |
| **LLM** | Tutoring model (curriculum-aware) |
| **TTS** | ElevenLabs (low-latency voice) |
| **Deployment** | Vercel |

---

## 🏗️ What's in This Repo

- **Next.js web platform** for curriculum and Sabi landing pages
- **Lesson content** (literacy and numeracy)
- **Cambridge-aligned scaffolding** (Grade 4 curriculum)
- **Supabase auth** and progress tracking
- **Sabi voice demo routes** (web-based preview)
- **Telephony integration routes** (Twilio, Africa's Talking, ElevenLabs)

---

## 🎯 Use Cases

**Feature phone access:** Children who can't afford smartphones  
**No internet required:** Voice calls over cellular network  
**Shared devices:** Multiple students using family phone  
**Adaptive learning:** Personalized pacing based on performance

---

## 🚀 What This Demonstrates

- **Telephony infrastructure:** Twilio, Africa's Talking, reliability engineering
- **Voice AI:** Low-latency speech loops (< 3s round-trip)
- **Curriculum design:** Cambridge-aligned, context-adapted content
- **Deployment constraints:** Low-bandwidth, interrupted calls, shared devices
- **Full-stack:** Next.js, Supabase, voice APIs, production infrastructure
- **Product design:** Real-world constraints, user research, iterative deployment

---

## 🌍 Impact

**Education for Equality** is building phone-accessible tutoring for the 10+ million Nigerian children who lack basic literacy and numeracy skills. Sabi is the first step: scalable, voice-first, infrastructure-reliable AI tutoring.

---

## 📂 Project Status

**Sabi** is live and deployed. Active development continues on:
- Pronunciation assessment
- Expanded curriculum (Grades 5-6)
- Parent/teacher dashboards
- SMS fallback for ultra-low connectivity
- Multi-language support (Yoruba, Igbo, Hausa)

---

## 📬 Contact

**Founder:** Naomi Ivie  
**GitHub:** https://github.com/thegirwhocodes  
**Portfolio:** https://naomiivie.vercel.app  
**Case Study:** https://naomiivie.vercel.app/sabi
