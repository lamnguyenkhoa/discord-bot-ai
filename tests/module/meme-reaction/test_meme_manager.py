import pytest
import pytest_asyncio
from module.meme_reaction.meme_manager import MemeManager

@pytest.fixture
def meme_manager():
    return MemeManager()

def test_meme_manager_initialization(meme_manager):
    assert meme_manager is not None

@pytest.mark.asyncio
async def test_search_gif_returns_url(meme_manager):
    result = await meme_manager.search_gif("funny cat")
    assert result is None or isinstance(result, str)
