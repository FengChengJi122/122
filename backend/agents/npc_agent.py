"""
NPCAgent — the core of each AI-driven character.

An NPCAgent combines:
- FSM for behaviour states
- VectorMemory for long-term recall
- LLMClient for language generation
- Function Calling for autonomous action execution
- EventBus integration for loose coupling

Concurrency: each agent runs its own asyncio task and can process messages
in parallel with other agents.
"""

from __future__ import annotations

import asyncio
import json
import logging
import time
from typing import Any, Dict, List, Optional

from ..engine.event_bus import EventBus, Event
from ..memory.vector_memory import VectorMemory
from ..llm.client import LLMClient
from ..llm.function_calling import TOOLS, execute_tool_call
from .fsm import FSM, NPCState

logger = logging.getLogger(__name__)


class NPCAgent:
    """
    A single AI-driven NPC agent.

    :param npc_id:       Unique identifier (slug-friendly, e.g. ``"aria"``).
    :param name:         Display name shown in the UI.
    :param personality:  One-paragraph backstory/personality for the system prompt.
    :param position:     Initial ``{"x": 0–100, "y": 0–100}`` on the canvas.
    :param event_bus:    Shared event bus instance.
    :param memory:       Shared vector memory store.
    :param llm_client:   Configured LLM client.
    :param mood:         Initial emotional state.
    :param avatar:       Avatar/sprite name used by the frontend.
    """

    def __init__(
        self,
        npc_id: str,
        name: str,
        personality: str,
        position: Dict[str, float],
        event_bus: EventBus,
        memory: VectorMemory,
        llm_client: LLMClient,
        mood: str = "neutral",
        avatar: str = "default",
    ) -> None:
        self.npc_id = npc_id
        self.name = name
        self.personality = personality
        self.position = dict(position)
        self.event_bus = event_bus
        self.memory = memory
        self.llm = llm_client
        self.mood = mood
        self.avatar = avatar

        self.fsm = FSM(npc_id=npc_id)
        self._message_queue: asyncio.Queue[Dict[str, Any]] = asyncio.Queue()
        self._conversation_history: List[Dict[str, str]] = []
        self._running = False
        self._task: Optional[asyncio.Task] = None

        # Register FSM hooks to emit events.
        self.fsm.register_enter(NPCState.THINKING, self._on_enter_thinking)
        self.fsm.register_enter(NPCState.RESPONDING, self._on_enter_responding)
        self.fsm.register_enter(NPCState.ACTING, self._on_enter_acting)

        # Subscribe to inbound events destined for this NPC.
        self.event_bus.subscribe(f"npc:{npc_id}:message", self._on_message_event)
        self.event_bus.subscribe("user:message", self._on_user_message_event)

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    async def start(self) -> None:
        """Start the agent's processing loop."""
        self._running = True
        self._task = asyncio.create_task(self._run(), name=f"npc-{self.npc_id}")
        await self.event_bus.publish(
            Event(
                type="agent:spawned",
                data=self._status_dict(),
                source=self.npc_id,
            )
        )
        logger.info("[%s] Agent started", self.npc_id)

    async def stop(self) -> None:
        """Stop the agent gracefully."""
        self._running = False
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
        await self.event_bus.publish(
            Event(type="agent:removed", data={"npc_id": self.npc_id}, source=self.npc_id)
        )
        logger.info("[%s] Agent stopped", self.npc_id)

    # ------------------------------------------------------------------
    # Processing loop
    # ------------------------------------------------------------------

    async def _run(self) -> None:
        while self._running:
            try:
                msg = await asyncio.wait_for(self._message_queue.get(), timeout=1.0)
                await self._process(msg)
            except asyncio.TimeoutError:
                continue
            except asyncio.CancelledError:
                break
            except Exception as exc:  # noqa: BLE001
                logger.exception("[%s] Unhandled error in agent loop: %s", self.npc_id, exc)
                await self.fsm.force_transition(NPCState.IDLE)

    async def _process(self, msg: Dict[str, Any]) -> None:
        """Full think → respond → act cycle for a single message."""
        user_text: str = msg.get("text", "")
        sender: str = msg.get("sender", "user")

        # IDLE → LISTENING
        if not self.fsm.can_transition_to(NPCState.LISTENING):
            logger.warning("[%s] Busy, dropping message: %s", self.npc_id, user_text[:60])
            return
        await self.fsm.transition(NPCState.LISTENING)

        # Store the incoming message in memory.
        self.memory.add_memory(
            self.npc_id,
            text=f"[{sender}]: {user_text}",
            memory_type="dialogue",
            importance=0.7,
        )

        # Build LLM messages.
        messages = self._build_messages(user_text, sender)

        # LISTENING → THINKING
        await self.fsm.transition(NPCState.THINKING)

        # Run the LLM (with possible tool-call loop).
        await self._llm_loop(messages)

    async def _llm_loop(self, messages: List[Dict[str, str]]) -> None:
        """
        Iterative LLM + function-call loop.

        1. Call LLM.
        2. If tool_calls → execute tools → append results → repeat.
        3. When finish_reason == "stop" → emit response.
        """
        max_iterations = 5
        for iteration in range(max_iterations):
            try:
                result = await self.llm.chat(messages, tools=TOOLS)
            except Exception as exc:  # noqa: BLE001
                logger.error("[%s] LLM call failed: %s", self.npc_id, exc)
                await self.fsm.force_transition(NPCState.IDLE)
                return

            # Append assistant message to history.
            assistant_msg: Dict[str, Any] = {"role": "assistant"}
            if result["content"]:
                assistant_msg["content"] = result["content"]
            if result["tool_calls"]:
                assistant_msg["tool_calls"] = [
                    {
                        "id": tc["id"],
                        "type": "function",
                        "function": {
                            "name": tc["function"],
                            "arguments": json.dumps(tc["arguments"]),
                        },
                    }
                    for tc in result["tool_calls"]
                ]
            messages.append(assistant_msg)

            if result["finish_reason"] == "tool_calls" and result["tool_calls"]:
                # THINKING → ACTING
                if self.fsm.can_transition_to(NPCState.ACTING):
                    await self.fsm.transition(NPCState.ACTING)

                for tc in result["tool_calls"]:
                    tool_result = await self._execute_tool(tc)
                    messages.append(
                        {
                            "role": "tool",
                            "tool_call_id": tc["id"],
                            "content": json.dumps(tool_result),
                        }
                    )
                # ACTING → THINKING for next iteration
                if self.fsm.can_transition_to(NPCState.THINKING):
                    await self.fsm.transition(NPCState.THINKING)
                elif self.fsm.can_transition_to(NPCState.RESPONDING):
                    await self.fsm.transition(NPCState.RESPONDING)
                continue

            # Finished — emit response.
            if self.fsm.can_transition_to(NPCState.RESPONDING):
                await self.fsm.transition(NPCState.RESPONDING)
            response_text = result.get("content") or ""
            await self._emit_response(response_text)
            return

        logger.warning("[%s] LLM loop exceeded max iterations", self.npc_id)
        await self.fsm.force_transition(NPCState.IDLE)

    async def _execute_tool(self, tc: Dict[str, Any]) -> Dict[str, Any]:
        """Execute a single tool call and emit a frontend action event."""
        fn = tc["function"]
        args = tc["arguments"]

        logger.info("[%s] Executing tool: %s(%s)", self.npc_id, fn, args)
        result = await execute_tool_call(
            npc_id=self.npc_id,
            function_name=fn,
            arguments=args,
            memory_manager=self.memory,
        )

        # Handle side-effects.
        if fn == "move_to":
            self.position = {"x": args.get("x", 50), "y": args.get("y", 50)}
            await self.fsm.force_transition(NPCState.MOVING)
            await asyncio.sleep(args.get("duration_ms", 800) / 1000)
            await self.fsm.force_transition(NPCState.ACTING)

        if fn == "update_mood":
            self.mood = args.get("mood", self.mood)
            await self.event_bus.publish(
                Event(
                    type="npc:mood_changed",
                    data={"npc_id": self.npc_id, "mood": self.mood},
                    source=self.npc_id,
                )
            )

        if fn == "send_message_to_npc":
            target = args.get("target_npc_id")
            message = args.get("message", "")
            if target:
                await self.event_bus.publish(
                    Event(
                        type=f"npc:{target}:message",
                        data={"text": message, "sender": self.npc_id},
                        source=self.npc_id,
                    )
                )

        # Emit action event to frontend.
        await self.event_bus.publish(
            Event(
                type="npc:action",
                data={
                    "npc_id": self.npc_id,
                    "action": fn,
                    "args": args,
                    "result": result,
                },
                source=self.npc_id,
            )
        )
        return result

    async def _emit_response(self, text: str) -> None:
        """Store response in memory and broadcast to frontend."""
        if text:
            self.memory.add_memory(
                self.npc_id,
                text=f"[{self.name}]: {text}",
                memory_type="dialogue",
                importance=0.6,
            )
            self._conversation_history.append(
                {"role": "assistant", "content": text}
            )

        await self.event_bus.publish(
            Event(
                type="npc:response",
                data={
                    "npc_id": self.npc_id,
                    "name": self.name,
                    "text": text,
                    "mood": self.mood,
                    "position": self.position,
                    "state": self.fsm.state.value,
                },
                source=self.npc_id,
            )
        )

        # Transition back to IDLE.
        if self.fsm.can_transition_to(NPCState.IDLE):
            await self.fsm.transition(NPCState.IDLE)
        else:
            await self.fsm.force_transition(NPCState.IDLE)

    # ------------------------------------------------------------------
    # Message building
    # ------------------------------------------------------------------

    def _build_messages(self, user_text: str, sender: str) -> List[Dict[str, str]]:
        """Construct the LLM message list with memory context."""
        system_prompt = self._build_system_prompt()

        # Fetch relevant memories.
        memories = self.memory.search_memories(self.npc_id, user_text, n_results=5)
        memory_context = ""
        if memories:
            snippets = [f"- {m.text}" for m in memories[:3]]
            memory_context = "\n\nRelevant memories:\n" + "\n".join(snippets)

        system_prompt += memory_context

        messages: List[Dict[str, str]] = [{"role": "system", "content": system_prompt}]

        # Include last N turns from conversation history.
        for turn in self._conversation_history[-10:]:
            messages.append(turn)

        messages.append({"role": "user", "content": f"[{sender}]: {user_text}"})
        self._conversation_history.append(
            {"role": "user", "content": f"[{sender}]: {user_text}"}
        )
        return messages

    def _build_system_prompt(self) -> str:
        return (
            f"You are {self.name}, an AI companion NPC in a cyberpunk desktop environment.\n"
            f"Personality: {self.personality}\n"
            f"Current mood: {self.mood}\n"
            f"Current position: x={self.position['x']:.0f}%, y={self.position['y']:.0f}%\n\n"
            "You can use tools to move, play animations, communicate with other NPCs, "
            "recall memories, change your mood, or trigger narrative events. "
            "Always respond in character. Keep replies concise (1-3 sentences) unless "
            "the situation demands more detail."
        )

    # ------------------------------------------------------------------
    # FSM hooks
    # ------------------------------------------------------------------

    async def _on_enter_thinking(self, fsm: FSM, prev_state: str) -> None:
        await self.event_bus.publish(
            Event(
                type="npc:state_changed",
                data={"npc_id": self.npc_id, "state": NPCState.THINKING.value},
                source=self.npc_id,
            )
        )

    async def _on_enter_responding(self, fsm: FSM, prev_state: str) -> None:
        await self.event_bus.publish(
            Event(
                type="npc:state_changed",
                data={"npc_id": self.npc_id, "state": NPCState.RESPONDING.value},
                source=self.npc_id,
            )
        )

    async def _on_enter_acting(self, fsm: FSM, prev_state: str) -> None:
        await self.event_bus.publish(
            Event(
                type="npc:state_changed",
                data={"npc_id": self.npc_id, "state": NPCState.ACTING.value},
                source=self.npc_id,
            )
        )

    # ------------------------------------------------------------------
    # Event handlers
    # ------------------------------------------------------------------

    async def _on_message_event(self, event: Event) -> None:
        """Handle a direct NPC-to-NPC message."""
        data = event.data or {}
        await self._message_queue.put(
            {"text": data.get("text", ""), "sender": data.get("sender", "npc")}
        )

    async def _on_user_message_event(self, event: Event) -> None:
        """Handle a broadcast user message (all NPCs see it)."""
        data = event.data or {}
        target = data.get("target_npc_id")
        # Only process if addressed to this NPC or broadcast (no target).
        if target is None or target == self.npc_id:
            await self._message_queue.put(
                {"text": data.get("text", ""), "sender": data.get("sender", "user")}
            )

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _status_dict(self) -> Dict[str, Any]:
        return {
            "npc_id": self.npc_id,
            "name": self.name,
            "avatar": self.avatar,
            "mood": self.mood,
            "position": self.position,
            "state": self.fsm.state.value,
        }

    async def get_status(self) -> Dict[str, Any]:
        return self._status_dict()

    def __repr__(self) -> str:
        return f"<NPCAgent id={self.npc_id!r} name={self.name!r} state={self.fsm.state.value}>"
