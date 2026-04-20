# Bot Act Nugger Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add module that allows running a command in a separate terminal to trigger the Discord bot to respond as if a user mentioned it.

**Architecture:** HTTP endpoint in bot + CLI module. Bot exposes lightweight HTTP server on localhost that receives external triggers and routes them through existing message-processing pipeline.

**Tech Stack:** aiohttp (already in requirements.txt), argparse, discord.py

---

## File Structure

- `bot_act_nugger/__init__.py` - Module init
- `bot_act_nugger/__main__.py` - CLI entry point
- `bot_act_nugger/client.py` - HTTP client for CLI
- `bot.py` - Add HTTP server endpoint (lines ~455-500)
- `config.py` - Add `EXTERNAL_TRIGGER_PORT` setting

---

## Tasks

### Task 1: Add config setting for external trigger port

**Files:**
- Modify: `config.py` - Add EXTERNAL_TRIGGER_PORT setting
- Test: None required (config change)

- [ ] **Step 1: Add config setting**

Read `config.py` to find where other settings are defined, then add:
```python
EXTERNAL_TRIGGER_PORT: int = int(os.getenv("EXTERNAL_TRIGGER_PORT", "8765"))
```

- [ ] **Step 2: Commit**

```bash
git add config.py
git commit -m "feat: add EXTERNAL_TRIGGER_PORT config setting"
```

---

### Task 2: Create bot_act_nugger module structure

**Files:**
- Create: `bot_act_nugger/__init__.py`
- Create: `bot_act_nugger/__main__.py`
- Create: `bot_act_nugger/client.py`

- [ ] **Step 1: Create __init__.py**

```python
"""Bot Act Nugger - External CLI trigger for Discord bot."""

__version__ = "1.0.0"
```

- [ ] **Step 2: Create client.py**

```python
"""HTTP client for sending triggers to the bot."""

import aiohttp
import sys


async def send_trigger(message: str, channel: str, port: int = 8765) -> dict:
    """Send a trigger request to the bot's HTTP endpoint."""
    url = f"http://127.0.0.1:{port}/trigger"
    payload = {"message": message, "channel": channel}

    async with aiohttp.ClientSession() as session:
        async with session.post(url, json=payload) as response:
            data = await response.json()
            return {"status": response.status, "body": data}


def send_trigger_sync(message: str, channel: str, port: int = 8765) -> dict:
    """Synchronous wrapper for send_trigger."""
    import asyncio
    return asyncio.run(send_trigger(message, channel, port))
```

- [ ] **Step 3: Create __main__.py**

```python
"""CLI entry point for bot_act_nugger."""

import argparse
import sys
from bot_act_nugger.client import send_trigger_sync


def main():
    parser = argparse.ArgumentParser(
        description="Trigger the Discord bot to respond as if mentioned"
    )
    parser.add_argument("message", help="Message to send to the bot")
    parser.add_argument("--channel", required=True, help="Discord channel (e.g., #general)")
    parser.add_argument("--port", type=int, default=8765, help="Bot HTTP port (default: 8765)")

    args = parser.parse_args()

    channel = args.channel.lstrip("#")

    try:
        result = send_trigger_sync(args.message, channel, args.port)
        if result["status"] == 200:
            print(f"Trigger sent successfully to #{channel}")
            print(f"Response: {result['body']}")
        else:
            print(f"Error: {result['body'].get('error', 'Unknown error')}", file=sys.stderr)
            sys.exit(1)
    except Exception as e:
        print(f"Connection failed: {e}", file=sys.stderr)
        print("Is the bot running with external trigger enabled?", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
```

- [ ] **Step 4: Commit**

```bash
git add bot_act_nugger/
git commit -m "feat: create bot_act_nugger module structure"
```

---

### Task 3: Add HTTP server endpoint to bot

**Files:**
- Modify: `bot.py` - Add HTTP server at end of file
- Test: Manual test (start bot, run CLI command)

- [ ] **Step 1: Read bot.py to find insertion point**

