# Meme Reaction Feature Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add automatic meme/GIF reactions to messages in watched channels with 5% trigger chance, keyword matching, and LLM sentiment analysis.

**Architecture:** Flow-based trigger system: message → random chance (5%) → keyword check → LLM sentiment → search GIF → reply. Modular structure under `module/meme-reaction/`.

**Tech Stack:** Python, aiohttp for API calls, discord.py, LLM for sentiment

---

## File Structure

```
module/
└── meme-reaction/
    ├── __init__.py        # exports public API
    ├── config.py         # meme-specific config
    ├── meme_manager.py   # GIF search + caching
    └── trigger_decider.py # keyword + sentiment logic
```

---

## Task 1: Create Module Structure

**Files:**
- Create: `module/__init__.py`
- Create: `module/meme-reaction/__init__.py`
- Modify: `config.py` (add MEME config vars)
- Modify: `.env.example` (add meme config)

- [ ] **Step 1: Create module/__init__.py**

```python
# Module marker
```

- [ ] **Step 2: Create module/meme-reaction/__init__.py**

```python
from .meme_manager import MemeManager, get_meme_manager
from .trigger_decider import TriggerDecider, get_trigger_decider

__all__ = ["MemeManager", "get_meme_manager", "TriggerDecider", "get_trigger_decider"]
```

- [ ] **Step 3: Add config to config.py**

Add at end of config.py:

```python
# Meme reaction feature
MEME_TRIGGER_CHANCE = int(os.getenv("MEME_TRIGGER_CHANCE", "5"))
MEME_API = os.getenv("MEME_API", "giphy").lower()
MEME_API_KEY = os.getenv("MEME_API_KEY", "")
MEME_COOLDOWN_SECONDS = int(os.getenv("MEME_COOLDOWN_SECONDS", "10"))
```

- [ ] **Step 4: Add to .env.example**

Add at end:

```
# Meme Reaction Feature
MEME_TRIGGER_CHANCE=5
MEME_API=giphy
MEME_API_KEY=your_api_key_here
MEME_COOLDOWN_SECONDS=10
```

- [ ] **Step 5: Commit**

```bash
git add module/ config.py .env.example
git commit -m "feat(meme-reaction): add module structure and config"
```

---

## Task 2: Implement meme_manager.py

**Files:**
- Create: `module/meme-reaction/meme_manager.py`

- [ ] **Step 1: Write the failing test**

Create `tests/module/meme-reaction/test_meme_manager.py`:

```python
import pytest
from module.meme_reaction.meme_manager import MemeManager

@pytest.fixture
def meme_manager():
    return MemeManager()

def test_meme_manager_initialization(meme_manager):
    assert meme_manager is not None

def test_search_gif_returns_url(meme_manager):
    # Will fail - method not implemented
    result = meme_manager.search_gif("funny cat")
    assert result is None or isinstance(result, str)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/module/meme-reaction/test_meme_manager.py -v`
Expected: FAIL with "AttributeError: 'MemeManager' object has no attribute 'search_gif'"

- [ ] **Step 3: Write minimal implementation**

Create `module/meme-reaction/meme_manager.py`:

