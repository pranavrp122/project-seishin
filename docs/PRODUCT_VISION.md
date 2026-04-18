# Seishin — Product Vision & Phased Roadmap

> A voice-first AI agent that gives every person in a tax resolution company instant access to everything they need — their own files, company case data, client documents, and the ability to act on it — all by speaking naturally.

---

## Table of Contents

1. [The Vision](#1-the-vision)
2. [What We've Built](#2-what-weve-built)
3. [The Market Opportunity](#3-the-market-opportunity)
4. [Phase 1 — Voice Intelligence Layer](#4-phase-1--voice-intelligence-layer)
5. [Phase 2 — Office Automation + Client Portal](#5-phase-2--office-automation--client-portal)
6. [Phase 3 — Unified Company Data](#6-phase-3--unified-company-data)
7. [Phase 4 — Specialist Agents + Hallucination Checking](#7-phase-4--specialist-agents--hallucination-checking)
8. [Phase 5 — Mobile + Proactive Push](#8-phase-5--mobile--proactive-push)
9. [Phase 6 — Full Agentic Orchestration](#9-phase-6--full-agentic-orchestration)
10. [Phase 7 — Enterprise Hardening](#10-phase-7--enterprise-hardening)
11. [How It All Fits Together](#11-how-it-all-fits-together)

---

## 1. The Vision

Tax resolution is a deeply human business. Clients come in scared — they have IRS notices, wage garnishments, liens on their homes. The people who help them are skilled professionals: enrolled agents, CPAs, attorneys who know the tax code inside out. The work they do is genuinely valuable.

But the work is also buried in logistics. Hours every day go into searching for documents, switching between systems, chasing clients for information, drafting the same types of emails for the thousandth time, pulling the same reports that management requests every Monday morning. For a company running hundreds or thousands of cases simultaneously, this is not a small problem — it is the central bottleneck between the people on staff and the outcomes they can deliver.

**Seishin is an AI agent that handles the logistics so the people can focus on the work.**

It lives on each person's laptop. You speak to it like you'd speak to a highly capable assistant. It can pull any case from the database, find any file on your machine or in the company's storage, draft any communication, surface any deadline, and — once you confirm — take action. Every role in the company gets their own agent that knows their context, respects their permissions, and operates within boundaries that the company controls.

The interface is voice because speaking is the fastest way to communicate and because this software is meant to be used while working — not as another window to stare at. By Phase 6, the agent will do the prep work for the day before the user even opens it, presenting ready-to-review outputs the moment they sit down. By the final phase, the entire company is running on it.

---

## 2. What We've Built

The technical foundation is complete and running. Here is what is live today:

**The voice pipeline:** User speaks → audio transcribed by Parakeet ASR → Gemma 4 (27B parameter LLM) classifies intent and generates response → Fish Speech synthesizes a natural voice → audio plays back. Full round trip. First audio response in under 1.5 seconds.

**The data layer:** Natural language queries are converted to SQL by Claude Haiku and run against the company database. Results are returned, voiced, and cached in memory. Follow-up commands — "filter to just the active ones," "sort by amount owed," "top 10" — execute in under 100 milliseconds against the cached data without re-querying the database. This is what makes the conversation feel instant.

**The intent system:** The agent understands 9 types of requests — new data queries, follow-ups on previous results, comparisons between two data sets, undo, discovery, data listing, confirm, cancel, and general conversation. All classified in real time.

**Quality safeguards built in from day one:** History-aware classification (understands "those" and "that" referring to prior results), fuzzy column matching (says "revenue" and gets `total_dollars`), date normalization ("last quarter" becomes real dates), compound request detection, and zero-result guidance that suggests a broader search rather than just saying nothing was found.

**Tests:** 114 passing across unit, integration, and end-to-end simulation.

What is waiting: AWS GPU quota approval (requested). Once approved, the system moves from running on local hardware to deploying into the company's own AWS account — their data, their infrastructure, their control.

---

## 3. The Market Opportunity

The AI-in-accounting market is valued at $10.9 billion in 2026 and growing at 44% per year. AI adoption among accounting and tax firms jumped from 9% to 41% in a single year. The demand is real and accelerating.

But voice AI adoption in financial services sits at just 11% — despite 91% of those same companies deploying AI in other forms. The gap exists because every AI product in this space is text and GUI. Nobody has built a voice-first interface for tax and financial professionals.

**The competitive landscape makes this clear:**

Every major player — Thomson Reuters CoCounsel, Harvey AI, TaxGPT, Microsoft Copilot for Finance, Amazon Quick Suite — is a text chat interface. They are also either too expensive for mid-market companies, locked into specific ecosystems, or require ingesting company data into a third-party cloud. For a company handling sensitive client tax information, putting that data into an external AI index creates real compliance exposure under IRC §7216 and IRS Publication 1075.

Our model is different: the agent queries the company's own data sources on demand and returns results. Nothing is indexed, nothing is copied, nothing is stored outside the company's own infrastructure. The company's data stays in the company's AWS account. This is not just a privacy feature — it is a compliance feature that directly addresses the legal exposure that makes competitors difficult to deploy in regulated financial services environments.

Combined with voice-first interaction and a per-person agent model, this is a product that does not exist in the market today.

---

## 4. Phase 1 — Voice Intelligence Layer

> *What gets deployed first. A complete proof of concept that delivers immediate value to every role — and establishes the foundation that every subsequent phase builds on.*

### What This Is

Phase 1 gives every person in the company a voice interface to their data. They can ask any question about the case portfolio, filter and slice the results naturally, find files on their machine, check their calendar, and draft emails that open directly in Outlook or Gmail. The agent is a desktop application — not a background process, not a browser extension. It opens when you want it and closes when you don't. When it's open, it is fully attentive.

This phase establishes the non-negotiable interaction principles that govern every feature in every phase that follows:

**Reads are instant, writes are confirmed.** The agent queries, searches, reads, and retrieves with no interruption. Before it sends anything, moves anything, or creates anything, it pauses and shows the user exactly what it is about to do.

**Every action has a visual.** When the agent drafts an email, the native Outlook or Gmail compose window opens on screen with the draft pre-filled. The user edits it directly in the app they already know. When it finds a file, File Explorer opens to the folder. The agent never operates in a black box.

**Email send queue — 5-minute delay.** No email sends the instant the user approves. It enters a visible queue with a countdown. The user can edit or cancel at any time during those 5 minutes. Given the stakes of IRS-related client communications, this is a permanent guardrail, not a temporary limitation.

**Audit log on everything.** Every query made, every file accessed, every email sent — logged with timestamp, user, and action. Available for compliance export.

### What It Can Do

**Company database queries — instant, natural language**

Every case management metric the company tracks is now accessible by voice. A case manager who used to open Salesforce, run a report, wait for it to load, and export it to Excel to filter it — now just asks. The results come back in 2-3 seconds and can be refined conversationally without rerunning anything.

Examples:
- "Show me all cases currently in the investigation phase"
- "Which cases have IRS response deadlines this week"
- "Filter those to just the ones without a filed response"
- "How many cases are in resolution right now versus last month"
- "Who has the highest caseload on the resolution team"

Each follow-up — another filter, a sort, a comparison — executes against the already-retrieved data in under 100 milliseconds. The conversation flows like talking to someone who has the whole database memorized.

**Local file operations**

- "Find the investigation file for case 4521" → File Explorer opens to the exact folder
- "Find all documents I worked on last week" → results listed by date, Explorer opens on selection
- "Move that to the Chen case folder" → File Explorer shows source and destination, user confirms, done

**Email drafting**

- "Draft a status update to this client" → Outlook compose window opens, draft pre-filled with the correct client name, case reference, and appropriate professional tone
- User edits directly in Outlook, says "send it"
- 5-minute queue starts. Visible countdown in the app sidebar.

**Calendar**

- "What do I have today?" → schedule voiced back
- "When is the next available time to schedule a call with the investigation team?" → checks calendar, suggests times

**Limited proactive — session start briefing**

When the agent opens each morning, before the user says anything, it automatically checks the database and surfaces the most important items. This is the first seed of what becomes a full proactive intelligence system in later phases. At Phase 1, it is simple and database-only:

> *"Morning. Quick update: 4 cases have IRS deadlines this week, and 6 clients still haven't uploaded the documents your team requested. Want to start with the deadlines or the missing documents?"*

The user does not have to ask. The agent already looked.

---

### Who Uses It — Phase 1 Roles in Action

**Case Manager**

A case manager's morning used to start with 20 minutes of navigating between Salesforce, the document portal, their email, and their local files just to understand what needed their attention. With Phase 1, they open the app and hear a briefing. They ask follow-up questions by voice. They find files by name. They draft client emails with a compose window that appears already written.

The most immediately valuable workflow: preparing for a client call. Instead of opening three systems and spending 10 minutes assembling context, they say "pull up everything on case 4521" and hear a summary in 3 seconds. Then: "draft a pre-call email to the client confirming the appointment." Outlook opens. They scan it, hit send. Queue starts.

**Executive / VP Level (Revenue Operations Example)**

An executive does not need to know about individual cases. They need to know whether the business is performing. Phase 1 gives them that by voice.

> *Executive opens the app Monday morning.*
>
> *Agent: "Morning. Quick update: you have 847 active cases. 23 have IRS deadlines this week. Investigation-phase cases are up 12% from last month, which is ahead of the intake volume trend. Resolution closures last week: 31. Average days to close in Q1 so far: 94, versus 108 same time last year. Anything you want to dig into?"*
>
> *Executive: "Show me resolution closures broken down by resolution type this quarter."*
>
> *Instant results. "We have 41 installment agreements, 28 offers in compromise, 19 currently not collectible, 14 penalty abatements. Want me to compare that to Q4?"*
>
> *"Yeah compare it."*
>
> *Sub-second. The agent already has last quarter cached. "OICs are up 34% quarter over quarter. Everything else is roughly flat."*

No dashboard. No report. No waiting. The executive got a full Monday morning business briefing in 4 minutes.

This is the value that sells Phase 1.

---

## 5. Phase 2 — Office Automation + Client Portal

> *Builds directly on Phase 1. Every feature in Phase 2 is only possible because Phase 1's infrastructure — the voice pipeline, the intent system, the database connectivity, and OpenClaw for local operations — is already in place.*

### What Phase 2 Adds

**Multi-user support.** Phase 1 can run for a single user. Phase 2 enables the full company — hundreds of users, concurrent sessions, each person with their own isolated context, history, and undo stack while sharing access to the same underlying data.

**Client portal connectivity.** The company's client portal — where clients upload documents, receive communications, and track their case status — becomes queryable by voice. Case managers can ask in real time what has and hasn't been submitted, without logging into a separate system.

- "Has Chen uploaded their 433-A?" → instant answer
- "Show me all clients in the investigation phase who haven't submitted their bank statements" → voiced list in 2 seconds
- "Which clients uploaded documents in the last 24 hours?" → instant

**Bulk email workflows with full visual control.** Building on Phase 1's single-email drafting, Phase 2 enables batch operations. "Draft document request emails to every client in investigation who is missing their financial disclosures" — the agent hits the portal database, identifies the subset, and opens an Outlook compose window for each client simultaneously. Each is fully pre-filled and independently editable. The user reviews, edits as needed, closes any they want to handle differently, and queues the rest. All in the send queue, all with individual cancel options.

**Calendar write operations.** Phase 1 reads the calendar. Phase 2 can create and modify events. The Google Calendar or Outlook event form opens pre-filled — the user reviews it before it's created. Nothing is scheduled without the user seeing it first.

**Advanced file operations.** Search across network drives and shared folders. Bulk organization with a preview list before any moves happen. Open any document directly — "open the Martinez 433-A" opens the file in the default application.

**Proactive briefing — Phase 2 form.** The session-start briefing now includes portal activity alongside the database summary:

> *"Morning. Overnight: 4 clients uploaded documents — Rivera sent bank statements, Chen sent their W-2, two others submitted items I'll need a reviewer to classify. 4 cases have IRS deadlines this week. 11 clients are past the 2-week mark with outstanding document requests. Want to start with the new uploads or the overdue requests?"*

---

## 6. Phase 3 — Unified Company Data

> *The product becomes genuinely different from anything else available. One voice command spans every system the company uses simultaneously — CRM, document storage, client portal, financial database, and the user's own local files.*

### What Phase 3 Adds

**Salesforce connector.** Every case record, contact, task, call log, and status update in Salesforce becomes queryable by voice. Users see only the cases and data they have permission to access — permissions inherit from the company's existing Salesforce profiles and role hierarchy. Nothing new to configure for data governance.

**AWS S3 connector.** All documents stored in the company's S3 buckets — scanned IRS mail, case files, uploaded client documents, correspondence — become searchable by case, by document type, by date. Read-only. Scoped to the company's own buckets.

**Unified result merger.** When a query spans multiple sources, results are merged before the voice response. The user hears a coherent answer, not a system-by-system readout.

### The Hybrid Query — The Core Differentiator

This is the feature that cannot be replicated by any competitor. One spoken sentence can simultaneously query Salesforce, S3, the client portal, the internal database, and the user's local machine — and return a single unified answer.

> *"Pull up everything we have on case 4521"*

The agent simultaneously:
1. Pulls the case record from Salesforce — status, assigned staff, timeline, tasks
2. Lists all documents in S3 for this case, sorted by date
3. Checks the client portal — what has been uploaded, what is missing per the checklist
4. Searches the user's local machine for any working files with this case number
5. Cross-references the Salesforce document checklist against what is actually on file

Result, spoken in approximately 3 seconds:

> *"Case 4521 — Chen estate, currently in active resolution. The IRS assigned a revenue officer last month. You have 12 documents in storage: the original notice, 3 years of returns, the 433-A, and 7 correspondence items. The checklist still shows the 2023 bank statements as outstanding — however, I can see the client uploaded something to the portal 18 minutes ago that I haven't classified yet. Want me to check if that's the bank statements?"*

**Every data source. One answer. Three seconds.**

Competitors either cannot do this at all, or require ingesting all of that data into a third-party cloud index — creating the IRC §7216 compliance problem. We query each source directly using the company's own credentials. Nothing is copied or stored outside their infrastructure.

### Document Review Specialist Agent

Phase 3 introduces the first specialist agent: the **Document Review Agent**. When documents are uploaded or found, this agent classifies them by type (IRS notice, 433-A, bank statement, pay stub, tax return), extracts key figures, and flags what is still missing for the specific resolution path this case is on (OIC requires different documents than an installment agreement). The result is voiced in plain language with specific gaps called out.

---

## 7. Phase 4 — Specialist Agents + Hallucination Checking

> *Every task now routes to a purpose-built specialist. The main LLM becomes a coordinator. Hallucination checking runs on every output before it reaches the user — no number, date, or figure is presented unless it can be sourced back to a verified document.*

### The Architecture Shift

In Phases 1-3, the main language model handles everything. Phase 4 introduces a specialist agent layer. When a user makes a request, the orchestrator identifies what type of task it is, retrieves the right specialist agent from a vector database, injects the relevant case context, and lets the specialist execute. Each specialist has a system prompt that is deeply optimized for its job.

The vector database stores each agent as a record: name, description, task types, the full system prompt, required context fields, and expected output format. Adding a new specialist requires writing its system prompt and adding a record — no code change needed.

```
User: "Draft an Offer in Compromise for case 4521"

Orchestrator:
  → Identifies: OIC drafting task
  → Vector search: retrieves OIC Calculator & Drafter (highest relevance match)
  → Fetches context: 433-A from portal, income/expense data from DB, total liability from Salesforce
  → Calls specialist with full context injected

OIC Calculator & Drafter:
  → Applies IRS Reasonable Collection Potential formula
  → Calculates monthly disposable income
  → Derives offer amount with appropriate cushion
  → Drafts Form 656 cover letter citing every figure from source data

Hallucination Checker:
  → Verifies every dollar amount against the source document it came from
  → Verifies every date against case records
  → Verifies client name and case number against Salesforce
  → Tags anything that cannot be sourced: [unverified — please confirm]

Result voiced to user. Document opens in Word for review.
```

### The Specialist Agent Roster

| Agent | What It Handles |
|-------|----------------|
| **IRS Response Letter Writer** | CP2000, CP503, CP504, levy release, audit response — IRS formatting, deadlines, required regulatory language |
| **OIC Calculator & Drafter** | Reasonable Collection Potential math, 433-A analysis, offer recommendation, Form 656 and cover letter |
| **CDP Hearing Preparer** | Collection Due Process arguments, hearing prep, supporting documentation checklist |
| **Penalty Abatement Writer** | First-time abatement, reasonable cause arguments, correct form and submission process |
| **Installment Agreement Drafter** | Streamlined vs non-streamlined, eligibility check, monthly payment calculation, Currently Not Collectible consideration |
| **Financial Disclosure Analyzer** | 433-A/433-B analysis, IRS National Standard expense allowances, income verification, net equity |
| **Client Communication Agent** | Status updates, document request letters, intake welcome emails, hearing instructions — client-facing tone |
| **New Client Intake Agent** | Case type identification from uploaded documents, initial liability summary, recommended resolution path |
| **Case Status Summarizer** | Clean, factual summaries for partner reviews, internal handoffs, client updates |
| **Deadline Tracker Agent** | IRS calendar awareness, response windows, statute of limitations, extension deadlines |

### Hallucination Checking — Why This Matters

Every other AI product in this space has the same problem: the model is trained on general knowledge and will confidently generate plausible-sounding numbers that are wrong. In tax resolution, a wrong figure in an OIC submission or an IRS response letter is not a minor error — it can harm the client's case.

Every output from a specialist agent runs through a verification step before reaching the user. The checker cross-references each specific claim against the source documents retrieved for that task. A liability figure must match the case database. An income figure must match the 433-A from the portal. An IRS notice date must match the scanned notice in S3. If it cannot be verified, it is tagged explicitly. The user sees exactly what is confirmed and what needs their judgment.

This adds approximately 200 milliseconds to response time. For content that may be submitted to the IRS, it is the most important 200 milliseconds in the system.

---

### Phase 4 in Action — Tax Professional Example

A senior enrolled agent is working on an OIC for a complex case. Historically this takes 90 minutes: pulling the 433-A, running the RCP calculation manually, looking up the current IRS National Standards for the client's county, drafting the cover letter, verifying everything lines up.

> *"Draft an Offer in Compromise for case 4521. Client's income has changed since we last ran the numbers."*

Agent pulls: 433-A from portal (uploaded 2 weeks ago), current income from the most recent pay stubs, IRS National Standards for Orange County (current year), total liability from the database.

OIC agent runs the math. Hallucination checker verifies each figure against its source. Word opens with the completed Form 656 cover letter pre-populated.

> *"Based on the updated 433-A and current IRS expense standards for this county, the Reasonable Collection Potential comes to $11,200. I'd recommend offering $12,500 — that's a 10% cushion above RCP, which tends to move faster. Every figure in the draft has been verified against the source documents. The one I couldn't confirm is the client's vehicle equity — that field was left blank on the 433-A. You'll want to address that before filing."*

The draft is on screen. One unresolved item flagged. The enrolled agent reviews, addresses the vehicle equity question, confirms, queues. Done in 12 minutes instead of 90.

---

## 8. Phase 5 — Mobile + Proactive Push

> *The agent stops waiting to be opened. Push notifications reach users wherever they are. The morning briefing arrives before the workday starts. WhatsApp integration means the agent is accessible from any phone without installing anything new.*

### What Phase 5 Adds

**Mobile app (iOS and Android).** A lightweight app that mirrors the desktop experience. Tap to speak, see transcription, hear the response. Full access to every capability from Phases 1-4. SSO login. Secure connection to the company's VPC.

**Messaging platform integration via OpenClaw.** The agent connects to WhatsApp, iMessage, and other platforms the company uses. A case manager can send a WhatsApp message asking "has Chen uploaded their 433-A yet?" from their car between appointments and get an instant answer. No additional app required.

**Push notifications — proactive without requiring the app to be open.**

| What triggers it | What the user receives |
|-----------------|----------------------|
| IRS deadline within 48 hours | Alert with case number, deadline, current document status |
| Client uploads to portal | "New documents from [client] — [X items] uploaded" |
| Case dormant for 3+ weeks | Flag for case manager and supervisor |
| New IRS notice detected in S3 | Alert with notice type, response window, assigned staff |
| Uncontacted new intake after 24 hours | Alert for intake team |

**Delivered to:** phone notification, WhatsApp/iMessage, or the desktop app — user configures preference.

**Proactive morning briefing — pushed, not pulled.** At a configured time each weekday morning, before the user opens any application, the agent assembles a briefing from all connected sources and delivers it to their phone.

> *Agent, 8:00am via WhatsApp:*
> *"Morning. This week: 6 IRS deadlines — 2 need responses that aren't drafted yet. 14 clients uploaded documents over the weekend. Pipeline update: 847 active cases, 31 in resolution closing range. 3 enrolled agents are over capacity based on current caseloads. I'll flag anything urgent as it comes in — have a good week."*

The user reads this before they even open their laptop. They arrive at their desk already knowing what matters. That is the value.

---

## 9. Phase 6 — Full Agentic Orchestration

> *The complete vision. The agent knows what needs doing, works through the day alongside the user, handles all preparation and logistics automatically, and brings the human in only for the decisions that require human judgment. Every action — every single one — still confirmed before execution.*

### How It Works

When the user opens the agent (or when their morning briefing arrives), the agent has already done the morning's preparatory work. It has read every case with upcoming deadlines, reviewed every overnight upload, checked the calendar for the day, and assembled ready-to-review outputs. The user is not starting from scratch — they are reviewing and approving work that has already been prepared.

The core rule has not changed from Phase 1: **reads are automatic, writes require confirmation.** The scope of "reads" has simply expanded. The agent can now do everything involved in preparing a task — pulling data, reading documents, drafting letters, calculating figures, researching relevant IRS guidance — entirely on its own. It only stops when it is about to do something that affects the outside world.

### The Morning Workflow

> *Case manager opens the agent at 9am.*
>
> *Agent: "Morning. I've done some prep. For the Chen case — CDP hearing is Thursday and the prep document is ready for your review, I just need you to look it over. For the Nguyen case — bank statements just came in and I've already analyzed them, income looks slightly higher than what was on the 433-A, which may affect the OIC calculation. I've flagged the discrepancy in a note. For the new Park intake from this morning — I've classified the documents, identified this as an installment agreement case, and drafted the welcome email. 3 minutes to review these and you'll have cleared most of your morning queue."*
>
> *Case manager: "Start with Chen."*
>
> *Agent: "The CDP response draft is open in Word. I've built the argument around economic hardship — it's the strongest angle given the financial disclosure. Every figure has been verified against the 433-A. There's one item I wasn't sure about: the client mentioned a rental property on the intake form but I don't have documentation for it in S3. I've flagged it in the document. Everything else is sourced."*
>
> *Case manager reviews, addresses the rental property flag, confirms to queue for attorney review.*
>
> *Total time: 8 minutes. Historically: 45.*

### State Persistence

If a workflow is interrupted — the user takes a call, closes the laptop, steps away — the agent saves its state. When they return:

> *"Welcome back. You were in the middle of the Chen CDP response — the draft is ready and you'd reviewed it to the rental property flag. The Thursday deadline is now 38 hours away. Want to continue?"*

Nothing is lost. Every workflow is resumable.

### Full Case Lifecycle Support

From intake to resolution, the agent supports every phase of case management:

**Intake.** New client's documents come in. Agent classifies them, identifies the resolution path, drafts the welcome message and intake questionnaire, routes to the correct team based on case type and current team capacity.

**Active case.** Tracks the document checklist, surfaces missing items, drafts IRS correspondence, prepares for hearings, monitors for IRS responses in S3, flags deadlines before they become crises.

**Resolution.** Drafts final resolution documents, coordinates the signature workflow, closes the case in Salesforce, generates the client-facing resolution summary.

At every step: the human confirms. The agent prepares.

---

## 10. Phase 7 — Enterprise Hardening

> *The product is ready for any company at any scale. Role-based access, full administrative control, SOC 2 alignment, and self-service deployment so new customers can be onboarded without engineering time.*

### What Phase 7 Adds

**Full role-based access control.** Every user has a defined role — Case Manager, Senior Manager, Department Head, Executive, IT Administrator — and their data access, agent capabilities, and notification scope are tied to that role. Permissions inherit from the company's existing SSO provider (Okta, Google Workspace, or Microsoft Entra) — no parallel permission system to maintain.

**Admin dashboard (web interface).** IT and operations teams manage the system here. User provisioning, role assignment, data source configuration, approved agent roster, usage analytics per user and per feature, audit log export, and cost tracking. Everything accessible to the people responsible for running the system, without requiring them to use the voice interface.

**Enterprise-grade security compliance:**
- Full audit trail on every query, action, and confirmation — exportable for compliance review
- All data processing within the company's own AWS VPC — nothing leaves their infrastructure
- Encryption in transit (TLS 1.3) and at rest (AWS KMS, customer-controlled keys)
- SOC 2 Type II architectural alignment — not certified at launch, positioned for certification after first enterprise contracts are signed

**Self-service deployment.** A new customer can deploy the full stack into their own AWS account using the provided CDK package — one command, one configuration file. The company pays AWS directly for infrastructure costs. We charge a software license on top.

**Team-level proactive intelligence.** Department heads and executives receive portfolio-level briefings — not individual case details, but cross-team performance, capacity distribution, deadline exposure across the whole operation, and trend analysis week over week.

---

## 11. How It All Fits Together

The seven phases are not separate products. Each one is a layer that is only possible because the previous layer exists. Here is how the progression works:

| Phase | What It Requires From Before | What It Unlocks |
|-------|------------------------------|----------------|
| **Phase 1** | The voice pipeline + DB connector we've already built | Voice queries, file ops, email drafting, basic morning summary |
| **Phase 2** | Phase 1's OpenClaw integration + DB connectivity | Multi-user, bulk operations, portal access, richer briefings |
| **Phase 3** | Phase 2's multi-user architecture + SSO layer | Salesforce + S3 connectors, hybrid queries across all sources |
| **Phase 4** | Phase 3's unified data access + all sources connected | Specialist agents that can pull from any source, hallucination checking |
| **Phase 5** | Phase 4's complete intelligence layer | Push notifications and mobile — delivery of smart content to any device |
| **Phase 6** | Phase 5's proactive foundation | Overnight prep work, full workflow orchestration, lifecycle management |
| **Phase 7** | Phase 6's full capability set | Enterprise-ready packaging, admin control, SOC 2, multi-company deployment |

**Phase 1 is a proof of concept that is genuinely useful.** A company deploys it and immediately sees every employee spend less time searching for information and more time doing their actual work. The morning briefing alone — instant, accurate, requiring no action — is a daily demonstration of what the product is becoming.

**Phase 4 is where it becomes transformative.** Specialist agents with verified outputs mean professionals can produce IRS-quality documents in a fraction of the time, with confidence in the numbers.

**Phase 6 is the full vision.** The agent does the prep. The professional does the work.

---

### The Proactive Intelligence Progression

One thread runs through all phases — the system's ability to surface what matters without being asked. Here is how it evolves:

| Phase | What "proactive" means |
|-------|----------------------|
| 1 | App opens → 3-item DB summary voiced automatically |
| 2 | Summary expands to include portal activity and overnight uploads |
| 3 | Full cross-source briefing: every system checked, items ranked by urgency |
| 4 | Specific task suggestions: "I can draft this now — want me to start?" |
| 5 | Pushed to phone before the user opens anything |
| 6 | Work prepared overnight, ready for review at session start |
| 7 | Portfolio-level briefings distributed to team leads and executives |

---

### Why This Product Wins

No existing product combines all of the following:

- **Voice-first interface** built for professionals who have their hands full and can't be at a keyboard
- **Personal + company data unified** — one query reaches local files, CRM, document storage, and client portal simultaneously
- **Stateless query model** — we query your existing systems, we don't ingest your data. Your client information never leaves your infrastructure. This is the compliance answer to every competitor's problem.
- **User orchestrates, not the system** — every write confirmed by voice. Liability stays with the professional. The agent accelerates; the human decides.
- **Specialist agents per task** — not one model trying to do everything, but purpose-built intelligence for each job, with verified outputs
- **Proactive by design** — the agent knows what matters before you ask, and it keeps getting better at knowing

---

*Written April 2026.*
