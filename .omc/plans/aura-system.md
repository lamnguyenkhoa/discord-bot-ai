# Aura System — Implementation Plan

## Context

The Discord bot "Mal" already has a personality instruction (line 59 of `system_prompt.txt`) that says:
> If someone does something nice or embarrassing, say "+n aura" or "-n aura", with n depend on how good or bad it is.

The bot produces this text naturally but nothing tracks it. This plan turns that flavor text into a real persistent reputation system.

**Existing assets we leverage:**
- `index/memory.sqlite` — SQLite DB already exists (WAL mode, used by indexer/search)
- `llm_client.py` — single LLM call site (`generate_reply`) we can extend
- `bot.py:on_message` — main handler where reply is processed post-generation
- `config.py` — central env-var config

---

## Design Decisions

### How the LLM signals aura changes

**Chosen approach: Parse structured markers from LLM reply text.**

The LLM already naturally says "+50 aura" or "-10 aura" in its replies. We formalize this with a regex pattern and add a system prompt instruction telling it to use a parseable format when it wants to award/deduct aura:

```
[AURA: @user +/-N]
```

The bot parses these markers out of the raw reply, applies the DB changes, then optionally reformats or keeps the natural-language version in the displayed message. This avoids function-calling complexity (which not all OpenRouter models support) and works with any LLM backend (Ollama, OpenRouter, etc.).

**Why not function calling:** The bot uses `openai` SDK against OpenRouter/Ollama backends. Function calling support varies across models and providers. A text-based marker is universally compatible and aligns with the bot's existing behavior.

**Why not a separate LLM call:** Extra latency and cost. The bot already produces aura commentary naturally -- we just need to capture it.

### Storage

**Chosen approach: New table in `index/memory.sqlite`.**

SQLite is already initialized on startup (`indexer.init_db()`). A new `aura` table keeps points per (guild_id, user_id) and a `aura_log` table provides an audit trail. No new dependencies.

### Bot's own aura

The bot has its own user ID (`client.user.id`). Users can mention the bot in conversation and the LLM can award/deduct aura to/from itself. The bot's aura is stored the same way as any user's -- no special handling needed beyond making its user ID available in the aura context.

---

## Schema

```sql
CREATE TABLE IF NOT EXISTS aura (
    guild_id TEXT NOT NULL,
    user_id  TEXT NOT NULL,
    points   INTEGER NOT NULL DEFAULT 0,
    PRIMARY KEY (guild_id, user_id)
);

CREATE TABLE IF NOT EXISTS aura_log (
    id        INTEGER PRIMARY KEY AUTOINCREMENT,
    guild_id  TEXT NOT NULL,
    user_id   TEXT NOT NULL,
    delta     INTEGER NOT NULL,
    reason    TEXT,
    source_msg_id TEXT,
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE INDEX IF NOT EXISTS idx_aura_log_user ON aura_log(guild_id, user_id);
```

---

## Task Flow

### Step 1: Create `aura_manager.py` — storage layer

**New file: `aura_manager.py`**

Responsibilities:
- `init_aura_db()` — creates `aura` and `aura_log` tables in `config.INDEX_PATH` (idempotent, called from `on_ready` alongside `indexer.init_db()`)
- `change_aura(guild_id, user_id, delta, reason=None, source_msg_id=None)` — atomically updates `aura.points` (upsert) and inserts into `aura_log`. Returns the new total.
- `get_aura(guild_id, user_id)` -> int — returns current points (0 if no row)
- `get_leaderboard(guild_id, limit=10)` -> list of (user_id, points) — top N by points descending
- All functions are synchronous (sqlite3 is not async) and use the shared `config.INDEX_PATH` DB.

**Acceptance criteria:**
- Tables are created on bot startup without breaking existing tables
- `change_aura` correctly upserts (INSERT OR REPLACE / ON CONFLICT) and logs
- `get_aura` returns 0 for unknown users
- `get_leaderboard` returns correct ordering

---

### Step 2: Update `system_prompt.txt` and add aura parsing to `llm_client.py`

**Modified file: `system_prompt.txt`**

