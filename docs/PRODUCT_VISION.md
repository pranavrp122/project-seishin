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

## 3. Phase 1 — MVP Deploy

> **Deployable product.** Voice assistant that can query the company database, manipulate results by voice, search and move files, check calendar, and draft emails — with full visual transparency on every action. First paying customer possible at end of this phase.

### Core UX Principles (Established in Phase 1, Apply Forever)

These rules govern how every feature works across all phases:

**1. The agent is not a background process.**
The app is open or it's off. When the user closes it, nothing runs. No silent daemons, no background syncing, no processes the user didn't start. This is intentional — it keeps the user in control and avoids surprises.

**2. Every action has a visual.**
When the agent is working on something, the relevant native window opens in front of the user. Drafting an email → Outlook or Gmail compose window pops up, fully editable. Moving a file → File Explorer/Finder opens to the destination. Opening a document → the document opens. The user never has to wonder what's happening — they can see it and touch it.

**3. Email send queue — 5-minute delay.**
No email ever sends the instant the user says "send it." It goes into a send queue with a 5-minute countdown, visible in the app. User can edit or cancel at any point during that window. After 5 minutes it sends automatically. This exists because "wait, not that one" is a real scenario and the stakes in tax dispute communications are high.

**4. Writes require explicit confirmation — reads are instant.**
The agent queries data, searches files, reads documents, checks calendars without asking. It pauses and shows the user before: sending anything, moving or deleting anything, creating calendar events, updating case records.

**5. Audit log for everything.**
Every action — query, file operation, email sent, calendar event created — is logged locally with timestamp, user, and what happened. Exportable for compliance reviews.

---

### What Gets Built

