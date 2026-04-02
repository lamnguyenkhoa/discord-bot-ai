# Implementation Plan: Discord Chat Companion Bot v1

**Plan ID:** discord-bot-v1
**Date:** 2026-04-01
**Source Spec:** `.omc/specs/deep-interview-discord-bot.md`
**Status:** COMPLETED

## Executor Notes (from Critic review)

**Resolve during implementation — no plan revision needed:**

1. **Circular import order** — `memory_manager.py` depends on `llm_client.summarize()`. Implement Step 3 (`llm_client.py`) before Step 2 (`memory_manager.py`), OR use a lazy import inside `summarize_if_needed()`: `from llm_client import summarize` inside the function body, not at the top of the file.

2. **Missing imports in `bot.py`** — Add `import datetime` and `import os` to the import block.

3. **Token counting deferred** — Spec says "50 messages or ~4000 tokens". Plan implements message counting only. This is intentional for v1; token counting is a phase-two enhancement.

4. **Fallback replies get logged** — When OpenRouter returns an error, the fallback string gets appended to memory. Consider skipping `append_exchange()` when `reply` is the fallback string.

5. **`.env.example`** — Create a committed `.env.example` file (not `.env`) so setup is self-documenting.

---

---

## RALPLAN-DR Summary

### Principles (5)

1. **Simplicity over abstraction** -- This is a single-purpose bot with ~4 source files. No framework overhead, no ORM, no class hierarchies beyond what discord.py requires.
2. **Configurability without code changes** -- Model name, system prompt, summarization threshold, and API keys all live outside source code (`.env`, `config.py`, `system_prompt.txt`).
3. **Graceful degradation** -- Every external call (OpenRouter API, file I/O) must have error handling that keeps the bot alive and sends a human-readable fallback.
4. **Separation of concerns** -- LLM calls, memory management, and Discord event handling live in distinct modules with clean interfaces.
5. **Minimal v1 scope** -- No MEMORY.md, no slash commands, no multi-server isolation. Ship daily-log memory only.

### Decision Drivers (Top 3)

| # | Driver | Why It Matters |
|---|--------|---------------|
| 1 | **Reliability (24/7 uptime)** | Bot runs unattended on a Windows laptop. Crashes or memory leaks are unacceptable. |
| 2 | **Contextual awareness via memory** | The core value proposition. Without memory loading, this is just a stateless chatbot. |
| 3 | **Speed of implementation** | Greenfield, single developer. Plan must be executable in a single focused session. |

### Viable Options

#### Option A: Flat-module architecture (RECOMMENDED)

Four Python files (`bot.py`, `memory_manager.py`, `llm_client.py`, `config.py`) with free functions / thin wrappers. No classes beyond what discord.py requires.

| Pros | Cons |
|------|------|
| Fastest to implement | No dependency injection; harder to unit test in isolation |
| Easy to read and modify | May need refactoring if scope grows significantly |
| Matches project structure from spec exactly | N/A |

#### Option B: Class-based service architecture

`MemoryService`, `LLMService`, `BotService` classes with constructor injection, interfaces, and a composition root in `bot.py`.

| Pros | Cons |
|------|------|
| More testable via mocking | Over-engineered for 4 files and a single-developer project |
| Extensible for future features | Slower to implement; more boilerplate |
| Familiar pattern for larger teams | Violates Principle 1 (simplicity) for v1 scope |

**Decision:** Option A. The spec explicitly defines a flat 4-file structure. Option B is invalidated because it adds complexity without proportional benefit for a single-server, single-developer v1 bot. If v2 adds MEMORY.md / multi-server, refactoring to classes is straightforward.

### ADR

- **Decision:** Flat-module architecture with free functions
- **Drivers:** Speed of implementation, simplicity, spec alignment
- **Alternatives considered:** Class-based service architecture
- **Why chosen:** v1 scope is narrow (4 files, single server, single developer). Class-based adds boilerplate without proportional testability benefit at this scale.
- **Consequences:** Refactoring needed if v2 significantly expands scope (acceptable trade-off).
- **Follow-ups:** Revisit architecture when MEMORY.md long-term persistence is added in phase two.

---

## Context

Greenfield Python Discord bot. No existing code. The bot responds to @mentions with LLM-generated replies, maintaining conversational context through daily markdown log files. Runs 24/7 on a Windows laptop.

## Work Objectives

1. Create a working Discord bot that connects, stays online, and responds to @mentions
2. Integrate OpenRouter LLM via the openai SDK for reply generation
3. Implement daily memory log system (load, append, summarize)
4. Make all configuration external (model, persona, thresholds, keys)

## Guardrails

