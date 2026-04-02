# Open Questions

## discord-bot-v1 - 2026-04-01
- [ ] Which OpenRouter model should be the default in `.env`? -- Current default is `openai/gpt-4o-mini` but user said "let me configure it later". They may want a different default.
- [ ] Should `summarize()` use the same model as `generate_reply()` or a cheaper/faster model? -- Summarization is a background task; using a cheaper model could save cost.
- [ ] Should the bot strip mentions of OTHER users from the message text, or only its own? -- Currently only strips self-mention. Other @mentions might confuse the LLM if left as raw `<@id>` syntax.
- [ ] What happens when Discord's rate limit is hit? -- discord.py handles this internally, but we should confirm the bot doesn't queue up stale replies if rate-limited for extended periods.
- [ ] Should the summarization be async (non-blocking) or is it acceptable to block the next reply briefly? -- Current plan calls `summarize_if_needed()` synchronously after each exchange. For v1 this is likely fine given the low threshold (50 messages), but could delay the next reply if summarization takes several seconds.

## facts-learning-ability - 2026-04-02
- [ ] How aggressive should keyword-overlap matching be for fact dedup? -- Too loose and unrelated facts get overwritten; too strict and duplicates slip through. The plan defaults to "at least 1 significant shared keyword" but this threshold may need tuning after real usage.
- [ ] Should the cross-mark reaction handler require the reactor to be the original message author, or allow any user? -- Current plan allows any user to react and trigger deletion. Server admins may want this, but it could also be abused. Decide whether to restrict to the original author only.
- [ ] What if the bot message being reacted to has no reply reference (e.g., an older message format)? -- The handler logs and exits gracefully, but those facts will be un-removable via reaction. Acceptable for v1 but worth noting.
- [ ] Should `upsert_user_fact` handle aliases/display name changes? -- If a user changes their Discord display name, old facts under the previous name won't match for dedup. No solution planned for v1.
