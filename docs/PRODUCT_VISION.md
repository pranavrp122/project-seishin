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

### Current Implementation

| Component | What it does | Status |
|-----------|-------------|--------|
| **Voice pipeline** | Speech → ASR → language model → text-to-speech → audio out. Low-latency voice responses. | ✅ Implemented |
| **Data layer** | Natural language → SQL → company database → results voiced back | ✅ Implemented |
| **Follow-up engine** | Filters, sorts, aggregates on cached results with no re-query to the database | ✅ Implemented |
| **Intent system** | 9 intent types classified in real time (query, follow-up, compare, undo, confirm, cancel, and more) | ✅ Implemented |
| **Quality safeguards** | History-aware context, fuzzy column matching, date normalization, compound requests, zero-result guidance | ✅ Implemented |
| **Test suite** | 114 tests passing across unit, integration, and E2E | ✅ Implemented |
| **OpenClaw** | Local automation framework — file ops, email OAuth, calendar connections | 🔲 Phase 1 |

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
| Amazon Quick Suite | AWS pricing | Ingests data into AWS index, no voice interface |

Every major competitor either can't connect to a company's actual data, or requires ingesting that data into a third-party cloud — and every single one is text and GUI only.

### Our Differentiation

We query the company's own systems on demand. Nothing is indexed, copied, or stored outside their infrastructure. Client data stays in their AWS account, accessed through their own credentials. Combined with a voice-first interface that no competitor has, this is a product that simply doesn't exist in the market today.

---

## 4. Phase 1 — Voice Intelligence Layer

> **Goal:** A complete, working personal AI assistant deployable on any laptop. Useful on its own — no company database required. Speaks naturally, finds files, drafts emails, researches anything online, reads your calendar, and learns your context over time. Also connects to a company database when one is available, making it the starting point for every company-specific capability that follows.
>
> **After Phase 1, this product can be demoed to anyone on any laptop and stand on its own.**

---

### Full Architecture

Everything the user sees and touches runs in the desktop app on their laptop. All the intelligence runs in the cloud — either on the company's own cloud infrastructure or, for a demo, on a shared server. The user's laptop only needs a microphone and internet access.

```
USER'S LAPTOP
─────────────────────────────────────────────────────────
  Seishin Desktop App
  ├── Microphone capture
  ├── Voice Activity Detection (speech start/end detection)
  ├── Audio streaming → server
  ├── Audio playback ← server
  ├── UI panels
  │   ├── Conversation / voice interface
  │   ├── Email compose panel (To, Subject, Body)
  │   ├── File result cards
  │   ├── Action confirmation cards
  │   └── Send queue sidebar (with countdown per email)
  ├── Client-side memory store (local, never leaves laptop)
  └── OpenClaw (starts and stops with the app)
      ├── Email connection (Gmail or Outlook via OAuth)
      ├── Calendar connection (Google Calendar or Outlook)
      ├── Local file search
      └── Browser automation (Chrome)

SERVER (AWS — company's own account or demo server)
─────────────────────────────────────────────────────────
  ├── Speech recognition (Parakeet) — audio → text
  ├── Language model (Gemma 4) — intent, conversation, responses
  ├── Text-to-speech (Fish Speech) — text → audio
  ├── SQL generation (Claude Haiku) — natural language → database query
  └── Company database — case data, financials, client records
```

**Data flow for a voice request:**

```
1. User speaks
2. Voice Activity Detection detects speech start/end on laptop
3. Audio streamed to server
4. Parakeet transcribes audio → text
5. Text sent to Gemma language model
6. Gemma classifies intent (what kind of request is this?)
7. Gemma routes to the right handler:
     → Database query    → SQL generation → database → results voiced
     → File search       → OpenClaw searches laptop → results shown in app
     → Email draft       → language model drafts → compose panel opens in app
     → Calendar          → OpenClaw reads calendar → schedule voiced
     → Browser research  → OpenClaw opens Chrome → agent voices findings
     → Conversation      → Gemma responds directly
8. Response text sent to Fish Speech → audio
9. Audio streamed back to laptop and played
10. Action logged to local audit log
```

---

### Sandboxed Workspace — The Agent Never Touches Your Real Files Until You Say So

This is one of the most important design decisions in Phase 1, and it is permanent.