```python
import aiohttp
import logging
import config

logger = logging.getLogger(__name__)


class MemeManager:
    def __init__(self):
        self._cache = {}
        self._cache_ttl = 300  # 5 minutes
        self._last_request_time = {}
        self._cooldown = config.MEME_COOLDOWN_SECONDS

    async def search_gif(self, query: str) -> str | None:
        """Search for GIF and return URL or None."""
        if not config.MEME_API_KEY:
            logger.warning("MEME_API_KEY not configured")
            return None

        # Truncate query
        query = query[-200:] if len(query) > 200 else query
        
        # Check cache
        if query in self._cache:
            return self._cache[query]

        # Choose API
        if config.MEME_API == "tenor":
            url = await self._search_tenor(query)
        else:
            url = await self._search_giphy(query)

        if url:
            self._cache[query] = url
        return url

    async def _search_giphy(self, query: str) -> str | None:
        api_url = "https://api.giphy.com/v1/gifs/search"
        params = {
            "api_key": config.MEME_API_KEY,
            "q": query,
            "limit": 1,
            "rating": "pg-13"
        }
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(api_url, params=params) as resp:
                    if resp.status == 429:
                        logger.warning("Giphy rate limited")
                        return None
                    data = await resp.json()
                    if data.get("data"):
                        return data["data"][0]["images"]["original"]["url"]
        except Exception as e:
            logger.error(f"Giphy API error: {e}")
        return None

    async def _search_tenor(self, query: str) -> str | None:
        api_url = "https://tenor.googleapis.com/v2/search"
        params = {
            "q": query,
            "limit": 1,
            "contentfilter": "medium",
            "key": config.MEME_API_KEY or ""
        }
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(api_url, params=params) as resp:
                    data = await resp.json()
                    if data.get("results"):
                        return data["results"][0]["url"]
        except Exception as e:
            logger.error(f"Tenor API error: {e}")
        return None


# Global singleton
_meme_manager = None


def get_meme_manager() -> MemeManager:
    global _meme_manager
    if _meme_manager is None:
        _meme_manager = MemeManager()
    return _meme_manager
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/module/meme-reaction/test_meme_manager.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add module/meme-reaction/meme_manager.py tests/module/meme-reaction/test_meme_manager.py
git commit -m "feat(meme-reaction): add MemeManager with Giphy/Tenor API"
```

---

## Task 3: Implement trigger_decider.py

**Files:**
- Create: `module/meme-reaction/trigger_decider.py`

- [ ] **Step 1: Write the failing test**

Add to `tests/module/meme-reaction/test_meme_manager.py`:

```python
import pytest
from module.meme_reaction.trigger_decider import TriggerDecider

@pytest.fixture
def trigger_decider():
    return TriggerDecider()

def test_keyword_matching(trigger_decider):
    # Should trigger on keywords
    assert trigger_decider.check_keywords("lol that's funny") == True
    assert trigger_decider.check_keywords("haha nice one") == True
    assert trigger_decider.check_keywords("omg that's crazy") == True
    
    # Should not trigger on non-keywords
    assert trigger_decider.check_keywords("hello world") == False

def test_sentiment_analysis(trigger_decider):
    # Will fail - not implemented
    result = trigger_decider.check_sentiment("I'm so excited about this!")
    assert isinstance(result, bool)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/module/meme-reaction/test_meme_manager.py -v`
Expected: FAIL

- [ ] **Step 3: Write minimal implementation**

Create `module/meme-reaction/trigger_decider.py`:

```python
import re
import llm_client
import config
import logging

logger = logging.getLogger(__name__)

KEYWORDS = [
    "lol", "haha", "lmao", "omg", "wow", "bro", "that's funny",
    "kekw", "lul", "pog", "lulw", "hah", "hahaha", "hahaa",
    "🤣", "😂", "😭", "😆", "🤪"
]


class TriggerDecider:
    def __init__(self):
        self._keyword_pattern = re.compile(
            r'\b(' + '|'.join(re.escape(k) for k in KEYWORDS) + r')\b',
            re.IGNORECASE
        )

    async def should_trigger_meme(self, message_text: str) -> bool:
        """Check if meme should be triggered."""
        # Check keywords first
        if self.check_keywords(message_text):
            return True
        
        # Check sentiment via LLM
        return await self.check_sentiment(message_text)

    def check_keywords(self, text: str) -> bool:
        """Check if text contains trigger keywords."""
        return bool(self._keyword_pattern.search(text.lower()))

    async def check_sentiment(self, text: str) -> bool:
        """Use LLM to check sentiment intensity (1-5)."""
        if not config.LLM_API_KEY:
            return False
        
        prompt = f"""Analyze this message and rate emotion intensity from 1-5.
Only respond with a number 1-5. No other text.

Message: {text[:200]}
Intensity (1=neutral, 5=very emotional):"""
        
        try:
            result = await llm_client.generate_reply(
                user_message=prompt,
                memory_context="",
                channel_name="sentiment-check"
            )
            result = result.strip()
            if result.isdigit():
                intensity = int(result)
                return intensity >= 4
        except Exception as e:
            logger.warning(f"Sentiment check failed: {e}")
        return False


# Global singleton
_trigger_decider = None


def get_trigger_decider() -> TriggerDecider:
    global _trigger_decider
    if _trigger_decider is None:
        _trigger_decider = TriggerDecider()
    return _trigger_decider
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/module/meme-reaction/test_meme_manager.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add module/meme-reaction/trigger_decider.py
git commit -m "feat(meme-reaction): add TriggerDecider with keyword + sentiment"
```