**Infrastructure (pending AWS quota):**
- Gemma 4 27B on EC2 g6e.xlarge (L40S) in company's AWS VPC — intent classification + conversation
- Parakeet TDT 0.6b v2 on EC2 g5.xlarge — ASR (audio stays in company's VPC)
- Fish Speech S2 Pro on same GPU — TTS
- Claude Haiku via Amazon Bedrock — SQL generation (already live)
- ALB + WebSocket endpoint
- CDK stack for BYOC deployment — company runs everything in their own AWS account

**Client app:**
- Silero VAD on laptop (2MB, CPU — detects speech start/end, prevents streaming silence)
- Audio streams to VPC over WebSocket
- OpenClaw daemon — installed as part of the app, NOT a background service, starts and stops with the app
- No models, no GPU needed on the laptop

**Database capabilities (already built):**
- Voice → company database query → results voiced back
- Follow-up manipulation: filter, sort, top N, aggregate, pivot, undo — sub-100ms, no re-querying
- 9 intents, history-aware, fuzzy column matching, date normalization

**Basic local operations (Phase 1 OpenClaw scope):**
| Intent | Trigger | What happens |
|--------|---------|-------------|
| `find_file` | "find the Nguyen engagement letter" | ripgrep searches local filesystem, results voiced, File Explorer opens to the folder |
| `move_file` | "move that to the Rivera case folder" | File Explorer opens showing source and destination — user confirms visually, then move executes |
| `get_calendar` | "what do I have today?" | Reads calendar, voices the schedule |
| `draft_email` | "draft a follow-up to Rivera" | Email Specialist Agent drafts, Outlook/Gmail compose window opens automatically with draft pre-filled — user edits directly in the native app |

**Email send queue:**
- User reviews the email in the native compose window (fully editable)
- Says "send it" or clicks send in the compose window
- Email goes into the send queue — visible countdown in the app: "Sending in 4:58..."
- User can say "cancel that email" or click cancel in the app at any point during the 5 minutes
- After 5 minutes, sends automatically via OpenClaw OAuth
- Logged to audit file: drafted at X, queued at Y, sent at Z (or cancelled)

### Who Can Use It

| Role | What they can do |
|------|-----------------|
| Case Manager | Query active cases, find local files, check calendar, draft client emails |
| Executive / Partner | Pull revenue reports, case volume, overdue invoices |
| Document Reviewer | Query what's uploaded per case, find missing documents, search local case files |
| IT Department | Deploy and manage the CDK stack in company's AWS account |

### Demo Workflow

> "Show me all active levy cases where the IRS response is due this week"

Agent queries the database, voices: "You have 4 levy cases with responses due this week. Nguyen is Friday, Chen and Park are Thursday, Rivera has no response filed yet. Want me to sort them by priority?"

> "Sort by amount owed"

Sub-100ms. CacheExecutor sorts. No DB call.

> "Find the Nguyen engagement letter"

File Explorer opens on the user's screen. ripgrep has already found it: `~/Documents/Cases/Nguyen/Nguyen_EL_2024.pdf`. Agent voices: "Found it — Nguyen engagement letter, March 2024, in your Cases folder."

> "Draft an email to Nguyen asking for their bank statements"

Outlook compose window opens on screen. Draft is pre-filled with the correct client name, professional tone, document request language. User can edit it directly. Agent voices: "Draft is open in Outlook — I've pre-filled it. Edit anything you want, then say 'send it' or just hit send."

User tweaks the wording directly in Outlook, says "send it."

App shows: "Sending in 5:00 — say 'cancel' to stop." Countdown visible. After 5 minutes, gone.

### Cost at This Phase (20 users)

| Component | Monthly |
|-----------|---------|
| EC2 g5.xlarge spot (8hr/day weekdays) — Parakeet + Fish Speech + Gemma | ~$280 |
| Bedrock Claude Haiku — SQL generation | ~$40 |
| ALB + networking | ~$30 |
| **Total AWS** | **~$350/mo (~$17/user)** |

**Charge $99/seat → ~83% gross margin.**

---

## 4. Phase 2 — Full Office Automation + Client Portal

> **Deeper office automation and client portal connectivity.** Builds on Phase 1's basic file/email/calendar with more advanced operations, calendar writes, bulk email workflows, and the ability to query what clients have uploaded to the portal.

### What Gets Built

**Advanced email workflows:**
- Bulk draft mode — "draft follow-ups to all clients with missing documents" generates N emails, each opens in a separate compose tab, user reviews and queues them individually
- Email templates per case type (IRS notice acknowledgment, document request, OIC status update) — specialist agent picks and fills the right template
- Reply drafting — agent reads an incoming email and drafts a response in the same thread, opening the reply window directly
- Send queue visible in the app sidebar: list of queued emails, time remaining on each, one-tap cancel per email

**Calendar write operations:**
- Create meetings — calendar invite opens for user to review before confirming
- Reschedule — existing event shown with proposed new time, user confirms
- Block time — "block Thursday afternoon for the Chen hearing prep"
- All calendar writes open the native calendar app (Google Calendar in Chrome or Outlook calendar) so the user sees exactly what's being created

**Advanced file operations:**
- Bulk file organization — "sort everything in my downloads into the right case folders" — shows a preview list of what will move where before doing anything
- File rename with case reference insertion
- Search across network drives and shared folders, not just local machine
- Open file directly — "open the Martinez 433-A" → document opens in the default app (PDF viewer, Word, etc.)

**Client portal connectivity:**
- Connect to the company's client portal database (read-only)
- Query what each client has uploaded, when, and what's still missing
- "Has Nguyen uploaded their 433-A yet?" → instant answer from portal DB
- "Show me all clients with incomplete document checklists" → pulls from portal, voices the list
- New portal uploads trigger a notification (Phase 5 adds proactive push; Phase 2 shows it on next app open)

### Specialist Agents Introduced (Phase 2)

**Email Specialist Agent**
Knows tax dispute communication norms. Never includes unverified figures. Picks the right tone (urgent vs routine vs empathetic). Cites the case reference in every outbound email. Flags when it's unsure of a fact rather than guessing.

**Calendar Specialist Agent**
Handles timezone correctness, scheduling conflict detection, client-facing vs internal language, and IRS hearing/deadline context.

### Example Workflow — Bulk Document Requests

Case manager has 6 clients all missing documents with deadlines approaching.

> "Draft document request emails to everyone with incomplete checklists due this week"

Agent hits the portal DB, identifies 6 cases with gaps. Routes to Email Specialist Agent 6 times (concurrent). Six Outlook compose windows open on screen — one per client, each pre-filled with the correct client name, specific missing documents, and deadline reference.

Case manager reviews each one, tweaks the tone on two of them, closes one (that client just called), says "queue the rest."

Five emails in the send queue. App sidebar shows: "5 emails sending in 5:00 — tap any to cancel."

All five send five minutes later. Each logged.

Total time for the case manager: 3 minutes instead of 45.

---

## 5. Phase 3 — Company Data Integration

> **Unified personal + company data.** One voice command can now span the user's laptop, the client portal, Salesforce, S3, and the internal database simultaneously. The "hybrid query" — the thing nobody else can do.

### What Gets Built

**Connectors:**

| Source | What's accessible | Permission model |
|--------|------------------|-----------------|
| Salesforce | Cases, contacts, tasks, call logs, case status | User sees only cases they're assigned to (configurable) |
| AWS S3 | Case documents, uploaded client files, scanned mail | Scoped to company's S3 bucket, prefix-based per case |
| Client portal DB | Everything clients have uploaded, submission history | Read-only, per-case permission |
| Internal SQL DB | Financial data, invoices, case financials | Existing report pipeline |

**Permission layer:**
- SSO login (Okta, Google Workspace, Microsoft Entra)
- User permissions inherit from company's existing IAM roles and Salesforce profiles
- Every query is permission-checked before execution — no override
- Audit log: every data source accessed, every file touched, by whom, at what time

**Unified result merger:**
When a query spans multiple sources, results are combined into a single coherent response before being voiced. The user never hears "checking Salesforce... now checking S3... now checking portal" — they just hear the answer.

### The Hybrid Query

This is the core differentiator at this phase. One spoken sentence can simultaneously hit the user's laptop, Salesforce, S3, and the client portal.

> "Pull up everything we have on the Nguyen case"

Agent:
1. Queries Salesforce → case record, status, assigned staff, outstanding tasks
2. Queries S3 → lists all documents for this case by date
3. Queries client portal → what the client has uploaded, what's still missing
4. Searches local laptop → any local notes or working files
5. Cross-references Salesforce document checklist vs what's actually on file

Result voiced back in ~3 seconds:
> "The Nguyen levy case is in active negotiation. You have 8 documents in S3 — the original levy notice, 3 years of returns, the 433-A, and two call logs. Still missing: the 2023 bank statements and the pay stubs you requested. The client uploaded the pay stubs 20 minutes ago but the bank statements aren't in yet. Your last call with them was Tuesday. Want me to draft a follow-up?"

That replaced: opening Salesforce (2 min), navigating S3 (3 min), checking portal (2 min), searching local files (2 min). **9 minutes → 3 seconds.**

### Document Specialist Agent Introduced

**Document Review Agent**
System prompt optimized for: identifying document types (IRS notices, 433-A, pay stubs, bank statements, tax returns), extracting key figures (total liability, income, expenses), flagging missing required documents for specific case types (OIC vs CDP vs installment agreement).

---

## 6. Phase 4 — Specialist Agent Architecture

> **Purpose-built agents for every task.** The main LLM becomes a router/orchestrator. Every meaningful task is handled by a specialist agent with its own system prompt, context, and self-checking logic. Hallucination checking runs on every output before it reaches the user.

### Architecture

```
User voice input
  → Main LLM (orchestrator)
      Classifies task type
      Retrieves specialist from vector DB
      Injects relevant case context
  → Specialist Agent (e.g. OIC Drafter)
      Executes task with specialized prompt
      Cites every fact from source data
  → Hallucination Checker
      Cross-references all numbers/dates/names against retrieved source documents
      Flags anything it can't verify
  → Main LLM (presenter)
      Voices result to user
      Flags any uncertainties
```

### Specialist Agent Roster (Tax Dispute Company)

Each agent is stored as a record in a vector database (pgvector on RDS, or Pinecone). The orchestrator embeds the task description, retrieves the most relevant specialist, and calls it with the right context.

| Agent | Specialized for |
|-------|----------------|
| **IRS Response Letter Writer** | CP2000, CP503, CP504, levy release requests, audit responses — knows IRS formatting, deadlines, required language |
| **OIC Calculator & Drafter** | Reasonable collection potential math, 433-A analysis, offer amount recommendation, OIC cover letter |
| **CDP Hearing Preparer** | Collection Due Process rights, hearing arguments, supporting documentation checklist |
| **Penalty Abatement Writer** | First-time abatement, reasonable cause arguments, correct IRS form and submission process |
| **Installment Agreement Drafter** | Streamlined vs non-streamlined, eligibility check, monthly payment calculation, CNC consideration |
| **Collection Appeals Agent** | CAP/CAR filing, suspension of collection, argument structuring |
| **Financial Disclosure Analyzer** | 433-A/433-B analysis, allowable expense standards, income verification, net equity calculation |
| **Client Communication Agent** | Status updates, document request letters, welcome emails, hearing prep instructions — client-facing tone |
| **New Client Intake Agent** | Case type identification from uploaded documents, initial liability summary, recommended resolution path |
| **Case Status Summarizer** | Clean, factual case summaries for internal handoffs, partner reviews, or client updates |
| **Deadline Tracker Agent** | IRS calendar awareness, extension deadlines, response windows, statute of limitations |

### How the Vector DB Works

Agent records contain: name, description, task_types[], system_prompt, required_context_fields[], output_format.

When user says: *"Draft a penalty abatement request for the Chen case"*

1. Orchestrator embeds: "draft penalty abatement request"
2. Vector search retrieves: **Penalty Abatement Writer** agent (highest cosine similarity)
3. Orchestrator fetches context: Chen case record from Salesforce, tax liability from DB, call logs
4. Calls specialist with context injected into prompt
5. Specialist drafts the letter, citing every figure from the source data
6. Hallucination checker runs

### Hallucination Checking

Every output from a specialist agent goes through a verification step before reaching the user.

**What gets checked:**
- Every dollar amount is verified against a source document (case DB, 433-A, IRS notice)
- Every date is verified against case records
- Every client name and case reference number is confirmed against Salesforce
- Any claim about what the IRS said is checked against uploaded notices in S3

**What happens on a flag:**
- If the checker finds an unverifiable claim, it tags it: "[unverified — please confirm]"
- Agent voices the output with explicit uncertainty: "I have $47,200 as the total liability from the case file — can you confirm that's still current?"
- Never silently presents a number it can't source

**Implementation:**
- Hallucination checker is itself a specialist LLM call (Claude Haiku — fast and cheap)
- Takes specialist output + source documents as input
- Returns: verified claims list + flagged claims list
- Adds ~200ms to response time — acceptable for content that might be sent to the IRS

### Example Workflow — OIC Draft

> "Draft an Offer in Compromise for the Martinez case"

Orchestrator → **OIC Calculator & Drafter** agent

Agent pulls: 433-A from portal, income/expense from DB, total liability from case record

Drafts offer with RCP calculation:
- Monthly income: $3,800 (from 433-A uploaded by client)
- Allowable monthly expenses: $3,520 (IRS National Standards applied)
- Monthly disposable income: $280
- RCP (48 months): $13,440
- Recommended offer: $14,500 (slight cushion above RCP)

Hallucination checker: verifies $3,800 income against uploaded pay stubs ✓, verifies $3,520 against IRS standards table ✓, verifies total liability $89,000 against case DB ✓

Agent voices: "Based on the 433-A Martinez uploaded and the IRS expense standards, the reasonable collection potential works out to around $13,400. I'd recommend offering $14,500. I've drafted the OIC cover letter and Form 656. Want me to read the key figures before you review it?"

---

## 7. Phase 5 — Mobile & Proactive Intelligence

> **Works from anywhere. Knows when to reach out.** Users can now interact via their phone — voice or text. The agent proactively surfaces what matters before the user has to ask.

### Mobile Interface

**Two delivery methods:**

**Option A — Native mobile app (iOS/Android)**
- Lightweight app, similar to the desktop client but mobile-optimized
- Tap to speak, see transcription, hear response
- Secure connection to company's VPC over HTTPS
- SSO login

**Option B — WhatsApp / Telegram / iMessage via OpenClaw**
- OpenClaw already supports all major messaging platforms
- User texts or voice-messages their agent on WhatsApp
- Useful for quick checks without opening an app: "Hey, has Nguyen uploaded the bank statements yet?"
- Simpler to deploy and no App Store review process

Both options connect to the same VPC backend. The interface is different; the intelligence is identical.

**Phone voice specifics:**
- VAD runs on the phone (OpenClaw mobile handles this)
- Audio streamed to Parakeet in VPC
- Response comes back as audio and text
- Works on any phone, any OS, no special hardware

### Proactive Intelligence

The agent monitors the company's data continuously and surfaces things the user should act on — without being asked. Not automated actions (Phase 6 handles that) — just smart, well-timed alerts.

**Principles:**
- Only surfaces things that require human decision or action
- Never sends a notification unless the user would thank you for it
- Grouped by urgency — critical (IRS deadlines), important (client uploaded docs), informational (weekly summaries)
- Delivered at the right time — not 11pm, not during obvious meeting blocks on calendar

**What triggers a proactive message:**

| Trigger | Message |
|---------|---------|
| IRS deadline < 48 hours | "Heads up — the Nguyen CDP response is due Friday. We still don't have their bank statements." |
| Client uploads documents to portal | "Rivera just uploaded 3 documents. Looks like the bank statements we've been waiting on." |
| Case has had no activity in 3+ weeks | "The Okafor OIC hasn't been touched in 3 weeks. The IRS typically responds within 6 months — we're at that window." |
| New IRS notice uploaded | "New CP2000 on the Chen case. Response window is 60 days from notice date — March 14th." |
| Uncontacted intake lead (24+ hours) | "2 new leads haven't been contacted yet — submitted yesterday morning." |
| Monday morning summary | Morning briefing pushed to phone: what's due this week, what changed over the weekend. |

**Delivery channels:**
- Push notification to mobile app
- WhatsApp/iMessage message (if user set that as preferred channel)
- Voice briefing when user opens the desktop app
- Summary email (optional, user configurable)

### Proactive Morning Briefing Example (Monday, via WhatsApp)

> **Agent (8:00am):** "Good morning. This week: 3 IRS deadlines — Nguyen on Friday is the most urgent (missing bank statements), Chen and Park both Thursday. 8 clients uploaded documents over the weekend. 2 OICs hit the 6-month follow-up window. Revenue: $67k invoiced last week, $23k outstanding past 30 days. Have a good week — I'll flag anything urgent as it comes up."

Short. Factual. Actionable. No fluff.

---

## 8. Phase 6 — Full Agentic Orchestration

> **The agent works through the day with the user.** It knows the full workload, builds a plan, executes the routine parts, and brings the human in only for decisions and approvals. Every permanent action confirmed by voice before it happens.

### The Core Rule

**Reads are automatic. Writes require a voice confirmation.**

The agent runs freely through: querying data, reading documents, pulling case files, searching emails, checking calendars, drafting content. It only pauses and presents to the user before: sending an email, filing a document, updating a case status, submitting anything to the IRS.

### The Morning Workflow

User opens the app or says "good morning."

**Agent:** "Morning. You have 5 things that need your attention today. Highest priority: Nguyen CDP hearing is Friday — response still not filed and we're missing her bank statements. Second: you have a call with the Martinez family at 2pm — their case is in active OIC negotiation, last call was 3 weeks ago. Third: 6 new documents came in overnight across 4 cases. Want me to start with Nguyen?"

**User:** "Yeah."

**Agent:** "I've checked — Nguyen still hasn't uploaded the bank statements. Last message to her was Tuesday. I'll draft a follow-up marked urgent."

**User:** "Do it."

**Agent:** "Here it is: 'Ms. Nguyen, we need your 2023 bank statements uploaded by Wednesday to meet your Friday IRS deadline. If you need help, call us now.' Send?"

**User:** "Send."

**Agent:** "Sent. Moving to the 2pm call prep. The Martinez case — OIC at $14,500, submitted 4 months ago, IRS assigned it to Revenue Officer Johnson. No counter-offer yet. Their income dropped since submission — do you want me to check if we should amend the offer?"

**User:** "Yeah check that."

**Agent:** "Based on the new 433-A they uploaded last month, their income dropped by $600/month. That lowers the RCP by about $4,800. We could amend the offer down to $9,700 and likely get a faster accept. Want me to draft an amended OIC?"

**User:** "Do it — I'll review it before the call."

The user has handled two critical cases, sent a client email, and has a draft amendment ready — all before 9am. They've made every decision; the agent handled all the prep and execution.

### Task Decomposition Engine

Every task is broken into atomic steps:

```
Task: "Prepare for the Martinez 2pm call"

Read steps (automatic):
  → Pull Salesforce case record
  → Pull S3 documents for case
  → Read last 3 call logs
  → Check portal — anything uploaded recently?
  → Check email thread with client

Write steps (voice confirm required):
  → Draft call prep summary → user reviews → user confirms to save
  → Draft amended OIC → user reviews → user confirms to send
  → Post-call: update case notes → user confirms
```

### State Persistence

If the user stops mid-workflow — closes laptop, takes a call, walks away — the agent saves state. When they return:

> "Welcome back. You were prepping for the Martinez call. We'd drafted the amended OIC. The call is in 35 minutes. Want to pick up where we left off?"

Everything is recoverable. No workflow is lost.

### Full Case Lifecycle Automation

With Phase 6 in place, the agent can handle the full lifecycle of a case from intake to resolution — with the human making every substantive decision:

**Intake:** New lead comes in → agent identifies case type from uploaded docs → drafts welcome + intake questionnaire → routes to correct caseworker

**Active case:** Manages document checklist → chases missing items → tracks IRS deadlines → drafts responses → prepares for hearings

**Resolution:** Drafts final resolution documents → coordinates signature → files with IRS (flags for human submission) → closes case in Salesforce → generates resolution summary for client

**Each step:** human confirms before anything permanent happens.

---

## 9. Phase 7 — Enterprise Hardening & Scale

> **Production-ready for any company.** Multi-user, fully auditable, self-service deployment, SOC 2 aligned. Ready to sell to 10-500 person firms.

### Multi-User

Currently single-session. Phase 7 enables full team deployment:

- Multiple concurrent sessions (vLLM already supports multi-sequence via `max-num-seqs` config)
- Per-user session isolation — each user has their own cache, history, undo stack, agent context
- Role-based access: partners see all cases, caseworkers see assigned cases only, admins see everything
- Team briefing: morning summary across the whole portfolio, surfaced to partners

### Admin Dashboard

Web UI (not voice) for IT and management:

- User provisioning and SSO configuration
- Role and permission management
- Approved specialist agent list (which agents this company has access to)
- Data source configuration (Salesforce org, S3 bucket, portal DB connection)
- Usage analytics per user, per feature, per data source
- Audit log export (CSV, filterable by date/user/action)
- Cost tracking per user per month

### Enterprise Safety Layer

| Feature | What it does |
|---------|-------------|
| Audit log | Every query, action, voice confirmation, email sent — logged with timestamp, user, input, output |
| SQL transparency | Every report shows the exact query that ran. Voice command: "show me the query" |
| Confirmation receipts | Every confirmed action recorded with the user's voice input and the action taken |
| Skill whitelist | Company controls which specialist agents are available — no external marketplace |
| Data residency | All processing in company's AWS account. No data leaves their VPC |
| Encryption | Data in transit (TLS 1.3) and at rest (AWS KMS keys, company-controlled) |

### SOC 2 Type II Alignment

Not certified at launch, but architecturally ready:

- All access is authenticated (SSO) and authorization-checked per query
- Full audit trail for security review
- No data stored outside company's AWS account
- Incident response process documented
- Penetration testing scheduled pre-launch

Certification timeline: 6-12 months after first enterprise contracts signed (~$30-50K cost, worth it for $150K+ ACV deals).

### BYOC (Bring Your Own Cloud) CDK Stack

```bash
cdk deploy SeishinStack \
  --context company=acme-tax-dispute \
  --context s3_bucket=acme-case-documents \
  --context salesforce_org=https://acme.salesforce.com \
  --context portal_db=postgresql://... \
  --context sso_provider=okta \
  --context bedrock_region=us-east-1
```

Provisions everything: EC2 GPU for ASR/TTS, Bedrock access, Lambda connectors, ALB, IAM roles, CloudWatch logging. Company pays AWS directly. You charge software license on top.

### Billing

| Tier | Price | Included | Target |
|------|-------|----------|--------|
| **Starter** | $49/seat/mo | 150 voice mins, 5 users, email + file ops, core DB connectors | Solo practitioner / 2-5 person shop |
| **Professional** | $99/seat/mo | 400 voice mins, 25 users, all connectors, audit logs, SSO, all specialist agents | Mid-size 10-50 person company |
| **Enterprise** | Custom ($150-250/seat) | Unlimited mins, unlimited users, BYOC deployment, dedicated support, custom agent build | Large company / software vendor white-label |

Annual discount: 20%.

**COGS at Professional tier (20 users):** ~$16/user/mo. Gross margin: ~84%.

**Billing stack:** Stripe (payments) + Lago (open source, self-hosted usage metering) — tracks voice minutes per user per session, emits events, generates invoices. Enterprise: PO-based, net-30.

---

## Deployment Timeline Summary

| Phase | What gets unlocked | Earliest deploy |
|-------|-------------------|----------------|
| **Phase 1** | Voice + DB queries, follow-up ops, first pilot customer | Once AWS quota approved (~2-3 weeks) |
| **Phase 2** | Email, file ops, calendar, client portal docs | +4 weeks after Phase 1 |
| **Phase 3** | Salesforce + S3 + unified hybrid queries | +4-6 weeks after Phase 2 |
| **Phase 4** | Specialist agents, hallucination checking, vector DB | +6-8 weeks after Phase 3 |
| **Phase 5** | Mobile app/WhatsApp, proactive notifications | +4 weeks after Phase 4 |
| **Phase 6** | Full agentic orchestration, morning workflow, state machine | +6-8 weeks after Phase 5 |
| **Phase 7** | Multi-user, admin dashboard, SOC 2 alignment, billing | +4-6 weeks after Phase 6 |

**Total to full product: ~9 months from Phase 1 deploy.**

Each phase is independently sellable. A company on Phase 1 is already getting value. Phase 4 is where it becomes genuinely transformative. Phase 6 is the final vision.

---

## Why This Is Different — One Summary

| What everyone else does | What we do |
|------------------------|-----------|
| Text/GUI interface | Voice-first, hands-free |
| Search company knowledge base | Query personal laptop + company data simultaneously |
| Ingest and index your data into their cloud | Query your existing sources on demand, store nothing |
| Autonomous agent that acts | User orchestrates — every permanent action confirmed by voice |
| One LLM for everything | Specialist agents per task, optimized system prompts |
| Trust the output | Hallucination checker verifies every fact before you hear it |
| Text chat on your laptop | Works on desktop, laptop, phone, WhatsApp |
| Reactive (answer questions) | Proactive (surfaces what you need before you ask) |

---

*Document compiled April 2026. Covers current state, market research, and full 7-phase roadmap from MVP to complete agentic assistant for tax dispute companies.*