When Seishin needs to work with your files — finding them, reading them, preparing operations on them — it works with a sandboxed copy of your workspace state. The real files on your machine are never touched until the user explicitly confirms an action. This means:

- The agent can "prepare" a file move, a rename, or an organization task and show you exactly what it plans to do — without any risk of something going wrong while it's thinking
- You can review, modify, or cancel at any point before anything is committed
- If the agent makes a mistake or misunderstands, the real file is untouched — the only thing that happened was a preview
- Destructive operations (moves, renames, organization) are staged in the sandbox first, then applied to the real filesystem only after confirmation

**How it works in practice:**

```
User: "Organize all my case files by client name"

Agent (in sandbox):
  → Scans filesystem, builds a full map of what would move where
  → Prepares the operation entirely in the sandboxed view
  → Shows user a preview: "I'd move 47 files across 12 folders.
     Here's the full list — confirm to apply, or cancel."

User reviews → confirms → changes applied to real filesystem
User reviews → cancels → nothing changed, original files untouched
```

The same principle applies to emails (5-minute queue after approval), calendar events (shown before created), and any other write operation. **The agent operates on copies and previews. Real changes happen only when the user says go.**

This makes the product safe to give to anyone — including people who are not technically confident — because the worst case is always "nothing happened."

---

### The Interaction Rules *(Established here. Never change.)*

> **Reads are instant — writes are confirmed.**
> The agent queries, searches, reads, and retrieves freely. Before it sends, moves, or creates anything, it stops and shows exactly what it's about to do. The user approves. Then it happens.

| Rule | How it works |
|------|-------------|
| **Sandbox first** | All file operations are prepared in a sandboxed workspace copy before touching real files. The user sees the full plan before anything is applied. |
| **Everything stays in the app** | File finds, calendar checks, confirmation cards — all shown inside Seishin. No external windows for these. |
| **Emails get a full compose view** | Before any email sends, a complete compose panel opens in the app — To, Subject, Body — all editable. The user reads the full email and confirms before it goes into the queue. |
| **Email send queue — 5-minute delay** | After approval, every email enters a visible countdown queue in the app sidebar. Cancel or re-edit anytime during those 5 minutes. No exceptions, ever. |
| **Browser opens Chrome** | The one exception to "stay in app." Web research opens a real Chrome tab so the user can see exactly where the agent goes and what it finds. The agent voices a summary when done. |
| **Audit log on everything** | Every query, file access, email sent, and browser action is logged locally with timestamp and action. |

---

### OpenClaw Integration

OpenClaw is bundled into the Seishin installer. No separate installation, no background service. It starts when Seishin opens and stops when Seishin closes. The user never configures it manually — on first launch, Seishin guides them through connecting their email and calendar accounts via standard OAuth (the same authorization flow used by every email client). Done once, works every session.

**What OpenClaw handles:**
- Email account connection and message delivery
- Calendar read and write access
- Local file search across the laptop
- Browser automation in Chrome

**What Seishin handles:**
- All UI — the compose panel, file cards, confirmation cards, send queue
- All decisions — nothing executes without user approval
- All intelligence — OpenClaw is the execution engine, Seishin's language model decides what to do and when

This separation is intentional. The interface and experience are consistent regardless of whether the user is on Gmail or Outlook, Google Calendar or Outlook Calendar. OpenClaw adapts; the user experience doesn't change.

---

### Client-Side Memory

Phase 1 introduces persistent memory that lives on the user's laptop. Between sessions, the agent remembers context — recent work, frequent requests, and things the user has explicitly told it to remember. This makes the agent feel genuinely personal rather than starting from scratch every time.

**What gets remembered:**

| Memory type | Example |
|------------|---------|
| Recent sessions | "Last session you were working on the Chen case — want to continue?" |
| Frequent queries | Recognizes patterns in what this user asks for and surfaces relevant context |
| Explicit instructions | "Remember I want emails sorted by urgency, not by date" |
| Recent files accessed | "Here are the files you had open last week" |
| Preferences | Response style, level of detail, preferred calendar view |

**How it works:**
- Memory is stored locally on the laptop — it never leaves the device
- When the app opens, recent memory is loaded into context alongside the conversation
- The language model can reference it naturally: "You were asking about something similar last Tuesday"
- The user can ask to clear it: "Forget everything from last week"
- Memory does not contain raw file contents or email bodies — only summaries and references

