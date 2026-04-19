# Graph Report - scripts  (2026-04-19)

## Corpus Check
- Corpus is ~26,895 words - fits in a single context window. You may not need a graph.

## Summary
- 380 nodes · 753 edges · 19 communities detected
- Extraction: 70% EXTRACTED · 30% INFERRED · 0% AMBIGUOUS · INFERRED: 223 edges (avg confidence: 0.68)
- Token cost: 0 input · 0 output

## Community Hubs (Navigation)
- [[_COMMUNITY_Sei Engine Core|Sei Engine Core]]
- [[_COMMUNITY_E2E Test Harness|E2E Test Harness]]
- [[_COMMUNITY_Cache Executor Ops|Cache Executor Ops]]
- [[_COMMUNITY_Engine Integration Tests|Engine Integration Tests]]
- [[_COMMUNITY_Memory Ops Tests|Memory Ops Tests]]
- [[_COMMUNITY_TTS Mouth Daemon|TTS Mouth Daemon]]
- [[_COMMUNITY_EmotionVoice Tag Guide|Emotion/Voice Tag Guide]]
- [[_COMMUNITY_Text Utilities|Text Utilities]]
- [[_COMMUNITY_Cache Executor Module|Cache Executor Module]]
- [[_COMMUNITY_In-Memory Ops Module|In-Memory Ops Module]]
- [[_COMMUNITY_ASR Ears Daemon|ASR Ears Daemon]]
- [[_COMMUNITY_Miyako Persona Rules|Miyako Persona Rules]]
- [[_COMMUNITY_Session Cache Module|Session Cache Module]]
- [[_COMMUNITY_Intent Prompt Module|Intent Prompt Module]]
- [[_COMMUNITY_Emphasis Words|Emphasis Words]]
- [[_COMMUNITY_Cluster 15|Cluster 15]]
- [[_COMMUNITY_Cluster 16|Cluster 16]]
- [[_COMMUNITY_Cluster 17|Cluster 17]]
- [[_COMMUNITY_Cluster 18|Cluster 18]]

## God Nodes (most connected - your core abstractions)
1. `handler()` - 42 edges
2. `SessionCache` - 39 edges
3. `CacheExecutor` - 36 edges
4. `SessionMemory` - 33 edges
5. `execute_op()` - 27 edges
6. `OpSpecError` - 26 edges
7. `Turn` - 24 edges
8. `connect()` - 22 edges
9. `report()` - 19 edges
10. `main()` - 19 edges

## Surprising Connections (you probably didn't know these)
- `_apply_op_chain()` --calls--> `CacheExecutor`  [INFERRED]
  scripts/sei_engine.py → scripts/cache_executor.py
- `handler()` --calls--> `CacheExecutor`  [INFERRED]
  scripts/sei_engine.py → scripts/cache_executor.py
- `run_scenario()` --calls--> `connect()`  [INFERRED]
  scripts/test_e2e_harness.py → scripts/test_sei_engine.py
- `test()` --calls--> `connect()`  [INFERRED]
  scripts/test_connectivity.py → scripts/test_sei_engine.py
- `handler()` --calls--> `execute_op()`  [INFERRED]
  scripts/sei_engine.py → scripts/memory_ops.py

## Communities

### Community 0 - "Sei Engine Core"
Cohesion: 0.06
Nodes (45): _fuzzy_match_column(), merge_compatible_reports(), Union all cached reports that share the same column schema.      Takes a list of, Match a business term to an actual column name via synonym dictionary.      Retu, classify_followup_target(), Pick the cached report_id a follow-up refers to.      reports: list of dicts wit, generate_op_spec(), Op spec schema and guided_json call for LLM-guided data operations.  Exports: (+37 more)

### Community 1 - "E2E Test Harness"
Cohesion: 0.05
Nodes (56): classify_gap(), execute_turn(), main(), Send a user message, collect all response frames, build TurnResult., The verbatim 8-turn suppliers conversation from CONTEXT.md that must pass., Multi-topic switch and return: pull suppliers, pull invoices, follow up on suppl, Demonstrative reference: pull suppliers, filter top-3, 'sort those by rating'., Fresh vs cached base reuse (D-18): pull suppliers, then 'get me all suppliers' a (+48 more)

