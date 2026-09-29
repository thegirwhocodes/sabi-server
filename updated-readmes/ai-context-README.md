# AI Context

**Status:** 🔨 **In Progress** | Development Infrastructure

GitHub-backed context management system for AI-assisted development workflows. This repository stores conversation transcripts, project memory, and recovery instructions for Claude and similar AI coding assistants.

> **Purpose:** Version-controlled AI context that enables session recovery, project continuity, and knowledge preservation across development sessions.

---

## 🎯 The Problem

AI coding assistants (Claude, GitHub Copilot, etc.) are:
- Stateless between sessions
- Context-limited within sessions
- Unable to recover from interruptions
- Disconnected from project history

**Developers need persistent context across sessions.**

---

## 💡 The Solution

**AI Context** provides:
- Conversation transcript storage
- Project memory export/import
- Context recovery workflows
- Session continuity tooling

---

## 📂 What Belongs Here

### ✅ Included

- Readable user/assistant conversation transcripts
- Curated project memory exports
- Recovery instructions and workflows
- Session indexes and metadata
- Export/verification/synchronization tooling
- Research notes and decision logs

### ❌ Excluded

- Raw JSONL or binary formats
- Tool outputs, shell snapshots, attachments
- Application databases
- Credentials, API keys, tokens, or secrets
- Unredacted sensitive information

---

## 🛠️ Tech Stack

| Component | Technology |
|-----------|-----------|
| **Version control** | Git, GitHub |
| **Format** | Markdown, JSON (structured) |
| **Sync** | GitHub sync scripts |
| **Local clone** | `~/ai-context` |
| **Tooling** | Python export/restore scripts |

---

## 🏗️ Workflow

```
Development session with AI
         ↓
    Export transcript
         ↓
    Redact sensitive info
         ↓
    Commit to ai-context repo
         ↓
    Future session recovery:
    - Read relevant transcripts
    - Restore project memory
    - Continue work
```

---

## 🎯 Use Cases

**Session recovery:** Resume after context limits or interruptions  
**Project continuity:** Onboard new AI sessions to existing projects  
**Decision tracking:** Record why choices were made  
**Knowledge preservation:** Long-term project memory

---

## 🚀 What This Demonstrates

- **AI workflow optimization:** Context management for productivity
- **Version control:** Git for non-code artifacts
- **Tool development:** Custom export/restore scripts
- **Developer experience:** Infrastructure for AI-assisted development

---

## 🔐 Security

- All exports are **reviewed and redacted** before commit
- No API keys, tokens, or credentials
- No unredacted personal information
- GitHub is the source of truth; `~/ai-context` is a working clone

---

## 📬 Contact

**GitHub:** https://github.com/thegirwhocodes  
**Portfolio:** https://naomiivie.vercel.app