Read the end of `bot.py` (around line 450-464) to see where to add the HTTP server.

- [ ] **Step 2: Add HTTP server imports and endpoint**

Add after the imports section:
```python
import aiohttp
from aiohttp import web
```

Add at the end of bot.py before `if __name__ == "__main__":`:
```python
_external_trigger_app = None
_external_trigger_runner = None


async def _handle_trigger(request):
    """Handle external trigger requests."""
    try:
        data = await request.json()
    except Exception:
        return web.json_response({"error": "Invalid JSON"}, status=400)

    message_text = data.get("message", "")
    channel_name = data.get("channel", "")

    if not message_text:
        return web.json_response({"error": "message is required"}, status=400)
    if not channel_name:
        return web.json_response({"error": "channel is required"}, status=400)

    channel_name = channel_name.lstrip("#")

    guild = None
    target_channel = None

    for g in request.app["client"].guilds:
        for ch in g.text_channels:
            if ch.name == channel_name:
                target_channel = ch
                guild = g
                break
        if target_channel:
            break

    if not target_channel:
        return web.json_response(
            {"error": f"Channel #{channel_name} not found. Bot must be in the guild."},
            status=404
        )

    from discord import Message
    from discord.ext import commands
    import asyncio

    author = guild.get_member(request.app["client"].user.id)

    class FakeMember:
        def __init__(self, user):
            self.user = user
            self.id = user.id
            self.display_name = user.display_name
            self.mention = user.mention

    class FakeMessage:
        def __init__(self, channel, guild, content):
            self.channel = channel
            self.guild = guild
            self.content = f"{request.app['client'].user.mention} {content}"
            self.author = FakeMember(request.app["client"].user)
            self.attachments = []
            self.mentions = [request.app["client"].user]
            self.id = 0

        async def reply(self, content, **kwargs):
            await self.channel.send(content, **kwargs)

    fake_message = FakeMessage(target_channel, guild, message_text)

    try:
        await request.app["client"].dispatch("message", fake_message)
        return web.json_response({"status": "ok", "message": "Trigger processed"})
    except Exception as e:
        logger.error(f"Trigger error: {e}")
        return web.json_response({"error": str(e)}, status=500)


async def start_external_trigger_server(client):
    """Start the external trigger HTTP server."""
    global _external_trigger_app, _external_trigger_runner

    app = web.Application()
    app["client"] = client
    app.router.add_post("/trigger", _handle_trigger)

    _external_trigger_app = app

    host = "127.0.0.1"
    port = config.EXTERNAL_TRIGGER_PORT

    _external_trigger_runner = web.AppRunner(app)
    await _external_trigger_runner.setup()
    site = web.TCPSite(_external_trigger_runner, host, port)
    await site.start()

    logger.info(f"External trigger server started at http://{host}:{port}")
```

- [ ] **Step 3: Modify on_ready to start server**

In `on_ready` function (around line 146), add after logger.info line:
```python
await start_external_trigger_server(client)
```

- [ ] **Step 4: Commit**

```bash
git add bot.py
git commit -m "feat: add HTTP trigger endpoint to bot"
```

---

### Task 4: Test end-to-end

**Files:**
- Test: Manual testing

- [ ] **Step 1: Start the bot**

In one terminal, run:
```bash
python bot.py
```
Expected: Bot starts, "External trigger server started" message appears.

- [ ] **Step 2: Run CLI trigger**

In another terminal, run:
```bash
python -m bot_act_nugger "Hello, what is 2+2?" --channel #general
```
Expected: Bot responds in #general with LLM answer.

- [ ] **Step 3: Commit**

```bash
git add .
git commit -m "test: verify bot_act_nugger end-to-end"
```

---

## Acceptance Criteria

1. CLI can trigger bot from separate terminal
2. Bot responds in specified Discord channel
3. Bot processes message through RAG + mem0 + LLM (same as regular mention)
4. Works only when bot is running
5. Local-only access (no external network access)
