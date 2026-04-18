# Seishin — Product Vision & Phased Roadmap

> **One sentence:** A voice-first AI agent that gives everyone in a tax resolution company instant access to their data, files, and tools — and the ability to act on it — all by speaking naturally.

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
12. [Things to Decide Before Each Phase](#12-things-to-decide-before-each-phase)

---

## 1. The Vision

Tax resolution is a deeply human business. Clients come in scared — IRS notices, wage garnishments, liens on their homes. The professionals who help them are genuinely skilled: enrolled agents, CPAs, attorneys who know the tax code and collections process inside out.

**The problem isn't their skill. It's the logistics buried underneath it.**

Every day, hours disappear into searching for documents, switching between systems, chasing clients for information, drafting the same types of communications again, and pulling reports that management asks for every Monday. For a company running hundreds or thousands of active cases, this isn't a small inconvenience — it is the main thing standing between the staff and the results they can deliver.

> **Seishin handles the logistics. The professionals focus on the work.**

You speak to it like you would a highly capable assistant. It pulls any case, finds any file, drafts any communication, surfaces any deadline — and once you confirm, it acts. Every role gets an agent that knows their context, respects their access level, and never does anything permanent without explicit approval.

By the final phase: the agent prepares work overnight and presents ready-to-review outputs the moment the user sits down. Every decision still belongs to the person.

---

## 2. What We've Built

The foundation is complete and running today.

### The Live Stack

| Component | What it does | Status |
|-----------|-------------|--------|
| **Voice pipeline** | Speech → Parakeet ASR → Gemma 4 LLM → Fish Speech TTS → audio out. First response under 1.5 seconds. | ✅ Live |
| **Data layer** | Natural language → SQL (via Claude Haiku) → company database → results voiced back | ✅ Live |
| **Follow-up engine** | Filters, sorts, aggregates on cached results in under 100ms — no re-query | ✅ Live |
| **Intent system** | 9 intent types classified in real time (query, follow-up, compare, undo, confirm, cancel, and more) | ✅ Live |
| **OpenClaw** | Local automation framework — handles file ops, email OAuth, calendar connections. Starts and stops with the app. Not a background process. | ✅ Integrated |
| **Quality safeguards** | History-aware context, fuzzy column matching, date normalization, compound requests, zero-result guidance | ✅ Live |
| **Test suite** | 114 tests passing across unit, integration, and E2E | ✅ Passing |

### What's Pending
AWS GPU quota approval (submitted). Once approved, the system moves from local hardware into the company's own AWS account — their infrastructure, their data, their control.

### Note on Verification (Pre-Phase 4)
Until Phase 4 adds automated hallucination checking, the user is the verification layer. This is intentional: every write action requires explicit confirmation before it executes. The user always reviews before anything goes out. Phase 4 adds a machine verification layer on top — it doesn't replace the human, it assists them.

---

## 3. The Market Opportunity

### By the Numbers

| Metric | Figure |
|--------|--------|
| AI-in-accounting market (2026) | $10.9B, growing 44%/year |
| Voice AI adoption in financial services | **11%** — despite 91% overall AI adoption |
| AI adoption in accounting firms (2024→2025) | Jumped from 9% → 41% in one year |

The gap at 11% exists because every AI product in this space is text and GUI. **No one has built a voice-first interface for tax and financial professionals.**

### The Competitor Problem

| Competitor | Price | Key Limitation |
|-----------|-------|---------------|
| Thomson Reuters CoCounsel | $75–500/user/mo | Locked to TR ecosystem, text-only |
| Harvey AI | $1,000+/user/mo (20-seat min) | Priced out of most firms, legal-only, text-only |
| TaxGPT | ~$1,600/user/yr | Research-only, no company data connection |
| Microsoft Copilot for Finance | $18–30/user/mo | Requires enterprise ERP stack, not tax-specific |
| Amazon Quick Suite | AWS pricing | Ingests data into AWS index — compliance exposure |

Every major competitor either can't connect to a company's actual data, or they require ingesting that data into a third-party cloud. For companies handling client tax information, this creates real legal exposure:

> **IRC §7216** requires written client consent before client data is used for anything outside direct tax services. Most competitor architectures are structurally incompatible with this.

### Our Differentiation

We query the company's own systems on demand. Nothing is indexed, copied, or stored outside their infrastructure. Client data stays in their AWS account, accessed through their own credentials. This is not just a privacy feature — it's the compliance answer that lets us operate where competitors cannot.

---

## 4. Phase 1 — Voice Intelligence Layer

> **Goal:** Ship a proof of concept that delivers immediate, measurable value to every role on day one. Simple enough to deploy confidently. Compelling enough to close pilot deals.

---

### The Interaction Rules *(Established here. Never change.)*

> **Reads are instant — writes are confirmed.**
> The agent queries, searches, and retrieves freely. Before it sends, moves, or creates anything, it pauses and shows exactly what it's about to do. The user approves. Then it happens.

| Rule | How it works |
|------|-------------|
| **Everything stays in the app** | File moves, calendar events, and all internal actions show a confirmation card inside Seishin. No external windows for these. |
| **Emails get a full compose view** | Before any email sends, a complete compose panel opens in the app — To, Subject, Body, all editable. Built as a React component in Tauri. Works with any email provider. OpenClaw handles delivery in the background. |
| **Email send queue — 5-minute delay** | After approval, every email enters a visible countdown queue. Cancel or re-edit anytime during those 5 minutes. Permanent rule — no exceptions. |
| **Browser opens Chrome** | Web research and browser tasks are the one deliberate exception to "stay in app." The user needs to see real web content. Chrome opens, the user watches, the agent voices what it found. |
| **Audit log on everything** | Every query, file access, and email sent is logged with timestamp, user, and action. Exportable for compliance. |

---

### What Phase 1 Delivers

#### Database Queries — Instant, Conversational

Any case metric, accessible by voice. Results in 2–3 seconds. Every follow-up (filter, sort, compare) runs in under 100ms against cached data — no re-query.

```
"Show me all cases in investigation phase"
  → voiced results

"Filter to only ones with IRS deadlines this week"
  → 100ms, no DB call

"Sort by amount owed"
  → instant
```

#### Local File Operations *(Read-only in Phase 1)*

| What you say | What happens |
|-------------|-------------|
| "Find the investigation file for case 4521" | File card appears in app: name, path, last modified. Say "open it" or click. |
| "Open the Chen 433-A" | Document opens in default viewer (PDF, Word) |
| "Find everything I worked on last week" | Listed by date in the app panel |

> File *moving* and *organizing* are held back until Phase 2. Phase 1 keeps local operations read-only to stay focused and low-risk.

#### Email Drafting

```
"Draft a status update to the client on case 4521"
  → In-app compose panel opens
  → To, Subject, Body pre-filled
  → User edits directly, then approves
  → 5-minute send queue starts
```

#### Calendar Read

- "What do I have today?" → schedule voiced back
- "When's my next opening this week?" → reads calendar, suggests times

#### Proactive Briefing *(Phase 1 form — simple, DB-only)*

When the app opens, before the user says anything, the agent checks the database and surfaces the top items:

> *"Morning. 4 cases have IRS deadlines this week, and 6 clients haven't uploaded the documents your team requested. Want to start with the deadlines?"*

---

### Phase 1 in Action

#### Case Manager
Opens the app. Hears what needs attention. Asks by voice. Gets instant answers. Drafts client emails — the full compose view appears in the app, pre-filled and ready to edit. Morning setup that used to take 20 minutes takes 5.

#### Executive — Monday Morning

> *Agent: "Morning. 847 active cases. Investigation volume up 12% from last month — ahead of intake trends. Resolution closures last week: 31. Average days to close this quarter: 94, down from 108 last year. 4 IRS deadlines this week, 2 without filed responses."*
>
> *Executive: "Show me closures by type this quarter."*
>
> *Agent: "41 installment agreements, 28 OICs, 19 currently not collectible, 14 penalty abatements. Compare to Q4?"*
>
> *Executive: "Yes."*
>
> *Agent: "OICs are up 34% quarter over quarter. Everything else roughly flat."*

**No dashboard. No waiting. Full business picture in 3 minutes. This is the demo that sells Phase 1.**

---

## 5. Phase 2 — Office Automation + Access Control

> **Goal:** Enable the full team to use the system simultaneously with proper permission boundaries. Add write operations that Phase 1 deliberately held back.

---

### Access Control — Why It's Here, Not Phase 7

A multi-user system deployed without role-based access control is not acceptable in a regulated financial services company. Phase 2 solves this *before* enabling concurrent team use, inheriting permissions directly from the company's existing SSO provider (Okta, Google Workspace, Microsoft Entra).

#### Role Tiers

| Role | Data access |
|------|------------|
| **Case Manager** | Assigned cases only, client communications, own local files |
| **Senior Manager** | Department-level case data, team workload, escalations |
| **Department Head / VP** | Full department portfolio, performance metrics, capacity |
| **Executive / C-Suite** | Company-wide metrics — volume, revenue, trends. Not individual case detail unless they drill in. |
| **IT Administrator** | System config and audit logs. No case data. |

Permissions are automatic — the voice interface scopes every answer to what the user is allowed to see. No manual filtering required.

**Concurrency model:** All users share one inference server in the company's VPC. Each user's session is isolated — their conversation history, cached data, and undo stack are private.

---

### What Phase 2 Adds

#### File Write Operations
| What you say | What happens |
|-------------|-------------|
| "Move this to the Chen case folder" | Confirmation card in app: source → destination, filename. Confirm → executes. |
| "Organize my downloads by case number" | Preview list of all moves before anything happens |
| "Rename this to include the case number" | Shows proposed name, user confirms |

#### Calendar Write Operations
| What you say | What happens |
|-------------|-------------|
| "Schedule a call Thursday at 2pm with the Chen team" | Event card in app: title, time, attendees. Confirm → creates via calendar API. |
| "Block Friday morning for hearing prep" | Same flow |
| "Reschedule my 3pm to next week" | Shows proposed change, user confirms |

#### Bulk Email Workflows
> "Draft document request emails to every investigation-phase client missing their financials"

- Agent queries portal DB, identifies subset
- Scrollable email queue panel opens in the app — one compose card per client
- Each card shows To, Subject, Body — independently editable
- User scrolls, tweaks, removes any to handle separately, approves the rest
- All queued with individual countdowns and cancel buttons

#### Client Portal Connectivity *(Read-only)*
- "Has Chen uploaded their 433-A?" → instant answer from portal DB
- "Show me all investigation clients missing bank statements" → voiced list in 2 seconds
- New portal uploads appear in the morning briefing

#### Browser Research via Chrome

> **The one deliberate exception to "stay in app" — Chrome opens for web tasks.**

| Type | Behavior |
|------|---------|
| **Read-only research** | Opens automatically, no confirmation needed |
| **Browser actions** (form submit, download) | Agent voices intent first, user confirms, then executes |

**Research examples:**
- "Look up the current IRS National Standards for Orange County" → Chrome opens, agent extracts figures, voices them back, uses them in OIC math
- "Find the revenue officer contact info for this district" → Chrome opens, agent voices the result
- "Look up 2024 payroll tax penalty rates" → Chrome opens IRS guidance, agent summarizes

**Action examples:**
- "Fill out the IRS payment plan request" → agent voices what it's submitting, user confirms, Chrome completes the form
- "Download the updated 433-A from the IRS website" → Chrome navigates, saves file, agent voices where it landed

Being able to watch the agent navigate Chrome live builds trust — users see exactly where it's going and what it's doing.

#### Proactive Briefing *(Phase 2 form — adds portal activity)*

> *"Morning. Overnight: Rivera submitted bank statements, Chen sent a W-2, two others uploaded documents that need classification. 4 IRS deadlines this week. 11 clients past the 2-week mark on outstanding requests. Where do you want to start?"*

---

## 6. Phase 3 — Unified Company Data

> **Goal:** One voice command spans every system simultaneously — CRM, document storage, client portal, internal database, local files. The hybrid query. Nothing else in this market can do this.

---

### What Phase 3 Connects

| Source | What becomes accessible | Permission model |
|--------|------------------------|-----------------|
| **Salesforce** | Case records, contacts, tasks, call logs, case stage | Inherits existing Salesforce role hierarchy |
| **AWS S3** | Scanned IRS mail, case documents, uploaded client files | Scoped to company's own buckets, prefix-based per case |
| **Client portal DB** | Client uploads, submission timestamps, checklist status | Read-only |
| **Internal database** | Financial data, invoices, revenue | Existing pipeline from Phase 1 |
| **Local machine** | Working files, downloaded documents | User's own files |

**Fallback behavior:** If any connector is unreachable, the agent voices which sources it could and couldn't reach, delivers the partial result, and explicitly flags what may be missing. It never silently returns incomplete data.

---

### The Hybrid Query

> *"Pull up everything we have on case 4521"*

**The agent simultaneously:**
1. Pulls case record from Salesforce — status, assigned staff, timeline, tasks
2. Lists all documents in S3 for this case by date
3. Checks client portal — what's been uploaded, what's still on the checklist
4. Searches local machine for working files on this case
5. Cross-references Salesforce document checklist against what's actually on file

**Result, voiced in ~3 seconds:**

> *"Case 4521 — Chen estate, active resolution. Revenue officer assigned last month. 12 documents in storage: original notice, 3 years of returns, the 433-A, 7 correspondence items. Checklist shows 2023 bank statements outstanding — but the client uploaded something to the portal 18 minutes ago that hasn't been classified yet. Want me to check if that's them?"*

**Previously: 8–10 minutes of manual navigation across 4 systems. Now: one sentence, 3 seconds.**

> **Note on CRM flexibility:** The connector architecture supports Salesforce by default because it's the most common CRM in this sector. Other systems (HubSpot, custom CRMs, practice management platforms) are supported through additional connectors built on the same pattern.

---

## 7. Phase 4 — Specialist Agents + Hallucination Checking

> **Goal:** Every task routes to a purpose-built specialist. Every output is verified against source documents before the user hears it. This is the phase where the product becomes genuinely transformative.

---

### How the Architecture Works

The main language model becomes a coordinator. When a user makes a request, it identifies the task type, retrieves the right specialist from a vector database, injects the relevant case context, and lets the specialist execute.

```
User: "Draft an OIC for case 4521"

 Orchestrator
  ├── Identifies: OIC drafting task
  ├── Vector search → retrieves: OIC Calculator & Drafter
  └── Fetches context: 433-A from portal, income from DB, liability from Salesforce

 OIC Calculator & Drafter
  ├── Applies IRS Reasonable Collection Potential formula
  ├── Calculates monthly disposable income
  ├── Derives offer amount with cushion above RCP
  └── Drafts Form 656 cover letter — every figure cited from source

 Hallucination Checker
  ├── Verifies each dollar amount against its source document
  ├── Verifies each date against case records
  ├── Verifies client name and case number against Salesforce
  └── Tags anything unverifiable: [unverified — please confirm]

 Result voiced. Document opens for review.
```

Adding a new specialist = write a system prompt + add a database record. No code change required.

---

### Specialist Agent Roster

| Agent | Handles |
|-------|---------|
| **IRS Response Letter Writer** | CP2000, CP503, CP504, levy release, audit response — correct IRS formatting and required language |
| **OIC Calculator & Drafter** | RCP math, 433-A analysis, offer recommendation, Form 656 and cover letter |
| **CDP Hearing Preparer** | Due process arguments, hearing preparation, documentation checklist |
| **Penalty Abatement Writer** | First-time abatement, reasonable cause, correct form and submission process |
| **Installment Agreement Drafter** | Streamlined vs non-streamlined eligibility, payment calculation, CNC consideration |
| **Financial Disclosure Analyzer** | 433-A/433-B, IRS National Standard expense allowances, income verification, net equity |
| **Document Review Agent** | Classifies document types, extracts key figures, flags what's missing per resolution path |
| **Client Communication Agent** | Status updates, document requests, welcome emails, hearing prep instructions |
| **New Client Intake Agent** | Case type from uploaded docs, liability summary, recommended resolution path |
| **Case Status Summarizer** | Clean handoff summaries for partner reviews and client updates |
| **Deadline Tracker Agent** | IRS calendar, response windows, statute of limitations, extension deadlines |

---

### Hallucination Checking

> **A wrong number in an OIC or IRS response letter is not a minor error. This layer is non-negotiable.**

Every specialist output runs through a verification pass. The checker cross-references every specific claim against the document it came from. Unverifiable claims are tagged explicitly — the user sees exactly what's confirmed and what needs their judgment.

- Adds ~200ms to response time
- That 200ms is the most important part of the system

**Agent maintenance:** IRS National Standard expense tables update annually. Specialist system prompts require scheduled review when IRS rules change — this is planned operational overhead, not a surprise cost.

---

### Phase 4 in Action — Enrolled Agent Example

> *"Draft an OIC for case 4521. The client's income changed since we last ran numbers."*

Agent pulls the updated 433-A, recent pay stubs, current IRS National Standards for the county, and total liability. Specialist runs the math. Checker verifies every figure.

> *"RCP comes to $11,200. I'd recommend offering $12,500 — 10% above RCP, which typically moves faster. Everything in the draft is verified. One flag: vehicle equity was left blank on the 433-A. Address that before filing."*

**Document opens for review. One unresolved item flagged. Done in 12 minutes instead of 90.**

---

## 8. Phase 5 — Mobile + Proactive Push

> **Goal:** The agent stops waiting to be opened. Alerts reach users on their phone. The morning briefing arrives before the workday starts.

---

### What Phase 5 Adds

#### Mobile App (iOS & Android)
- Tap to speak, see transcription, hear response
- Full access to every Phase 1–4 capability
- SSO login, encrypted connection to company VPC
- *Note: Requires configuring a secure API gateway in the company's AWS account — standard infrastructure work.*

#### WhatsApp Business API Integration
> "Has Chen uploaded their 433-A?" — sent from your phone while walking to a meeting. Answered instantly.

- No additional app install required
- Uses the messaging app the team already uses
- Other platforms (Telegram, Slack) follow on the same connector pattern
- *iMessage excluded — Apple does not provide a public API for third-party integrations*

#### Push Notifications

| Trigger | Alert sent |
|---------|-----------|
| IRS deadline < 48 hours | Case, deadline, current document status |
| Client uploads to portal | "New documents from [client] — [X items]" |
| Case dormant 3+ weeks | Flag to case manager and supervisor |
| New IRS notice in S3 | Notice type, response window, assigned staff |
| New intake uncontacted 24+ hours | Alert to intake team |

#### Proactive Morning Briefing — Pushed to Phone

Delivered at a configured time before the user opens anything:

> *Agent via WhatsApp, 8:00am:*
> *"Morning. This week: 6 IRS deadlines — 2 need responses that haven't been started. 14 clients uploaded over the weekend. 847 active cases, 31 approaching close. 3 enrolled agents are over capacity. I'll flag anything urgent as it comes in."*

User reads this before their laptop is open. They arrive knowing what matters.

#### Proactive Suggestions *(Phase 5 form)*
Because specialist agents from Phase 4 exist to execute tasks, the agent can now offer:

> *"The Nguyen CDP response is due Friday and I can draft it now — I have everything I need. Want me to start?"*

---

## 9. Phase 6 — Full Agentic Orchestration

> **Goal:** The agent works through the day alongside the user. It prepares, drafts, tracks, and handles the logistics of every case. The human makes every decision. The agent handles everything else. Every write still confirmed before execution.

---

### How It Works

When the user opens the agent, it has already done the morning's prep work:
- Read every case with upcoming deadlines
- Reviewed overnight uploads
- Checked the calendar
- Assembled ready-to-review outputs

The user isn't starting from scratch — they're reviewing work that's already been prepared.

> **The rule hasn't changed since Phase 1: reads are automatic, writes are confirmed.**
> The scope of automatic reads has simply grown to include all preparation involved in any task.

---

### The Morning Workflow

> *Case manager opens the app at 9am.*
>
> *Agent: "Morning. I've done some prep. Chen's CDP hearing is Thursday — the response is drafted and ready. Nguyen's bank statements came in overnight and income is slightly higher than the 433-A, which may affect the OIC. I've flagged the discrepancy. Park's intake from this morning is classified — installment agreement case — and the welcome email is drafted. About 3 minutes to clear the morning queue."*
>
> *Case manager: "Start with Chen."*
>
> *Agent: "Response is open. Argument built around economic hardship — strongest angle. All figures verified. One flag: rental property mentioned at intake but no documentation in storage."*
>
> *Case manager resolves the flag, confirms to queue for attorney review.*
>
> **8 minutes. Previously: 45.**

---

### State Persistence

If a workflow is interrupted — call comes in, laptop closes, user steps away:

> *"Welcome back. You were reviewing Chen's CDP response — you'd reached the rental property flag. Thursday hearing is now 38 hours away. Want to continue?"*

Nothing lost. Every workflow resumable.

---

### Full Case Lifecycle

| Stage | What the agent handles |
|-------|----------------------|
| **Intake** | Classifies documents → identifies resolution path → drafts welcome + questionnaire → routes to correct team |
| **Active case** | Tracks checklist → surfaces missing items → drafts IRS correspondence → prepares hearing docs → monitors for IRS responses → flags deadlines |
| **Resolution** | Drafts final documents → coordinates signatures → closes case in Salesforce → generates client summary |

At every step: **human confirms, agent prepares.**

---

## 10. Phase 7 — Enterprise Hardening

> **Goal:** The product is ready to sell to any company at any scale. Self-service deployment, full administrative control, and the compliance infrastructure a regulated enterprise requires.

---

### What Phase 7 Adds

#### Admin Dashboard *(Web interface, separate from the voice app)*

| Feature | What it does |
|---------|-------------|
| User provisioning | Add/remove users, assign roles, link to SSO groups |
| Data source management | Configure Salesforce org, S3 buckets, portal DB connection |
| Agent roster control | Approve which specialist agents are available to this company |
| Usage analytics | Per-user, per-feature, per-data-source breakdowns |
| Audit log export | CSV export, filterable by date, user, action type |
| Cost tracking | Per-user monthly usage and cost |

#### Security & Compliance

| Item | Status in Phase 7 |
|------|-----------------|
| All data in company's AWS VPC | ✅ Since Phase 1 |
| Full audit trail | ✅ Since Phase 1 |
| SSO + permission-checked queries | ✅ Since Phase 2 |
| TLS 1.3 in transit, AWS KMS at rest | ✅ Phase 7 formalizes |
| SOC 2 Type II architectural alignment | ✅ Phase 7 documentation + pen testing |
| SOC 2 certification | Pursued after first enterprise contracts signed (~6–12 months, ~$30–50K) |

#### Self-Service Deployment

New customer installs the full system with one command:

```bash
cdk deploy SeishinStack \
  --context salesforce_org=https://company.salesforce.com \
  --context s3_bucket=company-case-documents \
  --context portal_db=postgresql://... \
  --context sso_provider=okta
```

System builds itself in their AWS account. They pay AWS directly. We charge a software license.

#### Team-Level Executive Briefings
Portfolio-level morning briefings for department heads and executives — cross-team performance, capacity distribution, deadline exposure, and trend data week over week.

---

### Phase 7 in Action — IT Onboarding 40 Users

> *IT Admin opens the admin dashboard. Selects "Add Department" → links to Okta group for the new team → sets Salesforce data scope → assigns Case Manager role tier → configures notification preferences.*
>
> *All 40 users receive login instructions. Agent available on their desktop the same day. Permissions inherit automatically — role changes in Okta update access instantly.*

**No engineering tickets. No manual config per user. 40 users onboarded in an afternoon.**

---

## 11. How It All Fits Together

### Phase Dependencies

Each phase is only buildable because the previous one exists.

| Phase | Requires | Enables |
|-------|---------|---------|
| **1** | Voice pipeline + DB connector *(built)* | The query/response loop everything else rides on |
| **2** | Phase 1 + OpenClaw running | Write ops need confirmed patterns; multi-user needs permission boundaries first |
| **3** | Phase 2 permission layer | Cross-source queries need to know *who's asking* and *what they can see* |
| **4** | Phase 3 (all sources connected) | Specialists need to pull from every source simultaneously |
| **5** | Phase 4 (reliable, verified outputs) | Push only has value when the intelligence behind it can be trusted |
| **6** | Phase 5 proactive layer | Overnight prep is Phase 5 proactive extended to full task preparation |
| **7** | Phase 6 complete capability | Enterprise packaging wraps a complete product, not a partial one |

### Proactive Intelligence — How It Grows

| Phase | What "proactive" means |
|-------|----------------------|
| **1** | App opens → automatic 3-item DB summary |
| **2** | Adds portal activity + overnight uploads |
| **3** | Full cross-source briefing, ranked by urgency |
| **4** | Specific task suggestions: "I can draft this now — want me to start?" |
| **5** | Pushed to phone before the user opens anything |
| **6** | Work prepared overnight, ready to review at session start |
| **7** | Portfolio briefings distributed to team leads and executives |

### Timeline

| Phase | What the company has | Time estimate |
|-------|---------------------|--------------|
| **1** | Voice queries, file search, email drafts, session briefing | ~3 weeks post-quota |
| **2** | Full team, file moves, bulk email, portal, browser, RBAC | +4 weeks |
| **3** | Salesforce + S3 + hybrid queries | +4–6 weeks |
| **4** | Specialist agents, verified outputs | +6–8 weeks |
| **5** | Mobile, WhatsApp, push alerts | +4 weeks |
| **6** | Overnight prep, full orchestration | +6–8 weeks |
| **7** | Admin dashboard, SOC 2, self-service deployment | +4–6 weeks |

> **Full product: ~9 months from Phase 1 deploy.** Phase 1 closes pilots. Phase 4 is transformative. Phase 6 is the complete vision.

---

## 12. Things to Decide Before Each Phase

### Before Phase 2
- [ ] Define role tiers for the first customer (how many, what data each sees, how SSO groups map to roles)
- [ ] Specify session concurrency model: max concurrent sessions, timeout behavior, cache isolation
- [ ] Define audit log schema: required fields, format, retention policy

### Before Phase 3
- [ ] Salesforce schema review session with customer's admin: which objects = cases, contacts, docs, tasks
- [ ] Confirm S3 bucket structure: prefix conventions, document naming, access patterns
- [ ] Define fallback behavior: partial results with flagging vs. query failure

### Before Phase 4
- [ ] Choose vector database: pgvector (simpler, on existing RDS) vs. Pinecone vs. Weaviate (better search at scale)
- [ ] Define agent maintenance cycle: who reviews system prompts, what triggers an update
- [ ] Set hallucination checker confidence threshold: when does a figure get flagged vs. passed

### Before Phase 5
- [ ] Start WhatsApp Business API registration now (Phase 4 timeline) — requires Facebook Business Manager verification, 2–4 weeks
- [ ] Define notification rules: which roles get which alert types, quiet hours, escalation policy

### Before Phase 6
- [ ] Define overnight prep scope: which task types does the agent prepare unprompted? Start narrow, expand based on Phase 4 usage data.
- [ ] Specify state persistence: storage location, retention period, what gets restored on reconnect

---

*Written April 2026.*
