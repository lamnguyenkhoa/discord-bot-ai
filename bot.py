import os
os.environ.pop("SSL_CERT_FILE", None)

import asyncio
import aiohttp
import discord
import config
import memory_manager
import facts_manager
import llm_client
import indexer
import search as memory_search
import logging
import re
import datetime

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)

FALLBACK = llm_client.FALLBACK_REPLY

intents = discord.Intents.default()
intents.message_content = True
intents.reactions = True

client = discord.Client(intents=intents)


@client.event
async def on_ready():
    logger.info(f"Logged in as {client.user} (ID: {client.user.id})")
    indexer.init_db()

    if config.ONLINE_MESSAGE and config.STATUS_CHANNEL:
        for guild in client.guilds:
            channel = discord.utils.get(guild.text_channels, name=config.STATUS_CHANNEL)
            if channel:
                try:
                    online_msg = f"{config.ONLINE_MESSAGE} (Model: {config.MODEL_NAME})"
                    await channel.send(online_msg)
                    logger.info(f"Sent online message to #{channel}")
                except Exception as e:
                    logger.error(f"Failed to send online message: {e}")
                break


@client.event
async def on_disconnect():
    logger.info("Bot disconnected")

    if config.OFFLINE_MESSAGE and config.STATUS_CHANNEL:
        logger.info(f"Offline message (not sent - bot disconnected): {config.OFFLINE_MESSAGE}")


_TEXT_EXTENSIONS = {
    ".txt", ".md", ".py", ".js", ".ts", ".json", ".yaml", ".yml",
    ".csv", ".html", ".css", ".xml", ".log", ".sh", ".c", ".cpp",
    ".h", ".java", ".rb", ".go", ".rs", ".toml", ".ini", ".cfg",
}
_IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".gif", ".webp"}
_PDF_EXTENSIONS = {".pdf"}


async def _extract_pdf_text(session: aiohttp.ClientSession, att) -> str:
    import io
    import pypdf
    async with session.get(att.url) as resp:
        pdf_bytes = await resp.read()
    reader = pypdf.PdfReader(io.BytesIO(pdf_bytes))
    pages_text = []
    for page in reader.pages[:config.PDF_MAX_PAGES]:
        text = page.extract_text() or ""
        if text.strip():
            pages_text.append(text)
    return "\n\n".join(pages_text)


async def process_attachments(attachments):
    """Returns (extra_text, image_urls) from message attachments."""
    extra_text = []
    image_urls = []
    async with aiohttp.ClientSession() as session:
        for att in attachments:
            ext = os.path.splitext(att.filename)[1].lower()
            if ext in _IMAGE_EXTENSIONS:
                image_urls.append(att.url)
            elif ext in _TEXT_EXTENSIONS or (att.content_type and "text" in att.content_type):
                if att.size > config.ATTACHMENT_MAX_BYTES:
                    extra_text.append(f"[File: {att.filename} - too large to read ({att.size // 1024} KB)]")
                else:
                    try:
                        async with session.get(att.url) as resp:
                            content = await resp.text(errors="replace")
                        if len(content) > config.ATTACHMENT_MAX_CHARS:
                            content = content[:config.ATTACHMENT_MAX_CHARS] + f"\n... [truncated at {config.ATTACHMENT_MAX_CHARS} chars]"
                        extra_text.append(f"[File: {att.filename}]\n{content}")
                    except Exception as e:
                        logger.warning(f"Failed to fetch attachment {att.filename}: {e}")
                        extra_text.append(f"[File: {att.filename} - could not read]")
            elif ext in _PDF_EXTENSIONS or (att.content_type and "pdf" in att.content_type):
                if att.size > config.PDF_MAX_BYTES:
                    extra_text.append(f"[File: {att.filename} - too large to read ({att.size // (1024 * 1024):.1f} MB)]")
                else:
                    try:
                        content = await _extract_pdf_text(session, att)
                        if not content.strip():
                            extra_text.append(f"[File: {att.filename} - PDF contains no extractable text]")
                        else:
                            if len(content) > config.ATTACHMENT_MAX_CHARS:
                                content = content[:config.ATTACHMENT_MAX_CHARS] + f"\n... [truncated at {config.ATTACHMENT_MAX_CHARS} chars]"
                            extra_text.append(f"[File: {att.filename} (PDF)]\n{content}")
                    except Exception as e:
                        logger.warning(f"Failed to extract PDF {att.filename}: {e}")
                        extra_text.append(f"[File: {att.filename} - could not read PDF]")
            else:
                extra_text.append(f"[File: {att.filename} - unsupported type]")
    return extra_text, image_urls


