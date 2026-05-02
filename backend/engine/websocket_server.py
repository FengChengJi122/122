"""
WebSocket Server

Bridges the Python backend with the Electron/Web frontend.  Every connected
client is tracked; messages arriving from the frontend are forwarded to the
EventBus, and events emitted by agents are broadcast back to all clients.

Message protocol (JSON):
    Frontend → Backend:  { "type": "<event_type>", "data": { ... } }
    Backend  → Frontend: { "type": "<event_type>", "data": { ... } }
"""

from __future__ import annotations

import asyncio
import json
import logging
from typing import Any, Dict, Optional

import websockets
from websockets import ServerConnection

from .event_bus import EventBus, Event

logger = logging.getLogger(__name__)


class WebSocketServer:
    """
    Manages all WebSocket connections and routes messages through the EventBus.
    """

    def __init__(self, event_bus: EventBus, host: str = "localhost", port: int = 8765) -> None:
        self.event_bus = event_bus
        self.host = host
        self.port = port
        # client_id → websocket
        self._clients: Dict[str, ServerConnection] = {}
        self._client_counter = 0
        self._server: Optional[websockets.Server] = None

        # Forward outbound events back to the frontend.
        for event_type in (
            "npc:state_changed",
            "npc:response",
            "npc:action",
            "npc:mood_changed",
            "agent:spawned",
            "agent:removed",
            "system:status",
        ):
            self.event_bus.subscribe(event_type, self._relay_to_frontend)

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    async def start(self) -> None:
        """Start the WebSocket server (runs until cancelled)."""
        self._server = await websockets.serve(
            self._handle_client,
            self.host,
            self.port,
            ping_interval=20,
            ping_timeout=20,
        )
        logger.info("WebSocket server listening on ws://%s:%d", self.host, self.port)
        await self._server.wait_closed()

    async def stop(self) -> None:
        """Gracefully shut down the server."""
        if self._server:
            self._server.close()
            await self._server.wait_closed()
            logger.info("WebSocket server stopped")

    # ------------------------------------------------------------------
    # Connection handling
    # ------------------------------------------------------------------

    async def _handle_client(self, websocket: ServerConnection) -> None:
        self._client_counter += 1
        client_id = f"client_{self._client_counter}"
        self._clients[client_id] = websocket
        logger.info("Client connected: %s (total=%d)", client_id, len(self._clients))

        # Notify the system a new frontend client connected.
        await self.event_bus.publish(
            Event(type="ws:client_connected", data={"client_id": client_id})
        )

        try:
            async for raw in websocket:
                await self._handle_message(client_id, raw)
        except websockets.exceptions.ConnectionClosedOK:
            pass
        except (websockets.exceptions.ConnectionClosedError, websockets.exceptions.ConnectionClosed) as exc:
            logger.warning("Client %s disconnected with error: %s", client_id, exc)
        finally:
            del self._clients[client_id]
            logger.info("Client disconnected: %s (total=%d)", client_id, len(self._clients))
            await self.event_bus.publish(
                Event(type="ws:client_disconnected", data={"client_id": client_id})
            )

    async def _handle_message(self, client_id: str, raw: str) -> None:
        try:
            msg = json.loads(raw)
            event_type = msg.get("type", "unknown")
            data = msg.get("data", {})
            data["_client_id"] = client_id
            await self.event_bus.publish(Event(type=event_type, data=data, source=client_id))
        except (json.JSONDecodeError, KeyError) as exc:
            logger.error("Malformed message from %s: %s — %s", client_id, raw[:200], exc)

    # ------------------------------------------------------------------
    # Sending
    # ------------------------------------------------------------------

    async def broadcast(self, event_type: str, data: dict) -> None:
        """Send *data* to every connected frontend client."""
        if not self._clients:
            return
        payload = json.dumps({"type": event_type, "data": data})
        await asyncio.gather(
            *[ws.send(payload) for ws in self._clients.values()],
            return_exceptions=True,
        )

    async def send_to_client(self, client_id: str, event_type: str, data: dict) -> None:
        """Send *data* to a specific frontend client."""
        ws = self._clients.get(client_id)
        if ws is None:
            logger.warning("send_to_client: unknown client %s", client_id)
            return
        payload = json.dumps({"type": event_type, "data": data})
        await ws.send(payload)

    # ------------------------------------------------------------------
    # EventBus relay
    # ------------------------------------------------------------------

    async def _relay_to_frontend(self, event: Event) -> None:
        """Relay a backend Event to all connected frontend clients."""
        await self.broadcast(
            event.type,
            event.data if isinstance(event.data, dict) else {"payload": event.data},
        )

    @property
    def connected_count(self) -> int:
        return len(self._clients)
