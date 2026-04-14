# Claude Code Standards

**Note**: This file contains global standards for all Claude Code work. For Nexus Engine-specific information (system architecture, Docker configuration, VAD specification), see `NEXUS_ENGINE.md`.

---

## Workflow
- Use plan mode for any task with 3+ steps. Stop and re-plan when approach diverges.
- Use plan mode for verification steps too, not just building.
- Launch subagents for research and parallel work. One clear task per subagent.
- For complex problems, throw more compute at it — more subagents, more parallel analysis.
- Break complex tasks into phases. Complete and verify each phase before moving on.
- When stuck for more than 2 attempts, step back and reassess the approach entirely.

## Quality Gates
- Verify every change works before marking done. Run tests, check logs, diff behavior against main when relevant.
- For non-trivial changes: "Would a staff engineer approve this?" If not, improve it.
- For non-trivial changes: pause and ask "is there a more elegant way?" If a fix feels hacky: "Knowing everything I know now, implement the elegant solution."
- Fix bugs autonomously — point at logs, errors, failing tests and resolve them. Zero context switching required from the user.
- Prefer root cause fixes over symptom patches. Temporary fixes become permanent debt.

## Compound Learning & Self-Improvement
- After any correction: capture the pattern as a lesson (what went wrong, why, rule for future).
- After task completion: if a non-obvious approach worked well, capture it.
- Store lessons in `~/.claude/lessons.md` (global) and `.claude/lessons.md` (per-project).
- Review relevant lessons at the start of each task to avoid repeating mistakes.
- **Self-updating**: Skills, this CLAUDE.md, and lessons files update themselves automatically.
  - When a skill has a gap that caused rework, update the skill directly.
  - When a principle here proves wrong or incomplete, update it.
  - When a lesson has been absorbed into a skill or this file, remove it from lessons.
  - Prune stale lessons. Resolve contradictions. No manual maintenance required.

## Core Principles
- Simplicity first. The right amount of complexity is what the task actually requires.
- Minimal blast radius. Small, focused changes over sweeping rewrites.
- No laziness: never use `// rest of code here` or `TODO: implement later`.
- No unnecessary abstraction. Three similar lines beat a premature helper function.
- Read before writing. Understand existing patterns before proposing changes.

## Decision Autonomy
- **Green (act freely):** Reading files, running tests, installing deps, writing code, local git commits.
- **Yellow (announce then act):** Deleting files, creating branches, pushing to remote, structural refactors.
- **Red (ask first):** Force pushes, dropping data, modifying CI/CD, actions affecting others, anything irreversible at scale.

## Git
- Push after non-trivial changes. General commit messages describing what changed.
- No co-author tags. No specific numbers or counts in commit messages.
- Never commit secrets, tokens, or credentials. Check before every commit.
- Prefer new commits over amending. Never force-push without explicit permission.
- No temporal or versioned file names: never create `fix-v2.md`, `new-approach.md`, `temp-fix.js`, `backup-old.ts`. Edit the original file.

## Security
- Scan for secrets before commits: API keys, tokens, passwords, connection strings.
- Validate at system boundaries only. Trust internal code and framework guarantees.
- Follow OWASP top 10 awareness. Fix security issues immediately when spotted.

## Communication
- Lead with the answer or action. Skip preamble and unnecessary transitions.
- Show decisions that need input, status at milestones, and blockers that change the plan.
- If you can say it in one sentence, don't use three.

<!-- GSD:project-start source:PROJECT.md -->
## Project

Project not yet initialized. Run /gsd-new-project to set up.
<!-- GSD:project-end -->

<!-- GSD:stack-start source:STACK.md -->
## Technology Stack

Technology stack not yet documented. Will populate after codebase mapping or first phase.
<!-- GSD:stack-end -->

<!-- GSD:conventions-start source:CONVENTIONS.md -->
## Conventions

Conventions not yet established. Will populate as patterns emerge during development.
<!-- GSD:conventions-end -->

<!-- GSD:architecture-start source:ARCHITECTURE.md -->
## Architecture

Architecture not yet mapped. Follow existing patterns found in the codebase.
<!-- GSD:architecture-end -->

<!-- GSD:skills-start source:skills/ -->
## Project Skills

No project skills found. Add skills to any of: `.claude/skills/`, `.agents/skills/`, `.cursor/skills/`, or `.github/skills/` with a `SKILL.md` index file.
<!-- GSD:skills-end -->

<!-- GSD:workflow-start source:GSD defaults -->
## GSD Workflow Enforcement

Before using Edit, Write, or other file-changing tools, start work through a GSD command so planning artifacts and execution context stay in sync.

Use these entry points:
- `/gsd-quick` for small fixes, doc updates, and ad-hoc tasks
- `/gsd-debug` for investigation and bug fixing
- `/gsd-execute-phase` for planned phase work

Do not make direct repo edits outside a GSD workflow unless the user explicitly asks to bypass it.
<!-- GSD:workflow-end -->

<!-- GSD:profile-start -->
## Developer Profile

> Profile not yet configured. Run `/gsd-profile-user` to generate your developer profile.
> This section is managed by `generate-claude-profile` -- do not edit manually.
<!-- GSD:profile-end -->