**Session start with memory:**
> *"Morning. Last session you were asking about Q3 resolution rates and had the Chen case file open. You also have 3 unread items in your send queue from yesterday — 2 emails and a calendar event. Want to start there or something new?"*

---

### Voice Pipeline — How It Works End to End

Understanding the pipeline helps in debugging, optimizing, and extending it. Here is every step from microphone to audio response:

**Step 1 — Speech detection (on laptop)**
The app listens passively using a tiny local model that only detects whether someone is speaking. When speech starts, it begins streaming audio. When speech ends, it signals the server that the utterance is complete. This runs on the laptop CPU — no network call needed just to detect speech.

**Step 2 — Audio streaming**
Raw audio is streamed over a WebSocket connection to the server as the user speaks. It does not wait for the user to finish — it streams continuously, which is what enables the server to begin processing as early as possible.

**Step 3 — Transcription (on server)**
The speech recognition model on the server converts the audio stream to text. The result is a clean text transcript of what the user said.

**Step 4 — Intent classification (on server)**
The language model reads the transcript and classifies what the user wants. Is this a database query? A file search? An email draft? A calendar check? A web research request? General conversation? This classification determines the entire handling path. It uses the recent conversation history and the user's memory context to understand follow-ups and references ("those", "that", "the ones from last week").

**Step 5 — Execution (split between server and laptop)**
Depending on the classified intent:
- Database queries → SQL generated by a fast language model, run against the connected database, results returned
- File search → command sent back to OpenClaw on the laptop, results returned to server
- Email draft → language model drafts the email, full content sent back to app
- Calendar → command sent to OpenClaw on laptop, results returned
- Browser → command sent to OpenClaw, Chrome opens on laptop
- Conversation → language model generates response directly

**Step 6 — Response generation (on server)**
The language model generates a natural voice response — not a robotic readout of data, but a human-sounding conversational reply with the right information.

**Step 7 — Speech synthesis (on server)**
The response text is converted to audio by the text-to-speech model. This produces a natural, expressive voice.

**Step 8 — Audio playback (on laptop)**
Audio is streamed back to the laptop and played in real time. The user hears the response as it is being generated — they do not wait for the full response to be ready before audio starts.

---

### Intent System — What the Agent Understands

Every spoken request is classified into one of these intent types before anything else happens:

| Intent | What triggers it | What happens |
|--------|-----------------|-------------|
| `new_data_request` | Any question about data in the database | SQL generated and query executed |
| `follow_up_on_previous` | Refinement of a previous result ("filter those", "sort those") | Applied to cached result — no re-query |
| `compare_reports` | Comparing two data sets | Both fetched and compared |
| `find_file` | Any request about files on the laptop | OpenClaw searches local filesystem |
| `draft_email` | Any email writing request | Language model drafts, compose panel opens |
| `get_calendar` | Any calendar question | OpenClaw reads calendar |
| `browser_research` | Any request to look something up online | OpenClaw opens Chrome |
| `undo` | "go back", "undo", "revert" | Previous result restored |
| `list_cached_data` | "what did I pull?", "what do I have?" | Current session data voiced |
| `what_can_i_ask` | "what can you do?", "what data do you have?" | Capabilities voiced |
| `confirm` | "yes", "do it", "send it", "go ahead" | Pending action executes |
| `cancel` | "no", "never mind", "cancel" | Pending action discarded |
| `normal_chat` | Everything else | Language model responds conversationally |

The classifier also detects **compound requests** — a single sentence that contains both a data request and a follow-up operation. "Show me open cases sorted by deadline" is classified as `new_data_request` with a sort operation appended. Both execute in sequence automatically.

---

### What Phase 1 Can Do — General Demo Capabilities

These work on any laptop, with any email account, no company database required. This is the demo you can show anyone.

#### Email — Draft, Review, Send

The agent drafts emails in the full compose panel. The user reads the complete email — To, Subject, Body — edits any field directly, then approves. 5-minute queue before it sends.

**General examples:**
```
"Draft an email to my team about our project status update"
"Write a follow-up to the meeting I had this morning"
"Draft a message to Sarah letting her know the report is ready"
"Write a professional reply to this email — I want to decline politely"
"Email John asking if he's free Thursday afternoon"
"Draft a message to the whole team about the new schedule"
```

