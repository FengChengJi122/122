"""
Function Calling Definitions

These are the tools the LLM can invoke to make NPCs take actions in the
desktop environment.  Each tool definition follows the OpenAI function-calling
schema and is accompanied by an async Python implementation.

Available tools
---------------
move_to                 — Move an NPC to screen coordinates
play_animation          — Trigger a named animation on an NPC
send_message_to_npc     — Have one NPC send a message to another
search_memory           — Query the NPC's vector memory
update_mood             — Change the NPC's emotional state
execute_narrative_task  — Trigger a named narrative event
"""

from __future__ import annotations

import logging
from typing import Any, Callable, Coroutine, Dict, List

logger = logging.getLogger(__name__)

# Type alias for async tool implementations.
ToolImpl = Callable[..., Coroutine[Any, Any, Dict[str, Any]]]

# -------------------------------------------------------------------
# Tool definitions (OpenAI function-calling schema)
# -------------------------------------------------------------------

TOOLS: List[Dict[str, Any]] = [
    {
        "type": "function",
        "function": {
            "name": "move_to",
            "description": (
                "Move the NPC to a specific position on the desktop canvas. "
                "Coordinates are percentages of viewport width/height (0–100)."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "x": {"type": "number", "description": "Horizontal position 0–100"},
                    "y": {"type": "number", "description": "Vertical position 0–100"},
                    "duration_ms": {
                        "type": "integer",
                        "description": "Animation duration in milliseconds",
                        "default": 800,
                    },
                },
                "required": ["x", "y"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "play_animation",
            "description": "Play a named animation clip on the NPC sprite.",
            "parameters": {
                "type": "object",
                "properties": {
                    "animation": {
                        "type": "string",
                        "enum": [
                            "idle",
                            "wave",
                            "think",
                            "happy",
                            "sad",
                            "angry",
                            "excited",
                            "sleep",
                            "work",
                            "dance",
                        ],
                        "description": "Name of the animation clip",
                    },
                    "loop": {
                        "type": "boolean",
                        "description": "Whether the animation should loop",
                        "default": False,
                    },
                },
                "required": ["animation"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "send_message_to_npc",
            "description": "Send a direct message from this NPC to another NPC.",
            "parameters": {
                "type": "object",
                "properties": {
                    "target_npc_id": {
                        "type": "string",
                        "description": "ID of the target NPC",
                    },
                    "message": {
                        "type": "string",
                        "description": "The message content",
                    },
                },
                "required": ["target_npc_id", "message"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "search_memory",
            "description": (
                "Search the NPC's long-term vector memory for relevant past experiences."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "Natural-language query to search for",
                    },
                    "n_results": {
                        "type": "integer",
                        "description": "Number of results to return",
                        "default": 5,
                    },
                },
                "required": ["query"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "update_mood",
            "description": "Update the NPC's current emotional state / mood.",
            "parameters": {
                "type": "object",
                "properties": {
                    "mood": {
                        "type": "string",
                        "enum": [
                            "neutral",
                            "happy",
                            "sad",
                            "angry",
                            "curious",
                            "excited",
                            "bored",
                            "anxious",
                            "focused",
                        ],
                        "description": "The new mood",
                    },
                    "intensity": {
                        "type": "number",
                        "description": "Intensity 0.0–1.0",
                        "default": 0.5,
                    },
                },
                "required": ["mood"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "execute_narrative_task",
            "description": (
                "Trigger a narrative task or quest event by ID.  "
                "Use this to advance the story or unlock new interactions."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "task_id": {
                        "type": "string",
                        "description": "Unique identifier of the narrative task",
                    },
                    "payload": {
                        "type": "object",
                        "description": "Optional extra data for the task",
                        "default": {},
                    },
                },
                "required": ["task_id"],
            },
        },
    },
]

# -------------------------------------------------------------------
# Tool implementations
# -------------------------------------------------------------------


async def _impl_move_to(
    npc_id: str, x: float, y: float, duration_ms: int = 800
) -> Dict[str, Any]:
    logger.info("[%s] move_to(x=%.1f, y=%.1f, dur=%dms)", npc_id, x, y, duration_ms)
    return {"status": "ok", "action": "move_to", "x": x, "y": y, "duration_ms": duration_ms}


async def _impl_play_animation(
    npc_id: str, animation: str, loop: bool = False
) -> Dict[str, Any]:
    logger.info("[%s] play_animation(%s, loop=%s)", npc_id, animation, loop)
    return {"status": "ok", "action": "play_animation", "animation": animation, "loop": loop}


async def _impl_send_message_to_npc(
    npc_id: str, target_npc_id: str, message: str
) -> Dict[str, Any]:
    logger.info("[%s] → [%s]: %s", npc_id, target_npc_id, message[:80])
    return {
        "status": "ok",
        "action": "send_message_to_npc",
        "target": target_npc_id,
        "message": message,
    }


async def _impl_search_memory(
    npc_id: str, query: str, n_results: int = 5, memory_manager=None
) -> Dict[str, Any]:
    if memory_manager is None:
        return {"status": "ok", "memories": [], "note": "no memory manager"}
    results = memory_manager.search_memories(npc_id, query, n_results)
    return {
        "status": "ok",
        "action": "search_memory",
        "memories": [
            {"text": m.text, "type": m.memory_type, "importance": m.importance}
            for m in results
        ],
    }


async def _impl_update_mood(
    npc_id: str, mood: str, intensity: float = 0.5
) -> Dict[str, Any]:
    logger.info("[%s] mood → %s (intensity=%.2f)", npc_id, mood, intensity)
    return {"status": "ok", "action": "update_mood", "mood": mood, "intensity": intensity}


async def _impl_execute_narrative_task(
    npc_id: str, task_id: str, payload: Optional[Dict[str, Any]] = None
) -> Dict[str, Any]:
    logger.info("[%s] execute_narrative_task(%s)", npc_id, task_id)
    return {
        "status": "ok",
        "action": "execute_narrative_task",
        "task_id": task_id,
        "payload": payload or {},
    }


_IMPLEMENTATIONS: Dict[str, ToolImpl] = {
    "move_to": _impl_move_to,
    "play_animation": _impl_play_animation,
    "send_message_to_npc": _impl_send_message_to_npc,
    "search_memory": _impl_search_memory,
    "update_mood": _impl_update_mood,
    "execute_narrative_task": _impl_execute_narrative_task,
}


async def execute_tool_call(
    npc_id: str,
    function_name: str,
    arguments: Dict[str, Any],
    memory_manager=None,
) -> Dict[str, Any]:
    """
    Dispatch a tool call from the LLM to the corresponding Python implementation.

    :param npc_id:        The NPC that issued this function call.
    :param function_name: Name of the tool/function to invoke.
    :param arguments:     Parsed JSON arguments dict.
    :param memory_manager: Optional :class:`~memory.VectorMemory` instance.
    :returns:             Result dict that will be appended to the message history.
    """
    impl = _IMPLEMENTATIONS.get(function_name)
    if impl is None:
        logger.error("Unknown tool: %s", function_name)
        return {"status": "error", "message": f"Unknown tool: {function_name}"}

    try:
        if function_name == "search_memory":
            return await impl(npc_id, memory_manager=memory_manager, **arguments)
        return await impl(npc_id, **arguments)
    except Exception as exc:  # noqa: BLE001
        logger.exception("Tool %s failed: %s", function_name, exc)
        return {"status": "error", "message": str(exc)}
