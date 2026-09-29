# Ed.it

**Status:** 🔨 **In Progress**

Desktop AI video editor. Drop a clip, type the brief, and let a local agent inspect, plan, and render the video.

> Built on Claude Agent SDK + Gemini 2.5 Flash + FFmpeg, with a local SQLite memory layer and an Electron shell. Everything runs on your machine — only LLM calls leave it.

---

## 🎯 The Problem

Most AI video tools are:
- Web-based prompt wrappers with no real tool use
- Limited to pre-defined templates
- Can't inspect actual video content
- Don't remember past edits or user preferences

---

## 💡 The Solution

**Ed.it** is a local agentic video editor that:
- Inspects video files (duration, resolution, codec)
- Generates contact sheets to understand content
- Calls FFmpeg for actual editing operations
- Uses Gemini 2.5 Flash to analyze video content
- Remembers your style and preferences in SQLite
- Tracks cost and operation history

This is the **video-editing version of a real tool-using assistant**, not a prompt wrapper.

---

## ✨ Features

### Video Intelligence
- **File inspection:** Metadata, duration, resolution, codecs
- **Contact sheet generation:** Visual frame grid
- **Gemini analysis:** "What's happening in this clip?"
- **Content understanding:** Scene detection, key moments

### Agentic Editing
- **Natural language briefs:** "Make this a 30-second Instagram Reel"
- **Tool-using agent:** Plans operations, calls FFmpeg
- **Iterative refinement:** "Make it faster" / "Add a fade"
- **Multi-step workflows:** Trim → filter → export

### Local-First
- **SQLite memory:** Preferences, project history, style
- **Cost tracking:** Token usage, API calls
- **File management:** Local storage, no cloud dependency
- **Privacy:** Media never leaves your machine (except for Gemini API)

---

## 🛠️ Tech Stack

| Component | Technology |
|-----------|-----------|
| **Framework** | Electron (cross-platform desktop) |
| **Agent SDK** | Claude Agent SDK |
| **Video analysis** | Gemini 2.5 Flash (multimodal) |
| **Video processing** | FFmpeg (CLI tool) |
| **Memory/state** | SQLite |
| **Language** | Python (backend agent), TypeScript (Electron shell) |
| **UI** | HTML/CSS/JS (Electron renderer) |

---

## 🏗️ Architecture

```
User brief → Claude Agent SDK
       ↓
   Plan operations
       ↓
   ┌─────┴─────┬─────────┬─────────┐
   ↓           ↓         ↓         ↓
Inspect    Contact   Gemini    FFmpeg
video      sheet     analysis  edit
   ↓           ↓         ↓         ↓
   └─────┬─────┴─────────┴─────────┘
         ↓
   Memory (SQLite)
         ↓
   Render result
```

---

## 🎯 Quick Start

### CLI

```bash
cd "Social Media/Ed.it"
source .venv/bin/activate
pip install -e .
edit "path/to/video.mp4" "Make a 15-second highlight reel"
```

### Desktop App

```bash
npm install
npm start  # Launches Electron app
```

---

## 🚀 What This Demonstrates

- **Agentic AI:** Tool-using agent architecture (not prompt wrapper)
- **Multimodal AI:** Gemini video understanding
- **Local-first design:** Desktop app, SQLite, file-based workflows
- **Process integration:** FFmpeg CLI automation
- **Product design:** Practical creative tooling, memory, cost tracking
- **Full-stack:** Python agent + Electron + TypeScript

---

## 🔧 Current Status

**Working:**
- Video inspection and metadata extraction
- Contact sheet generation
- FFmpeg operation execution
- Gemini video analysis
- SQLite memory layer
- Basic CLI interface

**In Progress:**
- Full Electron UI
- Advanced editing workflows
- Style memory and preferences
- Export presets (Instagram, YouTube, TikTok)
- Multi-clip projects

---

## 📬 Contact

**GitHub:** https://github.com/thegirwhocodes  
**Portfolio:** https://naomiivie.vercel.app