**What the compose panel shows:**
```
┌─────────────────────────────────────────────────────┐
│  To:      sarah@company.com                         │
│  Subject: Re: Project Update                        │
├─────────────────────────────────────────────────────┤
│  Hi Sarah,                                          │
│                                                     │
│  The report is ready for your review. I've attached │
│  the Q3 summary as discussed. Let me know if you    │
│  have any questions before Thursday's meeting.      │
│                                                     │
│  Best,                                              │
│  [Name]                                             │
└─────────────────────────────────────────────────────┘
  [Edit]  [Send — queuing in 5:00]  [Cancel]
```

User edits directly in the panel. Clicks send or says "send it." Countdown starts. Visible in sidebar.

---

#### File Search — Find Anything on the Laptop

Searches across the full local filesystem. Results appear as file cards in the app — name, folder path, last modified date. Say "open it" or click to launch in the default application.

**General examples:**
```
"Find my resume"
"Find all PDFs I downloaded this month"
"Find the presentation I was working on last week"
"Find everything related to the Johnson project"
"Where is my tax return from last year?"
"Find all spreadsheets modified in the last 3 days"
"Find the contract we signed with Acme"
"Look for any file with 'budget' in the name"
```

**What a file result card looks like:**
```
┌─────────────────────────────────────────────────────┐
│  📄  Resume_2025_Final.pdf                          │
│  📁  ~/Documents/Personal/                         │
│  🕐  Modified: 3 days ago                          │
│                    [Open]  [Show in folder]         │
└─────────────────────────────────────────────────────┘
```

Multiple results stack as scrollable cards. Say "open the second one" or "show me more" to continue.

---

#### Browser Research — Look Up Anything in Chrome

The agent opens Chrome, navigates to the right place, finds what you asked for, and voices a summary. The user watches it happen in real time — full transparency on what it's doing and where it went.

**Read-only research (Chrome opens automatically):**
```
"What's the weather in Miami this weekend?"
"Look up the latest iPhone release specs"
"Research the best approach for tax loss harvesting"
"Find the IRS form for a payment extension"
"What are the current federal interest rates?"
"Look up reviews for the restaurant we're going to"
"Search for flights from LA to New York next Tuesday"
"Find the LinkedIn page for Acme Corp"
"What does the stock market look like today?"
"Look up how to use pivot tables in Excel"
```

**Browser actions (agent announces first, user confirms):**
```
"Fill out the contact form on their website"
"Download the PDF from that page"
"Submit the newsletter signup"
```

After research, Chrome stays open and the agent voices what it found. User can ask follow-up questions and the agent continues navigating.

---

#### Calendar — Read Your Schedule

Reads from Google Calendar or Outlook Calendar (whichever is connected).

```
"What do I have today?"
"Am I free Thursday afternoon?"
"When is my next meeting?"
"What does my week look like?"
"Do I have anything tomorrow morning?"
"When's my dentist appointment?"
"What time does my flight leave?"
"Find a free hour this week for a deep work block"
```

---

#### General Conversation and Context

The agent is conversational. It handles questions, discussions, and context naturally.

```
"What were we talking about last session?"
"Remind me what I was working on yesterday"
"What files did I have open earlier this week?"
"Give me a summary of what I've done today"
"I need to prepare for a meeting about Q3 results — help me think through it"
"What emails did I send this morning?"
```

---

### Proactive Session Start Briefing

When the app opens, the agent immediately surfaces what matters — before the user says anything.

> *"Morning. You have 4 emails in your draft queue from yesterday. 3 meetings today, first one at 10am. Last session you were working on the project proposal — the file is still open. Anything urgent or want to continue where you left off?"*

---

### Phase 1 in Action — General Demo (Personal Workspace)

This is what Phase 1 looks like on a personal laptop with no company system connected. A complete, compelling demonstration of the product.

**Scenario: Preparing for a Monday**

