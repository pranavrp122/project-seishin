# Phase 1 Planning Discussion — April 19, 2026

This document captures the full planning conversation around Phase 1 of the Seishin product vision. The goal was to take the large Phase 1 milestone from `PRODUCT_VISION.md` and break it into logical subphases that build on each other with clear, rigorous test gates before advancing.

---

## The Starting Point

Phase 1 in the product vision is titled **"Voice Intelligence Layer"** — described as a complete, working personal AI assistant deployable on any laptop. Useful standalone, no company database required. It covers:

- A full desktop app with voice interface
- A voice pipeline (VAD → streaming → ASR → LLM → TTS)
- OpenClaw integration (email OAuth, calendar, file search, browser automation)
- 13-intent classification system
- Sandboxed workspace (all file operations previewed before real execution)
- Client-side persistent memory
- Email compose panel with 5-minute send queue
- File search with result cards
- Browser research via Chrome
- Calendar read
- Proactive session start briefing

The question was: **is this a logical Phase 1, and how do we break it into subphases that each have a solid test gate before moving on?**

The answer: yes, it's logical — but it's genuinely massive. It's effectively 5–6 independent systems that all need to work together. The right move is to split it into sub-milestones, each one independently testable, each one a foundation for the next.

---

## Initial Subphase Breakdown (Before Current State Clarification)

The first pass at subphases, before knowing what was already built:

| Subphase | What it builds | Test gate |
|----------|---------------|-----------|
| **1.1** | Desktop app shell + voice transport (mic → VAD → WebSocket → server → audio playback) | Voice round-trip works, TTFA < 250ms, stable 10-min connection |
| **1.2** | Intent routing + core conversation — all 13 intent types wired end-to-end | 90%+ classification accuracy, conversation context carries across turns |
| **1.3** | File search — OpenClaw phase A | Finds files by name/type/date, result cards render, open works |
| **1.4** | Email — OpenClaw phase B (Gmail + Outlook OAuth, compose panel, 5-min queue) | OAuth persists across restarts, draft quality passes review, email delivers |
| **1.5** | Calendar + browser research — OpenClaw phase C | Calendar reads correctly, Chrome launches and navigates, summary voiced back |
| **1.6** | Client-side memory + session briefing | Memory survives app restart, briefing surfaces correct context, recall doesn't hallucinate |
| **1.7** | Sandboxed workspace + audit log | Real files untouched until confirmed, every action logged with timestamp |
| **1.8** | Full Phase 1 integration — the actual milestone | Full Monday morning demo scenario runs clean start to finish, all 13 intents handled, no regressions |

The rationale for 1.8 being the "main phase 1" is that it's the integration test — it doesn't add new features, it proves all the pieces work together under real conditions. The demo scenario from the product vision doc (finding the Friday meeting notes, drafting the follow-up email, researching three companies in Chrome) is the pass/fail criteria.

**Risk flag called out early:** 1.4 — email OAuth — is historically the biggest time sink in projects like this because Gmail and Outlook behave differently, token refresh logic is fiddly, and edge cases multiply. The recommendation: timebox it hard, don't let it hold up 1.5.

---

## Current State Clarification

After the initial breakdown, the actual state of the codebase was clarified:

- **1.1 is partially done** — but voice is deferred. The current implementation is text + LLM only. The voice layer (VAD, audio streaming, TTS playback) is easy to add at any point, so it was intentionally left for later. This was the right call — shipping voice prematurely before the core intelligence is solid would just add debugging noise.
- **1.2 is done** — intent routing and core conversation are fully implemented and tested.
- **1.3 and below are not implemented** — everything from file search onward is greenfield. OpenClaw, the compose panel, memory, sandbox, audit log — none of it exists yet.
- Fish Speech and Parakeet are not currently running.

So the revised view of what's actually left to build:

| Subphase | Status |
|----------|--------|
| 1.1 | ✅ Done (text-only, voice deferred) |
| 1.2 | ✅ Done |
| 1.3 — File search | 🔲 Not started |
| 1.4 — Email | 🔲 Not started |
| 1.5 — Calendar + browser | 🔲 Not started |
| 1.6 — Memory + briefing | 🔲 Not started |
| 1.7 — Sandbox + audit log | 🔲 Not started |
| 1.8 — Full integration | 🔲 Not started |

The foundation is solid. The intelligence layer works. Everything from here is building the actual workspace integrations and the safety layer on top of it.

---

## Repo Structure Discussion

The question came up: should Phase 1 get its own GitHub repo? The user has already been doing a pattern of separate repos for separate concerns — fish-speech lives separately, the report generator lives separately. Should this follow the same pattern?

**Recommendation: monorepo, don't split yet.**

The reasoning: in Phase 1, all the systems are too tightly coupled to safely separate. The desktop app calls the server, the server sends commands back to OpenClaw on the client, memory is shared across both sides of that connection. If those live in separate repos, you end up with versioning overhead, cross-repo PRs, and coordination friction before you've even proven the architecture works.

The components that are already separate — fish-speech, the report generator — are separate because they have a genuinely different release cadence and different concerns. Fish-speech is ML infrastructure. The report generator is a different product. Those separations make sense. The Seishin application stack doesn't have that same separation of concerns yet.

**Proposed directory structure for the monorepo:**