Add to the Response Style section a structured marker instruction:
```
When you award or deduct aura, include a marker like [AURA:@username +50] or [AURA:@username -20] somewhere in your reply.
You can give aura to multiple people in one message. The marker will be processed and removed from the displayed message.
Keep your natural "+50 aura" or "-10 aura" phrasing in the visible text — the [AURA:...] marker is just for tracking.
```

**Modified file: `llm_client.py`**

Add a function `parse_aura_markers(reply_text: str) -> tuple[str, list[dict]]`:
- Regex: `\[AURA:@(\w+)\s+([+-]?\d+)\]`
- Returns (cleaned_reply, list of {username: str, delta: int})
- Strips the `[AURA:...]` markers from the reply text so users see only the natural language

**Acceptance criteria:**
- `parse_aura_markers("[AURA:@rua +50] nice one rua, +50 aura")` returns `("nice one rua, +50 aura", [{"username": "rua", "delta": 50}])`
- Multiple markers in one message are all captured
- Malformed markers are left as-is (no crash)
- The natural-language aura text ("+50 aura") remains visible to users

---

### Step 3: Integrate aura processing into `bot.py:on_message`

**Modified file: `bot.py`**

Two aura sources are processed in `on_message`:

#### 3a. User-initiated aura (from incoming message)

After stripping the bot mention tag, scan the raw text for aura intent:

**Parse delta:** Regex `([+-]?\d+)\s*aura` (case-insensitive) — captures the numeric delta.

**Parse target name:** Extract the "other words" in the message that aren't the aura pattern. The name may appear before or after the aura amount (e.g. `"rua +50 aura"`, `"+50 aura to Lam"`, `"give Nguyen -10 aura"`). Strip common filler words (`to`, `give`, `for`, `from`, etc.) to isolate the candidate name string.

**Fuzzy name resolution** via a helper `resolve_member_by_name(guild, name_query) -> Member | None`:
- Lowercase compare against each member's `display_name` and `name` (username)
- Exact match first; then prefix match; then substring match
- If still no match, use difflib `SequenceMatcher` ratio > 0.6 as a fuzzy fallback (handles typos like "Ngyuen" → "Nguyen")
- Returns `None` if no confident match

**Target selection:**
- If a name is found in the message and resolves to a member → that member gets the aura
- If no name found, or name doesn't resolve → bot (`client.user`) gets the aura

For each resolved target, call `aura_manager.change_aura(guild_id, str(target.id), delta, reason=f"user award from {message.author.display_name}", source_msg_id=str(message.id))`

This runs before the LLM call so the LLM sees updated aura in context.

Examples:
- `"rua +50 aura"` → finds member matching "rua", awards +50
- `"Ngyuen -10 aura"` → fuzzy-matches "Nguyen", awards -10
- `"+30 aura"` (no name) → bot gets +30
- `"give lam 100 aura"` → finds member "lam", awards +100

#### 3b. LLM-initiated aura (from bot reply)

After `generate_reply` returns:
1. Call `parse_aura_markers(reply)` to extract markers and get cleaned reply
2. For each `{username, delta}`:
   - Resolve `username` to Discord member by `display_name` (case-insensitive); fall back to bot ID if name matches bot
   - Call `aura_manager.change_aura(guild_id, resolved_user_id, delta, reason=user_text[:100], source_msg_id=str(message.id))`
3. Use cleaned reply (markers stripped) for `message.reply()`

#### 3c. Context injection

Before calling `generate_reply`, fetch aura for the talking user and the bot, append to `facts_context`:
```
## Aura
{author.display_name} has {N} aura points.
Bot has {M} aura points.
```

#### 3d. Init on startup

In `on_ready`, call `aura_manager.init_aura_db()` after `indexer.init_db()`.

**Acceptance criteria:**
- User message `+N aura` awards N to mentioned users (or bot if no mention)
- LLM markers are stripped from displayed reply; changes persisted
- Username resolution handles display names; silently skips on failure (warning logged)
- Bot startup initializes aura tables without errors
- Aura context injected into every LLM call

---

### Step 4: Add query commands (`!aura`, `!leaderboard`)

