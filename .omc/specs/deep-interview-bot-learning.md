# Deep Interview Spec: Bot Learning Ability

## Metadata
- Interview ID: di-bot-learning-001
- Rounds: 6
- Final Ambiguity Score: 17%
- Type: brownfield
- Generated: 2026-04-02
- Threshold: 20%
- Status: PASSED

## Clarity Breakdown
| Dimension | Score | Weight | Weighted |
|-----------|-------|--------|----------|
| Goal Clarity | 0.85 | 35% | 0.298 |
| Constraint Clarity | 0.85 | 25% | 0.213 |
| Success Criteria | 0.80 | 25% | 0.200 |
| Context Clarity | 0.80 | 15% | 0.120 |
| **Total Clarity** | | | **0.831** |
| **Ambiguity** | | | **17%** |

## Goal
Extend the bot's existing fact-storage pipeline so it can **update/replace stale facts** (not just append), **detect explicit verbal corrections** from users, and **respond to ❌ reactions** by re-evaluating and discarding facts extracted from that exchange — all scoped to `facts.md` as the sole persistence layer.

## Constraints
- Only `memory/facts.md` may change as a result of learning — no edits to `system_prompt.txt`, no new per-user preference files
- Fact updates use **replace semantics**: the old fact line is overwritten with a corrected version (not deleted + re-appended)
- Reaction handling uses **re-evaluate + discard**: on ❌ reaction to a bot message, re-run fact extraction on that exchange and remove any facts it would have produced
- No per-message fact provenance tracking — keep it simple
- Existing `WATCH_CHANNELS` silent observation pipeline is unchanged
- API cost: fact correction/dedup logic should avoid extra LLM calls where possible

## Non-Goals
- Editing `system_prompt.txt` based on learned preferences
- Creating a separate per-user preference file
- Full fact provenance tracking (which exchange produced which fact)
- Learning from 👍 reactions (only ❌ triggers action)
- Any UI dashboard or admin commands to view/edit facts

## Acceptance Criteria
- [ ] When a user says something that contradicts a known fact (e.g., "I don't play LoL anymore" when facts.md has "rua: plays LoL"), the bot rewrites that fact line in facts.md with a corrected version rather than appending a duplicate
- [ ] When a user reacts ❌ to a bot message, the bot re-runs fact extraction on that exchange and removes matching facts from facts.md
- [ ] Facts extracted from a ❌-reacted exchange do not persist across sessions (verified by checking facts.md after reaction)
- [ ] No duplicate facts accumulate for the same user/topic over multiple sessions
- [ ] The bot's next reply after a correction reflects the updated fact (injected correctly via `load_facts()`)
- [ ] Existing on_message flow and WATCH_CHANNELS pipeline continue to work unchanged

## Assumptions Exposed & Resolved
| Assumption | Challenge | Resolution |
|------------|-----------|------------|
| "Learning" meant adapting behavior | Could mean preferences, fact quality, or feedback loops | All three scoped to facts.md changes |
| Feedback must come from reactions | Could be reactions, corrections, or both | Both — reactions (❌) + explicit verbal corrections |
| Facts need provenance tracking for reactions | Required for precise deletion | Simplified: re-evaluate exchange + discard, no tracking |
| Update = delete old + append new | Three options existed | Replace in-place semantics chosen |

## Technical Context

### Existing Codebase (brownfield)
- `facts_manager.py`: `append_user_fact()`, `append_server_fact()`, `load_facts()` — appends only, no update/delete
- `llm_client.py:59-80`: `extract_facts()` — conservative extraction, returns `{"user_facts": [...], "server_facts": [...]}` JSON
- `bot.py:87-93`: calls `extract_facts()` after every mention, then appends via facts_manager
- `bot.py`: NO `on_reaction_add` handler currently
- `memory/facts.md`: two sections `## User Facts` / `## Server Facts`, bullet format `- **username**: fact`

### Required Changes
1. **`facts_manager.py`**: Add `update_or_append_fact(section, username, new_fact)` — searches for existing fact line for that user+topic, replaces if found, appends if not. Add `remove_facts_from_exchange(exchange_text)` — given raw exchange text, removes any matching facts.
2. **`llm_client.py`**: Add `detect_correction(user_message, existing_facts)` — returns `{"is_correction": bool, "corrected_fact": str, "old_fact_pattern": str}` so the caller knows to update vs. append.
3. **`bot.py`**: Add `on_reaction_add` event handler — when ❌ added to a bot message, retrieve the message content, re-run extraction, remove matching facts. Wire correction detection into the existing `on_message` flow.

## Ontology (Key Entities)

| Entity | Type | Fields | Relationships |
|--------|------|--------|---------------|
| UserFact | core domain | username, fact_text, timestamp | stored in facts.md User Facts section |
| ServerFact | core domain | fact_text, timestamp | stored in facts.md Server Facts section |
| Reaction | external signal | emoji, message_id, user_id, message_content | triggers fact discard when emoji = ❌ |
| Correction | external signal | user_message, matched_fact, replacement_fact | triggers fact replace when detected by LLM |

## Ontology Convergence
| Round | Entity Count | New | Changed | Stable | Stability Ratio |
|-------|-------------|-----|---------|--------|----------------|
| 1 | 3 | 3 | - | - | N/A |
| 2 | 4 | 1 | 0 | 3 | 75% |
| 3 | 4 | 0 | 1 | 3 | 100% |
| 4–6 | 4 | 0 | 0 | 4 | 100% |

## Interview Transcript
<details>
<summary>Full Q&A (6 rounds)</summary>

### Round 1
**Q:** When you say the bot should "learn", what specific behavior would you see that doesn't exist today?
**A:** All 3 — remember user preferences, fix bad/outdated facts, improve reply quality from feedback
**Ambiguity:** 69% (Goal: 0.45, Constraints: 0.10, Criteria: 0.10, Context: 0.70)

### Round 2
**Q:** For the bot to learn that a reply was good or bad, how would you signal that?
**A:** Both reactions (❌) and explicit corrections in chat
**Ambiguity:** 64% (Goal: 0.60, Constraints: 0.10, Criteria: 0.10, Context: 0.70)

### Round 3
**Q:** When the bot "learns", what should it be allowed to change?
**A:** facts.md contents only
**Ambiguity:** 49% (Goal: 0.70, Constraints: 0.55, Criteria: 0.10, Context: 0.75)

### Round 4
**Q:** What's a real conversation that would make you say "yes, it learned"?
**A:** Both — fact corrections persist AND ❌ reactions prune bad facts
**Ambiguity:** 37% (Goal: 0.75, Constraints: 0.65, Criteria: 0.55, Context: 0.75)

### Round 5
**Q:** When someone corrects a fact, what happens to the old fact in facts.md?
**A:** Replace it — LLM rewrites the fact in place
**Ambiguity:** 24% (Goal: 0.80, Constraints: 0.80, Criteria: 0.65, Context: 0.75)

### Round 6 (Simplifier Mode)
**Q:** When someone reacts ❌ to a bot message, what should the bot do?
**A:** Simple — re-evaluate that exchange and discard what it finds (no provenance tracking)
**Ambiguity:** 17% (Goal: 0.85, Constraints: 0.85, Criteria: 0.80, Context: 0.80)

</details>
