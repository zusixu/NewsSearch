"""
tests/test_react_session.py

Tests for ReActStep and ReActSession state machines.

Coverage:
- ReActStep creation and field values
- ReActSession initialization
- add_step and current_step_count
- is_finished when is_complete=True
- is_finished when max_steps reached
- to_history_json output format
- Empty session behaviour
"""

from __future__ import annotations

import json

import pytest

from app.analysis.react.session import ReActStep, ReActSession


# ---------------------------------------------------------------------------
# ReActStep tests
# ---------------------------------------------------------------------------


class TestReActStep:
    """Tests for the ReActStep frozen dataclass."""

    def test_create_minimal_step(self) -> None:
        """A ReActStep can be created with minimal fields."""
        step = ReActStep(step_index=0, thought="Initial analysis")
        assert step.step_index == 0
        assert step.thought == "Initial analysis"
        assert step.action is None
        assert step.observation is None
        assert step.is_complete is False

    def test_create_full_step(self) -> None:
        """A ReActStep with all fields populated."""
        action = {"tool": "web_search", "params": {"query": "AI news"}}
        step = ReActStep(
            step_index=2,
            thought="Need more info",
            action=action,
            observation="Found 3 results",
            is_complete=True,
        )
        assert step.step_index == 2
        assert step.thought == "Need more info"
        assert step.action == action
        assert step.observation == "Found 3 results"
        assert step.is_complete is True

    def test_step_is_frozen(self) -> None:
        """ReActStep is a frozen dataclass."""
        step = ReActStep(step_index=0, thought="test")
        with pytest.raises(Exception):
            step.step_index = 1  # type: ignore[misc]

    def test_step_defaults(self) -> None:
        """ReActStep defaults for action, observation, is_complete."""
        step = ReActStep(step_index=5, thought="Default test")
        assert step.action is None
        assert step.observation is None
        assert step.is_complete is False

    def test_step_equality(self) -> None:
        """Two ReActSteps with same fields are equal."""
        s1 = ReActStep(step_index=0, thought="Same")
        s2 = ReActStep(step_index=0, thought="Same")
        assert s1 == s2

    def test_step_inequality_different_index(self) -> None:
        """ReActSteps with different step_index are not equal."""
        s1 = ReActStep(step_index=0, thought="Same")
        s2 = ReActStep(step_index=1, thought="Same")
        assert s1 != s2


# ---------------------------------------------------------------------------
# ReActSession tests
# ---------------------------------------------------------------------------


