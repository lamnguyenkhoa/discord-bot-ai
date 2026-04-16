# Follow-Up Chat Module Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a follow-up message feature that triggers after the bot responds to a user mention, with a configurable percentage chance.

**Architecture:** New module `module/follow_up_chat/` following existing patterns (auto_post, meme_reaction). Config via environment variables. Integrated in bot.py after initial reply.

**Tech Stack:** Python, Discord.py, existing llm_client

---

## File Structure

- Create: `module/follow_up_chat/__init__.py`
- Modify: `config.py`, `bot.py`

---

### Task 1: Add Config Variables

**Files:**
- Modify: `config.py:70-73` (append after existing config)

- [ ] **Step 1: Add config variables to config.py**

```python
# Follow-up chat feature
FOLLOW_UP_CHANCE = int(os.getenv("FOLLOW_UP_CHANCE", "33"))
FOLLOW_UP_COOLDOWN_SECONDS = int(os.getenv("FOLLOW_UP_COOLDOWN_SECONDS", "30"))
```

Run: `grep -n "MEME_" config.py` to verify insertion point
- [ ] **Step 2: Commit**

```bash
git add config.py
git commit -m "feat: add follow-up chat config variables"
```

---

### Task 2: Create Follow-Up Manager Module

**Files:**
- Create: `module/follow_up_chat/__init__.py`

- [ ] **Step 1: Create the follow_up_chat module directory and __init__.py**

```python
import random
import time
import logging
from typing import Optional
import config
import llm_client

logger = logging.getLogger(__name__)


class FollowUpManager:
    def __init__(self):
        self.last_follow_up_time: dict[str, float] = {}

    def should_trigger(self, channel_key: str) -> bool:
        if not config.FOLLOW_UP_CHANCE or config.FOLLOW_UP_CHANCE <= 0:
            return False

        last_time = self.last_follow_up_time.get(channel_key, 0)
        if time.time() - last_time < config.FOLLOW_UP_COOLDOWN_SECONDS:
            return False

        trigger_roll = random.randint(1, 100)
        return trigger_roll <= config.FOLLOW_UP_CHANCE

    async def generate_follow_up(self, user_message: str, bot_reply: str, channel_key: str) -> Optional[str]:
        prompt = f"""Given this conversation:
User: {user_message}
Bot: {bot_reply}

Write a brief follow-up message (1-2 sentences) to continue the conversation naturally. 
It could be a clarifying question, an additional thought, or relevant comment.
Keep it under 100 characters. If nothing meaningful to add, return empty string."""

        try:
            follow_up = await llm_client.generate_reply(prompt, "", channel_key)
            if follow_up and len(follow_up.strip()) > 0 and len(follow_up) <= 200:
                return follow_up.strip()
        except Exception as e:
            logger.warning(f"Follow-up generation failed: {e}")

        return None

    def record_follow_up(self, channel_key: str):
        self.last_follow_up_time[channel_key] = time.time()


_follow_up_manager = None


def get_follow_up_manager() -> FollowUpManager:
    global _follow_up_manager
    if _follow_up_manager is None:
        _follow_up_manager = FollowUpManager()
    return _follow_up_manager
```

Run: `ls module/follow_up_chat/` to verify creation

- [ ] **Step 2: Commit**

```bash
git add module/follow_up_chat/__init__.py
git commit -m "feat: add follow-up chat manager module"
```

---

### Task 3: Integrate in bot.py

**Files:**
- Modify: `bot.py:360-376` (after initial reply and memory capture)

- [ ] **Step 1: Add import and integration**

Add import at top of bot.py (after existing imports):
```python
from module.follow_up_chat import get_follow_up_manager
```

Modify bot.py after line 376 (after memory capture), add:
```python
    # Follow-up chat feature
    follow_up_manager = get_follow_up_manager()
    if follow_up_manager.should_trigger(str(message.channel)):
        follow_up = await follow_up_manager.generate_follow_up(user_text, reply, str(message.channel))
        if follow_up:
            await message.channel.send(follow_up)
            follow_up_manager.record_follow_up(str(message.channel))
            logger.info(f"Follow-up sent in #{message.channel}")
```

Run: `grep -n "message.reply(reply)" bot.py` to find exact line

- [ ] **Step 2: Run basic syntax check**

Run: `python -m py_compile bot.py config.py`
Expected: No output (success)

- [ ] **Step 3: Commit**

```bash
git add bot.py
git commit -m "feat: integrate follow-up chat in bot"
```