import aiohttp
import logging
import config

logger = logging.getLogger(__name__)


class MemeManager:
    def __init__(self):
        self._cache = {}
        self._cache_ttl = 300  # 5 minutes
        self._last_request_time = {}
        self._cooldown = config.MEME_COOLDOWN_SECONDS

    async def search_gif(self, query: str) -> str | None:
        """Search for GIF and return URL or None."""
        if not config.MEME_API_KEY:
            logger.warning("MEME_API_KEY not configured")
            return None

        # Truncate query
        query = query[-200:] if len(query) > 200 else query
        
        # Check cache
        if query in self._cache:
            return self._cache[query]

        # Choose API
        if config.MEME_API == "tenor":
            url = await self._search_tenor(query)
        else:
            url = await self._search_giphy(query)

        if url:
            self._cache[query] = url
        return url

    async def _search_giphy(self, query: str) -> str | None:
        api_url = "https://api.giphy.com/v1/gifs/search"
        params = {
            "api_key": config.MEME_API_KEY,
            "q": query,
            "limit": 1,
            "rating": "pg-13"
        }
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(api_url, params=params) as resp:
                    if resp.status == 429:
                        logger.warning("Giphy rate limited")
                        return None
                    data = await resp.json()
                    if data.get("data"):
                        return data["data"][0]["images"]["original"]["url"]
        except Exception as e:
            logger.error(f"Giphy API error: {e}")
        return None

    async def _search_tenor(self, query: str) -> str | None:
        api_url = "https://tenor.googleapis.com/v2/search"
        params = {
            "q": query,
            "limit": 1,
            "contentfilter": "medium",
            "key": config.MEME_API_KEY or ""
        }
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(api_url, params=params) as resp:
                    data = await resp.json()
                    if data.get("results"):
                        return data["results"][0]["url"]
        except Exception as e:
            logger.error(f"Tenor API error: {e}")
        return None


# Global singleton
_meme_manager = None


def get_meme_manager() -> MemeManager:
    global _meme_manager
    if _meme_manager is None:
        _meme_manager = MemeManager()
    return _meme_manager
