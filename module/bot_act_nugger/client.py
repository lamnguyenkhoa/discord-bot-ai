"""HTTP client for sending triggers to the bot."""

import aiohttp
import sys


async def send_trigger(channel: str, prompt: str = None, message: str = None, port: int = 8765, mention: str = None) -> dict:
    """Send a trigger request to the bot's HTTP endpoint."""
    url = f"http://127.0.0.1:{port}/trigger"
    payload = {"channel": channel}
    if prompt:
        payload["prompt"] = prompt
    if message:
        payload["message"] = message
    if mention:
        payload["mention"] = mention

    async with aiohttp.ClientSession() as session:
        async with session.post(url, json=payload) as response:
            data = await response.json()
            return {"status": response.status, "body": data}


def send_trigger_sync(channel: str, prompt: str = None, message: str = None, port: int = 8765, mention: str = None) -> dict:
    """Synchronous wrapper for send_trigger."""
    import asyncio
    return asyncio.run(send_trigger(channel, prompt, message, port, mention))
