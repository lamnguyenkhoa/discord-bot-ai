import os
os.environ.pop("SSL_CERT_FILE", None)

import asyncio
import aiohttp
import time
import random
import discord
import config
import mem0_manager
import llm_client
import indexer
import rag_manager
import logging
import re
from difflib import SequenceMatcher

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)

FALLBACK = llm_client.FALLBACK_REPLY

intents = discord.Intents.default()
intents.message_content = True
intents.reactions = True
intents.members = True  # needed for member name resolution; enable "Server Members Intent" in Discord Developer Portal

client = discord.Client(intents=intents)



def resolve_member_by_name(guild: discord.Guild, name_query: str) -> discord.Member | None:
    """Fuzzy-resolve a name string to a guild member. Returns None if no confident match."""
    if not name_query or not guild:
        return None
    q = name_query.lower()
    members = guild.members
    for m in members:
        if m.display_name.lower() == q or m.name.lower() == q:
            return m
    for m in members:
        if m.display_name.lower().startswith(q) or m.name.lower().startswith(q):
            return m
    for m in members:
        if q in m.display_name.lower() or q in m.name.lower():
            return m
    best, best_score = None, 0.0
    for m in members:
        score = max(
            SequenceMatcher(None, q, m.display_name.lower()).ratio(),
            SequenceMatcher(None, q, m.name.lower()).ratio(),
        )
        if score > best_score:
            best, best_score = m, score
    return best if best_score >= 0.6 else None




@client.event
async def on_ready():
    logger.info(f"Logged in as {client.user} (ID: {client.user.id})")
    indexer.init_db()
    await rag_manager.initialize()
    await mem0_manager.initialize()

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


class AutoPostState:
    def __init__(self):
        self.message_count: dict[str, int] = {}
        self.last_post_time: dict[str, float] = {}


auto_post_state = AutoPostState()


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


async def try_auto_post(message: discord.Message, guild, channel_key: str, guild_id: str):
    if config.AUTO_POST_ENABLED and guild_id:
        last_post = auto_post_state.last_post_time.get(channel_key, 0)
        if time.time() - last_post < config.AUTO_POST_COOLDOWN_SECONDS:
            auto_post_state.message_count[channel_key] = 0
            return

        channel_context = mem0_manager.format_context_for_prompt(guild_id, None, "")

        prompt = f"""In 1-2 sentences, write a standalone statement related to recent conversation in #{channel_key}.
It can comment on something discussed or share an interesting memory.
Keep it short (under {config.AUTO_POST_MAX_LENGTH} chars), conversational, no questions.

Recent context:
{channel_context}"""

        try:
            async with message.channel.typing():
                post = await llm_client.generate_reply(prompt, "", channel_key)

            if post and len(post) <= config.AUTO_POST_MAX_LENGTH:
                await message.channel.send(post)
                logger.info(f"Auto-posted in #{channel_key}")
                auto_post_state.last_post_time[channel_key] = time.time()
            elif post and len(post) > config.AUTO_POST_MAX_LENGTH:
                truncated = post[:497] + "..."
                await message.channel.send(truncated)
                logger.info(f"Auto-posted (truncated) in #{channel_key}")
                auto_post_state.last_post_time[channel_key] = time.time()
        except Exception as e:
            logger.warning(f"Auto-post failed: {e}")

    auto_post_state.message_count[channel_key] = 0


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
            return
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

    # RAG: retrieve relevant context (guild docs + web) first
    rag_context = ""
    if guild_id:
        try:
            rag_context = await rag_manager.format_rag_context(user_text)
        except Exception as e:
            logger.warning(f"RAG failed, falling back to mem0: {e}")

    # Mem0: fallback if RAG is empty
    if rag_context.strip() in ("", "No RAG context available."):
        memory_context = mem0_manager.format_context_for_prompt(guild_id, user_id, user_text)
    else:
        memory_context = rag_context


    async with message.channel.typing():
        reply = await llm_client.generate_reply(
            user_message=user_text,
            memory_context=memory_context,
            channel_name=str(message.channel),
            image_urls=image_urls,
        )

    if len(reply) > 2000:
        reply = reply[:1997] + "..."
    await message.reply(reply)

    # Skip logging if reply was the fallback error string
    if reply != FALLBACK and guild_id:
        author_name = str(message.author.display_name)
        await mem0_manager.capture_exchange(
            user_id=user_id,
            guild_id=guild_id,
            channel_name=str(message.channel),
            username=author_name,
            user_message=user_text,
            bot_reply=reply,
            msg_id=message.id,
        )


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