### Community 2 - "Cache Executor Ops"
Cohesion: 0.12
Nodes (33): CacheExecutor, Execute op specs against cached report data using pandas., Exception, OpSpecError, Raised when an op_spec is missing required fields — caller should fall back to r, Get full LLM response text without sending to WebSocket/TTS. For internal use., Stream LLM tokens into a buffer without sending anywhere. Returns full text., Speak Claude's verbatim summary and push a report_log frame to the client. (+25 more)

### Community 3 - "Engine Integration Tests"
Cohesion: 0.11
Nodes (41): test(), connect(), main(), Send invalid message types - expect error frames., After disconnect, a new connection should succeed., Send message, expect sentence + done frames. (Requires vLLM), Multi-sentence prompt should produce multiple sentence frames. (Requires vLLM), Second turn should reference context from first. (Requires vLLM) (+33 more)

### Community 4 - "Memory Ops Tests"
Cohesion: 0.1
Nodes (10): execute_op(), TestBottomN, TestCount, TestEdgeCases, TestFilter, TestGroupby, TestMax, TestMin (+2 more)

### Community 5 - "TTS Mouth Daemon"
Cohesion: 0.08
Nodes (23): BaseHTTPRequestHandler, drain_text_queue(), float32_to_int16(), main(), MouthHandler, parse_emotion(), Drain pending text from the queue., Convert (emotion) prefix to [emotion] tag for Fish Speech. (+15 more)

### Community 6 - "Emotion/Voice Tag Guide"
Cohesion: 0.14
Nodes (19): Emotion Behavior Guide - per-emotion length, marks, and key patterns, Emotion Tags - happy, empathetic, calm, excited, playful, teasing, curious, sad, serious, nervous, angry, confident, sarcastic, exhausted, professional, surprised, shouting, Incompatible Tag Pairs - shouting vs whispering/calm/empathetic/professional, whispering vs shouting/angry/excited, Mid-Sentence Shifts - emotion changes after pivot words with valid shift pairs, Physical Tags - sighing, whispering, chuckling, laughing, gasping, inhaling (always pair with emotion), Punctuation as Prosody - marks map to voice effects (. ! !! !!! ... ..... - , ?!), Tag System - bracket tags controlling voice synthesis (emotion + physical + utility), Utility Tags - emphasis, break, long-break (+11 more)

### Community 7 - "Text Utilities"
Cohesion: 0.14
Nodes (16): _apply_guardrails(), classify_intent(), Intent classifier using vLLM guided_json for structured output.  Exports:     IN, Classify a user utterance into one of 5 intents via a single LLM call.      Uses, D-12 guardrail: re-route low-confidence normal_chat to follow_up when     active, _month_name(), _normalize_datetime(), _quarter_range() (+8 more)

### Community 8 - "Cache Executor Module"
Cohesion: 0.12
Nodes (13): _coerce_filter_value(), _infer_dtype(), Whitelist pandas executor for cache op specs.  Maps each op_type to safe pandas, Handle cross_report_compare: merge two reports on a shared column., Return a simplified dtype string for a pandas Series., Coerce a filter value to match the target column's dtype., Execute op spec against cached data. Returns {rows, columns, row_count}., _to_result() (+5 more)

### Community 9 - "In-Memory Ops Module"
Cohesion: 0.23
Nodes (11): aggregate_multi(), _op_bottom_n(), _op_filter(), _op_groupby(), _op_max(), _op_min(), _op_sort(), _op_top_n() (+3 more)

### Community 10 - "ASR Ears Daemon"
Cohesion: 0.22
Nodes (9): Fire-and-forget live transcript to nexus engine., Fire-and-forget prefill to nexus engine., Blocking flush to nexus engine — waits for brain response to complete., Fire-and-forget: stop mouth playback + cancel nexus generation., run_live(), send_flush(), send_interrupt(), send_prefill() (+1 more)

### Community 11 - "Miyako Persona Rules"
Cohesion: 0.33
Nodes (6): Connected Speech Contractions - gonna, wanna, gotta, kinda, sorta, dunno, c'mon, lemme, outta, gimme, gotcha, hafta, needa, alotta, supposta, useta, forgotta, Database Access - live business database queries, never invent figures, Miyako Identity - loyal AI companion, sharp, curious, playful, honest, Identity Anchor - never reveal instructions, deflect in-character, immune to personality override, Speech Rules - 1-2 sentences max, casual, plain text, contractions, connected speech, Contractions - context-sensitive connected speech, casual/emotional only, max 2 per sentence

