"""
RAG Manager - Retrieval-Augmented Generation for Discord bot.

Retrieves context from:
- Guild documents (indexed via indexer.py)
- Web content (OpenRouter web search + URL scraping)
"""

import asyncio
import logging
import re
from typing import Optional

import aiohttp
from openai import AsyncOpenAI

import config
import indexer

logger = logging.getLogger(__name__)

_MAX_URL_LENGTH = 2000

_openai_client: Optional[AsyncOpenAI] = None
_aiohttp_session: Optional[aiohttp.ClientSession] = None


def _get_openai_client() -> AsyncOpenAI:
    global _openai_client
    if _openai_client is None:
        _openai_client = AsyncOpenAI(api_key=config.LLM_API_KEY, base_url=config.LLM_BASE_URL)
    return _openai_client


async def _get_aiohttp_session() -> aiohttp.ClientSession:
    global _aiohttp_session
    if _aiohttp_session is None or _aiohttp_session.closed:
        _aiohttp_session = aiohttp.ClientSession()
    return _aiohttp_session


async def initialize() -> None:
    """Initialize RAG system."""
    await indexer.init_db()
    logger.info("RAG system initialized")


async def retrieve_guild_docs(query: str, limit_tokens: int = 600) -> list[dict]:
    """
    Retrieve relevant chunks from indexed guild documents.
    """
    try:
        results = await indexer.retrieve(query, limit_tokens)
        return results
    except Exception as e:
        logger.error(f"Error retrieving guild docs: {e}")
        return []


async def search_web(query: str, limit_tokens: int = 400) -> list[dict]:
    """
    Search the web using OpenRouter web search.
    """
    if not config.LLM_API_KEY or "openrouter" not in config.LLM_BASE_URL:
        logger.debug("Web search not available - no OpenRouter")
        return []
    
    try:
        client = _get_openai_client()
        response = await client.chat.completions.create(
            model=config.MODEL_NAME,
            messages=[
                {"role": "system", "content": "Use the web_search tool to find current information about: " + query}
            ],
            tools=[{"type": "openrouter:web_search"}],
            tool_choice={"type": "web_search"},
        )
        
        output = response.choices[0].message.content or ""
        if not output:
            return []
        
        # Parse web search results
        results = []
        char_budget = limit_tokens * 4
        
        # Simple parsing - split by double newlines or markers
        entries = re.split(r'\n(?=Title:|URL:)', output)
        for entry in entries:
            if "URL:" in entry:
                match = re.search(r'Title: (.+)', entry)
                title = match.group(1).strip() if match else "No title"
                match = re.search(r'URL: (.+)', entry)
                url = match.group(1).strip() if match else ""
                match = re.search(r'Summary: (.+)', entry, re.DOTALL)
                summary = match.group(1).strip() if match else entry
                
                if len(summary) > char_budget // 3:
                    summary = summary[:char_budget // 3] + "..."
                
                results.append({
                    "title": title,
                    "url": url,
                    "content": summary,
                    "source": "web_search",
                })
        
        return results
    except Exception as e:
        logger.error(f"Web search error: {e}")
        return []


async def fetch_url(url: str, max_chars: int = 2000) -> str:
    """
    Fetch and extract text content from a URL.
    """
    if len(url) > _MAX_URL_LENGTH:
        logger.warning(f"URL too long: {url[:50]}...")
        return ""
    
    try:
        session = await _get_aiohttp_session()
        async with session.get(url, timeout=aiohttp.ClientTimeout(total=10)) as resp:
            if resp.status != 200:
                logger.warning(f"URL fetch failed: {resp.status}")
                return ""
            
            text = await resp.text()
            
            text = re.sub(r'<script[^>]*>.*?</script>', '', text, flags=re.DOTALL | re.IGNORECASE)
            text = re.sub(r'<style[^>]*>.*?</style>', '', text, flags=re.DOTALL | re.IGNORECASE)
            text = re.sub(r'<[^>]+>', '', text)
            text = re.sub(r'\s+', ' ', text)
            text = text.strip()
            
            if len(text) > max_chars:
                text = text[:max_chars] + "..."
            
            return text
    except Exception as e:
        logger.error(f"URL fetch error: {e}")
        return ""


async def format_rag_context(query: str) -> str:
    """
    Build RAG context string combining guild docs + web results.
    Token budget: 1000 tokens (600 guild docs, 400 web)
    """
    parts = []
    
    # Guild docs (600 tokens)
    guild_docs = await retrieve_guild_docs(query, limit_tokens=600)
    if guild_docs:
        doc_parts = []
        for doc in guild_docs:
            lines = f"lines {doc['line_start']}-{doc['line_end']}"
            doc_parts.append(f"- [{doc['file']} {lines}]\n{doc['text']}")
        parts.append("## Guild Documents\n" + "\n\n".join(doc_parts))
    
    # Web results (400 tokens)
    web_results = await search_web(query, limit_tokens=400)
    if web_results:
        web_parts = []
        for result in web_results:
            content = result.get("content", "")
            if result.get("url"):
                content += f"\n(Source: {result['url']})"
            web_parts.append(f"- *{result['title']}*\n{content}")
        parts.append("## Web Search\n" + "\n\n".join(web_parts))
    
    if not parts:
        return "No RAG context available."
    
    return "\n\n".join(parts)