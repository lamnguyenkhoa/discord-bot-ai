import os
os.environ.pop("SSL_CERT_FILE", None)

import discord
import config
import memory_manager
import facts_manager
import llm_client
import logging
import re
import datetime
import os

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
    
    # Send online message if configured
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
    
    # Send offline message if configured
    if config.OFFLINE_MESSAGE and config.STATUS_CHANNEL:
        # Note: We can't send messages when disconnected, so this is logged
        # The message will be sent before disconnecting if using close()
        logger.info(f"Offline message (not sent - bot disconnected): {config.OFFLINE_MESSAGE}")


@client.event
async def on_message(message: discord.Message):
    if message.author == client.user:
        return

    # Check for kill word - only allowed user can trigger it
    if config.KILL_WORD and config.KILL_WORD_ALLOWED_USER_ID:
        user_text = message.content.strip()
        if config.KILL_WORD in user_text and str(message.author.id) == config.KILL_WORD_ALLOWED_USER_ID:
            logger.info(f"Kill word '{config.KILL_WORD}' received from allowed user {message.author}. Stopping bot.")
            await message.reply("Sayonara (get zapped by lightnight).")
            # Send offline message before closing
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
                channel_name=str(message.channel),
                author_name=str(message.author.display_name),
                user_message=user_text,
                bot_reply="",
            )
            facts_context = facts_manager.load_facts()
            extracted = await llm_client.extract_facts(
                str(message.author.display_name), user_text, "", existing_facts=facts_context
            )
            author_name = str(message.author.display_name)
            for correction in extracted.get("corrections", []):
                if correction.get("user", "") != author_name:
                    logger.warning(f"Ignoring cross-user correction from {author_name} targeting {correction.get('user')}")
                    continue
                await facts_manager.upsert_user_fact(
                    author_name, correction["new_fact"],
                    msg_id=message.id, old_fact=correction.get("old_fact")
                )
            for fact in extracted["user_facts"]:
                await facts_manager.upsert_user_fact(str(message.author.display_name), fact, msg_id=message.id)
            for fact in extracted["server_facts"]:
                await facts_manager.upsert_server_fact(fact, msg_id=message.id)
        return

    if client.user not in message.mentions:
        return

    user_text = re.sub(r"<@!?\d+>", "", message.content).strip()
    if not user_text:
        user_text = "(empty mention)"

    logger.info(f"Mentioned by {message.author} in #{message.channel}: {user_text[:80]}")

    memory_context = memory_manager.load_context()
    facts_context = facts_manager.load_facts()

    async with message.channel.typing():
        reply = await llm_client.generate_reply(
            user_message=user_text,
            memory_context=memory_context,
            channel_name=str(message.channel),
            facts_context=facts_context,
        )

    if len(reply) > 2000:
        reply = reply[:1997] + "..."
    await message.reply(reply)

    # Skip logging to memory if reply was the fallback error string
    if reply != FALLBACK:
        memory_manager.append_exchange(
            channel_name=str(message.channel),
            author_name=str(message.author.display_name),
            user_message=user_text,
            bot_reply=reply,
        )
        extracted = await llm_client.extract_facts(
            str(message.author.display_name), user_text, reply, existing_facts=facts_context
        )
        author_name = str(message.author.display_name)
        for correction in extracted.get("corrections", []):
            if correction.get("user", "") != author_name:
                logger.warning(f"Ignoring cross-user correction from {author_name} targeting {correction.get('user')}")
                continue
            await facts_manager.upsert_user_fact(
                author_name, correction["new_fact"],
                msg_id=message.id, old_fact=correction.get("old_fact")
            )
        for fact in extracted["user_facts"]:
            await facts_manager.upsert_user_fact(str(message.author.display_name), fact, msg_id=message.id)
        for fact in extracted["server_facts"]:
            await facts_manager.upsert_server_fact(fact, msg_id=message.id)
        await memory_manager.summarize_if_needed(datetime.date.today())


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

    count = await facts_manager.remove_facts_by_msg_id(message.id)
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
    if not config.OPENROUTER_API_KEY:
        logger.error("OPENROUTER_API_KEY not set in .env")
        exit(1)

    os.makedirs(config.MEMORY_DIR, exist_ok=True)
    client.run(config.DISCORD_TOKEN, log_handler=None)
