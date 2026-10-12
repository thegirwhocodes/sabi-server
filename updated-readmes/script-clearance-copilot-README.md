# Script Clearance Copilot

**Status:** 🏆 **Complete** — Google Cloud Agentic Cinema Hackathon

An agentic script-clearance pass for indie filmmakers and small studio crews — built for the [Google Cloud Agentic Cinema Hackathon](https://agentic-cinema.devpost.com/) (Parallel track).

Paste a script. The agent (Gemini + Google's Agent Development Kit) reads it, pulls out every named person, business/brand, real-world place, and factual claim, and checks each one against the live web using [Parallel](https://parallel.ai)'s Search API — the same pass a professional script-clearance service runs before a film qualifies for errors & omissions (E&O) insurance.

---

## 🎯 The Problem

**Script clearance is required but often forgotten.**

Errors & omissions (E&O) insurance — required for distribution deals — depends on a clearance report. Without it:
- Distribution blocked
- Litigation risk
- Last-minute rewrites
- Costly delays

**Factual and clearance errors are the most common error type across produced films.**

---

## 💡 The Solution

**Automate the first pass** with an agentic clearance workflow:

1. **Parse the script** (character names, locations, brands, factual claims)
2. **Web search each entity** (Parallel Search API)
3. **Flag clearance issues:**
   - Real people who might sue
   - Trademarked brands used incorrectly
   - Factually inaccurate claims
   - Real locations requiring permission
4. **Generate a clearance report** (same format as professional services)

---

## ✨ Features

### Automated Entity Extraction
- Named characters
- Businesses and brands
- Real-world locations
- Factual claims and references

### Live Web Verification
- Parallel Search API for real-time checking
- Cross-references against current web data
- Flags potential legal issues

### Professional Report
- Clearance status per entity
- Risk assessment (high/medium/low)
- Suggested actions (rename, get permission, remove)
- E&O insurance readiness

---

## 🛠️ Tech Stack

| Component | Technology |
|-----------|-----------|
| **Agent framework** | Google ADK (`google-adk`) |
| **Language model** | Gemini 2.5 Flash |
| **Web search** | Parallel Search API |
| **Script parsing** | Natural language entity extraction |
| **Language** | Python |
| **Platform** | Google Cloud |

---

## 🏗️ Architecture

```
Script input → Gemini entity extraction
        ↓
    List of entities:
    - Named people
    - Businesses/brands
    - Locations
    - Factual claims
        ↓
    For each entity → Parallel Search
        ↓
    Clearance risk assessment
        ↓
    Generate report (PDF/web)
```

---

## 🎯 Use Cases

**Indie filmmakers:** Can't afford $5k+ professional clearance  
**Small studios:** Need fast first-pass before legal review  
**Film students:** Learning proper clearance workflow  
**Pre-production:** Catch issues before shooting

---

## 🏆 Recognition

**Google Cloud Agentic Cinema Hackathon — Parallel Track**

Judges recognized:
- Real-world utility (solves a painful, required step)
- Agentic architecture (not just a search wrapper)
- Professional workflow (mirrors industry standard)
- Integration quality (Google ADK + Parallel)

---

## 🚀 What This Demonstrates

- **Agentic AI:** Multi-step workflow with decision-making
- **Google ADK:** Agent framework and orchestration
- **API integration:** Parallel Search for live web data
- **Domain expertise:** Film industry clearance requirements
- **Practical tool:** Actual use case, not a tech demo

---

## 📂 Clearance Categories

### People
- Real individuals (living or recently deceased)
- Public figures vs private citizens
- Defamation risk assessment

### Brands
- Trademark status
- Usage context (positive/negative/neutral)
- Product placement rules

### Locations
- Private property
- Identifiable businesses
- Location release requirements

### Factual Claims
- Historical accuracy
- Scientific/medical claims
- Verifiable vs opinion

---

## 📬 Contact

**GitHub:** https://github.com/thegirwhocodes  
**Portfolio:** https://naomiivie.vercel.app  
**Hackathon:** [Google Cloud Agentic Cinema](https://agentic-cinema.devpost.com/)
