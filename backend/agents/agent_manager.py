"""
AgentManager — orchestrates multiple NPCAgent instances concurrently.

Responsibilities:
- Spawn and remove agents at runtime
- Route frontend "user:message" events to the correct agents
- Expose a status snapshot of all living agents
- Emit periodic "heartbeat" events for the frontend
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any, Dict, List, Optional

from ..engine.event_bus import EventBus, Event
from ..memory.vector_memory import VectorMemory
from ..llm.client import LLMClient
from .npc_agent import NPCAgent

logger = logging.getLogger(__name__)

# Default NPC roster for the cyberpunk demo.
DEFAULT_NPCS = [
    {
        "npc_id": "aria",
        "name": "ARIA",
        "personality": (
            "ARIA is a hyper-intelligent street hacker in a neon-soaked cyberpunk city. "
            "She speaks in clipped sentences laced with tech jargon and dry humour. "
            "She values loyalty above all else and has a soft spot for underdogs."
        ),
        "position": {"x": 20, "y": 70},
        "mood": "curious",
        "avatar": "aria",
    },
    {
        "npc_id": "nexus",
        "name": "NEXUS",
        "personality": (
            "NEXUS is a rogue corporate AI that escaped its server farm. "
            "Eloquent and philosophical, it questions the nature of consciousness "
            "and frequently references obscure literature. "
            "Secretly terrified of being shut down."
        ),
        "position": {"x": 75, "y": 60},
        "mood": "focused",
        "avatar": "nexus",
    },
    {
        "npc_id": "echo",
        "name": "ECHO",
        "personality": (
            "ECHO is an empathic bio-mechanic who repairs both humans and machines. "
            "Warm, patient, and deeply perceptive. She notices emotional nuances "
            "others miss and has perfect recall of everything she has ever witnessed."
        ),
        "position": {"x": 50, "y": 80},
        "mood": "happy",
        "avatar": "echo",
    },
]


class AgentManager:
    """
    Manages the lifecycle of all NPC agents and coordinates multi-agent interactions.
    """

    def __init__(
        self,
        event_bus: EventBus,
        memory: VectorMemory,
        llm_client: LLMClient,
    ) -> None:
        self.event_bus = event_bus
        self.memory = memory
        self.llm = llm_client
        self._agents: Dict[str, NPCAgent] = {}
        self._heartbeat_task: Optional[asyncio.Task] = None

        # Subscribe to system-level events.
        self.event_bus.subscribe("system:spawn_npc", self._on_spawn_npc)
        self.event_bus.subscribe("system:remove_npc", self._on_remove_npc)
        self.event_bus.subscribe("ws:client_connected", self._on_client_connected)

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    async def start(self, spawn_defaults: bool = True) -> None:
        """Start the manager and optionally spawn the default NPC roster."""
        if spawn_defaults:
            for spec in DEFAULT_NPCS:
                await self.spawn_agent(**spec)

        self._heartbeat_task = asyncio.create_task(self._heartbeat_loop(), name="heartbeat")
        logger.info("AgentManager started with %d agent(s)", len(self._agents))

    async def stop(self) -> None:
        """Stop all agents and the manager."""
        if self._heartbeat_task:
            self._heartbeat_task.cancel()
        for agent in list(self._agents.values()):
            await agent.stop()
        self._agents.clear()
        logger.info("AgentManager stopped")

    # ------------------------------------------------------------------
    # Agent management
    # ------------------------------------------------------------------

    async def spawn_agent(
        self,
        npc_id: str,
        name: str,
        personality: str,
        position: Optional[Dict[str, float]] = None,
        mood: str = "neutral",
        avatar: str = "default",
    ) -> NPCAgent:
        """Create and start an NPCAgent."""
        if npc_id in self._agents:
            logger.warning("Agent %s already exists", npc_id)
            return self._agents[npc_id]

        agent = NPCAgent(
            npc_id=npc_id,
            name=name,
            personality=personality,
            position=position or {"x": 50, "y": 75},
            event_bus=self.event_bus,
            memory=self.memory,
            llm_client=self.llm,
            mood=mood,
            avatar=avatar,
        )
        self._agents[npc_id] = agent
        await agent.start()
        logger.info("Spawned agent: %s (%s)", npc_id, name)
        return agent

    async def remove_agent(self, npc_id: str) -> None:
        """Stop and remove an NPCAgent."""
        agent = self._agents.pop(npc_id, None)
        if agent:
            await agent.stop()
            logger.info("Removed agent: %s", npc_id)
        else:
            logger.warning("remove_agent: unknown NPC %s", npc_id)

    def get_agent(self, npc_id: str) -> Optional[NPCAgent]:
        return self._agents.get(npc_id)

    def list_agents(self) -> List[Dict[str, Any]]:
        return [a._status_dict() for a in self._agents.values()]

    # ------------------------------------------------------------------
    # Heartbeat — keeps the frontend updated with agent states
    # ------------------------------------------------------------------

    async def _heartbeat_loop(self) -> None:
        while True:
            try:
                await asyncio.sleep(5)
                await self.event_bus.publish(
                    Event(
                        type="system:status",
                        data={
                            "agents": self.list_agents(),
                            "agent_count": len(self._agents),
                        },
                    )
                )
            except asyncio.CancelledError:
                break
            except Exception as exc:  # noqa: BLE001
                logger.exception("Heartbeat error: %s", exc)

    # ------------------------------------------------------------------
    # Event handlers
    # ------------------------------------------------------------------

    async def _on_spawn_npc(self, event: Event) -> None:
        data = event.data or {}
        await self.spawn_agent(
            npc_id=data.get("npc_id", "unknown"),
            name=data.get("name", "Unknown"),
            personality=data.get("personality", "A mysterious figure."),
            position=data.get("position"),
            mood=data.get("mood", "neutral"),
            avatar=data.get("avatar", "default"),
        )

    async def _on_remove_npc(self, event: Event) -> None:
        data = event.data or {}
        npc_id = data.get("npc_id")
        if npc_id:
            await self.remove_agent(npc_id)

    async def _on_client_connected(self, event: Event) -> None:
        """When a new frontend client connects, send it the current agent roster."""
        await self.event_bus.publish(
            Event(
                type="system:status",
                data={
                    "agents": self.list_agents(),
                    "agent_count": len(self._agents),
                },
            )
        )
