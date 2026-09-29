# Sage Mail

**Status:** 🚀 **Launched**

Voice-first email triage for people who need an assistant, not another inbox.

**Live:** https://voice-email-app.vercel.app

---

## 🎯 The Problem

Email interfaces are designed for scrolling and clicking, not for:
- Walking to meetings
- Getting dressed in the morning
- Recovering from decision fatigue
- Hands-free multitasking

---

## 💡 The Solution

**Sage Mail** lets you clear your inbox through natural conversation. Speak decisions, hear context, approve actions.

### Core Principles

1. **One email at a time** — No overwhelming lists
2. **Voice-first** — Designed for spoken input and output
3. **Approval-gated** — Never sends without explicit confirmation
4. **Contextual priority** — Smart sorting by relationship and importance

---

## ✨ Features

### Intelligent Prioritization
Sage sorts Gmail by relationship context:
- Founder/business contacts
- Family
- Wesleyan network
- Opportunities
- Vendors
- Friends
- Unknown senders

### Voice-Driven Actions
Natural speech commands:
- "Reply" — Draft a response
- "Skip" — Move to next email
- "Archive" — Remove from inbox
- "Hear more" — Get additional context
- "Revise" — Adjust the draft
- "Send" — Approve and send (gated)
- "Stop" — End session

### Smart Drafting
Replies are generated using:
- Your profile and writing style
- Conversation memory
- Past message patterns
- Full thread context

### Streaming Response
Assistant responses stream sentence-by-sentence for immediate feedback, not batch-delayed.

---

## 🛠️ Tech Stack

| Layer | Technology |
|-------|-----------|
| **Frontend** | Next.js, TypeScript, React |
| **Authentication** | Gmail OAuth 2.0 |
| **Email API** | Gmail API (read, send, archive) |
| **AI Model** | Claude (Anthropic) |
| **Voice** | Web Speech API / browser TTS |
| **Streaming** | Sentence-by-sentence LLM streaming |
| **Deployment** | Vercel |

---

## 🏗️ Architecture

```
User speaks → Voice input → Intent parsing
                ↓
           Gmail fetch (priority-sorted)
                ↓
           Email read aloud
                ↓
           User decision → Action router
                ↓
    ┌─────────┴─────────────┬──────────┐
    Reply              Archive        Skip
    ↓                      ↓            ↓
 Draft with context    Gmail API    Next email
    ↓
 Read aloud → User approval
    ↓
 Send (gated)
```

---

## 🎯 Use Cases

**Morning routine:** Clear overnight emails while getting ready  
**Commute:** Triage inbox while walking or on public transit  
**Decision fatigue:** When clicking and typing feel overwhelming  
**Accessibility:** For users who prefer or require voice interfaces

---

## 🚀 What This Demonstrates

- **Voice AI:** Natural language understanding, spoken interaction design
- **OAuth integration:** Secure Gmail API access, token management
- **Product design:** Constrained scope with clear guardrails (approval-gated sends)
- **Streaming UX:** Real-time response delivery, not batch-delayed
- **Context management:** User profile, memory, thread history
- **Full-stack:** Next.js, TypeScript, API integration, deployment

---

## 🔐 Privacy & Safety

- OAuth tokens are user-managed
- No emails stored server-side
- All sends require explicit approval
- Draft-only mode available

---

## 📬 Contact

**GitHub:** https://github.com/thegirwhocodes  
**Portfolio:** https://naomiivie.vercel.app
