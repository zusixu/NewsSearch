"""
app/analysis/react/session.py — ReAct step and session state machine.

Defines:
- ReActStep — a single reasoning/acting/observation step.
- ReActSession — manages the iterative ReAct loop for one analysis group.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any


# ---------------------------------------------------------------------------
# ReActStep — a single iteration step
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class ReActStep:
    """
    One iteration of the ReAct loop.

    Fields
    ------
    step_index
        0-based step number within the session.
    thought
        The LLM's reasoning / analysis text for this step.
    action
        Tool invocation requested by the LLM (``{"tool": "...", "params": {...}}``),
        or ``None`` when no action is taken.
    observation
        Result string returned by the tool execution, or ``None`` if no action
        was performed.
    is_complete
        Whether the LLM marked this step as the final one.
    """

    step_index: int
    thought: str
    action: dict[str, Any] | None = None
    observation: str | None = None
    is_complete: bool = False


# ---------------------------------------------------------------------------
# ReActSession — per-group ReAct loop manager
# ---------------------------------------------------------------------------


@dataclass
class ReActSession:
    """
    Manages the ReAct iterative loop for a single analysis group.

    Fields
    ------
    group_id
        Unique group identifier (from the grouper step).
    group_context
        Arbitrary context dictionary describing the group (theme, member chains, etc.).
    steps
        Accumulated :class:`ReActStep` instances in order.
    max_steps
        Hard limit on iterations; once reached, the session is considered finished.
    """

    group_id: str
    group_context: dict[str, Any] = field(default_factory=dict)
    steps: list[ReActStep] = field(default_factory=list)
    max_steps: int = 5

    def add_step(self, step: ReActStep) -> None:
        """Append a completed :class:`ReActStep` to the session."""
        self.steps.append(step)

    @property
    def current_step_count(self) -> int:
        """Number of steps taken so far."""
        return len(self.steps)

    @property
    def is_finished(self) -> bool:
        """
        Return ``True`` when the session should stop.

        The session stops when:
          - The last step has ``is_complete == True``, OR
          - The step count has reached ``max_steps``.
        """
        if self.current_step_count >= self.max_steps:
            return True
        if self.steps and self.steps[-1].is_complete:
            return True
        return False

    @property
    def last_step(self) -> ReActStep | None:
        """Return the most recent step, or ``None`` if no steps exist."""
        return self.steps[-1] if self.steps else None

    def to_history_json(self) -> str:
        """
        Serialize all steps into a JSON string for inclusion in LLM prompts.

        Returns a JSON array of step objects, each containing:
        ``step_index``, ``thought``, ``action``, ``observation``, ``is_complete``.
        """
        history = []
        for step in self.steps:
            history.append(
                {
                    "step_index": step.step_index,
                    "thought": step.thought,
                    "action": step.action,
                    "observation": step.observation,
                    "is_complete": step.is_complete,
                }
            )
        return json.dumps(history, ensure_ascii=False, indent=2)