---

## Task 4: Integrate into bot.py

**Files:**
- Modify: `bot.py`

- [ ] **Step 1: Add imports**

Add after existing imports:

```python
from module.meme_reaction import get_meme_manager, get_trigger_decider
```

- [ ] **Step 2: Add cooldown tracking**

Add after `auto_post_state`:

```python
meme_cooldown = {}
```

- [ ] **Step 3: Modify watched channel handler**

Replace the watched channel section (lines 193-215) to add meme logic:

```python
    # Silently observe watched channels
    channel_key = str(message.channel)
    if channel_key in config.WATCH_CHANNELS and client.user not in message.mentions:
        user_text = message.content.strip()
        if user_text:
            logger.debug(f"Observing #{channel_key}: {user_text[:80]}")
            await mem0_manager.capture_exchange(
                user_id=user_id,
                guild_id=guild_id,
                channel_name=channel_key,
                username=str(message.author.display_name),
                user_message=user_text,
                bot_reply="",
                msg_id=message.id,
            )
            # Track for auto-post
            if config.AUTO_POST_ENABLED:
                auto_post_state.message_count[channel_key] = auto_post_state.message_count.get(channel_key, 0) + 1
                trigger_threshold = random.randint(config.AUTO_POST_TRIGGER_MIN, config.AUTO_POST_TRIGGER_MAX)
                if auto_post_state.message_count[channel_key] >= trigger_threshold:
                    await try_auto_post(message, message.guild, channel_key, guild_id)
            
            # Meme reaction feature
            if config.MEME_TRIGGER_CHANCE > 0:
                last_meme = meme_cooldown.get(channel_key, 0)
                if time.time() - last_meme >= config.MEME_COOLDOWN_SECONDS:
                    if random.randint(1, 100) <= config.MEME_TRIGGER_CHANCE:
                        meme_manager = get_meme_manager()
                        trigger_decider = get_trigger_decider()
                        if await trigger_decider.should_trigger_meme(user_text):
                            gif_url = await meme_manager.search_gif(user_text)
                            if gif_url:
                                await message.reply(gif_url)
                                meme_cooldown[channel_key] = time.time()
                                logger.info(f"Sent meme in #{channel_key}")
            return
        return
```

- [ ] **Step 4: Commit**

```bash
git add bot.py
git commit -m "feat(meme-reaction): integrate into watched channel handler"
```

---

## Task 5: Verify and Test

- [ ] **Step 1: Run lint/type check**

Run: Check for syntax errors with `python -m py_compile bot.py module/meme-reaction/*.py`

- [ ] **Step 2: Manual test**

Start bot and verify:
1. Messages in watched channels don't crash
2. With 5% chance, meme triggers on keyword messages
3. Cooldown prevents spam

- [ ] **Step 3: Commit**

```bash
git commit --allow-empty -m "chore: verify meme-reaction integration"
```

---

## Summary

| Task | Description |
|------|-------------|
| 1 | Create module structure + config |
| 2 | Implement meme_manager.py (Giphy/Tenor API) |
| 3 | Implement trigger_decider.py (keyword + LLM sentiment) |
| 4 | Integrate into bot.py watched channel flow |
| 5 | Verify and test |