@client.event
async def on_message(message: discord.Message):
    if message.author == client.user:
        return

    user_id = str(message.author.id)
    guild_id = str(message.guild.id) if message.guild else None

    # Check for kill word - only allowed user can trigger it
    if config.KILL_WORD and config.KILL_WORD_ALLOWED_USER_ID:
        user_text = message.content.strip()
        if config.KILL_WORD in user_text and str(message.author.id) == config.KILL_WORD_ALLOWED_USER_ID:
            logger.info(f"Kill word '{config.KILL_WORD}' received from allowed user {message.author}. Stopping bot.")
            await message.reply("Sayonara (get zapped by lightnight).")
            if config.OFFLINE_MESSAGE and config.STATUS_CHANNEL:
                channel = discord.utils.get(message.guild.text_channels, name=config.STATUS_CHANNEL)
                if channel:
                    try:
                        await channel.send(config.OFFLINE_MESSAGE)
                        logger.info(f"Sent offline message to #{channel}")
                    except Exception as e:
                        logger.error(f"Failed to send offline message: {e}")
            await client.close()
            exit(0)

    # Silently observe watched channels
    if str(message.channel) in config.WATCH_CHANNELS and client.user not in message.mentions:
        user_text = message.content.strip()
        if user_text:
            logger.debug(f"Observing #{message.channel}: {user_text[:80]}")
            memory_manager.append_exchange(
                user_id=user_id,
                guild_id=guild_id,
                channel_name=str(message.channel),
                author_name=str(message.author.display_name),
                user_message=user_text,
                bot_reply="",
            )
            facts_context = facts_manager.load_facts(user_id, guild_id)
            extracted = await llm_client.extract_facts(
                str(message.author.display_name), user_text, "", existing_facts=facts_context
            )
            author_name = str(message.author.display_name)
            for correction in extracted.get("corrections", []):
                if correction.get("user", "") != author_name:
                    logger.warning(f"Ignoring cross-user correction from {author_name} targeting {correction.get('user')}")
                    continue
                await facts_manager.upsert_user_fact(
                    user_id, author_name, correction["new_fact"],
                    msg_id=message.id, old_fact=correction.get("old_fact"),
                )
            for fact in extracted["user_facts"]:
                await facts_manager.upsert_user_fact(user_id, author_name, fact, msg_id=message.id)
            for fact in extracted["server_facts"]:
                await facts_manager.upsert_server_fact(guild_id, fact, msg_id=message.id)
            asyncio.create_task(indexer.index_user(user_id))
        return

    if client.user not in message.mentions:
        return

    user_text = re.sub(r"<@!?\d+>", "", message.content).strip()
    if not user_text:
        user_text = "(empty mention)"

    if config.KILL_WORD and user_text.strip().lower() == config.KILL_WORD.lower():
        logger.info(f"Kill word received from {message.author} — shutting down.")
        await message.reply("ciao o7")
        await client.close()
        return

    logger.info(f"Mentioned by {message.author} in #{message.channel}: {user_text[:80]}")

    extra_text, image_urls = await process_attachments(message.attachments)
    if extra_text:
        user_text += "\n\n" + "\n\n".join(extra_text)

    # RAG: retrieve relevant memory chunks for context
    search_results = await memory_search.search(user_id, guild_id, user_text)
    memory_context = "\n\n---\n\n".join(search_results) if search_results else ""

    facts_context = facts_manager.load_facts(user_id, guild_id)

    async with message.channel.typing():
        reply = await llm_client.generate_reply(
            user_message=user_text,
            memory_context=memory_context,
            channel_name=str(message.channel),
            facts_context=facts_context,
            image_urls=image_urls,
        )

    if len(reply) > 2000:
        reply = reply[:1997] + "..."
    await message.reply(reply)

    # Skip logging if reply was the fallback error string
    if reply != FALLBACK:
        author_name = str(message.author.display_name)
        memory_manager.append_exchange(
            user_id=user_id,
            guild_id=guild_id,
            channel_name=str(message.channel),
            author_name=author_name,
            user_message=user_text,
            bot_reply=reply,
        )
        extracted = await llm_client.extract_facts(
            author_name, user_text, reply, existing_facts=facts_context
        )
        for correction in extracted.get("corrections", []):
            if correction.get("user", "") != author_name:
                logger.warning(f"Ignoring cross-user correction from {author_name} targeting {correction.get('user')}")
                continue
            await facts_manager.upsert_user_fact(
                user_id, author_name, correction["new_fact"],
                msg_id=message.id, old_fact=correction.get("old_fact"),
            )
        for fact in extracted["user_facts"]:
            await facts_manager.upsert_user_fact(user_id, author_name, fact, msg_id=message.id)
        for fact in extracted["server_facts"]:
            await facts_manager.upsert_server_fact(guild_id, fact, msg_id=message.id)

        today = datetime.date.today()
        await memory_manager.flush_memory_if_needed(user_id, today)
        await memory_manager.summarize_if_needed(user_id, today)

        # Re-index memory files async (non-blocking)
        asyncio.create_task(indexer.index_user(user_id))
        if guild_id:
            asyncio.create_task(indexer.index_guild(guild_id))