class TestReActSession:
    """Tests for the ReActSession state machine."""

    def test_initialization_defaults(self) -> None:
        """ReActSession initializes with sensible defaults."""
        session = ReActSession(group_id="g1")
        assert session.group_id == "g1"
        assert session.group_context == {}
        assert session.steps == []
        assert session.max_steps == 5

    def test_initialization_with_context(self) -> None:
        """ReActSession stores group_context correctly."""
        ctx = {"theme": "AI chips", "member_chain_ids": ["c1", "c2"]}
        session = ReActSession(group_id="g2", group_context=ctx)
        assert session.group_context == ctx

    def test_custom_max_steps(self) -> None:
        """ReActSession accepts a custom max_steps."""
        session = ReActSession(group_id="g3", max_steps=3)
        assert session.max_steps == 3

    def test_current_step_count_zero_initially(self) -> None:
        """current_step_count is 0 for a fresh session."""
        session = ReActSession(group_id="g1")
        assert session.current_step_count == 0

    def test_add_step_increments_count(self) -> None:
        """add_step() increases current_step_count."""
        session = ReActSession(group_id="g1")
        step = ReActStep(step_index=0, thought="First step")
        session.add_step(step)
        assert session.current_step_count == 1

    def test_add_multiple_steps(self) -> None:
        """Multiple steps accumulate correctly."""
        session = ReActSession(group_id="g1")
        for i in range(3):
            session.add_step(ReActStep(step_index=i, thought=f"Step {i}"))
        assert session.current_step_count == 3
        assert len(session.steps) == 3

    def test_is_finished_false_initially(self) -> None:
        """is_finished is False for an empty session."""
        session = ReActSession(group_id="g1")
        assert session.is_finished is False

    def test_is_finished_when_is_complete_true(self) -> None:
        """is_finished returns True when last step has is_complete=True."""
        session = ReActSession(group_id="g1")
        step = ReActStep(step_index=0, thought="Done", is_complete=True)
        session.add_step(step)
        assert session.is_finished is True

    def test_is_finished_when_max_steps_reached(self) -> None:
        """is_finished returns True when current_step_count >= max_steps."""
        session = ReActSession(group_id="g1", max_steps=2)
        session.add_step(ReActStep(step_index=0, thought="Step 1"))
        session.add_step(ReActStep(step_index=1, thought="Step 2"))
        assert session.current_step_count == 2
        assert session.is_finished is True

    def test_is_finished_not_only_by_max_steps(self) -> None:
        """is_finished is False when under max_steps and not complete."""
        session = ReActSession(group_id="g1", max_steps=3)
        session.add_step(ReActStep(step_index=0, thought="Step 1"))
        assert session.current_step_count == 1
        assert session.is_finished is False

    def test_last_step_returns_most_recent(self) -> None:
        """last_step returns the most recently added step."""
        session = ReActSession(group_id="g1")
        s1 = ReActStep(step_index=0, thought="First")
        s2 = ReActStep(step_index=1, thought="Second")
        session.add_step(s1)
        session.add_step(s2)
        assert session.last_step is s2

    def test_last_step_returns_none_for_empty(self) -> None:
        """last_step returns None when no steps exist."""
        session = ReActSession(group_id="g1")
        assert session.last_step is None

    def test_to_history_json_empty(self) -> None:
        """to_history_json returns empty array for empty session."""
        session = ReActSession(group_id="g1")
        result = session.to_history_json()
        data = json.loads(result)
        assert data == []

    def test_to_history_json_format(self) -> None:
        """to_history_json produces proper JSON with all expected keys."""
        session = ReActSession(group_id="g_test")
        action = {"tool": "web_search", "params": {"query": "AI"}}
        session.add_step(ReActStep(
            step_index=0, thought="Need info",
            action=action, observation="Results found",
            is_complete=False,
        ))
        session.add_step(ReActStep(
            step_index=1, thought="Analysis complete",
            action=None, observation=None, is_complete=True,
        ))

        result = session.to_history_json()
        data = json.loads(result)

        assert len(data) == 2

        # First step
        s0 = data[0]
        assert s0["step_index"] == 0
        assert s0["thought"] == "Need info"
        assert s0["action"] == action
        assert s0["observation"] == "Results found"
        assert s0["is_complete"] is False

        # Second step
        s1 = data[1]
        assert s1["step_index"] == 1
        assert s1["thought"] == "Analysis complete"
        assert s1["action"] is None
        assert s1["observation"] is None
        assert s1["is_complete"] is True

    def test_to_history_json_is_valid_json(self) -> None:
        """to_history_json always returns valid JSON."""
        session = ReActSession(group_id="g1")
        session.add_step(ReActStep(step_index=0, thought="Test with \"quotes\""))
        result = session.to_history_json()
        # Should parse without error
        data = json.loads(result)
        assert data[0]["thought"] == "Test with \"quotes\""

    def test_is_finished_with_intermediate_complete(self) -> None:
        """is_finished cares only about the LAST step's is_complete."""
        session = ReActSession(group_id="g1")
        session.add_step(ReActStep(step_index=0, thought="Not done", is_complete=False))
        session.add_step(ReActStep(step_index=1, thought="Done now", is_complete=True))
        assert session.is_finished is True

    def test_complete_before_max_stops_early(self) -> None:
        """Session finishes before max_steps when is_complete=True."""
        session = ReActSession(group_id="g1", max_steps=100)
        session.add_step(ReActStep(step_index=0, thought="One and done", is_complete=True))
        assert session.current_step_count == 1
        assert session.current_step_count < session.max_steps
        assert session.is_finished is True
