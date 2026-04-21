# bot_act_nugger

Trigger the Discord bot to send messages via HTTP.

## CLI

```bash
# Prompt mode - bot says something directly
python -m module.bot_act_nugger --channel general --prompt "Hello everyone!"

# Message mode - bot responds to a user message
python -m module.bot_act_nugger --channel general --message "What is 2+2?"

# With mention
python -m module.bot_act_nugger --channel general --prompt "Check this out!" --mention @username
```

## Options

| Option | Description |
|--------|-------------|
| `--channel` | Discord channel (e.g., #general) |
| `--prompt` | Prompt for bot to say something directly |
| `--message` | Message for bot to respond to |
| `--mention` | User to mention (e.g., @username) |
| `--port` | Bot HTTP port (default: 8765) |

## HTTP API

```bash
curl -X POST http://127.0.0.1:8765/trigger \
  -H "Content-Type: application/json" \
  -d '{"channel": "general", "prompt": "Hello!"}'
```