**Modified file: `bot.py`**

Add command handling at the top of `on_message`, before the mention check:

```python
# Aura commands (work without @mention)
if message.content.strip().lower() == "!aura":
    # Show the author's aura
    points = aura_manager.get_aura(guild_id, user_id)
    await message.reply(f"You have **{points}** aura points.")
    return

if message.content.strip().lower().startswith("!aura "):
    # Show mentioned user's aura: "!aura @user"
    if message.mentions:
        target = message.mentions[0]
        points = aura_manager.get_aura(guild_id, str(target.id))
        await message.reply(f"{target.display_name} has **{points}** aura points.")
    return

if message.content.strip().lower() == "!leaderboard":
    # Show top 10
    board = aura_manager.get_leaderboard(guild_id, limit=10)
    if not board:
        await message.reply("No aura points tracked yet.")
        return
    lines = []
    for rank, (uid, pts) in enumerate(board, 1):
        member = message.guild.get_member(int(uid))
        name = member.display_name if member else f"Unknown ({uid})"
        lines.append(f"**{rank}.** {name} — {pts} aura")
    await message.reply("\n".join(lines))
    return
```

These commands work without @mentioning the bot, keeping them lightweight.

**Acceptance criteria:**
- `!aura` shows the sender's points
- `!aura @user` shows a mentioned user's points
- `!leaderboard` shows top 10 sorted descending
- Commands return early (don't trigger LLM call)
- Commands work in any channel (not just watched channels)

---

### Step 5: Add `AURA_DB_PATH` config and update `.env.example`

**Modified file: `config.py`**

Add: `AURA_DB_PATH = os.getenv("AURA_DB_PATH", config.INDEX_PATH)` — allows separate DB but defaults to shared SQLite.

Actually, on reflection, reusing `INDEX_PATH` is simpler and avoids a new config var. The aura tables coexist fine with the indexer tables. Skip the new config var unless separation is needed later.

**Modified file: `.env.example`**

Add comments documenting that aura data is stored in the same SQLite DB as the search index.

**Acceptance criteria:**
- `.env.example` documents the aura feature
- No new required env vars (zero-config for existing users)

---

## Files Changed Summary

| File | Change Type | Description |
|------|-------------|-------------|
| `aura_manager.py` | NEW | SQLite storage layer for aura points and audit log |
| `llm_client.py` | MODIFY | Add `parse_aura_markers()` function |
| `system_prompt.txt` | MODIFY | Add structured `[AURA:@user +/-N]` marker instruction |
| `bot.py` | MODIFY | Integrate aura parsing post-reply, add `!aura`/`!leaderboard` commands, init DB on startup, inject aura context |
| `config.py` | NO CHANGE | Reuse `INDEX_PATH` for aura storage |
| `.env.example` | MODIFY | Document aura feature |

---

## Guardrails

### Must Have
- Two aura sources: user messages (awards to @mentions or bot if none) and LLM reply markers
- Audit log records every change with timestamp, delta, source (user vs LLM), and source message ID
- Zero new dependencies
- Zero new required env vars
- Graceful fallback if aura tables don't exist yet (no crash)

### Must NOT Have
- No function-calling / tools API usage (not universally supported)
- No separate LLM call for aura evaluation (latency/cost)
- No admin commands to manually set aura (keep it organic, LLM-driven)
- No negative aura floor or positive cap (let it be unconstrained for now)

---

## Open Questions

- **Should aura also be tracked in watched channels?** The bot currently extracts facts silently in watched channels but never replies. It could still parse hypothetical aura markers from a silent "evaluation" LLM call, but this adds latency to passive observation. Recommendation: skip for v1.
- **Should the LLM know other users' aura when replying?** Currently the plan only injects the talking user's aura. Injecting the full leaderboard or mentioned users' aura would give the LLM more context but costs prompt tokens. Could be a v2 enhancement.
- **Rate limiting on aura changes?** The LLM could theoretically spam large aura changes. A per-message cap (e.g., max +/-100 per message, max 3 aura changes per reply) could prevent runaway inflation. Recommendation: add a simple cap in `parse_aura_markers` or `change_aura`.