> *User opens Seishin.*
>
> *Agent: "Morning. You have 3 meetings today. 2 draft emails in your queue from Friday. You were working on the Q3 analysis last week — the file is still open on your desktop. Anything from the weekend I should know about?"*
>
> *User: "Find the notes I took from Friday's strategy meeting."*
>
> *Agent shows file card: `Strategy_Meeting_Notes_Fri.docx` — 3 days ago, in Documents/Meetings. "Found it. Open it?"*
>
> *User: "Yes. Also draft a follow-up email to the team about the action items we discussed."*
>
> *Compose panel opens. To: team@company.com. Subject: "Follow-up: Friday Strategy Meeting." Full email body drafted with action items in bullet form. User reads it, changes one item.*
>
> *User: "Good. Send it."*
>
> *Send queue starts. Sidebar shows: "Sending in 5:00."*
>
> *User: "Look up the market data for the three companies we discussed."*
>
> *Chrome opens. Agent navigates to financial data sites for each company, extracts key metrics, voices a summary.*
>
> *Agent: "Here's what I found: Company A is up 8% YTD with Q3 earnings coming next week. Company B reported a miss last quarter, stock down 12% since. Company C is private — no public financials, but I found their recent funding announcement. Want me to pull anything specific?"*

Total time: under 10 minutes. No app switching, no searching, no typing.

---

### What Phase 1 Is, End to End

After Phase 1 is deployed and configured, here is exactly what the product is:

**A desktop app that a person installs on their laptop.**
- Takes about 5 minutes to install and connect their email and calendar accounts
- Opens when they want it, closes when they don't — nothing runs when it's closed
- Works on Mac, Windows, or Linux

**A voice-first interface.**
- User speaks naturally — no commands, no keywords, no special syntax
- Agent responds in a natural voice
- Conversation is continuous — follow-ups understand context from prior turns
- Hands-free capable — user can be doing other things while interacting

**Connected to the user's personal workspace.**
- Finds any file on their laptop by description, name, content type, or date
- Opens files directly from the app
- Reads their email account — can reference recent emails in conversation
- Drafts and sends emails through the in-app compose panel with a 5-minute safety queue
- Reads their calendar — knows what meetings they have and when they're free
- Researches anything on the web by opening Chrome and navigating live

**Remembers context between sessions.**
- Knows what the user was working on last session
- Surfaces relevant context on open
- Learns preferences over time

**Always in control.**
- Nothing permanent happens without the user seeing it and approving it
- All emails reviewed in full before they queue
- All browser actions announced before they execute
- Full audit log of everything that happened

**This is a complete, useful product after Phase 1.** It is also the technical foundation that every subsequent phase builds on — the voice pipeline, the intent system, the OpenClaw integration, the memory store, and the confirmation patterns are all live and proven before Phase 2 adds a single new capability.

## 5. Phase 2 — Company-Specific Workflows + Specialist Agents

> **Goal:** The agent becomes specialized for the tax resolution industry. Everything still runs in the user's personal workspace — local files, email, calendar — but now the agent understands the domain deeply and routes tasks to specialist agents purpose-built for tax dispute work. The full team can use it simultaneously with proper access controls. No company database yet — that comes in Phase 3.

---

### What Changes in Phase 2

Phase 1 is a general personal assistant. Phase 2 makes it a tax resolution assistant. The difference is in the specialist agents — they understand the specific documents, workflows, and communication patterns of the industry. A user working with a case file on their local machine can now ask the agent to draft a real IRS response letter, calculate an OIC, or write a penalty abatement request — using documents already on their laptop.

---

### Specialist Agents — First Introduced Here

Phase 2 is where the specialist agent system begins. Rather than the main LLM handling every task generically, specific task types route to a dedicated agent with its own optimized system prompt stored in the agent database. The database starts small and grows with every phase.

**Agents added in Phase 2:**

| Agent | Called when | What it's optimized for |
|-------|------------|------------------------|
| **Email Specialist** | Any email drafting request | Tax dispute communication tone, urgency signals, case reference formatting, never includes unverified figures |
| **Calendar Specialist** | Any scheduling request | Timezone handling, conflict detection, client-facing vs. internal language, IRS deadline awareness |
| **Document Review Agent** | User asks about a document or uploads one | Classifies document type (W-2, 433-A, IRS notice, bank statement), extracts key figures, flags what's missing |
| **Client Communication Agent** | Drafting client-facing messages | Professional tone calibrated for tax resolution clients, clear action items, no jargon |

The pattern is established here and never changes: main LLM classifies the intent → routes to the right specialist → specialist executes with its purpose-built system prompt → result surfaces in the app for user review. More agents are added each phase.

