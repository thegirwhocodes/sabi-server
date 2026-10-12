# Dactyl

**Status:** 🏆 **Complete** — Morgan Hacks 2026, 1st Place

Bidirectional ASL translation glasses: signing becomes speech, and speech becomes captions.

**Built by:** Naomi Ivie & Tomisin  
**Devpost:** https://devpost.com/software/dactyl

---

## 🎯 The Problem

In conversations between a deaf signer and a hearing speaker:
- The deaf person currently carries the entire translation burden
- Interpreters aren't always available
- Communication remains one-directional or cumbersome

---

## 💡 The Solution

**Dactyl** creates a two-way bridge where both parties can communicate naturally:

### ASL → Speech
1. **Camera** captures signing
2. **MediaPipe** tracks 543 hand/body keypoints
3. **Custom LSTM** classifies signs
4. **LLM** (Groq) converts gloss to natural English
5. **Edge TTS** speaks it aloud

### Speech → Captions
1. **Microphone** captures audio
2. **Whisper** (local) transcribes speech
3. **Display** shows captions on the signer's glasses view

### Real-time Interface
- Flask + SocketIO backend
- Web-based dashboard and glasses display
- Sub-second latency for both directions

---

## 🛠️ Tech Stack

| Component | Technology |
|-----------|-----------|
| **Hand tracking** | MediaPipe (543 keypoints) |
| **Sign classification** | Custom LSTM model |
| **Speech synthesis** | Edge TTS |
| **Speech recognition** | OpenAI Whisper (local) |
| **Natural language** | Groq LLM |
| **Backend** | Flask, SocketIO |
| **Frontend** | HTML/CSS/JS, real-time rendering |

---

## 📊 Demo Scope

The trained model recognizes **12 core signs:**
- hello, goodbye, thank you, please
- happy, need, water, friend, hope
- my name, nice to meet, idle

---

## 🏆 Recognition

**Morgan Hacks 2026 — 1st Place**

Judges recognized Dactyl for:
- Bidirectional communication (not just one-way translation)
- Technical depth (computer vision + ML + voice)
- Real-world applicability
- Polished demo execution

---

## 🚀 What This Demonstrates

- **Computer vision:** MediaPipe integration, keypoint tracking
- **Machine learning:** LSTM model training and inference
- **Real-time systems:** Sub-second bidirectional processing
- **Voice AI:** Local Whisper, TTS, natural language processing
- **Full-stack:** Flask backend, web frontend, real-time communication
- **Hackathon velocity:** Concept to working demo in 36 hours

---

## 📬 Questions?

**GitHub:** https://github.com/thegirwhocodes  
**Portfolio:** https://naomiivie.vercel.app
