# Phase 1 Planning Discussion — April 19, 2026

## Current State

- **1.1 (Desktop App Shell + Voice Transport):** Text + LLM only for now. Voice layer deferred — easy to add later.
- **1.2 (Intent Routing + Core Conversation):** Done.
- **1.3 and below:** Not implemented. Everything from file search onward is greenfield.
- Fish Speech and Parakeet: not currently running.

---

## Phase 1 Subphases

| Subphase | What it builds | Test gate |
|----------|---------------|-----------|
| **1.1** | Desktop app shell + text LLM (voice deferred) | Round-trip text works, stable connection |
| **1.2** | Intent routing + core conversation ✅ | 90%+ classification accuracy, context carries across turns |
| **1.3** | File search — OpenClaw A | Finds files by name/type/date, cards render, open works |
| **1.4** | Email — OpenClaw B (Gmail + Outlook OAuth, compose panel, 5-min queue) | OAuth persists, draft quality passes, email delivers |
| **1.5** | Calendar + browser research — OpenClaw C | Calendar reads correctly, Chrome launches and navigates, summary returned |
| **1.6** | Client-side memory + session briefing | Memory survives restart, briefing accurate, recall doesn't hallucinate |
| **1.7** | Sandboxed workspace + audit log | Real files untouched until confirmed, every action logged |
| **1.8** | Full Phase 1 integration *(the milestone)* | Full Monday demo scenario passes clean, all 13 intents handled, no regressions |

**Risk flag:** 1.4 (email OAuth) can be a time sink due to Gmail/Outlook differences. Timebox it hard.

---

## Repo Structure Decision

**Recommendation: monorepo with clear module boundaries. Do not split into multiple repos yet.**

- Systems are too tightly coupled in Phase 1 to split safely
- Keep `fish-speech` separate (ML infra, different release cadence)
- Keep report generator separate (different product concern)
- Seishin application stack stays together

### Proposed structure

```
project-seishin/
  apps/
    desktop/        ← Electron/Tauri app
    server/         ← Backend API (LLM, intent, SQL)
  packages/
    openclaw/       ← File, email, calendar, browser automation
    memory/         ← Client-side memory store
    shared/         ← Types, schemas, shared utilities
  fish-speech/      ← existing (keep as-is)
  dataset_pipeline/ ← existing
  docs/
  .planning/
```

Use pnpm workspaces or Python packages per the stack. Each package has its own tests.

**When to split into a separate repo:** Only when a component has an independent release cadence or a different team owns it.

---

## Knowledge Organization

**Don't add Obsidian as a project dependency.** It's personal PKM — not version-controlled with the code, not queryable by the AI.

What's already in place is sufficient:
- `docs/PRODUCT_VISION.md` — product truth
- `.planning/` (GSD) — phase planning, tasks, research
- GitHub Issues — bugs and actionable tasks
- `CLAUDE.md` + memory system — AI context

**One gap to fill:** Add `docs/decisions/` — one markdown file per major architectural decision (ADR pattern). Cost: nothing. Payoff: every Phase 4+ revisit has context.

---

## Best Practices

1. **Module boundaries over repo boundaries** — clean interfaces enforced by types, not distance
2. **Contract-first** — define the API between desktop/server/OpenClaw before implementing either side
3. **One test suite per package** — each package tests its own surface
4. **ADRs** — `docs/decisions/` for every non-obvious architectural decision
5. **GSD phases stay granular** — the 1.3–1.8 split is the right unit size; don't let phases balloon
6. **Feature flags off by default** — especially for OpenClaw write operations; ship safely to testers before the full confirmation flow is hardened
