# Bot Act Nugger - External CLI Trigger Design

## Overview
Add a module that allows running a command in a separate terminal to trigger the Discord bot to respond as if a user mentioned it.

## Usage
```bash
python -m bot_act_nugger "Your message here" --channel #general
```

## Architecture

### Components

1. **HTTP Endpoint in Bot** (`bot.py`)
   - Lightweight HTTP server (aiohttp) running on localhost
   - Endpoint: `POST http://localhost:8765/trigger`
   - Accepts JSON: `{"message": "...", "channel": "#channel-name"}`
   - Routes to existing `on_message` processing pipeline

2. **CLI Module** (`bot_act_nugger/__main__.py`)
   - Command-line interface using argparse
   - Parses message and channel arguments
   - Sends HTTP request to bot's trigger endpoint
   - Prints response status

### Data Flow

```
Terminal CLI
    |
    | POST /trigger {"message": "...", "channel": "#general"}
    v
Bot HTTP Server (localhost:8765)
    |
    | Create synthetic Message object
    v
on_message processing (existing logic)
    |
    | LLM.generate_reply()
    v
message.reply() to Discord channel
```

## Implementation Details

### HTTP Server

- Port: 8765 (configurable via `EXTERNAL_TRIGGER_PORT` in config.py)
- Only binds to localhost (127.0.0.1) for security
- No authentication (local-only access)

### CLI Arguments

| Argument | Required | Default | Description |
|----------|----------|---------|-------------|
| `message` | Yes | - | The message to send to the bot |
| `--channel` | Yes | - | Discord channel name (e.g., #general) |
| `--port` | No | 8765 | Override default port |

### Error Handling

- Connection refused: Bot not running → print error and exit 1
- Channel not found: → print error and exit 1
- HTTP error responses: Forward error message from bot

## Files to Create/Modify

1. `bot_act_nugger/__init__.py` - Module init
2. `bot_act_nugger/__main__.py` - CLI entry point
3. `bot_act_nugger/client.py` - HTTP client for CLI
4. `bot.py` - Add HTTP server endpoint
5. `config.py` - Add `EXTERNAL_TRIGGER_PORT` setting
6. `config.py` - Add `EXTERNAL_TRIGGER_PORT` to .env.example

## Acceptance Criteria

1. CLI can trigger bot from separate terminal
2. Bot responds in specified Discord channel
3. Bot processes message through RAG + mem0 + LLM (same as regular mention)
4. Works only when bot is running
5. Local-only access (no external network access)
