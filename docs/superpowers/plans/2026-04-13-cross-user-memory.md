# Cross-User Memory Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Enable bot to remember conversational context across users by changing guild memory query to focus on discussion topics.

**Architecture:** Single change in `format_context_for_prompt()` - swap query string from "server knowledge" to "recently discussed".

**Tech Stack:** Python, mem0ai

---

## Task 1: Change Guild Memory Query

**Files:**
- Modify: `mem0_manager.py:194-199`

- [ ] **Step 1: Edit the query string**

Change line 195 in `mem0_manager.py`:
```python
# Before (line 195)
query=query or "server knowledge and preferences",

# After
query=query or "what was recently discussed or talked about",
```

Full context:
```python
guild_memories = _get_client().search(
    query=query or "what was recently discussed or talked about",
    user_id=_guild_id_only(guild_id),
    limit=5,
    threshold=GUILD_MEMORY_THRESHOLD,
)
```

- [ ] **Step 2: Commit**

```bash
git add mem0_manager.py
git commit -m "feat: query guild memory for conversation context"
```

---

## Verification

1. Start the bot
2. Have User A ask a question in a watched channel
3. Have User B mention the bot later and ask a follow-up
4. Verify bot can reference User A's earlier topic (implicitly)

---

## Rollback

If issues arise:
```bash
git revert HEAD
```

---

**Plan complete and saved to `docs/superpowers/plans/2026-04-13-cross-user-memory.md`.**
