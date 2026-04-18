# Seishin — Full Product Vision & Phased Roadmap

> Voice-first AI agent for tax dispute companies. Personal + company data, user-orchestrated, AWS-native. Written April 2026.

---

## Table of Contents

1. [Current State — What We Have](#1-current-state--what-we-have)
2. [Market Research](#2-market-research)
3. [Phase 1 — MVP Deploy](#3-phase-1--mvp-deploy)
4. [Phase 2 — Office Automation Layer](#4-phase-2--office-automation-layer)
5. [Phase 3 — Company Data Integration](#5-phase-3--company-data-integration)
6. [Phase 4 — Specialist Agent Architecture](#6-phase-4--specialist-agent-architecture)
7. [Phase 5 — Mobile & Proactive Intelligence](#7-phase-5--mobile--proactive-intelligence)
8. [Phase 6 — Full Agentic Orchestration](#8-phase-6--full-agentic-orchestration)
9. [Phase 7 — Enterprise Hardening & Scale](#9-phase-7--enterprise-hardening--scale)

---

## 1. Current State — What We Have

### The Stack

| Component | What it does | Model / Tech | Where it runs |
|-----------|-------------|--------------|---------------|
| Client app | Voice capture, playback | Tauri (Rust) | User's laptop |
| ASR | Audio → text | Parakeet TDT (cloud endpoint currently) | Cloud — moves to VPC in Phase 1 |
| Intent classification | Classifies what user wants | Gemma 4 27B NVFP4 via vLLM | Local RTX 5090 |
| Conversation / personality | Natural voice responses | Gemma 4 27B NVFP4 via vLLM | Local RTX 5090 |
| SQL generation | NL → SQL for reports | Claude Haiku 4.5 | Anthropic cloud |
| Report manipulation | Filter, sort, aggregate on cached data | CacheExecutor (pure pandas) | Server, no LLM needed |
| TTS | Text → voice audio | Fish Speech S2 Pro INT8 | Local RTX 5090 |

### Phases Completed

- **Phase 10**: LLM-native intent detection — Gemma replaces regex, guided JSON output
- **Phase 11**: Session cache + LLM-guided data operations — 9 op types via pandas, no re-querying DB on follow-ups
- **Phase 11.1**: Natural language UX hardening — 8 features (history-aware intent, fuzzy column matching, undo stack, compound requests, date normalization, discovery intent, zero-result guidance, cold-start cross-report compare)
- **Tests**: 114 passing across unit, integration, and E2E simulation

### Intent System (9 Intents Live)

| Intent | Example trigger | What happens |
|--------|----------------|-------------|
| `new_data_request` | "show me open cases" | Pulls fresh report from DB |
| `follow_up_on_previous` | "filter to just levies" | Applies op to cached data, no DB call |
| `compare_reports` | "compare those with last month" | Concurrent dual fetch → cross-report merge |
| `undo` | "go back" | Restores previous cached report |
| `what_can_i_ask` | "what data do you have?" | Voices available report types |
| `list_cached_data` | "what did I pull?" | Voices current session reports |
| `confirm` | "yes, do it" | Executes pending action |
| `cancel` | "never mind" | Clears pending action |
| `normal_chat` | anything else | Conversation |

### How Follow-ups Work

When a report is delivered, rows + column metadata + SQL + query are cached in SessionCache. Follow-up commands ("sort by amount", "only show active", "top 5") run through CacheExecutor — pure pandas, no LLM, no DB call, sub-100ms. Results cache as a new report, enabling unlimited chaining. Capped at 10 reports per session, 10-minute TTL.

### What's Waiting

- AWS G-quota request submitted (g6e.xlarge for Gemma 4 + Fish Speech)
- Phase 7 (cloud GPU), Phase 8 (local ASR in VPC), Phase 9 (TTS quality), Phase 12 (demo readiness) all planned and ready to execute once quota is approved

---

## 2. Market Research

### Market Size

| Market | Size (2026) | Growth |
|--------|-------------|--------|
| AI in accounting/tax | $10.9B | 44.6% CAGR → $68.75B by 2031 |
| Tax preparation services TAM | $36.9B | — |
| Voice AI market | $47.5B by 2034 | 34.8% CAGR |

AI adoption in accounting firms jumped from **9% → 41% in a single year** (2024-2025). Voice AI adoption in finance sits at just **11%** despite 91% overall AI adoption — that gap is the opportunity.

### Competitor Landscape

| Competitor | Price | What it does | Key gap we fill |
|-----------|-------|-------------|----------------|
| Thomson Reuters CoCounsel | $75-500/user/mo | Tax research, memo drafting | No voice, locked to TR ecosystem |
| Harvey AI | $1,000-1,200/user/mo (20-seat min, $288K/yr entry) | Legal document analysis | Absurdly expensive, no voice, legal-only |
| TaxGPT | ~$1,600/user/yr | Tax research co-pilot | Research-only, text-only, no company data |
| Intuit Assist | Bundled w/ QuickBooks | Transaction categorization, AI chat | Locked to Intuit ecosystem, no voice |
| Canopy Tax | ~$142/user/mo | Practice management + nascent AI | AI features immature, no voice |
| TaxDome | $50-83/user/mo | Practice management | Analytics dashboards only, minimal AI |
| Microsoft Copilot for Finance | $18-30/user/mo | Reconciliation, variance analysis | Requires enterprise ERP, not tax-specific, no voice |
| Amazon Quick Suite | AWS pricing | Agentic enterprise search, 90+ connectors | Indexes all data into AWS cloud, no voice, no laptop access |

### The White Space

**No competitor has a voice-first interface for tax dispute professionals.** Every product is text/GUI. The 5-50 person tax dispute company is completely underserved — Harvey charges $288K/yr minimum, TaxGPT is research-only, Quick Suite requires trusting AWS with client data (which triggers IRC §7216).

### Why "Stateless Query" Beats "Ingest and Index"

Amazon Quick Suite's model: copies your company data into an AWS vector index. Our model: queries original sources on demand, returns results, stores nothing.

For a tax dispute company handling client IRS notices, financial disclosures, and tax returns: putting that into a third-party index triggers **IRC §7216** (client consent required for any non-tax-prep use of their data), **IRS Publication 1075** (controls for Federal Tax Information), and the **FTC Safeguards Rule**. Querying S3 and Salesforce via existing IAM credentials is a completely different compliance conversation.

### Pain Points (Research Data)

- 60% of accountants spend too much time on manual tasks (Dext, 2025)
- Knowledge workers spend 8-10 hours/week searching for information (McKinsey)
- Tax professionals spend ~25% of their week on repetitive data retrieval
- 56% of CEOs report zero measurable ROI from AI despite record spending (PwC, Jan 2026) — the root cause is rework from AI that doesn't check itself
- Thomson Reuters: 60-70% time reduction in multi-jurisdiction cases using AI

### Compliance Requirements for Selling to Tax Dispute Companies

- **IRC §7216** — Client data can only be used for tax prep; any other use requires written client consent
- **IRS Publication 1075** — Strengthened controls for all Federal Tax Information recipients (Jan 2025)
- **FTC Safeguards Rule** — Tax preparers are classified as covered financial institutions
- **SOC 2 Type II** — Not legally required but expected by every firm's procurement process

---

## 3. Phase 1 — MVP: Voice Intelligence Layer

> **First deployable product. Something a company buys on day one.** Voice interface into the company database — ask anything, get real data back, refine it naturally. Plus basic local operations (file search, calendar, email drafts). The core value proposition is live and usable by all roles from day one.

### Core UX Principles (Established in Phase 1, Apply Forever)

**1. The agent is not a background process.**
The app is open or it's off. No silent daemons, no background syncing. Starts and stops with the user.

**2. Every action has a visual.**
Drafting an email → Outlook/Gmail compose window opens pre-filled. Moving a file → File Explorer opens. Opening a document → it opens. The user always sees and can touch what's happening.

**3. Email send queue — 5-minute delay.**
No email sends the instant the user says "send it." Goes into a queue with a visible countdown. Cancel anytime during the 5 minutes. This is non-negotiable given the stakes in IRS communications.

**4. Writes confirm, reads are instant.**
The agent queries, searches, reads, and checks freely. Pauses before: sending anything, moving anything, creating calendar events, updating records.

**5. Audit log for everything.**
Every action logged: timestamp, user, what happened, what was sent. Exportable.

---

### What Gets Built

**AWS infrastructure:**
- Gemma 4 27B on EC2 g6e.xlarge (L40S) in company VPC — intent + conversation
- Parakeet TDT 0.6b v2 on EC2 g5.xlarge — ASR (audio stays in VPC)
- Fish Speech S2 Pro — TTS (same GPU)
- Claude Haiku via Bedrock — SQL generation
- CDK stack — company deploys into their own AWS account, data never leaves

**Client app (thin, ~50MB install):**
- Silero VAD (2MB, CPU) — speech detection
- Audio streams to VPC
- OpenClaw — starts and stops with the app, NOT a background service

**Database capabilities (already built):**
- Voice → company DB query → results voiced back in natural language
- Follow-up ops: filter, sort, top N, aggregate, pivot, undo — sub-100ms, no re-querying
- History-aware intent, fuzzy column matching, date normalization, compound requests

**Basic local operations:**
| Intent | What happens | Visual |
|--------|-------------|--------|
| `find_file` | ripgrep searches local filesystem | File Explorer opens to the folder |
| `move_file` | Staged move with preview | File Explorer shows source → destination |
| `get_calendar` | Reads calendar, voices schedule | — |
| `draft_email` | Email Specialist Agent drafts | Outlook/Gmail compose window opens pre-filled |

**Email send queue:**
- User reviews draft in native compose window, edits directly
- Says "send it" → app shows "Sending in 5:00 — say cancel to stop"
- After 5 minutes, sends. Logged.

**Limited proactive — session start summary (Phase 1 form):**
When the user opens the app each morning, it automatically checks the database and surfaces the 3 most relevant items before the user says anything. No push notifications yet — just an instant briefing on open.

Example: *"Morning. Quick update: you have 2 IRS deadlines this week, and 3 clients who haven't uploaded their requested documents yet. Want to start there or ask me something?"*

This is the earliest version of what becomes the full proactive intelligence system by Phase 5. Phase 1: simple, DB-only, session-start only.

---

### Who Can Use It — All Roles From Day One

**Case Manager**
Query active cases by status and urgency, filter by deadline or type, find local files, check calendar, draft client emails with the compose window pre-filled. The 15-minute morning case review becomes a 2-minute voice summary.

**Document Reviewer**
"Show me all cases missing a signed engagement letter." "Which cases have IRS notices without a response filed?" "Find the Nguyen 433-A on my machine." Instantly actionable without touching Salesforce or opening five tabs.

**Executive / Partner**
"How many active cases do we have by resolution type?" "Show me cases where no billable work has been logged in 3 weeks." "Who has the highest caseload right now?" "What's our revenue this month vs last month?" "Which staff members have cases due this week?" Pull any operational metric by voice, slice it however you want.

**CEO / CTO — Executive Workflow Example**

CEO walks in Monday morning, opens the app.

> **Agent:** "Morning. Quick update: 2 IRS deadlines this week — Nguyen on Friday and Chen on Thursday. Last week: 3 cases resolved, $48k collected, 2 new intakes. 5 cases have had no activity in over 3 weeks. Want me to pull those?"

> **CEO:** "Yeah show me the stale ones."

Agent pulls from DB in 2 seconds, voices: "Peterson, Okafor, Westbrook Trust, Rivera, and Sanchez. Okafor is the most concerning — OIC submitted 5 months ago, should be getting a response soon. Want me to flag these for their case managers?"

> **CEO:** "Yes, flag Okafor as urgent for Marcus. Draft an email to the team about the other four."

Outlook compose window opens with a draft team message. CEO edits it directly, queues it. Done in 4 minutes. No dashboards, no tab switching.

**CTO — What They Use It For**
In Phase 1, the CTO's main interaction is setup: deploying the CDK stack into the company's AWS account, configuring IAM roles, connecting the database. The app has a web-based admin panel showing basic usage stats and audit log. Voice queries aren't the CTO's primary interface yet — that comes in Phase 7.

---

### Cost (20 users)

| Component | Monthly |
|-----------|---------|
| EC2 g5.xlarge spot (8hr/day weekdays) | ~$280 |
| Bedrock Claude Haiku | ~$40 |
| ALB + networking | ~$30 |
| **Total AWS** | **~$350/mo (~$17/user)** |

**Charge $99/seat → ~83% gross margin.**

---

## 4. Phase 2 — Office Automation + Client Portal

> **Builds on Phase 1:** Deeper email workflows, calendar writes, advanced file operations, and live access to the client portal. The session-start summary grows to include portal activity. Basic multi-user enabled so the whole team can use it simultaneously.

### What's New (Phase 2 adds to everything in Phase 1)

**Multi-user (first version):**
- Concurrent sessions — multiple staff can use the agent at the same time
- Per-user session isolation — each person has their own cache, history, and undo stack
- Shared data, private sessions — everyone queries the same DB but their in-session work is their own

**Advanced email workflows:**
- Bulk draft mode — "draft follow-ups to all clients with missing documents" → N compose windows open simultaneously, one per client, each pre-filled
- Email templates per case type — specialist agent picks the right template (document request, IRS notice acknowledgment, OIC status update) and fills it in
- Reply drafting — agent reads an incoming email and drafts a reply in the same thread, opening the reply window directly
- Send queue visible in app sidebar: each queued email listed with countdown, one-tap cancel per email

**Calendar write operations:**
- Create meetings — native calendar app opens with invite pre-filled, user confirms
- Reschedule — existing event shown with proposed new time
- Block time — "block Thursday afternoon for Chen hearing prep"

**Advanced file operations:**
- Bulk organize — "sort my downloads into case folders" → preview list shown before any moves
- Open file directly — "open the Martinez 433-A" → document opens in PDF viewer or Word
- Search network drives and shared folders, not just local machine

**Client portal connectivity:**
- Query what each client has uploaded and what's still missing
- "Has Nguyen uploaded their 433-A?" → instant answer from portal DB
- "Show me all clients with incomplete document checklists" → voiced list
- New portal uploads shown in next session-start summary

**Specialist agents introduced (Phase 2):**
- **Email Specialist Agent** — tax dispute communication norms, appropriate urgency, never guesses unverified facts
- **Calendar Specialist Agent** — timezone handling, conflict detection, IRS hearing context

**Proactive — session start summary (Phase 2 form):**
Now includes portal activity alongside DB data. When the user opens the app:

*"Morning. 3 clients uploaded documents overnight — Rivera sent the bank statements, Johnson sent a W-2, and Nguyen sent something I can't identify (looks like it might be a K-1). 2 IRS deadlines this week. Want to start with the new uploads?"*

---

### Example Workflow — Bulk Document Requests

> "Draft document request emails to everyone with incomplete checklists due this week"

Agent hits portal DB, identifies 6 cases. Email Specialist Agent drafts 6 emails concurrently. Six Outlook compose windows open on screen — one per client, each pre-filled with specific missing documents and deadline reference.

Case manager reviews each one, tweaks two, closes one (that client just called), says "queue the rest."

Five emails in the send queue. App sidebar: "5 emails sending in 5:00 — tap any to cancel."

All five send five minutes later. Total time: 3 minutes instead of 45.

---

## 5. Phase 3 — Company Data Integration + Rich Proactive

> **Builds on Phase 2:** Salesforce, S3, and all company data sources connected. One query spans everything simultaneously. The session-start summary becomes genuinely intelligent — it sees the full picture across all sources and surfaces what actually matters.

### What's New

**Company data connectors:**

| Source | What's accessible | Permission model |
|--------|------------------|-----------------|
| Salesforce | Cases, contacts, tasks, call logs, stage, assigned staff | User sees only assigned cases (configurable by role) |
| AWS S3 | Case documents, scanned IRS mail, uploaded client files | Scoped to company bucket, prefix-based per case |
| Client portal DB | Client uploads, submission timestamps, checklist status | Read-only, per-case |
| Internal SQL DB | Financial data, invoices, revenue | Existing pipeline |

**SSO + permission layer:**
- Okta / Google Workspace / Microsoft Entra
- Permissions inherit from company's existing IAM and Salesforce profiles
- Per-query permission check — no override

**Unified hybrid query:**
One sentence hits laptop + Salesforce + S3 + portal simultaneously. Results merged before voice.

> "Pull up everything we have on the Nguyen case"

1. Salesforce → case record, status, tasks
2. S3 → all documents listed by date
3. Portal → client uploads, what's missing
4. Laptop → local notes or working files
5. Cross-reference checklist vs what's actually filed

Voiced back in ~3 seconds: "The Nguyen levy case is in active negotiation. 8 documents in S3. Still missing the 2023 bank statements — though the client uploaded pay stubs 20 minutes ago. Last call was Tuesday. Want me to draft a follow-up?"

**9 minutes of manual work → 3 seconds.**

**Document Review Specialist Agent** introduced:
Identifies document types, extracts key figures, flags what's missing for each case type (OIC vs CDP vs installment agreement).

**Proactive — session start summary (Phase 3 form):**
Now fully cross-source. The agent sees everything: Salesforce case stages, S3 document status, portal activity, DB financials — and surfaces the most important items ranked by urgency.

*"Morning. This week: Nguyen CDP deadline Friday (still missing bank statements — I can draft the request), Chen hearing Thursday (all docs present, prep hasn't been done), and the Okafor OIC hits the 6-month response window tomorrow. 4 clients uploaded docs overnight. Revenue: $48k invoiced last week, $12k outstanding past 30 days. Where do you want to start?"*

This is now genuinely useful as a daily briefing. Not push notifications yet — still requires opening the app.

---

### CEO / CTO at Phase 3

**CEO:** Can now ask cross-source questions. "Show me all cases where we have IRS notices but haven't filed a response" pulls from Salesforce case stage + S3 documents + portal simultaneously. "Compare case resolution rate this quarter vs last quarter" pulls DB financials + Salesforce case closure dates.

**CTO:** Can now see data flow across all connected sources in the admin panel. Configure which connectors are active, which S3 prefixes are accessible, verify permissions are scoped correctly per role.

---

## 6. Phase 4 — Specialist Agent Architecture + Task Intelligence

> **Builds on Phase 3:** Every task now routes to a purpose-built specialist agent. Hallucination checking on every output. The proactive layer learns what needs doing — not just what has changed — and starts suggesting specific tasks by name.

### What's New

**Full specialist agent architecture:**

The main LLM becomes a router. Every meaningful task routes to a specialist with its own optimized system prompt stored in a vector database.

```
User: "Draft an OIC for the Martinez case"
  → Main LLM embeds the request
  → Vector DB retrieves: OIC Calculator & Drafter (highest cosine similarity)
  → Orchestrator fetches context: 433-A from portal, liability from DB, call logs from Salesforce
  → OIC Calculator drafts with cited figures
  → Hallucination Checker verifies every number against source docs
  → Result voiced to user
```

**Full specialist agent roster:**

| Agent | What it handles |
|-------|----------------|
| IRS Response Letter Writer | CP2000, CP503, CP504, levy release — IRS formatting, deadlines, required language |
| OIC Calculator & Drafter | RCP math, 433-A analysis, offer amount, Form 656 + cover letter |
| CDP Hearing Preparer | Due process rights, hearing arguments, documentation checklist |
| Penalty Abatement Writer | First-time abatement, reasonable cause, correct form and process |
| Installment Agreement Drafter | Streamlined vs non-streamlined, eligibility, payment calculation, CNC |
| Collection Appeals Agent | CAP/CAR filing, collection suspension, argument structure |
| Financial Disclosure Analyzer | 433-A/433-B, allowable expense standards, income verification, net equity |
| Client Communication Agent | Status updates, document requests, welcome emails, hearing instructions |
| New Client Intake Agent | Case type from uploaded docs, liability summary, recommended resolution path |
| Case Status Summarizer | Clean handoff summaries, partner reviews, client updates |
| Deadline Tracker Agent | IRS calendar, extension deadlines, response windows, statute of limitations |

**Hallucination checking on every output:**
- Every dollar amount verified against source document (case DB, 433-A, IRS notice)
- Every date verified against case records
- Every client name confirmed against Salesforce
- Unverifiable claims tagged: "[unverified — please confirm]"
- Never silently presents a number it can't source
- Adds ~200ms — acceptable for content that might go to the IRS

**Proactive — task suggestion (Phase 4 form):**
Now the session-start summary doesn't just say what changed — it suggests specific tasks by name, knowing what each one involves because the specialist agents exist to do them.

*"Morning. Three things I'd suggest today: First, the Nguyen CDP response is due Friday and I can draft it now — I have everything I need except the bank statements, so I'd start with a client message. Second, the Martinez OIC has been sitting 4 months without a counter — worth a follow-up call to the revenue officer. Third, Chen uploaded new documents overnight and I haven't reviewed them yet. Want me to start on any of these?"*

The user says "start with Nguyen" and the agent begins the task. This is the first phase where the agent proactively initiates work, not just surfaces information. Still requires the user to open the app and respond.

---

### Example Workflow — OIC Draft

> "Draft an Offer in Compromise for the Martinez case"

Agent → **OIC Calculator & Drafter**

Pulls: 433-A from portal ($3,800/mo income), allowable expenses from IRS National Standards ($3,520/mo), liability from DB ($89,000)

Hallucination checker: ✓ income matches pay stubs, ✓ expenses match IRS standards table, ✓ liability matches case DB

Agent voices: "RCP works out to about $13,400. I'd recommend offering $14,500 — slight cushion. I've drafted the OIC cover letter and Form 656. Want me to read the key figures before you review the document?"

Document opens in Word. User reviews, adjusts one figure, confirms. In send queue.

---

## 7. Phase 5 — Mobile + Full Proactive Push

> **Builds on Phase 4:** The agent no longer waits to be opened. Push notifications to phone. WhatsApp/iMessage integration. Morning briefings delivered automatically. The proactive layer now reaches the user wherever they are.

### What's New

**Mobile interface — two options:**

**Option A — Native mobile app (iOS/Android)**
- Lightweight, tap to speak, see transcription, hear response
- Full access to all Phase 1-4 capabilities from phone
- SSO login, secure connection to company VPC

**Option B — WhatsApp / Telegram / iMessage via OpenClaw**
- No app install required — use the messaging app they already have
- "Has Nguyen uploaded the bank statements?" answered in WhatsApp
- Simpler to deploy, no App Store review

**Push notifications — proactive that doesn't require opening the app:**

| Trigger | Notification |
|---------|-------------|
| IRS deadline < 48 hours | "Nguyen CDP response due Friday. Still missing bank statements." |
| Client uploads to portal | "Rivera uploaded 3 documents — looks like the bank statements." |
| Case dormant 3+ weeks | "Okafor OIC: 3 weeks no activity, 6-month IRS response window starting." |
| New IRS notice in S3 | "New CP2000 on Chen. 60-day response window — due March 14." |
| Uncontacted lead 24+ hours | "2 new leads uncontacted since yesterday morning." |

**Proactive — full morning briefing (Phase 5 form):**
Pushed to phone at a configured time (default 8am weekdays). No app open required.

> **Agent (8:00am via WhatsApp):** "Morning. This week: Nguyen CDP Friday (I can start the response when you're ready), Chen hearing Thursday (docs ready, prep outstanding), Okafor OIC at 6-month window. Revenue last week: $67k invoiced, $23k past 30 days. 8 client uploads over the weekend. I'll flag anything urgent as it comes up."

Short, factual, no fluff. User can reply directly from WhatsApp to start working.

**CEO / CTO at Phase 5:**

CEO gets the morning briefing on their phone every Monday. Can ask follow-up questions from WhatsApp without opening a laptop.

CTO can configure notification rules — which events trigger alerts, who gets them, quiet hours per user.

---

## 8. Phase 6 — Full Agentic Orchestration

> **Builds on Phase 5:** The agent doesn't just suggest tasks and send alerts — it starts working through the day with the user. It knows the full workload, plans the day, executes the routine parts, and brings the human in at every decision point. The proactive layer becomes a full workflow engine.

### The Core Rule (Unchanged From Phase 1)

**Reads are automatic. Writes require voice confirmation.** This never changes regardless of how capable the agent becomes.

### What's New

**Task decomposition engine:**
Every task breaks into atomic read/write steps. Reads run automatically. Writes pause and present to the user.

```
Task: "Prepare for the Martinez 2pm call"

Auto (no confirm):
  Pull Salesforce case record
  Pull S3 documents
  Read last 3 call logs
  Check portal — new uploads?
  Check email thread

Confirm required:
  Draft call prep summary → user reviews → user saves
  Draft amended OIC → user reviews → confirms to queue
  Post-call: update case notes → user confirms
```

**State persistence:**
Session interrupted → user returns → agent resumes exactly where it left off. "Welcome back. You were prepping for Martinez. The amended OIC is drafted. Call is in 35 minutes. Want to continue?"

**Full case lifecycle:**
- Intake: new lead → agent identifies case type from uploaded docs → drafts welcome + intake questionnaire → routes to correct caseworker
- Active case: manages checklist → chases missing docs → tracks deadlines → drafts responses → prepares hearings — all at user direction
- Resolution: drafts final documents → coordinates signature → closes case in Salesforce → generates summary for client
- Every step: human confirms before anything permanent

**Proactive — full workflow initiation (Phase 6 form):**
The agent now not only suggests tasks — it starts working on them proactively in the background (read-only prep work only) and presents ready-to-go outputs when the user opens the session.

User opens the app Monday morning:

> **Agent:** "Morning. I've done some prep while you were out. For Nguyen (Friday deadline): I've drafted the CDP response — I just need you to review it, it's ready. For Martinez (2pm call today): I've pulled the case file, reviewed the last 3 call logs, and flagged that their income dropped — I'd recommend amending the offer and I've drafted that too. For Chen (Thursday): all documents are in order, I've outlined the hearing arguments. Want to start with Nguyen or the Martinez call prep?"

The agent did hours of prep work. The user makes all the decisions. Nothing was sent, moved, or filed.

---

### CEO / CTO at Phase 6

**CEO:** Opens the app to a full morning brief with prep work already done. Revenue, pipeline, stale cases, upcoming deadlines — all surfaced with specific suggested actions, not just data. "We have 5 cases at risk this week — here's what I'd recommend for each." Can approve actions directly: "do that for all 5."

**CTO:** Monitors the full agentic workflow in the admin panel — see what prep work the agent did overnight, what was confirmed by users, what's pending. Full audit trail of automated reads and user-confirmed writes.

---

## 9. Phase 7 — Enterprise Hardening & Scale

> **Builds on Phase 6:** Multi-user with role-based access, admin dashboard for IT, SOC 2 alignment, self-service deployment for new companies, billing infrastructure. The product is now ready to sell to any size firm.

### What's New

**Full role-based multi-user:**
- Role tiers: Case Manager, Senior Manager, Partner/Executive, IT Admin
- Partners see all cases and full portfolio analytics
- Case managers see only assigned cases
- Executives get the macro view — revenue, pipeline, team performance
- IT Admin manages the whole system without voice access to case data

**Admin dashboard (web UI):**
- User provisioning, SSO config, role assignment
- Data source management (Salesforce org, S3 bucket, portal DB)
- Approved specialist agent list — company controls which agents are active
- Usage analytics per user, per feature, per data source
- Audit log export — filterable by date, user, action type
- Cost tracking per user per month

**Enterprise safety layer:**
| Feature | What it does |
|---------|-------------|
| Audit log | Every action logged: timestamp, user, input, output, confirmation |
| SQL transparency | Every report shows the query. Voice: "show me the query" |
| Confirmation receipts | Every confirmed write logged with the user's voice input |
| Skill whitelist | Company controls agent roster — no external marketplace |
| Data residency | All processing in company's AWS VPC — nothing leaves |
| Encryption | TLS 1.3 in transit, AWS KMS keys at rest |

**SOC 2 Type II readiness:**
Not certified at launch but architecturally aligned. All access authenticated and authorized per query, full audit trail, no data outside company's VPC. Certification timeline: 6-12 months post-launch (~$30-50K).

**BYOC CDK stack:**
```bash
cdk deploy SeishinStack \
  --context company=acme-tax-dispute \
  --context s3_bucket=acme-case-documents \
  --context salesforce_org=https://acme.salesforce.com \
  --context portal_db=postgresql://... \
  --context sso_provider=okta
```

### Billing

| Tier | Price | Included | Target |
|------|-------|----------|--------|
| **Starter** | $49/seat/mo | 150 voice mins, 5 users, core DB + file ops | 2-5 person shop |
| **Professional** | $99/seat/mo | 400 voice mins, 25 users, all connectors, audit logs, SSO, all specialist agents | 10-50 person company |
| **Enterprise** | Custom ($150-250/seat) | Unlimited, BYOC, dedicated support, custom agent builds | Large firm / white-label |

Annual discount: 20%. **COGS at Professional (20 users): ~$16/user/mo → ~84% gross margin.**

Billing stack: Stripe (payments) + Lago (open source, usage metering).

---

## Deployment Timeline Summary

| Phase | What gets unlocked | Proactive intelligence at this phase | Earliest deploy |
|-------|-------------------|------------------------------------|----------------|
| **Phase 1** | Voice + DB, file search, email draft, calendar read | Session-start: DB summary (3 items, open-app only) | ~3 weeks post-quota |
| **Phase 2** | Advanced email, bulk workflows, portal access, multi-user | Session-start: DB + portal activity | +4 weeks |
| **Phase 3** | Salesforce + S3 + hybrid queries, cross-source summary | Session-start: full cross-source briefing, ranked by urgency | +4-6 weeks |
| **Phase 4** | Specialist agents, hallucination checking, vector DB | Session-start: suggests specific named tasks, can initiate on user response | +6-8 weeks |
| **Phase 5** | Mobile app, WhatsApp, push notifications | Push alerts to phone, morning briefing delivered without opening app | +4 weeks |
| **Phase 6** | Full agentic orchestration, workflow engine, state machine | Overnight prep work done automatically, presented ready-to-go at session start | +6-8 weeks |
| **Phase 7** | Enterprise hardening, RBAC, admin dashboard, SOC 2, billing | Same as Phase 6 but across whole team with role-filtered briefings | +4-6 weeks |

**Total to full product: ~9 months from Phase 1 deploy.**

Phase 1 is the MVP that closes pilot deals. Phase 3 is where it becomes noticeably better than anything else. Phase 4 is where it becomes genuinely transformative. Phase 6 is the end vision.

---

## Why This Is Different — One Summary

| What everyone else does | What we do |
|------------------------|-----------|
| Text/GUI interface | Voice-first, hands-free |
| Search company knowledge base | Personal laptop + all company sources, simultaneously |
| Ingest your data into their cloud | Query original sources on demand, store nothing |
| Autonomous agent that acts | User orchestrates — every write confirmed by voice |
| One LLM for everything | Specialist agent per task, purpose-built system prompts |
| Trust the output | Hallucination checker verifies every fact before you hear it |
| Reactive — answers when asked | Proactive — surfaces what matters, preps work, pushes alerts |
| Desktop only | Desktop, phone, WhatsApp, iMessage |

---

*Document compiled April 2026. Covers current state, market research, and full 7-phase roadmap from MVP to complete agentic assistant for tax dispute companies.*