**Must Have:**
- Bot responds ONLY to @mentions (ignore all other messages)
- Today's + yesterday's memory loaded on every API call
- Each exchange appended to today's log immediately after reply
- Summarization when log exceeds threshold
- Graceful error handling on all external calls
- All secrets in `.env`, never in source

**Must NOT Have:**
- MEMORY.md long-term persistence (phase two)
- Slash commands or prefix commands
- Multi-server memory isolation
- Docker or cloud deployment config
- Hardcoded model names or API keys

---

## Task Flow

```
Step 1: config.py + .env + requirements.txt + system_prompt.txt
   |
Step 2: memory_manager.py (load, append, summarize)
   |
Step 3: llm_client.py (OpenRouter via openai SDK)
   |
Step 4: bot.py (discord.py event handlers, wiring)
   |
Step 5: Integration testing + hardening
```

---

## Detailed TODOs

### Step 1: Project scaffold and configuration

**Files:** `config.py`, `.env`, `requirements.txt`, `system_prompt.txt`, `memory/` directory

**config.py:**
```python
import os
from dotenv import load_dotenv

load_dotenv()

# Discord
DISCORD_TOKEN = os.getenv("DISCORD_TOKEN")

# OpenRouter
OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY")
OPENROUTER_BASE_URL = "https://openrouter.ai/api/v1"

# LLM
MODEL_NAME = os.getenv("MODEL_NAME", "openai/gpt-4o-mini")

# Memory
MEMORY_DIR = "memory"
SUMMARIZE_THRESHOLD = int(os.getenv("SUMMARIZE_THRESHOLD", "50"))  # messages

# System prompt
SYSTEM_PROMPT_FILE = "system_prompt.txt"
```

**requirements.txt:**
```
discord.py>=2.3,<3.0
openai>=1.0,<2.0
python-dotenv>=1.0,<2.0
```

**.env (template -- not committed):**
```
DISCORD_TOKEN=your_token_here
OPENROUTER_API_KEY=your_key_here
MODEL_NAME=openai/gpt-4o-mini
SUMMARIZE_THRESHOLD=50
```

**system_prompt.txt:**
```
You are a friendly, casual chat companion in a Discord server. You joke around, reference earlier conversations, and feel like chatting with a real person. Keep responses concise (1-3 paragraphs max) unless the topic warrants more detail.
```

**.gitignore:**
```
.env
memory/
*.raw.md
__pycache__/
```

**Acceptance criteria:**
- [ ] `config.py` loads all values from `.env` with sensible defaults
- [ ] `requirements.txt` pins major versions for all three dependencies
- [ ] `system_prompt.txt` exists with a default persona
- [ ] `memory/` directory exists (created at runtime if missing)
- [ ] `.gitignore` excludes `.env`, `memory/`, `*.raw.md`, `__pycache__/`

---

### Step 2: Memory manager

**File:** `memory_manager.py`

**Functions:**

```python
def get_log_path(date: datetime.date) -> str
    """Return path to memory/YYYY-MM-DD.md for the given date."""

def load_memory(date: datetime.date) -> str
    """Read and return contents of a day's log file. Returns empty string if file doesn't exist."""

def load_context() -> str
    """Load today's + yesterday's logs, concatenated. This is called before every LLM request."""

def append_exchange(channel_name: str, author_name: str, user_message: str, bot_reply: str) -> None
    """Append a formatted exchange block to today's log file.
    Format:
      ### [HH:MM] #channel
      User (name): message
      Bot: reply
    Creates the file if it doesn't exist (with ## YYYY-MM-DD header).
    """

def count_exchanges(date: datetime.date) -> int
    """Count the number of ### exchange blocks in a day's log."""

async def summarize_if_needed(date: datetime.date) -> None
    """If count_exchanges(date) > SUMMARIZE_THRESHOLD, call LLM to summarize
    the log and replace the file contents with the summary.
    Uses await llm_client.summarize() internally (async because llm_client is async).
    """
```

**Key logic:**
- `load_context()` calls `load_memory(today)` + `load_memory(yesterday)`, joins with a separator
- `append_exchange()` opens file in append mode, writes the formatted block
- `summarize_if_needed()` is async and called with `await` after each append; if threshold exceeded, it backs up the raw log (see below), calls `await llm_client.summarize()` with the full log content, and overwrites the file with a summary prefixed by `## YYYY-MM-DD (Summarized)`
- **Before overwriting with summary, back up the raw log** to prevent data loss from poor summaries:
  ```python
  import shutil
  raw_backup = path.replace(".md", ".raw.md")
  shutil.copy2(path, raw_backup)
  # Then overwrite path with summary
  ```
- All file I/O wrapped in try/except; errors logged but never crash the bot

