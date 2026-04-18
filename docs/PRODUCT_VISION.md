# Seishin — Product Vision & Phased Roadmap

> A voice-first AI agent that gives every person in a tax resolution company instant access to everything they need — their own files, company case data, client documents, and the ability to act on it — all by speaking naturally.

---

## Table of Contents

1. [The Vision](#1-the-vision)
2. [What We've Built](#2-what-weve-built)
3. [The Market Opportunity](#3-the-market-opportunity)
4. [Phase 1 — Voice Intelligence Layer](#4-phase-1--voice-intelligence-layer)
5. [Phase 2 — Office Automation + Access Control](#5-phase-2--office-automation--access-control)
6. [Phase 3 — Unified Company Data](#6-phase-3--unified-company-data)
7. [Phase 4 — Specialist Agents + Hallucination Checking](#7-phase-4--specialist-agents--hallucination-checking)
8. [Phase 5 — Mobile + Proactive Push](#8-phase-5--mobile--proactive-push)
9. [Phase 6 — Full Agentic Orchestration](#9-phase-6--full-agentic-orchestration)
10. [Phase 7 — Enterprise Hardening](#10-phase-7--enterprise-hardening)
11. [How It All Fits Together](#11-how-it-all-fits-together)
12. [Features to Specify Before Build Begins](#12-features-to-specify-before-build-begins)

---

## 1. The Vision

Tax resolution is a deeply human business. Clients come in scared — IRS notices, wage garnishments, liens on their homes. The professionals who help them are genuinely skilled: enrolled agents, CPAs, attorneys who know the tax code and the collections process inside out. The work they do matters.

But the work is buried in logistics. Every day, hours go into searching for documents, switching between systems, chasing clients for missing information, drafting the same types of communications for the thousandth time, and pulling the reports that management asks for every Monday morning. For a company running hundreds or thousands of cases simultaneously, this is not a small problem. It is the central bottleneck between the people on staff and the outcomes they can deliver.

**Seishin is an AI agent that handles the logistics so the professionals can focus on the work.**

It lives on each person's laptop. You speak to it the way you would speak to a highly capable assistant. It pulls any case, finds any file, drafts any communication, surfaces any deadline — and once you confirm, it acts. Every role gets an agent that knows their context, respects their access level, and operates within boundaries the company controls.

The interface is voice because speaking is the fastest way to communicate, and because this software is designed to be used while working — not as another window to manage. By the final phase, the agent will prepare work overnight and present ready-to-review outputs the moment the user sits down. Every decision still belongs to the person.

---

## 2. What We've Built

The technical foundation is complete and running. Here is what exists today:

**The voice pipeline.** User speaks → audio transcribed by Parakeet (speech recognition model) → Gemma 4 (27 billion parameter language model) classifies the request and generates a response → Fish Speech converts the text to a natural-sounding voice → audio plays back. Full round trip, first audio response in under 1.5 seconds.

**The data layer.** Natural language questions are converted to SQL by Claude Haiku (a fast, efficient language model from Anthropic) and run against the company database. Results are returned and voiced back. Follow-up commands — "filter to just the active ones," "sort by amount owed," "top 10" — execute in under 100 milliseconds against the already-retrieved data without re-querying the database. This is what makes the conversation feel instant rather than like waiting for a report.

**The intent system.** The agent understands 9 types of requests — new data queries, follow-ups on previous results, comparisons between data sets, undo, discovery, data listing, confirm, cancel, and general conversation. All classified in real time by the language model.

**OpenClaw.** An open-source personal automation framework that runs on the user's laptop alongside the voice interface. It handles local operations — finding and opening files, connecting to email accounts via OAuth, reading and writing calendars. OpenClaw manages the underlying email delivery (Gmail API, SMTP) and calendar API connections. The visual presentation of emails and actions happens inside the Seishin app itself — OpenClaw is the execution engine, Seishin's UI is what the user sees and edits. In Seishin, OpenClaw starts when the app starts and stops when the app closes. It is not a background process.

**Quality safeguards already in place.** History-aware classification (understands "those" and "that" in context), fuzzy column matching ("revenue" finds `total_dollars`), date normalization ("last quarter" becomes real dates), compound request detection, and zero-result guidance that suggests a broader search rather than just reporting no results.

**Tests.** 114 passing across unit, integration, and end-to-end simulation.

**What is pending.** AWS GPU quota approval (submitted). Once approved, the system moves from local hardware to the company's own AWS account — their infrastructure, their data, their control.

**Note on pre-Phase 4 outputs.** Until Phase 4 introduces automated hallucination checking, the user is the verification layer. This is an acceptable and deliberate design choice: every write action (sending, moving, filing) requires explicit confirmation before it happens. The user reviews before anything goes out. Phase 4 adds a second layer of machine verification on top of that — it does not replace the human, it assists them.

---

## 3. The Market Opportunity

The AI-in-accounting market is valued at $10.9 billion in 2026 and growing at 44% per year. AI adoption among accounting and tax firms jumped from 9% to 41% in a single year. The demand is real and accelerating.

Voice AI adoption in financial services sits at just 11% — despite 91% of those same companies deploying AI in other forms. The gap exists because every AI product built for this space is text and GUI. No one has built a voice-first interface for tax and financial professionals.

**The competitive landscape is clear:**

Every major player — Thomson Reuters CoCounsel ($75-500/user/month), Harvey AI ($1,000+/user/month, 20-seat minimum), TaxGPT, Microsoft Copilot for Finance — is a text chat interface. They are also either prohibitively expensive for most companies, locked into specific software ecosystems, or they require ingesting company data into a third-party cloud.

For a company handling sensitive client tax information, putting that data into an external AI index creates real compliance exposure. IRC §7216 requires written client consent before client information is used for anything beyond direct tax services. IRS Publication 1075 imposes strict controls on all Federal Tax Information. Most competitor products are structurally incompatible with these requirements.

**Our model is different.** The agent queries the company's own data sources on demand and returns results. Nothing is indexed, nothing is copied, nothing is stored outside the company's own infrastructure. The client data stays in the company's AWS account, accessed through the company's own credentials. This is not just a privacy feature — it is the compliance answer that makes deployment possible where competitors cannot go.

---

## 4. Phase 1 — Voice Intelligence Layer

> *First deployment. Proof of concept that delivers immediate value to every role from day one. Nothing here is experimental — it is the complete foundation that every subsequent phase builds on.*

### The Core Interaction Principles

These rules are established in Phase 1 and never change, regardless of how capable the system becomes in later phases.

**Reads are instant, writes are confirmed.** The agent queries, searches, reads, and retrieves freely. Before it sends, moves, creates, or modifies anything, it pauses and shows the user exactly what it is about to do — inside the Seishin app. The user approves. Then it happens.

**Everything stays in the app — except the browser.** For file moves, calendar events, and all internal actions, the agent shows a confirmation card inside Seishin before doing anything. The user never needs to leave the app for those. The one deliberate exception is browser tasks: when the agent needs to do web research, look something up, or take action on a website, it opens a Chrome tab. This is intentional — the user needs to see the actual web content, and Chrome is the right tool for it. The agent announces what it is opening and why, and voices a summary when it is done.

**Browser research and automation via Chrome.** If a user asks the agent to research something — look up IRS guidance, check a client's public business records, find a form on the IRS website, look up a revenue officer's contact — the agent opens Chrome, navigates to the relevant page, and voices back what it found. OpenClaw's browser automation handles navigation and data extraction. For read-only research, Chrome opens automatically. For any action in the browser (filling a form, submitting something), the agent pauses and voices what it is about to do before proceeding — the same confirmation rule applies.

**Emails get a full compose view within the app.** Email is the most consequential write action in this workflow — messages go to clients and to the IRS. Rather than trusting a voice description or opening a third-party compose window, Seishin renders a complete email compose panel inside the app: To, From, Subject, and Body all visible and editable, styled to look and feel like a real email. The user reads the full structure, edits any field directly, and then approves. This pattern is established in products like Spark AI, Fyxer, and Microsoft's Power Apps agent approval cards — we are applying it to the tax resolution context with full in-app control.

Technically, this is built as a React component inside the Tauri desktop app. OpenClaw handles the email OAuth connection and actual delivery (Gmail API / SMTP) in the background. The compose view is our own UI — which means it works consistently regardless of whether the company uses Outlook, Gmail, or any other email provider. We are not dependent on or limited by any external email client.

**Email send queue — 5-minute delay.** After the user approves in the compose view, the email enters a visible queue with a countdown. Cancel or edit at any point during those 5 minutes. Given the stakes of client and IRS communications, this is permanent.

**Audit log on everything.** Every query, file access, and email sent is logged with timestamp, user, and action. Available for compliance export.

---

### What Phase 1 Delivers

**Company database queries — instant, conversational**

Any case management metric is now accessible by voice. A case manager who previously opened the CRM, navigated to a report, waited for it to load, and exported it to filter it — now just asks. Results in 2-3 seconds, refineable in conversation without re-running anything.

- "Show me all cases currently in the investigation phase"
- "Which cases have IRS response deadlines this week"
- "Filter to only the ones where we haven't filed a response yet"
- "How many cases are in resolution right now versus last month"
- "Who on the resolution team has the highest active caseload"

Each follow-up — another filter, a sort, a comparison — executes in under 100 milliseconds against the already-retrieved data.

**Local file search and document opening**

- "Find the investigation file for case 4521" → app shows a file card: filename, folder path, last modified. Click or say "open it" to launch in the default application.
- "Open the Chen 433-A" → document opens in the default viewer (PDF reader, Word, etc.) directly from the app
- "Find all documents I worked on last week" → listed by date in the app panel, open any by voice or click

Note: File *moving* and *organizing* are intentionally deferred to Phase 2. Phase 1's local operations are read-only (find and open) to keep the first deployment focused and low-risk. Phase 2 adds write operations once the confirmation patterns are proven in production.

**Email drafting (no file moves yet)**

- "Draft a status update to the client on case 4521" → in-app email compose panel opens showing: To, Subject, and full Body, pre-filled with the correct client name, professional tone, and case reference
- User reads the full email structure, edits any field directly in the panel
- Says "send it" or clicks Send → 5-minute queue starts, visible in the app sidebar
- Cancel or re-edit anytime during the countdown

**Calendar read**

- "What do I have today?" → schedule voiced back
- "When's my next available time this week?" → reads calendar, suggests times

**Proactive — session start briefing (Phase 1 form)**

When the agent opens, before the user says anything, it checks the database and surfaces the most important items automatically. This is the first, simplest version of what grows into a full proactive intelligence system over later phases. At Phase 1 it is database-only:

> *"Morning. 4 cases have IRS deadlines this week, and 6 clients haven't uploaded the documents your team requested yet. Want to start with the deadlines?"*

No dashboard. No navigation. The information is there.

---

### Who Uses It — Phase 1 in Action

**Case Manager**

Opens the agent. Hears what needs attention. Asks by voice. Gets instant answers. Drafts client emails — the full compose view appears in the app, pre-filled and ready to edit. The daily information retrieval that used to take 20-30 minutes takes 5.

**Executive — Monday Morning Revenue Review**

> *Executive opens the app.*
>
> *Agent: "Morning. You have 847 active cases. Investigation-phase volume is up 12% from last month — ahead of intake trends. Resolution closures last week: 31. Average days to close this quarter: 94, down from 108 this time last year. 4 cases have IRS deadlines this week, 2 without filed responses yet."*
>
> *Executive: "Show me resolution closures broken down by type this quarter."*
>
> *Agent: "41 installment agreements, 28 offers in compromise, 19 currently not collectible, 14 penalty abatements. Want me to compare that to Q4?"*
>
> *Executive: "Yes."*
>
> *Agent: "OICs are up 34% quarter over quarter. Everything else roughly flat."*

No dashboard. No waiting for a report. Full business picture in 3 minutes.

This is the demonstration that sells the product.

---

## 5. Phase 2 — Office Automation + Access Control

> *Builds on Phase 1's foundation in two critical ways: it enables the full team to use the system simultaneously with proper permission boundaries, and it adds the write operations (file moves, calendar events, bulk email) that Phase 1 deliberately held back.*

### Why Access Control Comes Here, Not Phase 7

Deploying a multi-user system without role-based access control is not acceptable in a regulated financial services company. A case manager should not see executive financial data. An executive should not accidentally access case files outside their purview. Senior and junior staff have different levels of data access.

Phase 2 solves this before enabling concurrent team use. Permissions inherit from the company's existing SSO provider (Okta, Google Workspace, or Microsoft Entra) — the role definitions and data access boundaries already configured in the company's identity system flow directly into the agent. No parallel permission system to maintain.

**Role tiers established in Phase 2:**

| Role | What they can access |
|------|---------------------|
| Case Manager | Assigned cases only, client communications, their own local files |
| Senior Manager / Team Lead | Department-level case data, team workload distribution, escalations |
| Department Head / VP | Full department portfolio, performance metrics, capacity data |
| Executive / C-Suite | Company-wide business metrics — volume, revenue, performance trends. Not individual case detail unless they drill in. |
| IT Administrator | System configuration and audit logs, no access to case data |

The voice interface respects these boundaries automatically. An executive asking "how many cases are overdue?" gets a company-wide answer. A case manager asking the same question gets an answer scoped to their assigned cases.

**Concurrency model.** All users connect to the same inference server running in the company's AWS VPC. Each user's session is isolated — their conversation history, their cached data results, and their undo stack are private. The underlying data sources are shared. This is the same model as any multi-user SaaS: one backend, isolated sessions.

---

### What Phase 2 Also Adds

**File write operations (held back from Phase 1).**
- "Move this to the Chen case folder" → app shows a confirmation card: source path, destination path, filename. User confirms in the app, then the move executes.
- "Organize my downloads by case number" → preview list of what will move where, user confirms, then bulk move
- "Rename this to include the case number" → shows proposed new name, user confirms

**Calendar write operations.**
- "Schedule a call with the Chen investigation team Thursday at 2pm" → app shows an event card: title, date/time, attendees, description. User confirms in the app, then the event is created via calendar API.
- "Block Friday morning for hearing prep on case 4521" → same flow
- "Reschedule my 3pm to next week" → shows proposed change, user confirms

**Bulk email workflows.**
- "Draft document request emails to every investigation-phase client missing their financial disclosures" → agent queries the portal database, identifies the subset, and opens a scrollable email queue panel inside the app — one compose card per client, each showing To, Subject, and Body pre-filled. Each card is independently editable. The user scrolls through, tweaks what they need, removes any they want to handle separately, and approves the rest. All queued with individual countdowns and cancel buttons in the app sidebar.

**Client portal connectivity (read-only).**
- "Has Chen uploaded their 433-A?" → instant answer from portal database
- "Show me all investigation-phase clients who haven't submitted their bank statements" → voiced list in 2 seconds
- New portal uploads appear in the morning briefing

**Browser research and automation via Chrome.**
When the agent needs to look something up or take action on the web, it opens a Chrome tab. The user sees exactly what it is doing in real time — no black box.

Read-only research (opens automatically, no confirmation needed):
- "Look up the current IRS National Standards for Orange County" → Chrome opens to IRS website, agent extracts the figures and voices them back, then uses them in the OIC calculation
- "Find the revenue officer contact info for district 4521" → Chrome opens, agent searches and voices the result
- "Look up the penalty rates for 2024 payroll tax failures" → Chrome opens to IRS guidance, agent summarizes

Browser actions (agent announces intent, user confirms before executing):
- "Fill out the IRS payment plan request on their website" → agent voices what it is about to submit, user confirms, Chrome completes the form
- "Download the updated 433-A form from the IRS website" → Chrome navigates, file saves, agent voices where it was saved

OpenClaw's browser automation handles navigation and extraction. Chrome is the deliberate exception to the "stay in app" rule because users need to see actual web content — and being able to watch the agent navigate live builds trust in what it is doing.

**Proactive — Phase 2 form.**
Morning briefing now includes portal activity alongside database summary:

> *"Morning. Overnight: Rivera submitted bank statements, Chen sent a W-2, two other clients uploaded documents that need classification. 4 cases have IRS deadlines this week. 11 clients are past the 2-week mark on outstanding document requests. Where do you want to start?"*

---

## 6. Phase 3 — Unified Company Data

> *The product becomes genuinely different from anything else available. One voice command spans every system the company uses simultaneously. The technical foundation from Phases 1 and 2 — the intent system, the permission layer, the session architecture — is what makes this possible.*

### What Phase 3 Adds

**Salesforce connector.** Every case record, contact, task, call log, and status update in Salesforce becomes queryable by voice. Users see only the cases and data their Salesforce profile permits — the existing role hierarchy maps directly. No new access configuration needed.

**AWS S3 connector.** All documents in the company's S3 storage — scanned IRS mail, case files, uploaded client documents, correspondence — become searchable by case, type, and date. Read-only. Scoped to the company's own buckets.

**Unified result merger.** When a query spans multiple systems, results are merged before the voice response. The user hears a coherent answer, not a system-by-system readout.

**Fallback behavior.** If a connector is unreachable (network issue, API timeout), the agent voices which sources it could and could not reach, delivers the partial result, and flags what may be incomplete. It never silently returns incomplete data as if it were complete. If the query cannot be answered with sufficient confidence, it says so.

### The Hybrid Query

One spoken sentence simultaneously queries the CRM, document storage, client portal, internal database, and local machine — and returns a single unified answer. No other product in this space can do this.

> *"Pull up everything we have on case 4521"*

The agent simultaneously:
1. Pulls the case record from Salesforce — status, assigned staff, timeline, tasks
2. Lists all documents in S3 for this case by date
3. Checks the client portal — what has been uploaded, what the checklist still requires
4. Searches the user's local machine for any working files related to this case
5. Cross-references the Salesforce document checklist against what is actually on file

Voiced back in approximately 3 seconds:

> *"Case 4521 — Chen estate, active resolution. Revenue officer assigned last month. 12 documents in storage: original notice, 3 years of returns, the 433-A, 7 correspondence items. The checklist shows 2023 bank statements still outstanding — but the client uploaded something to the portal 18 minutes ago that hasn't been classified yet. Want me to check if that's the bank statements?"*

**Every data source. One answer. Three seconds.** Previously: 8-10 minutes of manual navigation across multiple systems.

**Note on CRM flexibility.** Phase 3 specifies Salesforce because it is the most common CRM in this sector. The connector architecture is designed to support other systems — HubSpot, custom CRMs, or practice management platforms — through additional connectors built on the same pattern. A company not on Salesforce is not excluded; they are a Phase 3 connector build rather than a Phase 3 include.

---

## 7. Phase 4 — Specialist Agents + Hallucination Checking

> *Every meaningful task now routes to a purpose-built specialist agent. The main language model becomes a coordinator. And every output is verified against source documents before the user hears it — no number, date, or figure is presented unless it can be traced back to a specific document.*

### The Architecture

The main language model classifies the task type, retrieves the appropriate specialist agent from a vector database, injects the relevant case context, and lets the specialist execute. Each specialist has a system prompt that is deeply optimized for its specific job. The vector database stores each agent as a record: name, description, task types, the full system prompt, required context fields, and expected output format.

Adding a new specialist requires writing its system prompt and adding a record to the database — no code change required. The system grows with the company's needs.

```
User: "Draft an Offer in Compromise for case 4521"

Orchestrator:
  → Identifies: OIC drafting task
  → Vector search retrieves: OIC Calculator & Drafter
  → Fetches context: 433-A from portal, income data from DB, liability from Salesforce
  → Calls specialist with full context

OIC Calculator & Drafter:
  → Applies IRS Reasonable Collection Potential formula
  → Calculates monthly disposable income
  → Derives offer amount with cushion above RCP
  → Drafts Form 656 cover letter, every figure cited from source

Hallucination Checker:
  → Verifies each dollar amount against the source document it came from
  → Verifies each date against case records
  → Verifies client name and case number against Salesforce
  → Tags unverifiable claims: [unverified — please confirm]

Result voiced. Document opens in Word.
```

### The Specialist Agent Roster

| Agent | What It Handles |
|-------|----------------|
| **IRS Response Letter Writer** | CP2000, CP503, CP504, levy release, audit response — correct IRS formatting, deadlines, required language |
| **OIC Calculator & Drafter** | Reasonable Collection Potential math, 433-A analysis, offer amount, Form 656 and cover letter |
| **CDP Hearing Preparer** | Collection Due Process arguments, hearing preparation, supporting documentation checklist |
| **Penalty Abatement Writer** | First-time abatement, reasonable cause arguments, correct form and process |
| **Installment Agreement Drafter** | Streamlined vs non-streamlined eligibility, payment calculation, Currently Not Collectible consideration |
| **Financial Disclosure Analyzer** | 433-A/433-B analysis, IRS National Standard expense allowances, income verification, net equity |
| **Document Review Agent** | Classifies document types (W-2, 1099, IRS notice, 433-A, bank statement), extracts key figures, flags what is missing for each resolution path |
| **Client Communication Agent** | Status updates, document requests, welcome emails, hearing prep instructions — client-facing tone |
| **New Client Intake Agent** | Case type identification from uploaded documents, liability summary, recommended resolution path |
| **Case Status Summarizer** | Factual summaries for partner reviews, internal handoffs, client updates |
| **Deadline Tracker Agent** | IRS calendar awareness, response windows, statute of limitations, extension deadlines |

Note: The Document Review Agent is introduced here, as part of the full specialist framework, rather than in Phase 3. Phase 3's unified data access is a prerequisite — the Document Review Agent needs to pull documents from S3 and the portal simultaneously to do its job properly.

### Hallucination Checking — Why This Is Non-Negotiable

Tax resolution professionals are liable for what they submit to the IRS. A language model trained on general knowledge will sometimes generate plausible-sounding figures that are wrong. In this domain, a wrong number in an OIC or a misquoted liability in an IRS response is not a minor error.

Every specialist agent output runs through a verification pass before reaching the user. The checker cross-references each specific claim against the source document it was derived from. If it cannot find the source, it tags the claim explicitly. The user sees exactly what is confirmed and what requires their judgment.

This adds approximately 200 milliseconds to the response time. It is the most important 200 milliseconds in the system.

**Note on agent maintenance.** IRS National Standard expense tables are updated annually. Revenue officer assignment procedures change. New resolution programs emerge. The specialist agent system prompts require maintenance as IRS rules evolve. This is planned operational overhead — a scheduled review and update cycle for each agent's system prompt, triggered by IRS rule changes or annual policy updates.

---

### Phase 4 in Action — Tax Professional Example

A senior enrolled agent needs to prepare an OIC. Historically: 90 minutes to pull the 433-A, run the RCP calculation, look up National Standards for the county, draft the cover letter, and verify everything aligns.

> *"Draft an Offer in Compromise for case 4521. The client's income changed since we last ran numbers."*

Agent pulls the updated 433-A from the portal, most recent pay stubs, current IRS National Standards for the client's county, and total liability from the database. The OIC specialist runs the math. The hallucination checker verifies every figure.

> *"Based on the updated 433-A and current IRS expense standards for this county, Reasonable Collection Potential comes to $11,200. I'd recommend offering $12,500 — 10% above RCP, which typically moves faster. Everything in the draft has been verified against source documents. One item I couldn't confirm: the vehicle equity field was left blank on the 433-A. You'll want to address that before filing."*

Word opens with the completed Form 656 cover letter. One unresolved item flagged. The enrolled agent reviews, resolves the vehicle equity question, confirms, queues. Done in 12 minutes instead of 90.

---

## 8. Phase 5 — Mobile + Proactive Push

> *The agent stops waiting to be opened. Alerts reach users wherever they are. The morning briefing arrives before the workday begins. Builds on Phase 4's complete intelligence layer — push notifications are only valuable when the underlying intelligence is reliable.*

### What Phase 5 Adds

**Mobile app (iOS and Android).** A lightweight app that mirrors the desktop experience. Tap to speak, see transcription, hear response. Full access to every Phase 1-4 capability from any phone. SSO login. Encrypted connection to the company's VPC.

Note on infrastructure: The mobile app requires the backend to be accessible as a service over HTTPS — not just via local network. This means the Phase 5 build includes configuring a secure API gateway in the company's AWS account that the mobile app connects to. This is standard AWS infrastructure; the effort is in the configuration and security review, not novel engineering.

**Messaging platform integration (WhatsApp Business API).** Via OpenClaw's messaging connectors, the agent connects to WhatsApp Business. Case managers can send a message from their phone — "has Chen uploaded their 433-A yet?" — and get an instant answer without opening an app. Platform note: iMessage does not provide a public API for third-party integrations and is not supported. WhatsApp Business API is the primary mobile messaging channel for Phase 5; other platforms (Telegram, Slack) can be added on the same connector pattern.

**Push notifications.** The agent monitors connected data sources and pushes alerts when something requires human attention.

| Trigger | What gets sent |
|---------|---------------|
| IRS deadline within 48 hours | Alert: case, deadline, current document status |
| Client uploads to portal | "New documents from [client] — [X items] uploaded" |
| Case dormant for 3+ weeks | Flag for case manager and their supervisor |
| New IRS notice found in S3 | Notice type, response window, assigned staff |
| Uncontacted new intake after 24 hours | Alert to intake team |

**Proactive morning briefing — pushed to phone.**

At a configured time each weekday morning, before the user opens any application, the agent assembles a briefing from all connected sources and delivers it to their phone.

> *Agent, 8:00am via WhatsApp:*
>
> *"Morning. This week: 6 IRS deadlines — 2 need responses that haven't been started. 14 clients uploaded documents over the weekend. Pipeline: 847 active cases, 31 approaching resolution close. 3 enrolled agents are over capacity. I'll flag anything urgent as it comes in."*

The user reads this before their laptop is open. They arrive knowing what matters.

**Proactive — Phase 5 form.** Suggestions now include specific tasks by name, because the specialist agents from Phase 4 exist to execute them:

> *"The Nguyen CDP response is due Friday and I can draft it now — I have everything I need. Want me to start?"*

---

## 9. Phase 6 — Full Agentic Orchestration

> *The complete vision. The agent works through the day alongside the user — preparing, drafting, tracking, and executing the logistics of every case. The human makes every decision. The agent handles everything else. Every write still confirmed before execution.*

### How It Works

When the user opens the agent, it has already completed the morning's preparatory work: read every case with upcoming deadlines, reviewed overnight uploads, checked the calendar, and assembled ready-to-review outputs. The user reviews and approves work that has already been prepared — they are not starting from scratch.

The rule has not changed since Phase 1: reads are automatic, writes are confirmed. The scope of automatic reads has simply grown to include everything involved in preparing a task — pulling data, reading documents, drafting, calculating, cross-referencing. The agent stops when it is about to affect something outside the system.

### The Morning Workflow

> *Case manager opens the agent at 9am.*
>
> *Agent: "Morning. I've done some prep. For the Chen case — CDP hearing is Thursday and the response is drafted and ready for your review. For Nguyen — bank statements came in overnight and the income is slightly higher than what was on the 433-A, which may affect the OIC calculation. I've flagged the discrepancy in a note. For the Park intake from this morning — I've classified the documents, identified this as an installment agreement case, and drafted the welcome email. About 3 minutes to review these three and you'll have cleared the morning queue."*
>
> *Case manager: "Start with Chen."*
>
> *Agent: "CDP response is open in Word. Argument is built around economic hardship — strongest angle given the financial disclosure. All figures verified. One flag: the client mentioned a rental property on intake but there's no documentation for it in storage. Flagged in the document."*
>
> *Case manager reviews, resolves the rental property question, confirms to queue for attorney review.*
>
> *Total time: 8 minutes. Previously: 45.*

### State Persistence

If a workflow is interrupted — the user takes a call, closes the laptop, steps away — the agent saves its state completely. When they return:

> *"Welcome back. You were reviewing the Chen CDP response — you'd gotten to the rental property flag. The Thursday hearing is now 38 hours away. Want to continue?"*

Nothing is lost. Every workflow is resumable.

### Full Case Lifecycle Support

**Intake.** New client documents arrive → agent classifies them, identifies the resolution path, drafts the welcome message and intake questionnaire, routes to the correct team based on case type and current capacity.

**Active case.** Tracks the document checklist → surfaces missing items → drafts IRS correspondence → prepares for hearings → monitors for IRS responses → flags deadlines before they become crises.

**Resolution.** Drafts final documents → coordinates signature workflow → closes the case in Salesforce → generates the client-facing resolution summary.

At every step: the human confirms. The agent prepares.

---

## 10. Phase 7 — Enterprise Hardening

> *The product is ready to be sold to any company at any scale. Self-service deployment, comprehensive administrative control, and the operational infrastructure needed for a regulated enterprise.*

### What Phase 7 Adds

**Admin dashboard (web interface).** Separate from the voice interface — this is the control panel for IT and operations teams. User provisioning, role assignment, data source configuration (which Salesforce org, which S3 buckets, which portal database), approved specialist agent list, usage analytics per user and feature, audit log export, and cost tracking per user per month.

**Enhanced SOC 2 alignment.** The architecture from Phase 1 has always been SOC 2-compatible by design: all access authenticated and permission-checked, full audit trail, data never leaves the company's infrastructure. Phase 7 formalizes this with documentation, penetration testing, and incident response procedures. SOC 2 Type II certification is pursued after first enterprise contracts are signed.

**Self-service deployment package.** A CDK stack (automated infrastructure setup for AWS) that a new customer can deploy with a single command and a configuration file. The company specifies their Salesforce organization, S3 bucket, portal database, and SSO provider. The system builds itself in their AWS account. They pay AWS for the underlying compute costs.

**Team-level briefings for executives.** Portfolio-level morning briefings for department heads and executives — not individual case status, but cross-team performance metrics, capacity distribution, deadline exposure across the operation, and trend data week over week.

### Phase 7 in Action — Operations Example

An operations director is onboarding a new department of 40 case managers. Previously this would require IT tickets, manual permission setup in multiple systems, and a full-day onboarding session.

> *IT Administrator opens the admin dashboard.*
>
> *Selects "Add Department" → links to the company's Okta group for the new team → sets data access scope to their case queue in Salesforce → assigns the Case Manager role tier → configures notification preferences.*
>
> *All 40 users receive SSO login instructions. The agent is available on their desktop the same day. Permissions automatically inherit from the Okta group — if someone changes roles later, their access updates instantly.*

No engineering work. No custom configuration per user. 40 users onboarded in an afternoon.

---

## 11. How It All Fits Together

### Phase Dependencies — Why This Order

Each phase is only buildable because the previous one exists. The sequence is not arbitrary.

| Phase | Requires from before | What it enables next |
|-------|---------------------|---------------------|
| **1** | Voice pipeline + DB connector (built) | The query/response loop that all future features ride on |
| **2** | Phase 1 infrastructure + OpenClaw for local ops | Multi-user requires permission boundaries; write ops require confirmed patterns from Phase 1 |
| **3** | Phase 2 permission layer + multi-user architecture | Unified cross-source queries require knowing *who* is asking and *what they can see* |
| **4** | Phase 3 data access (all sources connected) | Specialist agents need to pull from every source to do their jobs |
| **5** | Phase 4 intelligence layer (reliable, verified outputs) | Push notifications only have value when the underlying intelligence can be trusted |
| **6** | Phase 5 proactive foundation | Agentic overnight prep is Phase 5 proactive expanded to full task preparation |
| **7** | Phase 6 complete capability set | Enterprise packaging is the last layer — it wraps a complete product, not a partial one |

### The Proactive Intelligence Progression

One thread runs through all phases — the system's ability to surface what matters without being asked.

| Phase | What "proactive" means |
|-------|----------------------|
| 1 | App opens → automatic 3-item DB summary |
| 2 | Summary expands to include portal activity and overnight uploads |
| 3 | Full cross-source briefing: every system, items ranked by urgency |
| 4 | Specific task suggestions with specialist agent readiness: "I can draft this now" |
| 5 | Pushed to phone before the user opens anything |
| 6 | Work prepared overnight, ready for review at session start |
| 7 | Portfolio briefings distributed to team leads and executives |

### Deployment Timeline

| Phase | What a company has at this stage | Estimated timeline |
|-------|--------------------------------|-------------------|
| Phase 1 | Voice queries, file find/open, email drafts, session briefing | Ready once AWS quota approved (~3 weeks) |
| Phase 2 | Full team deployment, file moves, bulk email, portal access, access control | +4 weeks |
| Phase 3 | Salesforce + S3 + hybrid queries across all sources | +4-6 weeks |
| Phase 4 | Specialist agents per task type, verified outputs | +6-8 weeks |
| Phase 5 | Mobile app, WhatsApp push, proactive alerts | +4 weeks |
| Phase 6 | Overnight prep, full workflow orchestration | +6-8 weeks |
| Phase 7 | Self-service deployment, admin dashboard, enterprise packaging | +4-6 weeks |

**Total to full product: approximately 9 months from Phase 1 deployment.**

Phase 1 closes pilot deals. Phase 4 is where it becomes transformative for professionals. Phase 6 is the complete vision.

---

## 12. Features to Specify Before Build Begins

The following items require decisions before the relevant phase can be implemented cleanly. They are called out here so they are addressed in planning rather than discovered mid-build.

**Before Phase 2:**
- Define the exact role tier model: how many tiers, what data each tier can access, how role assignment works in the SSO provider of the first customer
- Specify the multi-user session concurrency model: maximum concurrent sessions, session timeout behavior, cache isolation approach
- Define the audit log schema: what fields are required, what format, what retention policy

**Before Phase 3:**
- Map the first customer's Salesforce schema: which objects represent cases, contacts, documents, and tasks. The connector is configurable but the initial mapping requires a schema review session with the customer's Salesforce admin.
- Confirm S3 bucket structure: prefix conventions, document naming, access patterns
- Define what happens when a connector is unavailable: partial results with explicit flagging, or query failure with error message

**Before Phase 4:**
- Decide the vector database: pgvector (on existing RDS) vs. Pinecone vs. Weaviate. Trade-off is operational simplicity (pgvector) vs. search quality at scale (dedicated vector DB)
- Define the agent maintenance process: who reviews specialist system prompts, how often, what triggers an update (IRS rule change, new case type, observed output quality issue)
- Set the hallucination checker confidence threshold: at what certainty level does a figure get passed vs. flagged

**Before Phase 5:**
- Register a WhatsApp Business API account: requires Facebook Business Manager verification, typically 2-4 weeks. Start this process during Phase 4 to avoid delay.
- Define notification delivery rules: which roles get which notification types, quiet hours, escalation if no response to a critical deadline alert

**Before Phase 6:**
- Define the overnight prep scope: which tasks does the agent prepare without being asked? Too broad creates noise; too narrow misses the value. Start with the highest-frequency task types from Phase 4 usage data.
- Specify state persistence storage: where is session state saved, how long is it retained, what is restored on reconnect

---

*Written April 2026.*
