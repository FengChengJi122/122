"""
Finite State Machine (FSM) for NPC Behaviour

States model the NPC's current activity.  Transitions are validated against
an explicit allow-list so the system can never enter an inconsistent state.

States
------
IDLE         → Waiting for interaction
LISTENING    → Processing incoming user / system message
THINKING     → Awaiting LLM response
RESPONDING   → Streaming / delivering response to frontend
ACTING       → Executing a function-call action
MOVING       → Physically relocating on the desktop canvas
INTERACTING  → In a dialogue with another NPC
"""

from __future__ import annotations

import asyncio
import logging
from enum import Enum, auto
from typing import Callable, Coroutine, Dict, List, Optional, Set, Tuple

logger = logging.getLogger(__name__)

Handler = Callable[["FSM", str], Coroutine | None]


class NPCState(str, Enum):
    IDLE = "idle"
    LISTENING = "listening"
    THINKING = "thinking"
    RESPONDING = "responding"
    ACTING = "acting"
    MOVING = "moving"
    INTERACTING = "interacting"


# fmt: off
# (from_state, to_state) — empty set means "any → X" is allowed.
VALID_TRANSITIONS: Set[Tuple[NPCState, NPCState]] = {
    (NPCState.IDLE,         NPCState.LISTENING),
    (NPCState.IDLE,         NPCState.MOVING),
    (NPCState.IDLE,         NPCState.INTERACTING),
    (NPCState.LISTENING,    NPCState.THINKING),
    (NPCState.LISTENING,    NPCState.IDLE),
    (NPCState.THINKING,     NPCState.RESPONDING),
    (NPCState.THINKING,     NPCState.ACTING),
    (NPCState.THINKING,     NPCState.IDLE),
    (NPCState.RESPONDING,   NPCState.IDLE),
    (NPCState.RESPONDING,   NPCState.ACTING),
    (NPCState.ACTING,       NPCState.IDLE),
    (NPCState.ACTING,       NPCState.RESPONDING),
    (NPCState.MOVING,       NPCState.IDLE),
    (NPCState.MOVING,       NPCState.INTERACTING),
    (NPCState.INTERACTING,  NPCState.IDLE),
    (NPCState.INTERACTING,  NPCState.THINKING),
}
# fmt: on


class FSMError(Exception):
    pass


class FSM:
    """
    Lightweight FSM with async enter/exit hooks.

    Example::

        fsm = FSM(npc_id="aria", initial=NPCState.IDLE)

        @fsm.on_enter(NPCState.THINKING)
        async def start_thinking(fsm, prev_state):
            print(f"{fsm.npc_id} started thinking (was {prev_state})")

        await fsm.transition(NPCState.LISTENING)
        await fsm.transition(NPCState.THINKING)
    """

    def __init__(self, npc_id: str, initial: NPCState = NPCState.IDLE) -> None:
        self.npc_id = npc_id
        self._state = initial
        self._enter_hooks: Dict[NPCState, List[Handler]] = {s: [] for s in NPCState}
        self._exit_hooks: Dict[NPCState, List[Handler]] = {s: [] for s in NPCState}
        self._history: List[NPCState] = [initial]

    # ------------------------------------------------------------------
    # State access
    # ------------------------------------------------------------------

    @property
    def state(self) -> NPCState:
        return self._state

    @property
    def history(self) -> List[NPCState]:
        return list(self._history)

    # ------------------------------------------------------------------
    # Transition
    # ------------------------------------------------------------------

    async def transition(self, new_state: NPCState) -> None:
        """
        Move the FSM to *new_state*, running exit/enter hooks.

        Raises :class:`FSMError` when the transition is not permitted.
        """
        if (self._state, new_state) not in VALID_TRANSITIONS:
            raise FSMError(
                f"[{self.npc_id}] Invalid transition: {self._state.value} → {new_state.value}"
            )

        old_state = self._state
        logger.debug("[%s] %s → %s", self.npc_id, old_state.value, new_state.value)

        # Run exit hooks for current state.
        for hook in self._exit_hooks.get(old_state, []):
            result = hook(self, new_state.value)
            if asyncio.iscoroutine(result):
                await result

        self._state = new_state
        self._history.append(new_state)

        # Run enter hooks for new state.
        for hook in self._enter_hooks.get(new_state, []):
            result = hook(self, old_state.value)
            if asyncio.iscoroutine(result):
                await result

    async def force_transition(self, new_state: NPCState) -> None:
        """Transition without validating the transition table (use sparingly)."""
        old_state = self._state
        self._state = new_state
        self._history.append(new_state)
        logger.warning("[%s] FORCED %s → %s", self.npc_id, old_state.value, new_state.value)

    # ------------------------------------------------------------------
    # Hook registration
    # ------------------------------------------------------------------

    def on_enter(self, state: NPCState) -> Callable[[Handler], Handler]:
        """Decorator to register an enter-hook for *state*."""
        def decorator(fn: Handler) -> Handler:
            self._enter_hooks[state].append(fn)
            return fn
        return decorator

    def on_exit(self, state: NPCState) -> Callable[[Handler], Handler]:
        """Decorator to register an exit-hook for *state*."""
        def decorator(fn: Handler) -> Handler:
            self._exit_hooks[state].append(fn)
            return fn
        return decorator

    def register_enter(self, state: NPCState, handler: Handler) -> None:
        self._enter_hooks[state].append(handler)

    def register_exit(self, state: NPCState, handler: Handler) -> None:
        self._exit_hooks[state].append(handler)

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def is_idle(self) -> bool:
        return self._state == NPCState.IDLE

    def can_transition_to(self, target: NPCState) -> bool:
        return (self._state, target) in VALID_TRANSITIONS

    def __repr__(self) -> str:
        return f"<FSM npc={self.npc_id!r} state={self._state.value!r}>"