**Acceptance criteria:**
- [ ] `load_context()` returns combined today + yesterday logs
- [ ] `load_memory()` returns empty string for non-existent files (no crash)
- [ ] `append_exchange()` creates file with date header if new, appends formatted block
- [ ] `count_exchanges()` accurately counts `###` blocks
- [ ] `summarize_if_needed()` is async and uses `await llm_client.summarize(...)`
- [ ] `summarize_if_needed()` triggers summarization only when threshold exceeded
- [ ] `summarize_if_needed()` backs up raw log to `*.raw.md` before overwriting with summary
- [ ] All file I/O has try/except with logging

---

### Step 3: LLM client

**File:** `llm_client.py`

**Functions:**

```python
from openai import AsyncOpenAI
import config

client = AsyncOpenAI(
    api_key=config.OPENROUTER_API_KEY,
    base_url=config.OPENROUTER_BASE_URL,
)

def load_system_prompt() -> str
    """Read system_prompt.txt, return contents. Falls back to a hardcoded default if file missing."""

async def generate_reply(user_message: str, memory_context: str, channel_name: str) -> str
    """Build messages array and call OpenRouter. Returns the reply text.

    Messages structure:
      [0] system: load_system_prompt() + "\n\n## Recent Memory\n" + memory_context
      [1] user: user_message

    Calls await client.chat.completions.create(model=config.MODEL_NAME, messages=messages)
    Returns response.choices[0].message.content

    On any exception: logs the error, returns fallback string.
    """

async def summarize(log_content: str) -> str
    """Call LLM to summarize a day's log.

    System message: "Summarize this conversation log concisely, preserving key topics,
    names, and any promises or commitments made. Keep it under 500 words."
    User message: log_content

    Returns the summary text. On error, returns the original log_content unchanged.
    """
```

**Key logic:**
- Module-level `AsyncOpenAI` client instantiation (created once at import time) -- uses async client to avoid blocking the discord.py event loop during LLM calls (which take 2-10 seconds)
- `generate_reply()` is async and uses `await client.chat.completions.create(...)` -- this is critical to prevent heartbeat misses and disconnections
- `summarize()` is async and uses `await client.chat.completions.create(...)` for the same reason
- Both functions inject memory context or summarization prompts into the system message
- Both functions catch all exceptions, log them, and return safe fallbacks
- The fallback message for `generate_reply()`: `"Sorry, I'm having trouble thinking right now. Try again in a moment!"`

**Acceptance criteria:**
- [ ] `AsyncOpenAI` client points at `https://openrouter.ai/api/v1` with the configured API key
- [ ] `generate_reply()` is async and uses `await client.chat.completions.create(...)`
- [ ] `generate_reply()` includes memory context in the system message
- [ ] `generate_reply()` uses `config.MODEL_NAME` (not hardcoded)
- [ ] `generate_reply()` returns a fallback string on any API error
- [ ] `summarize()` is async and uses `await client.chat.completions.create(...)`
- [ ] `summarize()` returns original content on error (no data loss)
- [ ] `load_system_prompt()` reads from file, falls back gracefully if missing

---

### Step 4: Bot main entry point

**File:** `bot.py`

**Structure:**

```python
import discord
import config
import memory_manager
import llm_client
import logging
import re

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)

intents = discord.Intents.default()
intents.message_content = True

client = discord.Client(intents=intents)

@client.event
async def on_ready():
    logger.info(f"Logged in as {client.user} (ID: {client.user.id})")

@client.event
async def on_message(message: discord.Message):
    # Ignore own messages
    if message.author == client.user:
        return

    # Only respond to @mentions
    if client.user not in message.mentions:
        return

    # Strip the mention from the message text
    # Uses regex to handle both <@ID> and <@!ID> mention formats
    user_text = re.sub(r"<@!?\d+>", "", message.content).strip()
    if not user_text:
        user_text = "(empty mention)"

    logger.info(f"Mentioned by {message.author} in #{message.channel}: {user_text[:80]}")

    # Load memory context
    memory_context = memory_manager.load_context()

    # Generate reply (await async LLM call)
    async with message.channel.typing():
        reply = await llm_client.generate_reply(
            user_message=user_text,
            memory_context=memory_context,
            channel_name=str(message.channel),
        )

    # Send reply (truncate to Discord's 2000 char limit)
    if len(reply) > 2000:
        reply = reply[:1997] + "..."
    await message.reply(reply)

    # Append to memory
    memory_manager.append_exchange(
        channel_name=str(message.channel),
        author_name=str(message.author.display_name),
        user_message=user_text,
        bot_reply=reply,
    )

    # Check if summarization needed (await async call)
    await memory_manager.summarize_if_needed(datetime.date.today())

if __name__ == "__main__":
    if not config.DISCORD_TOKEN:
        logger.error("DISCORD_TOKEN not set in .env")
        exit(1)
    if not config.OPENROUTER_API_KEY:
        logger.error("OPENROUTER_API_KEY not set in .env")
        exit(1)

    os.makedirs(config.MEMORY_DIR, exist_ok=True)
    client.run(config.DISCORD_TOKEN, log_handler=None)
```

