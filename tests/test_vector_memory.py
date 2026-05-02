"""
Unit tests for VectorMemory (ChromaDB-backed NPC memory).
"""

import time
import pytest
import tempfile
import os

import sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from backend.memory.vector_memory import VectorMemory, MemoryEntry, _HashEmbeddingFunction


@pytest.fixture
def memory(tmp_path):
    """Create a fresh VectorMemory backed by a temporary directory using
    the offline hash embedding function (no network required)."""
    return VectorMemory(
        persist_directory=str(tmp_path / "chroma"),
        embedding_function=_HashEmbeddingFunction(),
    )


# ---------------------------------------------------------------------------
# Basic write / read
# ---------------------------------------------------------------------------

def test_add_and_count(memory):
    npc_id = "test_npc"
    memory.add_memory(npc_id, "I met a stranger at the docks.")
    collection = memory._get_or_create_collection(npc_id)
    assert collection.count() == 1


def test_add_returns_id(memory):
    mid = memory.add_memory("npc1", "Remember the rain.")
    assert isinstance(mid, str) and len(mid) > 0


def test_add_multiple_memories(memory):
    for i in range(5):
        memory.add_memory("npc2", f"Memory number {i}")
    col = memory._get_or_create_collection("npc2")
    assert col.count() == 5


# ---------------------------------------------------------------------------
# Search
# ---------------------------------------------------------------------------

def test_search_returns_results(memory):
    npc_id = "searcher"
    memory.add_memory(npc_id, "The neon lights flickered at midnight.", importance=0.9)
    memory.add_memory(npc_id, "I repaired a broken android today.", importance=0.7)
    memory.add_memory(npc_id, "Rain poured on the empty streets.", importance=0.5)

    results = memory.search_memories(npc_id, "lights and city", n_results=2)
    assert len(results) <= 2
    assert all(isinstance(r, MemoryEntry) for r in results)


def test_search_empty_collection(memory):
    results = memory.search_memories("empty_npc", "anything")
    assert results == []


def test_search_distance_populated(memory):
    npc_id = "dist_npc"
    memory.add_memory(npc_id, "Hello world.")
    results = memory.search_memories(npc_id, "Hello", n_results=1)
    assert results[0].distance is not None


# ---------------------------------------------------------------------------
# Recent memories
# ---------------------------------------------------------------------------

def test_get_recent_memories_empty(memory):
    results = memory.get_recent_memories("nobody", limit=5)
    assert results == []


def test_get_recent_memories_returns_entries(memory):
    npc_id = "recent_npc"
    memory.add_memory(npc_id, "First memory.")
    memory.add_memory(npc_id, "Second memory.")
    results = memory.get_recent_memories(npc_id, limit=10)
    assert len(results) == 2
    # Should be sorted newest first.
    assert results[0].timestamp >= results[-1].timestamp


# ---------------------------------------------------------------------------
# Delete
# ---------------------------------------------------------------------------

def test_delete_memory(memory):
    npc_id = "del_npc"
    mid = memory.add_memory(npc_id, "Temporary memory.")
    memory.delete_memory(npc_id, mid)
    col = memory._get_or_create_collection(npc_id)
    assert col.count() == 0


def test_clear_memories(memory):
    npc_id = "clear_npc"
    memory.add_memory(npc_id, "Memory A.")
    memory.add_memory(npc_id, "Memory B.")
    memory.clear_memories(npc_id)
    # After clear, collection is fresh.
    col = memory._get_or_create_collection(npc_id)
    assert col.count() == 0


# ---------------------------------------------------------------------------
# Memory metadata
# ---------------------------------------------------------------------------

def test_memory_entry_fields(memory):
    npc_id = "meta_npc"
    memory.add_memory(npc_id, "Test content.", memory_type="observation", importance=0.9)
    results = memory.get_recent_memories(npc_id, limit=1)
    assert len(results) == 1
    entry = results[0]
    assert entry.npc_id == npc_id
    assert entry.text == "Test content."
    assert entry.memory_type == "observation"
    assert entry.importance == pytest.approx(0.9)


def test_multiple_npcs_isolated(memory):
    """Each NPC's memories are stored in separate collections."""
    memory.add_memory("npc_a", "NPC A memory.")
    memory.add_memory("npc_b", "NPC B memory.")

    a_mems = memory.get_recent_memories("npc_a", limit=10)
    b_mems = memory.get_recent_memories("npc_b", limit=10)

    assert len(a_mems) == 1
    assert len(b_mems) == 1
    assert a_mems[0].text == "NPC A memory."
    assert b_mems[0].text == "NPC B memory."