---

### Access Control — Full Team Deployment

Phase 2 is when the system goes from a single user to the whole company. Role-based access is configured before enabling concurrent team use — permissions inherit from the company's existing identity provider (Okta, Google Workspace, Microsoft Entra). No separate permission system to maintain.

#### Role Tiers

| Role | What the agent knows about their data |
|------|--------------------------------------|
| **Case Manager** | Their assigned cases, their own files, their own communications |
| **Senior Manager** | Their team's workload and escalations |
| **Department Head / VP** | Department-level view |
| **Executive / C-Suite** | Company-wide metrics. Not individual case detail unless they drill in. |
| **IT Administrator** | System configuration and audit logs. No case data. |

**Concurrency model:** All users share one inference server. Each session is isolated — conversation history, cached results, and undo stack are private per user.

---

### What Phase 2 Adds

#### File Write Operations
*(Phase 1 was read-only for files. Phase 2 adds write operations.)*

| What you say | What happens |
|-------------|-------------|
| "Move this to the Chen case folder" | Confirmation card: source → destination. Confirm → executes. |
| "Organize my downloads by case number" | Preview list of all moves shown before anything happens |
| "Rename this to include the case number" | Shows proposed name, user confirms |

#### Calendar Write Operations

| What you say | What happens |
|-------------|-------------|
| "Schedule a call Thursday at 2pm with the Chen team" | Event card in app: title, time, attendees. Confirm → creates via calendar. |
| "Block Friday morning for hearing prep" | Same flow |
| "Reschedule my 3pm to next week" | Shows proposed change, user confirms |

#### Bulk Email Workflows

> "Draft document request emails to all clients I have files for who are missing their financials"

- Agent reviews local case files, identifies the gap
- Scrollable email queue panel opens — one compose card per client
- Each card shows To, Subject, Body — independently editable
- User reviews, tweaks, removes any to handle differently, approves the rest
- All queued with individual countdowns and cancel buttons

---

### Phase 2 in Action — Company-Specific Workflows

#### Case Manager — Working with Local Case Files

> *User opens Seishin with local case files on their machine.*
>
> *"Find all the 433-A forms I have in my Cases folder."*
>
> *Agent shows file cards for 4 documents — one per case. "Found 4 — Chen, Martinez, Nguyen, and Rivera. Want me to review any of them?"*
>
> *"Review the Martinez one."*
>
> *Document Review Agent opens the file, extracts key figures, voices back: "Martinez 433-A — monthly income $3,800, allowable expenses $3,520, net disposable $280. Vehicle equity field is blank. Looks like it was submitted without that section completed."*
>
> *"Draft an email to the Martinez family asking them to complete the vehicle section and resubmit."*
>
> *Email Specialist Agent drafts the message — professional tone, specific about which section is missing, includes the portal upload link. Compose panel opens.*
>
> *User reviews, confirms. Email queues.*

No company database. Everything from local files and the specialist agents' domain knowledge.

#### Executive — Monday Morning (Phase 2 form — personal workspace only)

At Phase 2, executives use the agent for their personal workflow: reviewing documents on their machine, preparing for meetings, drafting communications. Company-wide metrics come in Phase 3 when the database is connected.

> *"Find the Q3 performance summary I was working on."*
> *"Open it and draft an email to the partners with the key highlights."*
> *"Look up the industry benchmark for average case resolution time."*

---

### Proactive Briefing — Phase 2 form

> *"Morning. You have 2 emails in your queue from yesterday. 3 meetings today. Last session you were reviewing the Martinez 433-A — the vehicle equity field is still blank. Also flagging: you have 6 case files in your Downloads folder that haven't been organized yet. Want to start with Martinez or the meetings?"*

---

## 6. Phase 3 — Unified Company Data

> **Goal:** The company's systems are connected for the first time. Voice queries now reach the internal database, Salesforce, S3, and the client portal — alongside the local files from Phases 1 and 2. One voice command spans every system simultaneously. The hybrid query. Nothing else in this market can do this.
>
> This is also where the executive company data experience begins — revenue metrics, case volume, team performance — all accessible by voice for the first time.

---

### What Phase 3 Connects