**Key logic:**
- `intents.message_content = True` is required to read message text (must be enabled in Discord Developer Portal too)
- `on_message` checks `client.user in message.mentions` -- this is the ONLY trigger
- Mention stripping uses `re.sub(r"<@!?\d+>", "", message.content).strip()` to handle both `<@ID>` and `<@!ID>` formats (some Discord clients use the `!` variant)
- `async with message.channel.typing()` wraps `await llm_client.generate_reply(...)` -- the `await` is critical to avoid blocking the event loop
- All LLM calls use `await` (`generate_reply`, `summarize_if_needed`) since they are now async
- Reply is truncated to 2000 chars (Discord limit)
- Memory append happens AFTER successful reply send
- Summarization check happens after each exchange
- Startup validates that required env vars are present

**Acceptance criteria:**
- [ ] Bot connects and logs "Logged in as ..." on startup
- [ ] Bot ignores its own messages
- [ ] Bot ignores messages that don't @mention it
- [ ] Bot replies in the same channel to @mentions
- [ ] Mention stripping handles both `<@ID>` and `<@!ID>` formats via regex
- [ ] `generate_reply()` and `summarize_if_needed()` called with `await`
- [ ] "Typing" indicator shown while generating reply
- [ ] Reply truncated to 2000 chars if needed
- [ ] Memory appended after each successful reply
- [ ] Summarization checked after each exchange
- [ ] Missing env vars produce clear error message and exit

---

### Step 5: Integration testing and hardening

**Actions (no new files):**

1. **Install dependencies:** `pip install -r requirements.txt`
2. **Configure .env:** Add real `DISCORD_TOKEN` and `OPENROUTER_API_KEY`
3. **Discord Developer Portal:** Ensure bot has `MESSAGE_CONTENT` privileged intent enabled
4. **First run:** `python bot.py` -- verify "Logged in as ..." in console
5. **Mention test:** @mention the bot in Discord, verify reply appears within ~5 seconds
6. **Memory verification:** Check that `memory/YYYY-MM-DD.md` was created with the exchange
7. **Context test:** Send a second @mention referencing the first conversation -- verify bot's reply shows awareness
8. **Error handling test:** Temporarily set an invalid API key, @mention the bot, verify fallback message appears
9. **Overnight stability:** Leave bot running overnight, verify it's still responsive the next morning
10. **Summarization test:** Either lower `SUMMARIZE_THRESHOLD` to 3 or manually populate a log file, trigger summarization, verify file is replaced with summary and a `*.raw.md` backup was created

**Acceptance criteria:**
- [ ] Bot connects and shows as online in Discord
- [ ] @mention produces reply in same channel within ~5 seconds
- [ ] Reply generated by OpenRouter (verifiable via OpenRouter dashboard)
- [ ] Today's + yesterday's memory files included in every API call
- [ ] Each exchange appended to today's memory log
- [ ] Log summarized when threshold exceeded
- [ ] API errors handled gracefully with fallback message
- [ ] Model name read from config, not hardcoded
- [ ] Bot stays stable overnight without crashing

---

## Success Criteria (mapped to verification)

| # | Criterion | How to Verify |
|---|-----------|--------------|
| 1 | Bot connects and shows online | Discord UI shows bot with green dot |
| 2 | @mention produces reply in ~5s | Send @mention, time the response |
| 3 | Reply from OpenRouter | Check OpenRouter usage dashboard after a reply |
| 4 | Memory context in API calls | Add a `logger.debug` showing memory length, or check log file content is reflected in replies |
| 5 | Exchange appended to log | Read `memory/YYYY-MM-DD.md` after sending a message |
| 6 | Summarization works | Lower threshold to 3, send 4 messages, check file is summarized |
| 7 | Graceful error handling | Set invalid API key, send @mention, verify fallback message |
| 8 | Model from config | Change `MODEL_NAME` in `.env`, restart, verify different model used (OpenRouter dashboard) |
| 9 | Overnight stability | Leave running overnight, test next morning |

---

## Estimated Complexity

**LOW-MEDIUM** -- 4 source files, ~200 lines total, well-defined interfaces, no complex state management. A focused executor session should complete this in one pass.
