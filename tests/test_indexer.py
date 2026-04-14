import pytest
import os
import tempfile
import asyncio
from unittest.mock import patch

import sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import indexer
import config


@pytest.fixture
def temp_dir():
    with tempfile.TemporaryDirectory() as tmpdir:
        yield tmpdir


@pytest.fixture
def temp_db(temp_dir):
    db_path = os.path.join(temp_dir, "test_memory.sqlite")
    yield db_path
    if os.path.exists(db_path):
        os.remove(db_path)


@pytest.fixture
def temp_memory(temp_dir):
    memory_path = os.path.join(temp_dir, "memory")
    os.makedirs(memory_path, exist_ok=True)
    yield memory_path


@pytest.fixture
def sample_md(temp_memory):
    content = """# Test Document

This is a test file with multiple lines.

## Section 1
Some content here.

## Section 2
More content.
"""
    path = os.path.join(temp_memory, "test.md")
    with open(path, "w") as f:
        f.write(content)
    return path


@pytest.mark.asyncio
async def test_index_file(temp_db, sample_md):
    with patch.object(config, 'INDEX_PATH', temp_db):
        indexer.init_db(temp_db)
        await indexer.index_file(sample_md, temp_db)

        stats = indexer.get_stats()
        assert stats["files"] == 1
        assert stats["chunks"] > 0


@pytest.mark.asyncio
async def test_index_all(temp_memory, temp_db):
    with open(os.path.join(temp_memory, "file1.md"), "w") as f:
        f.write("# File 1\nContent")
    with open(os.path.join(temp_memory, "file2.md"), "w") as f:
        f.write("# File 2\nContent")

    with patch.object(config, 'KNOWLEDGE_PATH', temp_memory):
        with patch.object(config, 'INDEX_PATH', temp_db):
            indexer.init_db(temp_db)
            stats = await indexer.index_all()

    assert stats["files"] == 2
    assert stats["chunks"] > 0


def test_get_stats_empty(temp_db):
    with patch.object(config, 'INDEX_PATH', temp_db):
        indexer.init_db(temp_db)
        stats = indexer.get_stats()
        assert stats["files"] == 0
        assert stats["chunks"] == 0


@pytest.mark.asyncio
async def test_get_indexed_files(temp_db, sample_md):
    with patch.object(config, 'INDEX_PATH', temp_db):
        indexer.init_db(temp_db)
        await indexer.index_file(sample_md, temp_db)

        files = await indexer.get_indexed_files()
        assert isinstance(files, list)
        assert len(files) == 1
        assert files[0]["path"] == sample_md
        assert files[0]["chunks"] > 0
