"""Tests for the workflow execution engine, store, and API endpoints."""

from __future__ import annotations

import pytest
from datetime import datetime, timezone

from a_cal.workflows.models import WorkflowDef, WorkflowNode, WorkflowRunResult
from a_cal.workflows.store import WorkflowStore
from a_cal.workflows.runner import WorkflowRunner
from a_cal.db.store import PersistentStore
from tests._authclient import make_authed_client


# --- Model tests -------------------------------------------------------------

class TestWorkflowModels:
    """Workflow data model serialization tests."""

    def test_node_round_trip(self):
        """A WorkflowNode should survive to_dict → from_dict."""
        node = WorkflowNode(
            id="n1",
            agent="a_cal_schedule_agent",
            label="Find free slots",
            config={"duration": 30, "pref_start": 9},
            conditional="intent:schedule",
        )
        d = node.to_dict()
        restored = WorkflowNode.from_dict(d)
        assert restored.id == "n1"
        assert restored.agent == "a_cal_schedule_agent"
        assert restored.label == "Find free slots"
        assert restored.config["duration"] == 30
        assert restored.conditional == "intent:schedule"

    def test_workflow_round_trip(self):
        """A WorkflowDef should survive to_dict → from_dict."""
        wf = WorkflowDef(
            id="wf-1",
            name="Morning Briefing",
            description="Scan email and summarize schedule",
            nodes=[
                WorkflowNode(id="n1", agent="a_cal_email_agent", label="Scan inbox"),
                WorkflowNode(id="n2", agent="a_cal_schedule_agent", label="List today"),
            ],
            trigger="manual",
            version="1.0.0",
            created_at="2026-07-12T00:00:00+00:00",
            updated_at="2026-07-12T00:00:00+00:00",
        )
        d = wf.to_dict()
        restored = WorkflowDef.from_dict(d)
        assert restored.id == "wf-1"
        assert restored.name == "Morning Briefing"
        assert len(restored.nodes) == 2
        assert restored.nodes[0].agent == "a_cal_email_agent"
        assert restored.trigger == "manual"
        assert restored.version == "1.0.0"

    def test_empty_workflow_serialization(self):
        """An empty workflow should serialize without errors."""
        wf = WorkflowDef(name="Empty")
        d = wf.to_dict()
        assert d["nodes"] == []
        restored = WorkflowDef.from_dict(d)
        assert restored.name == "Empty"
        assert restored.nodes == []


# --- Store tests --------------------------------------------------------------

class TestWorkflowStore:
    """WorkflowStore CRUD tests using in-memory SQLite."""

    def test_save_and_get_workflow(self):
        """Saving a workflow should assign an ID and be retrievable."""
        store = WorkflowStore(PersistentStore(in_memory=True))
        wf = WorkflowDef(
            name="Test Workflow",
            description="A test",
            nodes=[WorkflowNode(id="n1", agent="a_cal_conductor", label="Step 1")],
        )
        saved = store.save_workflow(wf)
        assert saved.id != ""
        assert saved.created_at != ""
        assert saved.updated_at != ""

        retrieved = store.get_workflow(saved.id)
        assert retrieved is not None
        assert retrieved.name == "Test Workflow"
        assert len(retrieved.nodes) == 1

    def test_list_workflows(self):
        """List should return all saved workflows."""
        store = WorkflowStore(PersistentStore(in_memory=True))
        store.save_workflow(WorkflowDef(name="WF1"))
        store.save_workflow(WorkflowDef(name="WF2"))
        workflows = store.list_workflows()
        assert len(workflows) == 2

    def test_update_workflow(self):
        """Updating an existing workflow should keep the same ID."""
        store = WorkflowStore(PersistentStore(in_memory=True))
        wf = WorkflowDef(name="Original")
        saved = store.save_workflow(wf)
        original_id = saved.id

        saved.name = "Updated"
        updated = store.save_workflow(saved)
        assert updated.id == original_id
        assert updated.name == "Updated"

        # Should not have created a duplicate
        assert len(store.list_workflows()) == 1

    def test_delete_workflow(self):
        """Deleting a workflow should remove it from the store."""
        store = WorkflowStore(PersistentStore(in_memory=True))
        wf = WorkflowDef(name="ToDelete")
        saved = store.save_workflow(wf)

        assert store.delete_workflow(saved.id) is True
        assert store.get_workflow(saved.id) is None
        assert store.delete_workflow(saved.id) is False

    def test_get_nonexistent_workflow(self):
        """Getting a non-existent workflow should return None."""
        store = WorkflowStore(PersistentStore(in_memory=True))
        assert store.get_workflow("nonexistent") is None


