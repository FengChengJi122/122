"""
Unit tests for the FSM (Finite State Machine).
"""

import asyncio
import pytest

import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from backend.agents.fsm import FSM, NPCState, FSMError


@pytest.fixture
def fsm():
    return FSM(npc_id="test_npc")


# ---------------------------------------------------------------------------
# Initial state
# ---------------------------------------------------------------------------

def test_initial_state(fsm):
    assert fsm.state == NPCState.IDLE


def test_history_starts_with_initial(fsm):
    assert fsm.history == [NPCState.IDLE]


# ---------------------------------------------------------------------------
# Valid transitions
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_idle_to_listening(fsm):
    await fsm.transition(NPCState.LISTENING)
    assert fsm.state == NPCState.LISTENING


@pytest.mark.asyncio
async def test_full_interaction_cycle(fsm):
    """IDLE → LISTENING → THINKING → RESPONDING → IDLE"""
    await fsm.transition(NPCState.LISTENING)
    await fsm.transition(NPCState.THINKING)
    await fsm.transition(NPCState.RESPONDING)
    await fsm.transition(NPCState.IDLE)
    assert fsm.state == NPCState.IDLE


@pytest.mark.asyncio
async def test_thinking_to_acting(fsm):
    await fsm.transition(NPCState.LISTENING)
    await fsm.transition(NPCState.THINKING)
    await fsm.transition(NPCState.ACTING)
    assert fsm.state == NPCState.ACTING


@pytest.mark.asyncio
async def test_idle_to_moving(fsm):
    await fsm.transition(NPCState.MOVING)
    assert fsm.state == NPCState.MOVING


# ---------------------------------------------------------------------------
# Invalid transitions
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_invalid_transition_raises(fsm):
    with pytest.raises(FSMError):
        # Cannot jump from IDLE directly to RESPONDING.
        await fsm.transition(NPCState.RESPONDING)


@pytest.mark.asyncio
async def test_invalid_transition_idle_to_acting(fsm):
    with pytest.raises(FSMError):
        await fsm.transition(NPCState.ACTING)


# ---------------------------------------------------------------------------
# Force transition
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_force_transition_bypasses_rules(fsm):
    await fsm.force_transition(NPCState.RESPONDING)
    assert fsm.state == NPCState.RESPONDING


# ---------------------------------------------------------------------------
# Hooks
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_enter_hook_called(fsm):
    entered = []

    async def on_enter(fsm_obj, prev):
        entered.append(prev)

    fsm.register_enter(NPCState.LISTENING, on_enter)
    await fsm.transition(NPCState.LISTENING)

    assert entered == [NPCState.IDLE.value]


@pytest.mark.asyncio
async def test_exit_hook_called(fsm):
    exited = []

    async def on_exit(fsm_obj, next_state):
        exited.append(next_state)

    fsm.register_exit(NPCState.IDLE, on_exit)
    await fsm.transition(NPCState.LISTENING)

    assert exited == [NPCState.LISTENING.value]


@pytest.mark.asyncio
async def test_decorator_hook(fsm):
    events = []

    @fsm.on_enter(NPCState.THINKING)
    async def on_thinking(f, prev):
        events.append("entered thinking")

    await fsm.transition(NPCState.LISTENING)
    await fsm.transition(NPCState.THINKING)

    assert "entered thinking" in events


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def test_is_idle_true(fsm):
    assert fsm.is_idle()


@pytest.mark.asyncio
async def test_is_idle_false_after_transition(fsm):
    await fsm.transition(NPCState.LISTENING)
    assert not fsm.is_idle()


def test_can_transition_to(fsm):
    assert fsm.can_transition_to(NPCState.LISTENING)
    assert not fsm.can_transition_to(NPCState.RESPONDING)


@pytest.mark.asyncio
async def test_history_records_all_transitions(fsm):
    await _run_transitions(fsm)
    # IDLE → LISTENING → THINKING → IDLE
    assert NPCState.THINKING in fsm.history


async def _run_transitions(fsm):
    await fsm.transition(NPCState.LISTENING)
    await fsm.transition(NPCState.THINKING)
    await fsm.transition(NPCState.IDLE)
