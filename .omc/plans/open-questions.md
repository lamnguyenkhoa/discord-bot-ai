# Open Questions

## discord-bot-v1 - 2026-04-01
- [ ] Which OpenRouter model should be the default in `.env`? -- Current default is `openai/gpt-4o-mini` but user said "let me configure it later". They may want a different default.
- [ ] Should `summarize()` use the same model as `generate_reply()` or a cheaper/faster model? -- Summarization is a background task; using a cheaper model could save cost.
- [ ] Should the bot strip mentions of OTHER users from the message text, or only its own? -- Currently only strips self-mention. Other @mentions might confuse the LLM if left as raw `<@id>` syntax.
- [ ] What happens when Discord's rate limit is hit? -- discord.py handles this internally, but we should confirm the bot doesn't queue up stale replies if rate-limited for extended periods.
- [ ] Should the summarization be async (non-blocking) or is it acceptable to block the next reply briefly? -- Current plan calls `summarize_if_needed()` synchronously after each exchange. For v1 this is likely fine given the low threshold (50 messages), but could delay the next reply if summarization takes several seconds.
