# Adjutant

**Status:** 🏆 **Complete** — SCSP Hackathon 2026, GenAI.mil Track

Voice-first, fully offline AI assistant for the Army's bureaucratic tail.

> *Speak it. Sign it. Move out.*

A junior NCO speaks naturally — *"I need ten days of leave starting June 3 for my sister's wedding"* — and gets a regulation-cited answer plus a populated **DA‑31 PDF** in under 15 seconds. The same voice flow handles TDY (DD‑1351‑2 with JTR per‑diem math) and counseling (DA‑4856).

---

## 🎯 The Problem

Army admin is:
- Regulation-heavy (hundreds of pages of references)
- Form-intensive (DA-31, DD-1351-2, DA-4856, etc.)
- Time-consuming for junior NCOs and soldiers
- Often requires internet/secure systems (not always available)

**Junior leaders need answers and forms *now*, not after research.**

---

## 💡 The Solution

### One Sentence → Three Filled Forms

*"Going to JRTC at Fort Polk for 5 days, need to counsel SPC Garcia tomorrow, want 2 days of leave when I get back"*

**→ DD‑1351‑2 + DA‑4856 + DA‑31, all signed-ready, in one pass.**

### Fully Offline

**Runs entirely on a laptop.** No internet required.

- Local Whisper for speech recognition
- Local FAISS for regulation retrieval
- Local Llama for language understanding
- Local Kokoro for text-to-speech

In our demo, we pull the wifi cable before the first query. **The room sees nothing change.**

---

## ✨ Features

### Voice-First Interface
- Speak naturally, no command syntax
- Under 15 seconds from speech to filled form
- Regulation-cited answers

### Multi-Form Support
- **DA-31:** Leave request form
- **DD-1351-2:** TDY travel voucher with JTR per-diem calculations
- **DA-4856:** Developmental counseling form

### Regulation Retrieval
- FAISS vector database of Army regulations
- Cited answers with reg numbers and sections
- Context-aware responses

### Zero Internet Dependency
- All models run locally
- All data stays on the machine
- Demo includes dramatic wifi-cable disconnect

---

## 🛠️ Tech Stack

| Component | Technology |
|-----------|-----------|
| **Speech recognition** | Whisper (local) |
| **Vector search** | FAISS |
| **Language model** | Llama (local) |
| **Text-to-speech** | Kokoro (local) |
| **Form generation** | Python (PDF fill) |
| **Regulation data** | Army regs (DA PAM, AR, JTR) |
| **Language** | Python |

---

## 🏗️ Architecture

```
Spoken query → Whisper transcription
        ↓
    Parse intent
        ↓
    FAISS retrieval (regulations)
        ↓
    Llama reasoning (cited answer)
        ↓
    Form fill (PDF generation)
        ↓
    Kokoro TTS (read answer aloud)
```

All processing happens **on the laptop**, no cloud.

---

## 🏆 Recognition

**SCSP Hackathon 2026 — GenAI.mil Track**

Judges recognized:
- Offline operation (critical for military environments)
- Voice-first UX (hands-free in field conditions)
- Regulation citation (trustworthy answers)
- Form automation (real time savings)
- Demo execution (wifi-cable disconnect moment)

---

## 🎯 Use Cases

**Leave requests:** "I need 10 days of leave starting June 3"  
**TDY travel:** "Going to JRTC at Fort Polk for 5 days"  
**Counseling:** "Need to counsel SPC Garcia on uniform standards"  
**Field conditions:** No internet, no secure terminal, just a laptop

---

## 🚀 What This Demonstrates

- **Voice AI:** Low-latency, offline speech loops
- **Local models:** Whisper, Llama, FAISS, Kokoro integration
- **RAG systems:** Regulation retrieval with cited answers
- **Form automation:** PDF generation from natural language
- **Product design:** Military UX constraints (offline, fast, cited)
- **Hackathon velocity:** Concept to working demo in 48 hours

---

## 📂 Demo Scope

### Supported Forms
- DA-31 (Leave Request)
- DD-1351-2 (TDY Travel Voucher)
- DA-4856 (Developmental Counseling)

### Regulation Coverage
- Army Regulation (AR) excerpts
- Department of the Army Pamphlet (DA PAM) excerpts
- Joint Travel Regulations (JTR) for per-diem

---

## 📬 Contact

**GitHub:** https://github.com/thegirwhocodes  
**Portfolio:** https://naomiivie.vercel.app

---

**Team:** Adjutant  
**Track:** GenAI.mil  
**Hackathon:** SCSP Hackathon 2026