@client.event
async def on_raw_reaction_add(payload: discord.RawReactionActionEvent):
    if payload.emoji.name != "\u274c":
        return
    if payload.user_id == client.user.id:
        return

    channel = client.get_channel(payload.channel_id)
    if channel is None:
        return

    try:
        message = await channel.fetch_message(payload.message_id)
    except Exception as e:
        logger.warning(f"on_raw_reaction_add: could not fetch message {payload.message_id}: {e}")
        return

    if message.author.id != client.user.id:
        return

    # Authorization: only the user the bot replied to can remove facts
    if not message.reference:
        logger.debug(f"on_raw_reaction_add: bot message {message.id} has no reference, ignoring")
        return
    try:
        original = await channel.fetch_message(message.reference.message_id)
        if payload.user_id != original.author.id:
            logger.debug(f"on_raw_reaction_add: reactor {payload.user_id} is not original author {original.author.id}")
            return
    except Exception as e:
        logger.warning(f"on_raw_reaction_add: could not fetch original message: {e}")
        return

    original_user_id = str(original.author.id)
    guild_id = str(payload.guild_id) if payload.guild_id else None

    count = await facts_manager.remove_facts_by_msg_id(message.id, original_user_id, guild_id)
    if count > 0:
        logger.info(f"Removed {count} fact(s) via reaction on msg {message.id}")
        try:
            await message.add_reaction("\u2705")
        except Exception:
            pass
    else:
        logger.info(f"No facts matched msg_id={message.id} for reaction removal")


if __name__ == "__main__":
    if not config.DISCORD_TOKEN:
        logger.error("DISCORD_TOKEN not set in .env")
        exit(1)
    _is_local = "localhost" in config.LLM_BASE_URL or "127.0.0.1" in config.LLM_BASE_URL
    if not config.LLM_API_KEY and not _is_local:
        logger.error("LLM_API_KEY (or OPENROUTER_API_KEY) not set in .env")
        exit(1)

    os.makedirs(config.MEMORY_BASE_PATH, exist_ok=True)
    client.run(config.DISCORD_TOKEN, log_handler=None)
