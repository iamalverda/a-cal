"""Workflow data models for A-Cal's visual workflow builder.

A workflow is a chain of agent steps that execute sequentially. Each node
dispatches a message to a specific agent (via the conductor), and the output
is passed as context to the next node. Conditional nodes can skip execution
based on a simple expression evaluated against the accumulated context.

Workflows are stored in SQLite via the PersistentStore's settings table
(serialized as JSON under the ``workflows`` key).
"""

from __future__ import annotations

import uuid as _uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional


@dataclass
class WorkflowNode:
    """A single step in a workflow.

    Attributes:
        id: Unique node identifier within the workflow.
        agent: Agent name to dispatch to (e.g. ``a_cal_schedule_agent``).
        label: Human-readable label shown in the UI.
        config: Free-form configuration for this node (passed to the agent
            as part of the prompt context).
        conditional: Optional condition expression. If set and evaluates to
            falsy, the node is skipped. Currently supports simple ``key:value``
            checks against the accumulated context.
    """

    id: str
    agent: str
    label: str
    config: dict[str, Any] = field(default_factory=dict)
    conditional: str | None = None

    def to_dict(self) -> dict[str, Any]:
        """Serialize to a JSON-safe dict."""
        return {
            "id": self.id,
            "agent": self.agent,
            "label": self.label,
            "config": self.config,
            "conditional": self.conditional,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> WorkflowNode:
        """Deserialize from a dict."""
        return cls(
            id=data.get("id", ""),
            agent=data.get("agent", ""),
            label=data.get("label", ""),
            config=data.get("config", {}),
            conditional=data.get("conditional"),
        )


@dataclass
class WorkflowDef:
    """A complete workflow definition.

    Attributes:
        id: Unique workflow identifier (auto-generated on save).
        name: User-given workflow name.
        description: Short description of what the workflow does.
        nodes: Ordered list of workflow nodes.
        trigger: When this workflow should fire (manual, schedule_change,
            email_received, conflict_detected).
        version: Semver version string.
        created_at: ISO timestamp of creation.
        updated_at: ISO timestamp of last update.
    """

    id: str = ""
    name: str = ""
    description: str = ""
    nodes: list[WorkflowNode] = field(default_factory=list)
    trigger: str = "manual"
    version: str = "0.1.0"
    created_at: str = ""
    updated_at: str = ""

    def to_dict(self) -> dict[str, Any]:
        """Serialize to a JSON-safe dict."""
        return {
            "id": self.id,
            "name": self.name,
            "description": self.description,
            "nodes": [n.to_dict() for n in self.nodes],
            "trigger": self.trigger,
            "version": self.version,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> WorkflowDef:
        """Deserialize from a dict."""
        return cls(
            id=data.get("id", ""),
            name=data.get("name", ""),
            description=data.get("description", ""),
            nodes=[WorkflowNode.from_dict(n) for n in data.get("nodes", [])],
            trigger=data.get("trigger", "manual"),
            version=data.get("version", "0.1.0"),
            created_at=data.get("created_at", ""),
            updated_at=data.get("updated_at", ""),
        )


@dataclass
class WorkflowRunResult:
    """Result of executing a workflow.

    Attributes:
        workflow_id: The workflow that was run.
        success: Whether all nodes completed without error.
        steps: Per-node execution results.
        final_output: The response text from the last executed node.
        error: Error message if the run failed.
        started_at: When execution started.
        finished_at: When execution finished.
    """

    workflow_id: str
    success: bool
    steps: list[dict[str, Any]] = field(default_factory=list)
    final_output: str = ""
    error: str | None = None
    started_at: str = ""
    finished_at: str = ""

    def to_dict(self) -> dict[str, Any]:
        """Serialize to a JSON-safe dict."""
        return {
            "workflow_id": self.workflow_id,
            "success": self.success,
            "steps": self.steps,
            "final_output": self.final_output,
            "error": self.error,
            "started_at": self.started_at,
            "finished_at": self.finished_at,
        }