# --- Runner tests -------------------------------------------------------------

class TestWorkflowRunner:
    """WorkflowRunner execution tests with a mock conductor."""

    class _MockConductor:
        """Mock conductor that echoes the message back."""

        def __init__(self) -> None:
            self.calls: list[str] = []

        async def handle(self, message: str) -> dict:
            self.calls.append(message)
            return {
                "response": f"Processed: {message[:50]}",
                "actions": [{"type": "echo"}],
                "routing": {"intent": "chat", "specialist": "mock"},
            }

    @pytest.mark.asyncio
    async def test_run_single_node(self):
        """A single-node workflow should execute and return output."""
        conductor = self._MockConductor()
        runner = WorkflowRunner(conductor)
        wf = WorkflowDef(
            name="Single",
            nodes=[WorkflowNode(id="n1", agent="a_cal_conductor", label="Do something")],
        )
        result = await runner.run(wf)
        assert result.success is True
        assert len(result.steps) == 1
        assert result.steps[0]["skipped"] is False
        assert "Processed:" in result.final_output

    @pytest.mark.asyncio
    async def test_run_multi_node_context_passing(self):
        """Multi-node workflows should pass context between nodes."""
        conductor = self._MockConductor()
        runner = WorkflowRunner(conductor)
        wf = WorkflowDef(
            name="Multi",
            nodes=[
                WorkflowNode(id="n1", agent="a_cal_email_agent", label="Scan emails"),
                WorkflowNode(id="n2", agent="a_cal_schedule_agent", label="Check calendar"),
            ],
        )
        result = await runner.run(wf)
        assert result.success is True
        assert len(result.steps) == 2
        # The second call should include context from the first
        assert "Previous steps" in conductor.calls[1]
        assert "Scan emails" in conductor.calls[1]

    @pytest.mark.asyncio
    async def test_conditional_node_skipped(self):
        """A conditional node whose condition is not met should be skipped."""
        conductor = self._MockConductor()
        runner = WorkflowRunner(conductor)
        wf = WorkflowDef(
            name="Conditional",
            nodes=[
                WorkflowNode(id="n1", agent="a_cal_conductor", label="First step"),
                WorkflowNode(
                    id="n2",
                    agent="a_cal_conductor",
                    label="Conditional step",
                    conditional="nonexistent:keyword",
                ),
            ],
        )
        result = await runner.run(wf)
        assert result.success is True
        assert len(result.steps) == 2
        assert result.steps[1]["skipped"] is True
        # Only the first node should have been dispatched
        assert len(conductor.calls) == 1

    @pytest.mark.asyncio
    async def test_conditional_node_executed(self):
        """A conditional node whose condition IS met should execute."""
        conductor = self._MockConductor()
        runner = WorkflowRunner(conductor)
        wf = WorkflowDef(
            name="ConditionalMet",
            nodes=[
                WorkflowNode(id="n1", agent="a_cal_conductor", label="Find schedule"),
                WorkflowNode(
                    id="n2",
                    agent="a_cal_conductor",
                    label="Handle schedule",
                    conditional="find:schedule",
                ),
            ],
        )
        result = await runner.run(wf)
        assert result.success is True
        assert result.steps[1]["skipped"] is False
        assert len(conductor.calls) == 2

    @pytest.mark.asyncio
    async def test_initial_message_included(self):
        """An initial message should be included in the first node's context."""
        conductor = self._MockConductor()
        runner = WorkflowRunner(conductor)
        wf = WorkflowDef(
            name="WithInput",
            nodes=[WorkflowNode(id="n1", agent="a_cal_conductor", label="Process")],
        )
        result = await runner.run(wf, initial_message="New email from boss")
        assert result.success is True
        assert "New email from boss" in conductor.calls[0]

    @pytest.mark.asyncio
    async def test_node_failure_stops_workflow(self):
        """If a node raises an exception, the workflow should stop and report error."""
        class _FailingConductor:
            async def handle(self, message: str) -> dict:
                raise RuntimeError("agent unavailable")

        runner = WorkflowRunner(_FailingConductor())
        wf = WorkflowDef(
            name="Failing",
            nodes=[
                WorkflowNode(id="n1", agent="a_cal_conductor", label="Step 1"),
                WorkflowNode(id="n2", agent="a_cal_conductor", label="Step 2"),
            ],
        )
        result = await runner.run(wf)
        assert result.success is False
        assert result.error is not None
        assert "Step 1" in result.error
        # The second node should not have been attempted
        assert len(result.steps) == 1

    @pytest.mark.asyncio
    async def test_empty_workflow(self):
        """An empty workflow should complete successfully with no steps."""
        conductor = self._MockConductor()
        runner = WorkflowRunner(conductor)
        wf = WorkflowDef(name="Empty", nodes=[])
        result = await runner.run(wf)
        assert result.success is True
        assert len(result.steps) == 0
        assert result.final_output == ""

    @pytest.mark.asyncio
    async def test_node_config_included_in_message(self):
        """Node config should be included in the dispatched message."""
        conductor = self._MockConductor()
        runner = WorkflowRunner(conductor)
        wf = WorkflowDef(
            name="WithConfig",
            nodes=[
                WorkflowNode(
                    id="n1",
                    agent="a_cal_schedule_agent",
                    label="Find slots",
                    config={"duration": 60, "pref_start": 9},
                ),
            ],
        )
        result = await runner.run(wf)
        assert result.success is True
        assert "duration" in conductor.calls[0]
        assert "60" in conductor.calls[0]


