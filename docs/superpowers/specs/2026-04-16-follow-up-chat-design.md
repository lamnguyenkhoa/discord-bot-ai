# Follow-Up Chat Module Design

## Overview
Add a follow-up message feature that triggers after the bot responds to a user mention, with a configurable percentage chance.

## Functionality

### Trigger Logic
- Trigger after bot sends a reply in response to a user mention
- Check `FOLLOW_UP_CHANCE` percentage (0-100, default 33)
- If triggered, generate follow-up via LLM with context of the original exchange
- LLM decides what kind of follow-up (question, remark, etc.)

### Cooldown
- Per-channel cooldown tracking to prevent spam
- Configurable via `FOLLOW_UP_COOLDOWN_SECONDS` (default 30 seconds)

### Integration Point
In `bot.py`, after the bot sends its initial reply (line ~363), call the follow-up manager to potentially send a follow-up message.

## Configuration

| Variable | Default | Description |
|----------|---------|-------------|
| FOLLOW_UP_CHANCE | 33 | Percentage chance (0-100) to trigger follow-up |
| FOLLOW_UP_COOLDOWN_SECONDS | 30 | Cooldown per channel |

## Architecture

```
module/follow_up_chat/
├── __init__.py          # FollowUpManager class
└── follow_up_manager.py # (optional separation)
```

`FollowUpManager`:
- `should_trigger(channel_key: str) -> bool` - Check chance + cooldown
- `generate_and_send(message, user_text, bot_reply)` - Generate follow-up via LLM and send

## Implementation Steps
1. Add config variables to config.py
2. Create module/follow_up_chat/__init__.py with FollowUpManager
3. Integrate in bot.py after initial reply