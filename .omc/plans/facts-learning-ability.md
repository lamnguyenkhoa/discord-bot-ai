# Plan: Facts Learning Ability (Replace, Correct, React-Delete)

**Date:** 2026-04-02
**Ambiguity:** 17% (spec gathered via deep interview)
**Status:** COMPLETED
**Complexity:** MEDIUM (3 files changed, 1 new Discord event, 1 new LLM prompt)

---

## RALPLAN-DR Summary

### Principles
1. **Minimize LLM calls** -- every extra API call adds latency and cost; prefer string matching before falling back to LLM
2. **Single source of truth** -- `memory/facts.md` is the only facts store; all mutations go through `facts_manager.py`
3. **Non-destructive to existing flow** -- `on_message` and WATCH_CHANNELS observation pipeline must not break
4. **Idempotent corrections** -- applying the same correction twice should not corrupt the file
5. **Fail-safe** -- if LLM or matching fails, keep existing facts rather than deleting blindly

### Decision Drivers
1. **LLM call budget** -- the current pipeline already makes 1 extract_facts call per exchange; adding a second call per exchange is expensive
2. **Matching accuracy** -- string-based dedup is cheap but brittle; LLM-based matching is accurate but costly
3. **Discord API constraints** -- reaction events require `intents.reactions = True` and fetching the original message for context

### Options Considered

**Option A: Hybrid heuristic-first with message-ID tagging (CHOSEN)**
- Dedup/replace: parse facts.md into structured list, match by `(user, keyword-overlap)` using a defined token-matching algorithm; on new fact extraction, check for existing fact with same user and overlapping non-stop tokens before appending
- Correction detection: extend the `extract_facts` prompt to also return a `corrections` field when the user contradicts a known fact (piggyback on existing LLM call -- zero extra calls)
- Reaction delete: each fact bullet carries a `<!-- msg:ID -->` tag linking it to the Discord message that produced it; `on_raw_reaction_add` looks up facts by message ID and removes them deterministically -- zero LLM calls
- Pros: no extra LLM calls anywhere (normal path or reaction path); reaction deletion is deterministic with no wording mismatch risk
- Cons: string matching may miss semantic equivalence in edge cases; facts.md format gains an HTML comment per line (invisible when rendered)