# --- API endpoint tests ------------------------------------------------------

class TestWorkflowAPI:
    """Workflow API endpoint tests via FastAPI TestClient."""

    def test_save_and_list_workflows(self):
        """Saving a workflow via API and listing it should work."""
        from fastapi.testclient import TestClient
        from a_cal.api.standalone import app

        client = make_authed_client()
        # Save a workflow
        resp = client.post("/api/a-cal/developer/workflows", json={
            "name": "API Test Workflow",
            "description": "Created via API",
            "nodes": [
                {"id": "n1", "agent": "a_cal_conductor", "label": "Step 1"},
            ],
            "trigger": "manual",
            "version": "0.1.0",
        })
        assert resp.status_code == 200
        saved = resp.json()
        assert saved["id"] != ""
        assert saved["name"] == "API Test Workflow"

        # List workflows
        resp = client.get("/api/a-cal/developer/workflows")
        assert resp.status_code == 200
        workflows = resp.json()
        assert any(w["id"] == saved["id"] for w in workflows)

    def test_get_and_delete_workflow(self):
        """Getting and deleting a workflow via API should work."""
        from fastapi.testclient import TestClient
        from a_cal.api.standalone import app

        client = make_authed_client()
        # Save
        resp = client.post("/api/a-cal/developer/workflows", json={
            "name": "To Delete",
            "nodes": [],
        })
        wf_id = resp.json()["id"]

        # Get
        resp = client.get(f"/api/a-cal/developer/workflows/{wf_id}")
        assert resp.status_code == 200
        assert resp.json()["name"] == "To Delete"

        # Delete
        resp = client.delete(f"/api/a-cal/developer/workflows/{wf_id}")
        assert resp.status_code == 200

        # Get again should 404
        resp = client.get(f"/api/a-cal/developer/workflows/{wf_id}")
        assert resp.status_code == 404

    def test_get_nonexistent_workflow_404(self):
        """Getting a non-existent workflow should return 404."""
        from fastapi.testclient import TestClient
        from a_cal.api.standalone import app

        client = make_authed_client()
        resp = client.get("/api/a-cal/developer/workflows/nonexistent-id")
        assert resp.status_code == 404
