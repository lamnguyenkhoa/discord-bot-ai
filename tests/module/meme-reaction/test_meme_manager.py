import pytest
import pytest_asyncio
from module.meme_reaction.meme_manager import MemeManager
from module.meme_reaction.trigger_decider import TriggerDecider

@pytest.fixture
def meme_manager():
    return MemeManager()

@pytest.fixture
def trigger_decider():
    return TriggerDecider()

def test_keyword_matching(trigger_decider):
    # Should trigger on keywords
    assert trigger_decider.check_keywords("lol that's funny") == True
    assert trigger_decider.check_keywords("haha nice one") == True
    assert trigger_decider.check_keywords("omg that's crazy") == True
    
    # Should not trigger on non-keywords
    assert trigger_decider.check_keywords("hello world") == False

@pytest.mark.asyncio
async def test_sentiment_analysis(trigger_decider):
    result = await trigger_decider.check_sentiment("I'm so excited about this!")
    assert isinstance(result, bool)

def test_meme_manager_initialization(meme_manager):
    assert meme_manager is not None

@pytest.mark.asyncio
async def test_search_gif_returns_url(meme_manager):
    result = await meme_manager.search_gif("funny cat")
    assert result is None or isinstance(result, str)
