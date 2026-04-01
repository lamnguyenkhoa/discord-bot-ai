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

client = discord.Client(intents=intents)


@client.event
async def on_ready():
    logger.info(f"Logged in as {client.user} (ID: {client.user.id})")


@client.event
async def on_message(message: discord.Message):
    if message.author == client.user:
        return

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
            extracted = await llm_client.extract_facts(
                str(message.author.display_name), user_text, ""
            )
            for fact in extracted["user_facts"]:
                facts_manager.append_user_fact(str(message.author.display_name), fact)
            for fact in extracted["server_facts"]:
                facts_manager.append_server_fact(fact)
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
            str(message.author.display_name), user_text, reply
        )
        for fact in extracted["user_facts"]:
            facts_manager.append_user_fact(str(message.author.display_name), fact)
        for fact in extracted["server_facts"]:
            facts_manager.append_server_fact(fact)
        await memory_manager.summarize_if_needed(datetime.date.today())


if __name__ == "__main__":
    if not config.DISCORD_TOKEN:
        logger.error("DISCORD_TOKEN not set in .env")
        exit(1)
    if not config.OPENROUTER_API_KEY:
        logger.error("OPENROUTER_API_KEY not set in .env")
        exit(1)

    os.makedirs(config.MEMORY_DIR, exist_ok=True)
    client.run(config.DISCORD_TOKEN, log_handler=None)