**Option B: Full LLM matching for every operation**
- Every append checks all existing facts via LLM for duplicates
- Pros: highest accuracy
- Cons: doubles LLM calls per exchange (violates Driver #1); latency doubles
- **Invalidated:** violates "minimize extra LLM calls" constraint

**Option C: Keyword index / embedding store**
- Build a keyword or vector index over facts for semantic matching
- Pros: accurate without per-call LLM cost after indexing
- Cons: massive overengineering for a <500 line bot with a small facts file; adds dependencies (numpy/faiss)
- **Invalidated:** complexity far exceeds benefit for current scale

---

## Context

The bot currently appends facts to `memory/facts.md` but never updates or removes them. This causes:
- Duplicate/stale facts accumulating (e.g., "rua: plays LoL" then "rua: quit LoL" -- both persist)
- No way for users to signal the bot learned something wrong
- No self-correction when users explicitly contradict prior facts

## Work Objectives

1. Fact dedup/replace: when a new fact is extracted for `(user, topic)`, overwrite the old line instead of appending
2. Verbal correction: when the user explicitly corrects a fact, update facts.md in-place
3. Reaction delete: when user reacts with a cross-mark on a bot message, remove facts linked to that message by stored message ID

## Guardrails

**Must Have:**
- All mutations go through `facts_manager.py` (no direct file writes from bot.py)
- Existing `on_message` flow unchanged for non-correction exchanges
- WATCH_CHANNELS pipeline unchanged
- Bot reply after correction reflects updated facts
- Each fact bullet carries a `<!-- msg:ID -->` HTML comment tag for deterministic reaction deletion
- Module-level `asyncio.Lock` in `facts_manager.py` protecting all read-modify-write cycles

**Must NOT Have:**
- No new files (no preference files, no database)
- No edits to `system_prompt.txt`
- No extra LLM calls in any path (normal, correction, or reaction)

---

## Keyword-Overlap Algorithm Specification

This algorithm is used by `upsert_user_fact` and `upsert_server_fact` to decide whether a new fact replaces an existing one or gets appended.

### Tokenization
1. Split input string on whitespace
2. Lowercase each token
3. Strip leading/trailing punctuation from each token (strip chars: `.,!?;:'"()[]{}`)

### Stop Words (complete list)
```
STOP_WORDS = {"likes", "plays", "is", "are", "was", "were", "has", "have", "had",
              "a", "an", "the", "and", "or", "but", "in", "on", "at", "to", "for",
              "of", "with", "about", "from", "by", "not", "no", "i", "my", "me",
              "he", "she", "they", "we", "it"}
```

### Match Condition
- Extract non-stop tokens from `new_fact` -> set A
- Extract non-stop tokens from `existing_fact.text` -> set B
- Match if `len(A & B) >= 2` (at least 2 shared non-stop tokens)
- Rationale: `>= 1` causes false-positive replacements (e.g. "loves coffee" replaced by "coffee table arrived" via single "coffee" token). Single-token topics like "LoL" rely on the LLM correction path when explicitly contradicted.

### Tie-Breaking
- If multiple existing facts match for the same user, replace the one with the highest `len(A & B)` count
- If still tied, replace the first match (lowest index in the parsed list)

### Correction Path Override
- When a correction is received via the LLM `corrections` field, `old_fact` text is provided verbatim. Use exact substring match on `old_fact` against existing fact text instead of keyword overlap. This makes correction handling reliable regardless of stop words.

---

## Task Flow

### Step 1: Extend `facts_manager.py` with structured parsing, mutation functions, and file lock

**What to add:**

0. Module-level `asyncio.Lock`:
   - Add `import asyncio` to `facts_manager.py` imports
   - `_facts_lock = asyncio.Lock()` at module scope
   - All public functions that mutate facts.md (`upsert_user_fact`, `upsert_server_fact`, `remove_facts_by_msg_id`) must acquire this lock before reading and release after writing
   - This is needed because `on_raw_reaction_add` introduces a second coroutine that writes to facts.md concurrently with `on_message`

1. `STOP_WORDS` constant:
   - Define the complete set as specified in the algorithm section above

2. `_tokenize(text: str) -> set[str]`:
   - Split on whitespace, lowercase, strip punctuation, remove stop words
   - Return set of remaining tokens

3. `_parse_facts() -> list[dict]`
   - Parse `facts.md` into a list of `{"section": "user"|"server", "user": str|None, "text": str, "msg_id": int|None, "raw_line": str}`
   - User facts pattern: `- **username**: fact text <!-- msg:123 -->` -> `{"section": "user", "user": "username", "text": "fact text", "msg_id": 123, "raw_line": "..."}`
   - The `<!-- msg:ID -->` tag is optional (existing facts without it get `msg_id: None`)
   - Server facts pattern: `- fact text <!-- msg:123 -->` -> `{"section": "server", "user": None, "text": "fact text", "msg_id": 123, "raw_line": "..."}`

4. `_write_facts(facts: list[dict]) -> None`
   - Reconstruct the markdown file from the structured list, preserving the `# Bot Memory` / `## User Facts` / `## Server Facts` headers
   - For each fact, write the bullet with the `<!-- msg:ID -->` tag appended if `msg_id` is not None

5. `async def upsert_user_fact(user_name: str, new_fact: str, msg_id: int | None = None, old_fact: str | None = None) -> None`
   - Acquire `_facts_lock`
   - Parse existing facts
   - Search user facts where `user == user_name`
   - If `old_fact` is provided (correction path): use exact substring match — find the first fact entry whose `text` contains `old_fact` as a substring; if found, replace its `text` with `new_fact` and update `msg_id`; if not found, fall back to keyword overlap
   - Otherwise (normal upsert path): tokenize both `new_fact` and each `existing.text`, compute `len(A & B)` for each; if one or more matches found (score >= 2): replace the one with highest overlap (tie-break: first match); update `text` to `new_fact` and `msg_id` to the new `msg_id`
   - If no match found by either path: append as new bullet with `msg_id` tag
   - Write back and release lock
   - Log whether it was a replace (correction/overlap) or append

6. `async def upsert_server_fact(new_fact: str, msg_id: int | None = None) -> None`
   - Same logic as `upsert_user_fact` but matches across all server facts using keyword overlap
   - Server fact corrections are out of scope for v1 -- server facts rely on keyword-overlap upsert only

7. `async def remove_facts_by_msg_id(msg_id: int) -> int`
   - Acquire `_facts_lock`
   - Parse existing facts, find all entries where `entry["msg_id"] == msg_id`, remove them
   - Write back and release lock
   - Return count of removed facts
   - Log each removal

**Acceptance criteria:**
- `upsert_user_fact("rua", "quit playing League of Legends")` when `facts.md` contains `- **rua**: plays League of Legends <!-- msg:111 -->` results in replacement (`{"league", "legends"}` — 2 shared non-stop tokens)
- `upsert_user_fact("rua", "quit LoL", old_fact="plays LoL")` when `facts.md` contains `- **rua**: plays LoL <!-- msg:111 -->` results in replacement via exact-match correction path (bypasses keyword threshold)
- `upsert_user_fact("rua", "works at Google")` when only `- **rua**: plays LoL <!-- msg:111 -->` exists results in append (zero shared non-stop tokens between `{"works", "google"}` and `{"lol"}`)
- `upsert_user_fact("rua", "loves coffee")` when `- **rua**: coffee table arrived <!-- msg:111 -->` exists results in append (only 1 shared token "coffee" — below threshold of 2; no false replacement)
- `remove_facts_by_msg_id(111)` removes all facts tagged `<!-- msg:111 -->` and returns the count
- Empty or missing facts file is handled gracefully (no crash)
- Concurrent calls to `upsert_user_fact` and `remove_facts_by_msg_id` do not corrupt facts.md (lock serializes access)

---

### Step 2: Extend `extract_facts` prompt in `llm_client.py` to detect corrections

**What to change:**

1. Modify `_EXTRACT_SYSTEM` prompt to also accept current facts context and return a `corrections` field:
   - New prompt addition: "If the user explicitly contradicts or corrects a previously known fact, include it in `corrections` as `{\"user\": \"username\", \"old_fact\": \"exact text of old fact as stored\", \"new_fact\": \"the corrected fact\"}`. Only flag corrections when the user clearly states the old info is wrong. When a fact belongs in `corrections`, do NOT also include it in `user_facts`."
   - Updated return schema: `{"user_facts": [...], "server_facts": [...], "corrections": [...]}`

2. Update `extract_facts` function signature:
   - `async def extract_facts(user_name: str, user_message: str, bot_reply: str, existing_facts: str = "") -> dict`
   - Pass `existing_facts` as additional context in the user message so the LLM can detect contradictions
   - Handle missing `corrections` key gracefully (default to `[]`)

**Why this works with zero extra LLM calls:**
- The `extract_facts` call already happens after every exchange
- We piggyback correction detection onto the same call by enriching the prompt with existing facts context
- The LLM sees both the new exchange and existing facts, so it can detect contradictions in one pass

**Acceptance criteria:**
- When called with existing facts containing `"**rua**: plays LoL"` and user_message `"I actually quit LoL last month"`, the response includes `corrections: [{"user": "rua", "old_fact": "plays LoL", "new_fact": "quit LoL"}]` and `user_facts` does NOT contain a duplicate "quit LoL" entry
- When no contradiction exists, `corrections` is `[]`
- Existing `user_facts` and `server_facts` extraction behavior is unchanged
- If LLM returns no `corrections` key, code defaults to `[]` (backward compatible)

---

### Step 3: Wire correction handling into `bot.py:on_message`

**What to change in `on_message`:**

1. Pass `facts_context` to `extract_facts` call:
   - Before: `extracted = await llm_client.extract_facts(user_name, user_text, reply)`
   - After: `extracted = await llm_client.extract_facts(user_name, user_text, reply, existing_facts=facts_context)`
   - (Same for WATCH_CHANNELS branch)

2. Process corrections before upserting new facts:
   ```
   for correction in extracted.get("corrections", []):
       await facts_manager.upsert_user_fact(
           correction["user"],
           correction["new_fact"],
           msg_id=message.id,
           old_fact=correction.get("old_fact")
       )
   ```
   - For corrections, `upsert_user_fact` uses exact substring match on `correction["old_fact"]` against existing facts to find the entry to replace. If no exact match is found, fall back to the standard keyword-overlap algorithm.

3. Replace `append_user_fact` calls with `upsert_user_fact`:
   - Before: `facts_manager.append_user_fact(user_name, fact)`
   - After: `await facts_manager.upsert_user_fact(user_name, fact, msg_id=message.id)`

4. Replace `append_server_fact` calls with `upsert_server_fact`:
   - Before: `facts_manager.append_server_fact(fact)`
   - After: `await facts_manager.upsert_server_fact(fact, msg_id=message.id)`

**Do NOT change:**
- The `on_message` control flow (early returns, mention check, typing indicator, reply logic)
- The WATCH_CHANNELS silent observation structure
- The `generate_reply` call or its parameters (facts_context is already passed there)

**Acceptance criteria:**
- Normal exchange: facts are upserted (deduped) instead of blindly appended, each tagged with `<!-- msg:ID -->`
- Correction exchange: old fact is replaced using exact match on `old_fact` text before bot's next reply opportunity
- WATCH_CHANNELS path also uses upsert instead of append, passing `message.id`
- No new LLM calls introduced (extract_facts is the same single call, just with richer prompt)

---

### Step 4: Add `on_raw_reaction_add` handler in `bot.py` for cross-mark reaction

**What to add:**

1. Enable reaction intent in bot.py:
   - Add `intents.reactions = True` after `intents.message_content = True`

2. New event handler `on_raw_reaction_add(payload: discord.RawReactionActionEvent)`:
   - Guard: ignore if `payload.emoji.name != "\u274c"` (the cross-mark emoji)
   - Guard: ignore if the reactor is the bot itself
   - Fetch the full message: `channel = client.get_channel(payload.channel_id)` then `message = await channel.fetch_message(payload.message_id)`
   - Guard: ignore if the fetched message was not sent by the bot
   - Look up facts by `message.id`: call `count = await facts_manager.remove_facts_by_msg_id(message.id)`
   - If facts were removed (count > 0): react to the original message with a checkmark emoji to confirm deletion to the user
   - If no facts were removed (count == 0): log "no facts matched msg_id={message.id}" at INFO level
   - No LLM calls in this path -- deletion is fully deterministic via message-ID lookup

**Why message-ID tagging instead of LLM re-extraction:**
- Eliminates the LLM call entirely from the reaction path (zero extra API cost)
- Deterministic: no risk of wording mismatch between the original extraction and re-extraction
- Simpler code: no need to fetch the replied-to message or reconstruct the exchange

**Why `on_raw_reaction_add` instead of `on_reaction_add`:**
- `on_reaction_add` only fires for messages in the internal cache
- `on_raw_reaction_add` fires for all messages, even those sent before the bot restarted
- This is important because users may react to older bot messages

**Acceptance criteria:**
- Reacting with cross-mark on a bot reply removes all facts tagged with that message's ID from facts.md
- Bot reacts with checkmark on the message if facts were successfully removed
- If no facts are found for that message ID, handler logs and exits gracefully (no error, no user-facing message)
- Reacting with other emojis does nothing
- Reacting on non-bot messages does nothing
- The reaction handler makes zero LLM calls

---

### Step 5: Manual verification of all acceptance criteria

**Test plan (manual -- no test framework in this project):**

| # | Test | Steps | Expected Result |
|---|------|-------|-----------------|
| 1 | Dedup on same topic | Tell bot "I play LoL". Wait. Then tell bot "I quit LoL". Check `facts.md`. | Only one LoL-related fact for your user, with "quit" text and `<!-- msg:ID -->` tag |
| 2 | No dedup on different topic | Tell bot "I play LoL". Then "I like cats". Check `facts.md`. | Two separate facts for your user, each with msg tags |
| 3 | Verbal correction reflected | Tell bot "my name is Alice". Wait. Tell bot "actually my name is Bob". Check `facts.md` then ask "what's my name?" | facts.md shows Bob (not Alice), bot replies Bob |
| 4 | Cross-mark removes facts | Tell bot something factual. React with cross-mark on bot's reply. Check `facts.md`. | Facts tagged with that message ID are gone; bot reacts with checkmark |
| 5 | Cross-mark on non-bot msg | React with cross-mark on another user's message. | Nothing happens, no errors in log |
| 6 | Other emoji ignored | React with thumbs-up on bot's reply. | No fact removal |
| 7 | WATCH_CHANNELS unaffected | Send messages in a watched channel without mentioning bot. | Facts still extracted and upserted (not duplicated), each with msg tags |
| 8 | Persistence after restart | Do test #4 (remove via reaction). Restart bot. Check facts.md. | Removed facts stay removed |
| 9 | Fallback resilience | Trigger a fallback reply (e.g., bad API key temporarily). React cross-mark on it. | No crash, no fact removal (fallback replies aren't logged, so no msg_id match) |
| 10 | Correction not duplicated | Tell bot "I play LoL", then "I actually quit LoL". Check `facts.md`. | Only one entry for the user about LoL (correction did not also appear in user_facts) |
| 11 | Concurrent safety | Trigger a reaction delete and a new message extraction at roughly the same time. | No file corruption; both operations complete (lock serializes them) |
| 12 | Legacy facts without msg tag | Manually add a fact line without `<!-- msg:ID -->` to facts.md. Send a new message. | Old fact is still parsed and participates in keyword-overlap matching; reaction delete on untagged facts returns 0 |

---

## Sequencing

```
Step 1 (facts_manager.py)  -- no dependencies, can be built and tested in isolation
    |
    v
Step 2 (llm_client.py)     -- depends on understanding the new facts structure
    |
    v
Step 3 (bot.py wiring)     -- depends on Steps 1 + 2
    |
    v
Step 4 (reaction handler)  -- depends on Step 1 (remove_facts_by_msg_id)
    |
    v
Step 5 (manual testing)    -- depends on all above
```

Steps 1 and 2 can be worked on in parallel since they touch different files. Step 3 and 4 both modify `bot.py` so they should be sequential.

---

## Success Criteria

- [ ] No duplicate facts accumulate for same user/topic (keyword-overlap upsert)
- [ ] Verbal corrections overwrite old facts in-place using exact match on `old_fact` text
- [ ] Cross-mark reaction removes facts by message-ID lookup (zero LLM calls)
- [ ] Bot reacts with checkmark to confirm successful fact deletion
- [ ] Removed facts do not reappear after restart
- [ ] Bot reply after correction reflects updated fact
- [ ] Existing on_message flow and WATCH_CHANNELS unchanged
- [ ] Zero additional LLM calls in any path (normal, correction, or reaction)
- [ ] `facts.md` format remains human-readable markdown (HTML comment tags are invisible when rendered)
- [ ] `asyncio.Lock` prevents concurrent file corruption
- [ ] Server fact corrections are documented as v1 limitation (keyword-overlap only)

---

## ADR: Hybrid Heuristic-First with Message-ID Tagging

**Decision:** Use keyword-overlap heuristics for fact dedup/replace, piggyback correction detection on the existing `extract_facts` LLM call with exact-match on `old_fact` text, and use message-ID tagging for deterministic reaction-based deletion with zero LLM calls.

**Drivers:** LLM call budget (primary), matching accuracy, implementation simplicity, deterministic deletion.

**Alternatives considered:**
- Full LLM matching per operation -- too expensive, doubles API calls
- Embedding/vector index -- overengineered for current scale
- LLM re-extraction on reaction (original plan) -- replaced by message-ID tagging because it required an LLM call and risked wording mismatch between original extraction and re-extraction

**Why chosen:** Zero extra LLM calls across all paths (normal, correction, and reaction). The heuristic approach handles the common case (same user + overlapping topic keywords) well enough. The LLM prompt enrichment for correction detection is free since the call already happens. Message-ID tagging makes reaction deletion deterministic and eliminates the most fragile part of the original design.

**Consequences:**
- Heuristic matching may miss corrections where topics are described with entirely different words (e.g., "League of Legends" vs "LoL") -- acceptable for v1
- facts.md gains `<!-- msg:ID -->` HTML comment tags on each line -- invisible when rendered as markdown, but visible in raw text
- Facts written before this feature ships will lack msg_id tags and cannot be deleted via reaction (gracefully handled: returns 0)
- Server fact corrections are not supported in v1 -- they rely on keyword-overlap upsert only

**Follow-ups:**
- If heuristic matching proves too brittle in practice, upgrade to LLM-based matching for the upsert path (adds 1 call per exchange)
- Consider adding a `--force-relearn` command if users want to trigger a full re-evaluation of all facts
- Consider backfilling msg_id tags for legacy facts if reaction deletion of old facts becomes a user need