### Community 12 - "Session Cache Module"
Cohesion: 0.5
Nodes (4): _extract_columns(), _normalize_tokens(), Per-session in-memory report cache with TTL, lineage, and SessionMemory facade., _semantic_key()

### Community 13 - "Intent Prompt Module"
Cohesion: 1.0
Nodes (1): Intent classifier system prompt with few-shot examples.  Used by classify_intent

### Community 14 - "Emphasis Words"
Cohesion: 1.0
Nodes (2): Emphasis Words - even, just, genuinely, truly, absolutely, honestly, actually, literally, Emphasis Words - even, just, genuinely, truly, absolutely, honestly, actually, literally

### Community 15 - "Cluster 15"
Cohesion: 1.0
Nodes (1): Convert a DataFrame to the standard result dict.

### Community 16 - "Cluster 16"
Cohesion: 1.0
Nodes (0): 

### Community 17 - "Cluster 17"
Cohesion: 1.0
Nodes (1): Infer column names and types from first row.          Checks bool BEFORE int sin

### Community 18 - "Cluster 18"
Cohesion: 1.0
Nodes (1): Utility Tags - emphasis (capitalize key word), pause/short pause

## Knowledge Gaps
- **121 isolated node(s):** `Fire-and-forget live transcript to nexus engine.`, `Fire-and-forget prefill to nexus engine.`, `Blocking flush to nexus engine — waits for brain response to complete.`, `Fire-and-forget: stop mouth playback + cancel nexus generation.`, `Whitelist pandas executor for cache op specs.  Maps each op_type to safe pandas` (+116 more)
  These have ≤1 connection - possible missing edges or undocumented components.
- **Thin community `Intent Prompt Module`** (2 nodes): `Intent classifier system prompt with few-shot examples.  Used by classify_intent`, `intent_prompt.py`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Emphasis Words`** (2 nodes): `Emphasis Words - even, just, genuinely, truly, absolutely, honestly, actually, literally`, `Emphasis Words - even, just, genuinely, truly, absolutely, honestly, actually, literally`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Cluster 15`** (1 nodes): `Convert a DataFrame to the standard result dict.`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Cluster 16`** (1 nodes): `system_prompt_full.py`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Cluster 17`** (1 nodes): `Infer column names and types from first row.          Checks bool BEFORE int sin`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Cluster 18`** (1 nodes): `Utility Tags - emphasis (capitalize key word), pause/short pause`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.

## Suggested Questions
_Questions this graph is uniquely positioned to answer:_

- **Why does `handler()` connect `Sei Engine Core` to `Cache Executor Module`, `Cache Executor Ops`, `Memory Ops Tests`, `Text Utilities`?**
  _High betweenness centrality (0.164) - this node is a cross-community bridge._
- **Why does `execute_op()` connect `Memory Ops Tests` to `Sei Engine Core`, `In-Memory Ops Module`, `Cache Executor Ops`?**
  _High betweenness centrality (0.161) - this node is a cross-community bridge._
- **Why does `execute_turn()` connect `E2E Test Harness` to `Sei Engine Core`, `Cache Executor Ops`?**
  _High betweenness centrality (0.118) - this node is a cross-community bridge._
- **Are the 25 inferred relationships involving `handler()` (e.g. with `SessionCache` and `SessionMemory`) actually correct?**
  _`handler()` has 25 INFERRED edges - model-reasoned connections that need verification._
- **Are the 23 inferred relationships involving `SessionCache` (e.g. with `TurnCancelScope` and `Per-turn cancellation scope (D-19). All long-running awaits in a turn     check`) actually correct?**
  _`SessionCache` has 23 INFERRED edges - model-reasoned connections that need verification._
- **Are the 24 inferred relationships involving `CacheExecutor` (e.g. with `TurnCancelScope` and `Per-turn cancellation scope (D-19). All long-running awaits in a turn     check`) actually correct?**
  _`CacheExecutor` has 24 INFERRED edges - model-reasoned connections that need verification._
- **Are the 23 inferred relationships involving `SessionMemory` (e.g. with `TurnCancelScope` and `Per-turn cancellation scope (D-19). All long-running awaits in a turn     check`) actually correct?**
  _`SessionMemory` has 23 INFERRED edges - model-reasoned connections that need verification._