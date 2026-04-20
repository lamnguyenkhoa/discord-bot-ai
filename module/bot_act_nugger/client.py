"""HTTP client for sending triggers to the bot."""

import aiohttp
import sys


async def send_trigger(message: str, channel: str, port: int = 8765) -> dict:
    """Send a trigger request to the bot's HTTP endpoint."""
    url = f"http://127.0.0.1:{port}/trigger"
    payload = {"message": message, "channel": channel}

    async with aiohttp.ClientSession() as session:
        async with session.post(url, json=payload) as response:
            data = await response.json()
            return {"status": response.status, "body": data}


def send_trigger_sync(message: str, channel: str, port: int = 8765) -> dict:
    """Synchronous wrapper for send_trigger."""
    import asyncio
    return asyncio.run(send_trigger(message, channel, port))