| Source | What becomes accessible | Permission model |
|--------|------------------------|-----------------|
| **Salesforce** | Case records, contacts, tasks, call logs, case stage | Inherits existing Salesforce role hierarchy |
| **AWS S3** | Scanned IRS mail, case documents, uploaded client files | Scoped to company's own buckets, prefix-based per case |
| **Client portal DB** | Client uploads, submission timestamps, checklist status | Read-only |
| **Internal database** | Financial data, invoices, case records, revenue | Connected here for the first time — voice queries against company data |
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

**Result, voiced back in a few seconds:**

> *"Case 4521 — Chen estate, active resolution. Revenue officer assigned last month. 12 documents in storage: original notice, 3 years of returns, the 433-A, 7 correspondence items. Checklist shows 2023 bank statements outstanding — but the client uploaded something to the portal 18 minutes ago that hasn't been classified yet. Want me to check if that's them?"*

**Previously: 8–10 minutes of manual navigation across 4 systems. Now: one sentence, a few seconds.**

> **Note on CRM flexibility:** The connector architecture supports Salesforce by default because it's the most common CRM in this sector. Other systems (HubSpot, custom CRMs, practice management platforms) are supported through additional connectors built on the same pattern.

---

### Phase 3 in Action — Executive Monday Morning

This is the first phase where an executive can ask company-wide data questions by voice. Previously that required pulling reports manually. Now:

> *Agent: "Morning. Investigation-phase volume is up 12% from last month. Resolution closures last week: 31. Average days to close this quarter is down from last year. 4 IRS deadlines this week, 2 without filed responses."*
>
> *Executive: "Show me closures by type this quarter."*
>
> *Agent: "41 installment agreements, 28 OICs, 19 currently not collectible, 14 penalty abatements. Compare to Q4?"*
>
> *Executive: "Yes."*
>
> *Agent: "OICs are up 34% quarter over quarter. Everything else roughly flat."*

No dashboard. No waiting. Full business picture in a few minutes. **This is the demo that sells the platform.**

---

## 7. Phase 4 — Specialist Agent Expansion + Hallucination Checking

> **Goal:** The specialist agent system introduced in Phase 2 now covers every meaningful task type in tax resolution. Hallucination checking is added as a second verification layer on every output. This is the phase where the product becomes genuinely transformative.

---

### How the Architecture Works

The specialist agent pattern started in Phase 2 with email and calendar. Phase 4 scales it to the full roster of tax resolution tasks, backed by a vector database that retrieves the right agent for any request. The main language model acts as a coordinator — it classifies the task, retrieves the right specialist, injects the relevant case context, and lets the specialist execute.

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

### Specialist Agent Roster — Full Phase 4 Expansion

Agents are stored in a vector database. The orchestrator embeds the user's request, retrieves the best-matching specialist, and calls it with the right context. Adding a new agent = write a system prompt + add a record. No code change.

**Carried forward from Phase 2:**

| Agent | Added in |
|-------|---------|
| Email Specialist | Phase 2 |
| Calendar Specialist | Phase 2 |

**New agents added in Phase 4:**

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

- Adds a small amount of processing time per response
- Worth every millisecond for content that may be submitted to the IRS

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
| **1** | Voice pipeline + OpenClaw *(built)* | Personal workspace assistant — the foundation everything runs on |
| **2** | Phase 1 confirmed patterns + OpenClaw running | Company-specific workflows and specialist agents; write ops after confirm patterns proven |
| **3** | Phase 2 permission layer + multi-user architecture | Company database queries need to know *who's asking* and *what they can see* |
| **4** | Phase 3 (all sources connected) | Specialists need every source connected to do their jobs accurately |
| **5** | Phase 4 (reliable, verified outputs) | Push notifications only have value when the underlying intelligence can be trusted |
| **6** | Phase 5 proactive layer | Overnight prep is Phase 5 proactive extended to full task preparation |
| **7** | Phase 6 complete capability | Enterprise packaging wraps a complete product, not a partial one |

### Proactive Intelligence — How It Grows

| Phase | What "proactive" means |
|-------|----------------------|
| **1** | App opens → surfaces recent work, draft queue, calendar summary |
| **2** | Adds local case file flags and company-specific context from personal files |
| **3** | Full cross-source briefing — database, Salesforce, S3, portal — ranked by urgency |
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
