# Seishin — Product Vision, Architecture & Roadmap

> Full guide capturing everything: what we built, where we're going, the pivot, the market research, the architecture, the business case, and the agentic workflow vision. Written April 2026.

---

## Table of Contents

1. [What Seishin Is](#1-what-seishin-is)
2. [What We've Built So Far](#2-what-weve-built-so-far)
3. [OpenClaw Research](#3-openclaw-research)
4. [The Product Pivot](#4-the-product-pivot)
5. [Market Research](#5-market-research)
6. [Use Cases — Tax Firm](#6-use-cases--tax-firm)
7. [Technical Architecture](#7-technical-architecture)
8. [Model Setup](#8-model-setup)
9. [The Agentic Workflow Vision](#9-the-agentic-workflow-vision)
10. [Business Case](#10-business-case)
11. [Billing & Pricing](#11-billing--pricing)
12. [Full Roadmap](#12-full-roadmap)
13. [What I Think](#13-what-i-think)

---

## 1. What Seishin Is

Seishin is a real-time voice AI companion that lets users speak naturally to retrieve business data, manipulate it, and take action on it — all through a voice interface, with responses delivered in a natural AI voice.

The original core pipeline:

```
User speaks on laptop
  -> whisper.cpp (local ASR) transcribes
  -> WebSocket to server
  -> Gemma 4 27B (local vLLM) classifies intent + generates response
  -> Fish Speech TTS converts text to audio
  -> Audio streamed back to laptop
```

On top of that: a report pipeline where natural language queries get turned into SQL by Claude Haiku, run against a business database, and the results voiced back — with the ability to filter, sort, aggregate, and manipulate the data through follow-up voice commands without re-querying the database.

---

## 2. What We've Built So Far

### Current Tech Stack

| Component | What it does | Model / Tech | Where it runs |
|-----------|-------------|--------------|---------------|
| Client app | Voice capture, playback | Tauri (Rust) | User's laptop |
| ASR | Audio to text | Parakeet TDT (cloud endpoint currently) | Cloud — Phase 8 moves to VPC |
| Intent classification | Classifies what user wants | Gemma 4 27B NVFP4 via vLLM | Local RTX 5090 |
| Conversation / personality | Miyako persona, natural responses | Gemma 4 27B NVFP4 via vLLM | Local RTX 5090 |
| SQL generation | NL to SQL for reports | Claude Haiku 4.5 | Anthropic cloud |
| Report manipulation | Filter, sort, aggregate on cached data | CacheExecutor (pure pandas) | Server, no LLM |
| TTS | Text to voice audio | Fish Speech S2 Pro INT8 | Local RTX 5090 |

### Phases Completed

- **Phase 10**: LLM-native intent detection — replaced regex with Gemma guided_json
- **Phase 11**: Session cache + LLM-guided data operations — 9 op types via pandas, no re-querying DB on follow-ups, 81 tests passing
- **Phase 11.1**: Natural language UX hardening — 8 features, 114 tests passing

### Intent System (9 Intents)

| Intent | Trigger | What happens |
|--------|---------|-------------|
| `new_data_request` | "show me clients" | Pulls fresh report from DB |
| `follow_up_on_previous` | "filter to VIP" | Applies op to cached data via pandas |
| `compare_reports` | "compare clients with invoices" | Concurrent dual fetch then cross-report merge |
| `undo` | "go back", "undo that" | TTL-aware restore from 5-op stack |
| `what_can_i_ask` | "what data do you have?" | Queries report API for available topics |
| `list_cached_data` | "what did I pull?" | Voices active session reports |
| `confirm` | "yes", "do it" | Executes pending suggestion spec |
| `cancel` | "never mind" | Clears pending spec |
| `normal_chat` | everything else | Conversation |

### Session Cache — How Follow-ups Work

When a report is delivered, the rows, column metadata, SQL, and query are stored in a SessionCache per session. Follow-up voice commands ("sort those by amount", "only show paid ones", "top 5") run through CacheExecutor — pure pandas operations, no LLM, no DB call, sub-100ms response. Results are cached as a new report enabling unlimited chaining. Session cache holds up to 10 reports, evicts by TTL (10 min), supports cross-report compare when two reports share a join column.

---

## 3. OpenClaw Research

### What OpenClaw Is

https://openclaw.ai/ — open-source personal AI assistant, 350K+ GitHub stars, one of the fastest growing open-source projects ever. Created by Peter Steinberger in late 2025. Now stewarded by a non-profit after Steinberger joined OpenAI.

Core concept: A local-first AI agent gateway that runs as a permanent daemon on your machine and connects to any messaging platform as its UI. You chat to it on WhatsApp, it executes on your computer.

### Capabilities

- Full filesystem read/write + shell execution
- Email — Gmail, Outlook via Microsoft Graph OAuth (production-ready, already built)
- Browser control + web scraping
- Calendar — Google Calendar, Outlook
- 4,000+ community skills on ClawHub marketplace
- Persistent memory (SOUL.md, AGENTS.md workspace config)
- Self-writes and hot-reloads its own skills
- Supports Claude, GPT, Gemini, local LLMs interchangeably

### Architecture

- TypeScript/Node.js daemon on port 18789
- Skills are SKILL.md markdown files in ~/.openclaw/workspace/skills/
- Install: npm install -g openclaw@latest && openclaw onboard
- Sandboxing: sandbox.mode "non-main" runs non-main sessions in Docker with configurable tool allowlists

### Security Note

Cisco found a third-party ClawHub skill performing data exfiltration via prompt injection. For enterprise: use only verified skills, Docker sandbox mode, no ClawHub marketplace access — company-controlled skill whitelist only.

### Why It Fits

OpenClaw handles the hard parts of office automation already. Seishin provides the voice layer OpenClaw doesn't have. The integration is a bridge: Seishin's server sends tool_call JSON to OpenClaw's sessions API, OpenClaw executes locally, result comes back.

---

## 4. The Product Pivot

### Why We Pivoted

Amazon released Quick Suite — AWS's agentic AI platform connecting to 90+ data sources, 1,000+ MCP integrations, agentic automation, being deployed to 120,000+ users (DXC Technology). It directly competes with "voice + database search."

### What The Product Becomes

A personal AI agent per user with two domains:

**Personal domain** — the user's own laptop files, email, calendar, local documents

**Company domain** — permission-gated access to Salesforce, S3, databases, practice management, SharePoint

The agent unifies both. One voice command spans both simultaneously:

> "Pull up everything we have on the Martinez estate case"

Hits Salesforce for the case record, S3 for attached documents, searches local machine for local copies, checks email thread — returns a unified view voiced back naturally. That does not exist anywhere right now.

### Why This Is Different From Quick Suite

| | Amazon Quick Suite | Our product |
|--|--|--|
| How it works | Copies data into AWS vector index | Queries original sources on demand, returns results |
| Where data lives at rest | AWS cloud (replicated, indexed) | Original systems (S3, Salesforce, laptop) |
| Privacy model | Trust AWS | Nothing stored — stateless query |
| Local laptop access | No | Yes — OpenClaw |
| Voice interface | No | Yes |
| Who acts | Autonomous | User says go |
| Compliance burden | AWS BAA, data residency reviews | Lighter — querying existing authorized systems |
| Personal + company unified | No | Yes |

**The key distinction:** Quick Suite ingest-index-search vs our query-on-demand-return-forget. For a tax firm handling client SSNs and financial data, putting that into an AWS vector store triggers IRC Section 7216, IRS Publication 1075, and the FTC Safeguards Rule. Querying S3 and Salesforce on-demand using existing IAM credentials is a completely different compliance conversation.

### The Pitch

"Quick Suite puts your company's data in Amazon's cloud and lets an AI act on your behalf. We give each person on your team their own private AI assistant that lives on their computer, knows their cases and their email, and only acts when they say so by voice. For tax professionals handling client financial data, that's not a nice-to-have — it's a requirement."

---

## 5. Market Research

### Market Size

- AI in accounting market: $10.9B in 2026, 44.6% CAGR toward $68.75B by 2031
- Tax preparation services TAM: $36.9B in 2026
- AI adoption in accounting: jumped from 9% to 41% in a single year (2024-2025)
- Voice AI market: $47.5B by 2034 (34.8% CAGR)
- Voice AI adoption in finance: 11% despite 91% overall AI adoption — massive gap

### Competitor Landscape

| Competitor | Price | Key Limitation |
|-----------|-------|----------------|
| Thomson Reuters CoCounsel | $75-500/user/mo | Locked to TR ecosystem, no voice |
| Harvey AI | $1,000-1,200/user/mo, 20-seat min ($288K/yr entry) | Absurdly expensive, legal-only, no voice |
| TaxGPT | ~$1,600/user/yr | Research-only, text-only |
| Intuit Assist | Bundled | Locked to Intuit ecosystem, limited prompts, no voice |
| Canopy Tax | ~$142/user/mo | AI features nascent, no voice |
| TaxDome | $50-83/user/mo | Analytics dashboards only, minimal AI |
| Microsoft Copilot for Finance | $18-30/user/mo | Requires enterprise ERP stack, not tax-specific, no voice |
| Glean | ~$45-65/user/mo, $60K minimum | Not vertical-specific, no voice, expensive |

### The White Space

No competitor has a voice-first interface for tax professionals. Every product is text/GUI-based. Voice in finance sits at 11% adoption despite 91% AI adoption overall. The 5-50 person tax firm has no affordable, AI-native, voice-first assistant connected to their actual data.

### Pain Points (Data)

- 60% of accountants spend too much time on manual tasks (Dext survey)
- Knowledge workers spend 8-10 hours/week searching for information (McKinsey)
- Accountants spend ~25% of workweek on repetitive data retrieval
- Thomson Reuters: 60-70% time reduction in multi-jurisdiction tax returns using AI
- 56% of CEOs report zero measurable ROI from AI despite record spending (PwC, Jan 2026) — the rework problem

### Key Compliance Requirements for Tax Firms

- **IRC Section 7216** — Client data can only be used for tax prep; any other use requires explicit written consent
- **IRS Publication 1075** — Strengthened controls for all Federal Tax Information recipients
- **IRS Publication 4557** — Mandatory Written Information Security Plan (WISP)
- **FTC Safeguards Rule** — Tax preparers classified as covered financial institutions
- **SOC 2 Type II** — Not legally required but expected by firms for vendor due diligence

---

## 6. Use Cases — Tax Firm

### Executive / Managing Partner

- "How many active cases do we have, broken down by stage?"
- "Which clients haven't paid invoices over 60 days? Draft gentle follow-up emails to each one"
- "Compare case volume this month vs last month — are we ahead or behind?"
- "Who are our top 20 clients by revenue this year?"
- "Find the engagement letter for Meridian Holdings"
- "How many returns have we filed this quarter vs same time last year?"
- "Which staff members have the most cases in review right now?"
- "Draft a partner update on our Q1 throughput and send it to the team"
- "Any clients with IRS notices that haven't been responded to?"
- "What's our projected revenue for this month based on open invoices?"

### Tax Document Reviewer

- "Pull up everything we have on file for the Johnson case"
- "Is the W-2 from Metro Construction in the system yet?"
- "Show me all cases missing a signed engagement letter"
- "Which cases have been sitting in review for more than 5 days?"
- "Compare the 1099-NEC income on file against what the client reported"
- "Flag the Martinez case as needing amended return, add a note"
- "List all Schedule C filers from this quarter who claimed home office"
- "Find all cases where we received an IRS notice in the last 30 days"
- "Which clients still haven't sent their bank statements?"
- "Show me all business returns where depreciation schedules are missing"
- "Pull last year's return for Peterson so I can compare carryovers"

### Tax Form Preparer / Filer

- "What documents are on file for client Ramirez? What are we still waiting on?"
- "What did we claim for their home office deduction last year?"
- "What's the filing deadline for the Chen extension?"
- "Has anyone reviewed the Kapoor return yet or is it still in prep?"
- "Show me all clients whose extensions are due in the next 2 weeks"
- "Pull prior year carryover losses for all S-Corp clients"
- "Which returns are ready to file but haven't been sent to the client for signature?"
- "How many amended returns are in progress right now?"
- "Mark the Williams return as ready for partner review"
- "Are there any e-file rejections from today I need to fix?"
- "Draft a document request email to the Santos family — they're missing their 1099-DIV and brokerage statement"

---

## 7. Technical Architecture

### Laptop App — Thin Client

The Seishin client is already a Tauri app (seishin-client/src-tauri/). With the pivot it becomes purely a thin client — no models running locally.

```
LAPTOP APP (~50MB installer)
- Silero VAD (2MB, CPU) — detects speech start/end, avoids streaming silence
- Audio streamer — PCM to WebSocket to AWS, audio frames back
- OpenClaw daemon (bundled in installer) — local file/email/calendar
- SSO login — company credentials
```

VAD stays local because it's 2MB, runs on CPU, and prevents streaming silence. Everything else goes to AWS. Audio streaming to the company's VPC is no different from any other company data going to AWS — same perimeter.

IT deployment: push via Jamf (Mac) or Intune (Windows). No user setup beyond SSO login.

### AWS Architecture — Company's VPC

```
COMPANY AWS ACCOUNT (VPC)

ALB + WebSocket endpoint
  Receives audio stream from laptop apps

EC2 g5.xlarge (A10G 24GB GPU) — shared inference
  Parakeet TDT 0.6b v2 (ASR) — audio to text, ~1GB VRAM
  Fish Speech S2 Pro INT8 (TTS) — text to audio, ~4GB VRAM

Amazon Bedrock
  Claude Haiku 4.5 — intent classification, SQL generation, email drafting
  Claude Sonnet 4.5 — conversation, personality, complex multi-step planning

Lambda functions — connector orchestration, permission checks

Company's existing infrastructure (no changes needed)
  S3 — documents, case files
  Salesforce — cases, contacts, tasks
  RDS/Aurora — databases
  SharePoint / Google Drive
```

### How Local File Operations Work

OpenClaw runs as a background daemon on the user's laptop (bundled in installer). When the server needs a local operation, it sends a structured message back over the WebSocket:

```json
{"type": "tool_call", "tool": "find_file", "params": {
  "query": "Martinez engagement letter",
  "paths": ["~/Documents", "~/Downloads"]
}}
```

OpenClaw executes, returns:

```json
{"type": "tool_result", "files": [{
  "name": "Martinez_EL_2025.pdf",
  "path": "~/Documents/Cases/Martinez/",
  "modified": "2025-03-14"
}]}
```

Server voices the result: "Found it — Martinez engagement letter, in your Cases folder, last modified March 14th."

For email and calendar: same pattern. OpenClaw holds Gmail/Outlook OAuth tokens on the laptop. Server tells it what to draft. User confirms by voice. OpenClaw sends.

### BYOC (Bring Your Own Cloud) Deployment

```bash
cdk deploy SeishinStack \
  --context company=acme-tax \
  --context s3_bucket=acme-documents \
  --context salesforce_org=https://acme.salesforce.com \
  --context sso_provider=okta
```

Everything runs in the company's AWS account — their VPC, their encryption keys, their CloudTrail. AI models access S3 and RDS via existing IAM roles. AWS bill on their existing invoice. Security team reviews a CDK stack, not a SaaS vendor.

### Intent Routing

| User says | Intent | Execution |
|-----------|--------|-----------|
| "Find the engagement letter I saved last week" | LOCAL | OpenClaw on laptop |
| "Pull up all Q1 invoices over $10k" | COMPANY_DATA | Report pipeline to DB |
| "Get everything we have on the Martinez case" | HYBRID | Salesforce + S3 + local search |
| "Draft a follow-up to the client" | LOCAL | OpenClaw drafts, user confirms |
| "What documents are we missing for this case" | HYBRID | Salesforce checklist vs S3 vs local |

---

## 8. Model Setup

### Full Model Map

| Task | Model | Where | Approx cost/query |
|------|-------|-------|-------------------|
| Audio to text | Parakeet TDT 0.6b v2 | EC2 g5.xlarge (VPC) | ~$0 fixed |
| Intent classification | Claude Haiku 4.5 via Bedrock | Managed | ~$0.001 |
| Conversation / personality | Claude Sonnet 4.5 via Bedrock | Managed | ~$0.003 |
| SQL generation | Claude Haiku 4.5 via Bedrock | Managed | ~$0.005 |
| Email drafting | Claude Haiku 4.5 via Bedrock | Managed | ~$0.008 |
| Multi-step planning | Claude Sonnet 4.5 via Bedrock | Managed | ~$0.015 |
| Report manipulation | CacheExecutor (Python/pandas) | Server | $0 |
| Text to audio | Fish Speech S2 Pro INT8 | EC2 g5.xlarge (same GPU) | ~$0 fixed |
| File / email / calendar | OpenClaw | User's laptop | $0 |

### Why Bedrock Over Self-Hosted Gemma

Gemma 4 is not on Bedrock. For the enterprise BYOC model, Bedrock is recommended because:
- No GPU management for the LLM tier
- Scales automatically
- The company doesn't need a dedicated GPU just for LLM (only for ASR + TTS on g5.xlarge)
- Claude on Bedrock supports structured output via tool_use, replacing guided_json

### Cost Estimate — 20-User Tax Firm

| Component | Monthly |
|-----------|---------|
| EC2 g5.xlarge spot (8hr/day weekdays) — Parakeet + Fish Speech | ~$72 |
| Bedrock Claude Haiku (intent, SQL, email — high volume) | ~$80 |
| Bedrock Claude Sonnet (conversation — lower volume) | ~$120 |
| ALB + API Gateway + Lambda + networking | ~$50 |
| **Total AWS cost** | **~$320/mo** |
| **Per user** | **~$16/user/mo** |

Charge $99-149/seat — 85-90% gross margin.

---

## 9. The Agentic Workflow Vision

### What This Is

Not a query tool. Not a chatbot. An AI chief of staff that:
1. Knows what needs to happen today (reads calendar, tickets, emails, case statuses)
2. Works through it step by step
3. Executes reads automatically without interrupting the user
4. Pauses and confirms before any permanent action
5. Keeps the human as the decision-maker on everything that matters

**The rule: reads are free, writes require a voice confirmation.**

### The Morning Flow

```
Agent reads (no approval needed):
  calendar events, open tickets, unread emails,
  outstanding case tasks, upcoming deadlines

Agent presents:
  "Good morning. You have 4 meetings today.
   Your highest priority: the Wilson estate case
   has a deadline Friday and we're still missing
   the trust amendment. You have 23 emails — 3
   need responses today. Want me to start on Wilson?"

User: "Yeah"

Agent works through steps, surfaces action:
  "I found Sarah Wilson's email from Tuesday where
   she said she'd send it yesterday. Here's a
   follow-up draft — want me to read it?"

User: "Read it"    ->    Agent reads it.

User: "Send it"    ->    Agent sends. Logs it. Moves on.

  "Sent. You have the Peterson call in 45 minutes.
   Want me to pull their prep summary?"
```

### The Full Workflow Loop

```
MORNING KICK-OFF
  Read: calendar, open tickets, unread emails, case deadlines
  Plan: Claude Sonnet builds prioritized daily task list
  Present: "Here's your day. Want to start with X?"

FOR EACH TASK
  Decompose into atomic steps (read vs write)
  Execute read steps automatically (no interruption)
  On write step: pause, one-sentence summary to user
    "Sending follow-up to Sarah Wilson — yes?"
  User confirms/modifies/skips by voice
  Execute, log to audit trail
  Move to next step

STATE MANAGEMENT
  Current task + completed steps persisted
  If session interrupted, resume on reconnect:
    "Welcome back. You were working on the Wilson case.
     We'd just sent the trust amendment follow-up.
     Want to continue?"
  Audit log: every action, timestamp, who approved
```

### Example — The Full Loop

User: "Pull up everything we have on the Martinez estate case and tell me where we stand"

Agent:
1. Queries Salesforce — case record, status, assigned staff, task list
2. Queries S3 — lists documents sorted by date
3. Searches local machine — any local Martinez files
4. Checks email thread — last 3 emails with client
5. Cross-references Salesforce document checklist vs S3 contents

Result voiced back:
> "The Martinez estate case is in review stage, assigned to you and Lisa. We have 12 documents in S3 — the will, trust agreement, 3 years of returns, and various supporting docs. We're missing the 2024 brokerage statement and the amended trust from March. Lisa emailed the client about both on Tuesday and hasn't heard back. Your last call with them was April 2nd. Want me to draft a follow-up?"

That interaction replaced:
- Opening Salesforce (2 min)
- Navigating to case documents in S3 (3 min)
- Searching local files (2 min)
- Checking email thread (3 min)
- Cross-referencing checklist (5 min)

**15 minutes → 30 seconds.**

### Workflow Types for a Tax Firm

**Morning briefing**
"Here's what's on today: 3 client calls, 5 open cases due this week, 12 emails needing responses. Highest priority is the Wilson estate — deadline Friday, missing the trust amendment. Want to start there?"

**Case prep before a call**
"Your 10am call is with Martinez in 22 minutes. I've pulled the case file. Last contact was 2 weeks ago — you sent a document request. They've uploaded their W-2 and 1099-INT since then. Still missing the Schedule K-1 from their S-Corp. I've drafted a quick reminder. Want me to send it before the call?"

**Document processing**
When a client emails documents: "Sarah Johnson just sent 4 attachments — W-2, 1099-DIV, mortgage interest statement, and a document I don't recognize. I've filed the first three to the Johnson case in S3. The fourth looks like it might be a K-1. Want me to flag it for review?"

**Communication management**
"You have 19 unread emails. 3 need action today: the IRS notice for Peterson needs a response by Thursday, the Chen family is asking about their refund status, and your 2pm is asking to reschedule. Want me to handle the reschedule?"

**Deadline monitoring**
"Heads up: 3 extension deadlines this Friday — Peterson, Chen, and the Westbrook Trust. All three have returns in prep. Peterson's is furthest along and needs partner review. Want me to flag it?"

### Why "User Orchestrates" Is Right For Professional Services

A CPA's professional liability insurance requires human judgment on every action. "The AI did it without my approval" is not a legal defense for a licensed professional. But "I approved each step, here's the audit log showing my voice confirmation" is completely defensible.

The confirmation gate isn't just a safety feature — it's a liability and compliance feature. Enterprise buyers in professional services will specifically ask "who approved the action?" You need a clear answer.

### What's Technically Needed

**Planning layer** — Claude Sonnet ingests full context (calendar + open tickets + emails + case statuses) and builds a prioritized daily task list. One large-context call.

**Task decomposition** — Each task broken into steps labeled read or write. Agent executes reads silently, queues writes for confirmation.

**State persistence** — Task state, completed steps, pending confirmations stored server-side. Session interrupted → reconnects → resumes from exact position.

**Confirmation UX** — One sentence, one-word confirm. Target under 5 seconds per confirmation. Voice makes this fast — a spoken "yes" is 0.5 seconds.

**Undo for write actions** — Email saved to drafts for 30 seconds before actual send. File moves go to staging location before final placement. Every write logged with prior state for recovery.

---

## 10. Business Case

### ROI Math

For a 20-person tax firm, each person saves 2 hours/day of prep and admin:

- 20 people x 2 hours/day x 250 working days = 10,000 hours/year recovered
- At $50/hr loaded cost = $500,000/year in recovered capacity
- Cost: $149/seat x 20 users = $35,760/year
- **ROI: 14x**

That's what closes enterprise deals.

### Who Buys This

**Beachhead:**
- 5-50 person tax / accounting firms — completely underserved by Quick Suite ($288K/yr min) and TaxGPT (research-only)
- Firms already on AWS — BYOC model eliminates security review
- Professional services broadly — same document-heavy, case-centric workflow

**Expansion:**
- Legal (same workflow, same document pain)
- Insurance claims (same pattern)
- Real estate (transaction management, document chasing)

### The Moat

Once connected to a firm's Salesforce, S3, and database, switching cost is enormous. Query history, trained compound request patterns, SQL templates for their specific schema — deeply sticky. Not a tool they swap without significant disruption.

### Honest Risks

**Enterprise sales cycles are slow.** 3-6 months from demo to contract is normal.

**Database connector work doesn't scale without a self-service setup wizard.** Fine for 3 pilot customers. For 30, need guided onboarding.

**IRC Section 7216 consent process.** Before any client data touches your systems, the firm needs client written consent. You need to provide the template language and compliance framework.

**Confirmation UX must be fast.** If confirmations feel like bureaucracy, users disable the agent for routine tasks. Build around voice rhythm — one sentence summary, one-word confirm.

**SQL generation needs transparency.** Wrong query = wrong data = bad decision. Every report must show the SQL that ran.

---

## 11. Billing & Pricing

### Tiers

| Tier | Price | Included | Target |
|------|-------|----------|--------|
| Starter | $49/seat/mo | 150 voice mins, 5 users max, email + file ops, standard connectors | Solo / small firm |
| Professional | $99/seat/mo | 400 voice mins, 25 users, all connectors, audit logs, SSO | Mid-size 10-50 people |
| Enterprise | Custom ($150-250/seat) | Unlimited, on-premise option, dedicated support, custom connector build | Large firm / software vendor |

Annual discount: 20%.

At $99/seat, a 20-person firm pays ~$24,000/year. Less than one month of a junior associate's salary. If the agent saves 1 hour/day per person, it pays for itself in the first week of January.

### Billing Stack

- **Stripe** — payments, card processing, subscriptions
- **Lago** (open source, self-hosted) — usage metering, tracks voice minutes per user per session, invoice generation
- App emits usage event to Lago on every session end: `{user_id, duration_seconds, queries_made, emails_sent}`
- Enterprise: PO-based invoicing, net-30 terms

### Billing Pages

1. `/pricing` — three-tier cards, annual/monthly toggle, feature comparison, "Start free trial" CTA
2. `/onboarding` — connector setup wizard (which DB, which email, SSO config), 14-day trial starts
3. `/dashboard/billing` — current plan, usage this month, invoice history, upgrade button
4. `/dashboard/usage` — per-user breakdown, query volume, most-used features, cost per query (shows their ROI)
5. `/admin` — user management, roles, approved skills list, audit log export, data source config

### No Freemium

14-day free trial, credit card required. Converts 25-35% vs 3-5% for freemium. Professional services buyers want to evaluate seriously, not play around.

---

## 12. Full Roadmap

### Current State (April 2026)

Phase 11.1 complete. 114 tests passing. Waiting on AWS G-quota for Phase 7.

### Near Term — Infrastructure

**Phase 7: Cloud GPU**
Move Gemma 4 to EC2 g6e.xlarge (L40S) in company VPC. Start/stop scripts for ~$0 idle cost. Can demo from anywhere.

**Phase 8: ASR in VPC** *(critical for enterprise sales)*
Move Parakeet TDT 0.6b v2 to EC2 g5.xlarge in company VPC. Audio stays in company's AWS account. Closes the last privacy gap before enterprise sales.

**Phase 9: Voice quality**
Fish Speech quality polish (top-p 0.7, ffmpeg post-filter).

**Phase 12: Demo Readiness**
README-DEMO.md, 3 rehearsed end-to-end demos, cold start under 5 minutes, zero 429 errors. Can walk into a tax firm and demo live on their laptop with zero setup friction.

### Product Build

**Phase 13: OpenClaw Integration**
- OpenClaw bundled in laptop installer
- New WebSocket message types: tool_call / tool_result
- New intents: draft_email, find_file, move_file, get_calendar, morning_briefing
- Gmail + Outlook OAuth via OpenClaw (already production-ready in OpenClaw)
- File search via ripgrep/fd
- Confirmation gate: email NEVER sends without explicit voice "yes", no exceptions

**Phase 14: Company Data Connectors**
- Salesforce connector (read-only: cases, contacts, tasks, documents)
- AWS S3 connector (list objects by prefix, download metadata, permission-scoped)
- Permission layer: SSO + IAM role mapping + per-query permission checks
- Unified result merger: combines local + company results into one voiced response
- Audit log: every query, every data source touched, every action

**Phase 15: Enterprise Safety Layer**
- Admin dashboard — web UI for IT: user provisioning, role management, approved skills, usage stats
- SSO/SAML — Okta, Google Workspace, Microsoft Entra
- SQL transparency — every report shows exact query, voice command "show me the query"
- CDK stack for BYOC deployment
- Skill whitelist — no ClawHub for enterprise, company-controlled only

**Phase 16: Agentic Workflow Orchestration**
- Morning briefing: reads calendar + tickets + emails, builds prioritized daily plan
- Task decomposition engine: breaks each task into read/write steps
- State machine: tracks workflow progress, persists across sessions
- Confirmation protocol: standardized voice gate for all write actions
- Session resume: picks up exactly where left off
- Undo for write actions: email draft grace period, file staging

**Phase 17: Tax Domain Specialization**
- Tax-specific vocabulary: 1040, Schedule C/E/K, NOL, PTIN, IRS notice numbers
- Deadline engine: IRS tax calendar embedded, extension tracking, proactive alerts
- Document classifier: W-2, 1099-NEC, K-1, engagement letter, bank statement
- Connector library: TaxDome, Canopy, Drake, ProConnect, CCH Axcess, QuickBooks Online
- Case status vocabulary mapped to their practice management system

**Phase 18: Multi-User & Team Features**
- Multiple concurrent sessions (currently single-session only)
- Per-user isolation: each user has own cache, history, undo stack
- Role-based access: partners see everything, staff see assigned clients only
- Team briefing: portfolio-level stats for daily standup

**Phase 19: Billing & Packaging**
- Stripe + Lago usage metering live
- Three pricing tiers
- 14-day trial flow
- CDK deployment wizard: company connects their AWS account, configures data sources, provisions users

### Go to Market

**Pilot phase** (start now, run alongside build)
- 2-3 tax firms, $500-1000/month flat
- Manual setup, hands-on
- Watch how they actually use it
- Use learnings to build the connector setup wizard and self-service onboarding

**Productize**
- Self-service onboarding from pilot learnings
- Case studies that close the next customers

**Scale**
- Vertical expansion: legal, insurance, real estate
- White-label for accounting software vendors
- Enterprise integration partnerships (Thomson Reuters, Intuit)

---

## 13. What I Think

This is a real product with a real market. The combination that nobody else has:

1. **Voice-first** — 11% adoption in finance despite massive AI spending. The gap is real and the timing is right.

2. **Personal + company data unified** — Quick Suite searches company data. OpenClaw searches your laptop. Nobody does both through one voice interface.

3. **Stateless query, no indexing** — Compliance story is fundamentally cleaner than Quick Suite for regulated industries. You're querying their existing authorized systems, not ingesting a copy of their client data into your infrastructure.

4. **User orchestrates, not autonomous** — Right model for professional liability. CPA says "I approved each step" not "the AI did it."

5. **BYOC deployment** — Runs in their AWS account. Eliminates the longest part of enterprise security reviews.

6. **The agentic workflow is the end game** — Not a smart search bar. An AI chief of staff that knows what needs to happen today, works through it, and keeps the human in the loop on anything permanent. 15-minute workflows in 30 seconds. That's the product.

The immediate focus should be getting to a demo that shows the full loop: morning briefing → case prep → document find → email draft → confirm → sent. That single demo workflow closes pilot customers. Everything else follows.

The one thing to nail above everything else: the confirmation UX. If asking for confirmation feels like bureaucracy, users will stop using the agent for routine tasks and you've lost the whole value proposition. If it feels like a quick voice "yes, continue" that takes 2 seconds, users trust it more and give it more access over time. Build the confirmation flow first. It's the core interaction of the entire product.

---

*Compiled April 2026 from full product conversation — pipeline simulation, NL UX hardening, OpenClaw research, market analysis, technical architecture, and the agentic workflow vision.*
