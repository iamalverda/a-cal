"""Workflow execution engine — runs agent chains sequentially.

The ``WorkflowRunner`` takes a ``WorkflowDef`` and executes each node in
order. Each node dispatches a message to the conductor (which routes to
the appropriate specialist agent). The output of each node is accumulated
and passed as context to subsequent nodes, enabling multi-step agent
workflows like "scan emails for meetings → check calendar conflicts →
draft reschedule proposals."

Conditional nodes can be skipped based on a simple ``key:value`` check
against the accumulated context. This is intentionally simple — the goal
is to let users build useful pipelines without a complex expression engine.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone, UTC
from typing import Any, Dict, Optional

from a_cal.workflows.models import WorkflowDef, WorkflowNode, WorkflowRunResult

logger = logging.getLogger(__name__)


class WorkflowRunner:
    """Executes workflow definitions by dispatching to the conductor.

    Args:
        conductor: The ACalConductor instance used for agent dispatch.
            The runner calls ``conductor.handle(message)`` for each node.
    """

    def __init__(self, conductor: Any) -> None:
        """Initialize the runner with a conductor instance."""
        self._conductor = conductor

    async def run(
        self,
        workflow: WorkflowDef,
        initial_message: str = "",
    ) -> WorkflowRunResult:
        """Execute a workflow sequentially.

        Each node's agent receives a message composed of the node's label,
        any node config, and the accumulated context from previous nodes.
        The conductor routes each message to the appropriate specialist.

        Args:
            workflow: The workflow definition to execute.
            initial_message: Optional starting message (e.g. from the user
                or the triggering event). Prepended to the first node's input.

        Returns:
            A ``WorkflowRunResult`` with per-step outputs and final result.
        """
        started = datetime.now(UTC)
        result = WorkflowRunResult(
            workflow_id=workflow.id or workflow.name,
            success=True,
            started_at=started.isoformat(),
        )

        # Accumulated context passed between nodes.
        context_parts: list[str] = []
        if initial_message:
            context_parts.append(f"[Initial input]: {initial_message}")

        for idx, node in enumerate(workflow.nodes):
            step_result: dict[str, Any] = {
                "node_id": node.id,
                "node_index": idx,
                "agent": node.agent,
                "label": node.label,
                "skipped": False,
            }

            # Check conditional — skip if condition is not met.
            if node.conditional and not self._evaluate_condition(
                node.conditional, context_parts,
            ):
                step_result["skipped"] = True
                step_result["output"] = "Skipped (condition not met)"
                result.steps.append(step_result)
                continue

            # Build the message for this node.
            message = self._build_node_message(node, context_parts)

            try:
                # Dispatch to the conductor (which routes to the agent).
                response = await self._conductor.handle(message)
                output = response.get("response", "")
                actions = response.get("actions", [])

                step_result["output"] = output
                step_result["actions"] = actions
                step_result["routing"] = response.get("routing")

                # Append this node's output to the context for the next node.
                context_parts.append(f"[{node.label}]: {output}")
                result.final_output = output

            except Exception as exc:
                logger.error(
                    "workflow node %s failed: %r", node.label, exc,
                )
                step_result["error"] = str(exc) or repr(exc)
                step_result["output"] = f"Error: {step_result['error']}"
                result.success = False
                result.error = f"Node '{node.label}' failed: {step_result['error']}"
                result.steps.append(step_result)
                break

            result.steps.append(step_result)

        finished = datetime.now(UTC)
        result.finished_at = finished.isoformat()
        return result

    def _build_node_message(
        self,
        node: WorkflowNode,
        context_parts: list[str],
    ) -> str:
        """Build the message text for a single node.

        Combines the node's label, config, and accumulated context from
        previous nodes into a single message string for the conductor.

        Args:
            node: The workflow node to build a message for.
            context_parts: Accumulated context from previous nodes.

        Returns:
            A message string suitable for the conductor.
        """
        parts: list[str] = []

        # Include accumulated context from previous nodes.
        if context_parts:
            parts.append("[Previous steps in this workflow:]")
            parts.extend(context_parts)
            parts.append("")

        # Include node config as key-value pairs.
        if node.config:
            config_lines = [f"  {k}: {v}" for k, v in node.config.items()]
            parts.append("[Configuration for this step:]")
            parts.extend(config_lines)
            parts.append("")

        # The actual instruction for this node.
        parts.append(node.label)

        return "\n".join(parts)

    def _evaluate_condition(
        self,
        condition: str,
        context_parts: list[str],
    ) -> bool:
        """Evaluate a simple condition against the accumulated context.

        Supports ``key:value`` — returns True if the context contains
        a line with both the key and value. This is intentionally simple;
        a full expression engine can be added later.

        Args:
            condition: A ``key:value`` string to check.
            context_parts: The accumulated context to search.

        Returns:
            True if the condition is met, False otherwise.
        """
        joined = "\n".join(context_parts).lower()
        cond_lower = condition.lower().strip()

        if ":" in cond_lower:
            key, value = cond_lower.split(":", 1)
            key = key.strip()
            value = value.strip()
            return key in joined and value in joined

        return cond_lower in joined
