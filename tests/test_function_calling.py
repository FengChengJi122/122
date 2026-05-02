"""
Unit tests for Function Calling tool definitions and dispatch.
"""

import asyncio
import pytest

import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from backend.llm.function_calling import TOOLS, execute_tool_call


# ---------------------------------------------------------------------------
# Tool definition structure
# ---------------------------------------------------------------------------

def test_tools_is_list():
    assert isinstance(TOOLS, list)
    assert len(TOOLS) > 0


def test_all_tools_have_required_keys():
    for tool in TOOLS:
        assert tool["type"] == "function"
        fn = tool["function"]
        assert "name" in fn
        assert "description" in fn
        assert "parameters" in fn


def test_expected_tool_names():
    names = {t["function"]["name"] for t in TOOLS}
    expected = {
        "move_to",
        "play_animation",
        "send_message_to_npc",
        "search_memory",
        "update_mood",
        "execute_narrative_task",
    }
    assert expected.issubset(names)


# ---------------------------------------------------------------------------
# Tool execution
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_move_to():
    result = await execute_tool_call(
        npc_id="aria",
        function_name="move_to",
        arguments={"x": 30.0, "y": 60.0, "duration_ms": 500},
    )
    assert result["status"] == "ok"
    assert result["action"] == "move_to"
    assert result["x"] == 30.0
    assert result["y"] == 60.0


@pytest.mark.asyncio
async def test_play_animation():
    result = await execute_tool_call(
        npc_id="aria",
        function_name="play_animation",
        arguments={"animation": "wave", "loop": False},
    )
    assert result["status"] == "ok"
    assert result["animation"] == "wave"


@pytest.mark.asyncio
async def test_update_mood():
    result = await execute_tool_call(
        npc_id="aria",
        function_name="update_mood",
        arguments={"mood": "happy", "intensity": 0.8},
    )
    assert result["status"] == "ok"
    assert result["mood"] == "happy"


@pytest.mark.asyncio
async def test_send_message_to_npc():
    result = await execute_tool_call(
        npc_id="aria",
        function_name="send_message_to_npc",
        arguments={"target_npc_id": "nexus", "message": "Hello!"},
    )
    assert result["status"] == "ok"
    assert result["target"] == "nexus"


@pytest.mark.asyncio
async def test_execute_narrative_task():
    result = await execute_tool_call(
        npc_id="aria",
        function_name="execute_narrative_task",
        arguments={"task_id": "quest_001", "payload": {"key": "value"}},
    )
    assert result["status"] == "ok"
    assert result["task_id"] == "quest_001"


@pytest.mark.asyncio
async def test_search_memory_without_manager():
    result = await execute_tool_call(
        npc_id="aria",
        function_name="search_memory",
        arguments={"query": "past events", "n_results": 3},
        memory_manager=None,
    )
    assert result["status"] == "ok"
    assert result["memories"] == []


@pytest.mark.asyncio
async def test_unknown_tool_returns_error():
    result = await execute_tool_call(
        npc_id="aria",
        function_name="nonexistent_tool",
        arguments={},
    )
    assert result["status"] == "error"
    assert "Unknown tool" in result["message"]