```
project-seishin/
  apps/
    desktop/          ← Electron or Tauri desktop app
    server/           ← Backend API: LLM routing, intent classification, SQL
  packages/
    openclaw/         ← The automation framework: file, email, calendar, browser
    memory/           ← Client-side memory store and retrieval
    shared/           ← Shared types, schemas, and utilities
  fish-speech/        ← Existing (keep as-is, separate concern)
  dataset_pipeline/   ← Existing
  docs/
  .planning/          ← GSD planning artifacts
```

Use pnpm workspaces if the stack is JavaScript/TypeScript, or Python packages with a `pyproject.toml` workspace if Python. Each package owns its own tests — no cross-package test dependencies.

**The rule for when to split into a separate repo:** only when a component has an independent release cadence, or when a different team owns it. Not before. Three similar things in one repo is fine. Premature repo splits create maintenance overhead that compounds with every new phase.

As the project grows into Phases 2–4, new connectors (Salesforce, S3) and the specialist agent system will become new packages in the same repo. That's the right time to think about workspace tooling and package boundaries — not now.

---

## Knowledge Organization and Tooling

The user asked whether to bring in Obsidian or another database system for organizing everything as the project gets bigger.

**Short answer: don't add Obsidhin as a project dependency.**

Obsidian is excellent personal knowledge management, but it's the wrong tool here. It's not version-controlled with the code, it's not queryable by AI, and it adds friction for anyone who doesn't have it installed. The information it would hold — architectural decisions, context, project state — is better kept closer to the code itself.

What's already in place is actually a complete system:
- `docs/PRODUCT_VISION.md` — the product truth, well-maintained and comprehensive
- `.planning/` with GSD — phase planning, task tracking, research, verification artifacts
- GitHub Issues — actionable bugs and tasks
- `CLAUDE.md` + the AI memory system — Claude's persistent context across sessions

The one gap worth filling: **Architecture Decision Records** in `docs/decisions/`. One markdown file per major architectural decision. The format is simple — what was decided, why, what alternatives were considered, what would change the decision. The cost is a few minutes per decision. The payoff is enormous: every time you revisit a decision in Phase 4 or Phase 6, you have the full context for why things are the way they are instead of having to reconstruct it from git history.

Example files that should exist there soon:
- `docs/decisions/001-monorepo-structure.md`
- `docs/decisions/002-electron-vs-tauri.md` (once that's decided)
- `docs/decisions/003-openclaw-execution-model.md`
- `docs/decisions/004-sandbox-before-write.md`

---

## Best Practices Summary

Everything distilled from the conversation into a set of principles to carry forward:

**1. Module boundaries over repo boundaries**
Clean interfaces between systems — enforced by types and contracts, not by physical distance in different repos. The boundary between the desktop app, the server, and OpenClaw should be as explicit as if they were in different repos, without the coordination overhead of actually being in different repos.

**2. Contract-first development**
Define the API between components before implementing either side. For Phase 1, this means: write out the interface between the server and OpenClaw (what commands does the server send? what format do results come back in?) before writing a line of either. This catches assumptions early and makes parallel development possible.

**3. One test suite per package**
Each package in the monorepo tests its own surface. No cross-package test dependencies. The integration test (1.8) lives at the top level and imports from all packages as a black-box consumer — same as any real user of those packages.

**4. ADRs in `docs/decisions/`**
Every non-obvious architectural decision gets a file. This isn't overhead — it's the thing that makes Phase 5 and Phase 6 not feel like archaeology.

**5. GSD phases stay granular**
The 1.3–1.8 split is the right unit size. Each subphase is one coherent thing with a clear test gate. Don't let phases balloon — the temptation is always to add "just one more thing" to a phase because it's related. Resist it. Small phases with clear gates mean you always know exactly where you are.

**6. Feature flags off by default**
Especially for OpenClaw write operations — email sending, file moves, calendar event creation. These should be gated behind a feature flag that defaults to off during development. This means you can ship the UI and the logic to testers before the full confirmation + sandbox flow is hardened, without any risk of accidental writes. Turn the flag on once the safety layer is verified.

**7. Voice layer last**
The current decision to defer voice (keep 1.1 as text-only) is correct. The intelligence has to be solid before you add the latency budget and debugging complexity of real-time audio. Voice is a presentation layer on top of the intent system — add it once you're confident in what's underneath.

---

## What Comes After Phase 1

For reference: Phase 1 ships a complete, standalone product. Every subsequent phase adds a new layer of capability on top of the proven foundation.

- **Phase 2** makes it company-specific — specialist agents for tax resolution, write file operations, calendar writes, bulk email, team access with RBAC
- **Phase 3** connects company systems — Salesforce, S3, the client portal DB, hybrid queries spanning all sources simultaneously
- **Phase 4** adds specialist agent expansion and hallucination checking — the phase where the product becomes genuinely transformative
- **Phase 5** goes mobile — WhatsApp integration, push notifications, proactive morning briefings to the phone
- **Phase 6** is full agentic orchestration — overnight prep, work ready to review when the user sits down
- **Phase 7** is enterprise hardening — admin dashboard, SOC 2, self-service one-command deployment

The decisions made in Phase 1 about module structure, confirmation patterns, sandbox behavior, and the contract between desktop and server will echo through all seven phases. Get them right here.

---

*Conversation date: April 19, 2026. Written up for device migration and future reference.*
