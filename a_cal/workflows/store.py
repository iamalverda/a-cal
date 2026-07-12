"""Workflow storage — persists workflow definitions to SQLite.

Workflows are stored as a JSON dict under the ``workflows`` setting key
in the PersistentStore. Each workflow is keyed by its auto-generated ID.
"""

from __future__ import annotations

import logging
import uuid as _uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from a_cal.workflows.models import WorkflowDef

logger = logging.getLogger(__name__)


class WorkflowStore:
    """CRUD storage for workflow definitions.

    Wraps the PersistentStore's settings table to persist workflows
    as JSON. Each workflow gets a UUID on first save.

    Args:
        db: A PersistentStore instance with get_setting/set_setting.
    """

    def __init__(self, db: Any) -> None:
        """Initialize with a PersistentStore instance."""
        self._db = db

    def _get_all_raw(self) -> Dict[str, Dict[str, Any]]:
        """Load all workflows from the settings table."""
        data = self._db.get_setting("workflows", {})
        return data if isinstance(data, dict) else {}

    def _save_all_raw(self, data: Dict[str, Dict[str, Any]]) -> None:
        """Persist all workflows to the settings table."""
        self._db.set_setting("workflows", data)

    def list_workflows(self) -> List[WorkflowDef]:
        """Return all saved workflows, ordered by updated_at descending."""
        raw = self._get_all_raw()
        workflows = [WorkflowDef.from_dict(v) for v in raw.values()]
        workflows.sort(key=lambda w: w.updated_at or w.created_at, reverse=True)
        return workflows

    def get_workflow(self, workflow_id: str) -> Optional[WorkflowDef]:
        """Get a single workflow by ID."""
        raw = self._get_all_raw()
        data = raw.get(workflow_id)
        if data:
            return WorkflowDef.from_dict(data)
        return None

    def save_workflow(self, workflow: WorkflowDef) -> WorkflowDef:
        """Create or update a workflow.

        If ``workflow.id`` is empty, a new UUID is generated. The
        ``created_at`` and ``updated_at`` timestamps are managed here.

        Args:
            workflow: The workflow definition to save.

        Returns:
            The saved workflow with ID and timestamps set.
        """
        raw = self._get_all_raw()
        now = datetime.now(timezone.utc).isoformat()

        if not workflow.id:
            workflow.id = str(_uuid.uuid4())
            workflow.created_at = now

        workflow.updated_at = now
        raw[workflow.id] = workflow.to_dict()
        self._save_all_raw(raw)
        return workflow

    def delete_workflow(self, workflow_id: str) -> bool:
        """Delete a workflow by ID.

        Returns:
            True if the workflow was found and deleted, False otherwise.
        """
        raw = self._get_all_raw()
        if workflow_id in raw:
            del raw[workflow_id]
            self._save_all_raw(raw)
            return True
        return False
