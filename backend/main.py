"""
Backend Entry Point

Starts the async event-driven engine, WebSocket server, and all NPC agents.

Usage::

    python -m backend.main

Configuration via environment variables (or .env file):
    LLM_API_KEY      — LLM API key
    LLM_BASE_URL     — LLM API base URL
    LLM_MODEL        — model name
    WS_HOST          — WebSocket host (default: localhost)
    WS_PORT          — WebSocket port (default: 8765)
    CHROMA_DIR       — ChromaDB persist directory (default: ./chroma_db)
"""

from __future__ import annotations

import asyncio
import logging
import os
import signal
import sys

# Load .env if present.
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

from .engine.event_bus import EventBus
from .engine.websocket_server import WebSocketServer
from .memory.vector_memory import VectorMemory
from .llm.client import LLMClient
from .agents.agent_manager import AgentManager

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)
logger = logging.getLogger(__name__)


async def main() -> None:
    # ----------------------------------------------------------------
    # Bootstrap core components
    # ----------------------------------------------------------------
    event_bus = EventBus()

    ws_host = os.getenv("WS_HOST", "localhost")
    ws_port = int(os.getenv("WS_PORT", "8765"))
    chroma_dir = os.getenv("CHROMA_DIR", "./chroma_db")

    ws_server = WebSocketServer(event_bus, host=ws_host, port=ws_port)
    memory = VectorMemory(persist_directory=chroma_dir)
    llm_client = LLMClient()
    agent_manager = AgentManager(event_bus, memory, llm_client)

    # ----------------------------------------------------------------
    # Graceful shutdown
    # ----------------------------------------------------------------
    stop_event = asyncio.Event()

    def _handle_signal(*_):
        logger.info("Shutdown signal received")
        stop_event.set()

    loop = asyncio.get_running_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        try:
            loop.add_signal_handler(sig, _handle_signal)
        except NotImplementedError:
            # Windows does not support add_signal_handler for all signals.
            pass

    # ----------------------------------------------------------------
    # Start everything
    # ----------------------------------------------------------------
    logger.info("Starting AI Multi-Agent Desktop Companion System …")
    await agent_manager.start(spawn_defaults=True)

    ws_task = asyncio.create_task(ws_server.start(), name="ws-server")

    logger.info(
        "System ready — WebSocket: ws://%s:%d | Agents: %d",
        ws_host,
        ws_port,
        len(agent_manager._agents),
    )

    # Wait for shutdown signal.
    await stop_event.wait()

    # ----------------------------------------------------------------
    # Cleanup
    # ----------------------------------------------------------------
    logger.info("Shutting down …")
    ws_task.cancel()
    await agent_manager.stop()
    await ws_server.stop()
    logger.info("Bye.")


if __name__ == "__main__":
    asyncio.run(main())
