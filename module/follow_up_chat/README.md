# Follow-Up Chat

After the bot responds to a user mention, there's a chance it will send a follow-up message to continue the conversation.

## Configuration

| Variable | Default | Description |
|----------|---------|-------------|
| FOLLOW_UP_CHANCE | 33 | Percentage chance (0-100) to trigger follow-up |
| FOLLOW_UP_COOLDOWN_SECONDS | 30 | Cooldown per channel before another follow-up can trigger |

## Example

```bash
# Enable with 33% chance, 30s cooldown (defaults)
FOLLOW_UP_CHANCE=33
FOLLOW_UP_COOLDOWN_SECONDS=30

# Higher chance (50%)
FOLLOW_UP_CHANCE=50

# Disable
FOLLOW_UP_CHANCE=0
```

## How It Works

1. User mentions the bot and asks something
2. Bot replies with an answer
3. After the reply, a random check runs against `FOLLOW_UP_CHANCE`
4. If triggered, the LLM generates a brief follow-up (question, comment, or clarification)
5. Follow-up is sent as a new message in the channel
6. Cooldown prevents spam in the same channel