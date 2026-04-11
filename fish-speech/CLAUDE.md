<!-- GSD:project-start source:PROJECT.md -->
## Project

**Fish Speech S2-Pro Optimization**

Fresh rebuild of Fish Speech S2-Pro inference server with INT8 quantization, torch.compile, and TF32 precision optimizations. Targets ~9.74GB VRAM and ~0.20x RTF (5x faster than real-time) on RTX 5090.

**Core Value:** The optimized server must produce identical voice quality to upstream while using <10GB VRAM and achieving RTF under 0.5x.

### Constraints

- **GPU memory**: Must not start any local LLM servers — GPU dedicated to this task
- **Approach**: One step at a time. Test and verify each step before moving on.
- **Fidelity**: Follow CHANGES.md log but can improvise fixes as needed for the current environment
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
