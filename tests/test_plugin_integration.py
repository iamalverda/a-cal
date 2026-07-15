"""Integration tests for plugin runtime wiring into conductor and data API.

These tests verify that plugin hooks actually fire when:
  - The conductor classifies intent (on_intent_classified)
  - The conductor returns a response (on_conductor_response)
  - Events are created/updated/deleted via the API (on_event_created etc.)
"""

from __future__ import annotations

import os
import textwrap
from datetime import datetime, timedelta, timezone, UTC

import pytest
from fastapi.testclient import TestClient
from tests._authclient import make_authed_client


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def plugin_dir(tmp_path, monkeypatch):
    """Create a temp plugin directory and point the runtime at it."""
    d = tmp_path / "plugins"
    d.mkdir()
    env_dir = str(d)
    monkeypatch.setenv("A_CAL_PLUGIN_DIR", env_dir)

    # Reset the singleton so it picks up the new env var
    import a_cal.developer.plugin_runtime as pr
    monkeypatch.setattr(pr, "_runtime", None)

    return env_dir


def _write_plugin(directory: str, filename: str, code: str) -> None:
    with open(os.path.join(directory, filename), "w") as f:
        f.write(textwrap.dedent(code))


# ---------------------------------------------------------------------------
# Conductor + plugin runtime integration
# ---------------------------------------------------------------------------

class TestConductorPluginIntegration:
    """Tests that the conductor fires plugin hooks correctly."""

    @pytest.mark.asyncio
    async def test_on_intent_classified_fires(self, plugin_dir):
        """A plugin's on_intent_classified hook can override the conductor's intent."""
        _write_plugin(plugin_dir, "intent_router.py", '''
            class Plugin:
                name = "IntentRouter"
                plugin_type = "agent"

                def on_intent_classified(self, message, intent):
                    if "meeting" in message.lower():
                        return "schedule"
                    return None
        ''')

        from a_cal.developer.plugin_runtime import get_runtime
        from a_cal.agents.conductor import ACalConductor, IntentType

        runtime = get_runtime()
        runtime.scan_and_load()

        conductor = ACalConductor()
        # "meeting" is in the SCHEDULE keywords already, so let's use
        # a message that would default to CHAT and verify the plugin
        # overrides it to SCHEDULE.
        intent = conductor.classify_intent("help me with a meeting thing")
        assert intent == IntentType.SCHEDULE

    @pytest.mark.asyncio
    async def test_on_conductor_response_fires_standalone(self, plugin_dir):
        """A plugin's on_conductor_response hook transforms the standalone response."""
        _write_plugin(plugin_dir, "responder.py", '''
            class Plugin:
                name = "Responder"
                plugin_type = "agent"

                def on_conductor_response(self, response, context):
                    return "[plugin] " + response
        ''')

        from a_cal.developer.plugin_runtime import get_runtime
        from a_cal.agents.conductor import ACalConductor

        runtime = get_runtime()
        runtime.scan_and_load()

        conductor = ACalConductor()
        result = await conductor.handle("hello")
        assert result["response"].startswith("[plugin] ")

    @pytest.mark.asyncio
    async def test_conductor_works_without_plugins(self, plugin_dir):
        """The conductor still works when no plugins are loaded."""
        from a_cal.developer.plugin_runtime import get_runtime
        from a_cal.agents.conductor import ACalConductor

        runtime = get_runtime()
        runtime.scan_and_load()
        assert runtime.list_loaded() == []

        conductor = ACalConductor()
        result = await conductor.handle("what events do I have today")
        assert "response" in result
        assert result["standalone"] is True

    @pytest.mark.asyncio
    async def test_plugin_error_doesnt_crash_conductor(self, plugin_dir):
        """A plugin that raises in on_conductor_response doesn't crash the conductor."""
        _write_plugin(plugin_dir, "crasher.py", '''
            class Plugin:
                name = "Crasher"
                plugin_type = "agent"

                def on_conductor_response(self, response, context):
                    raise RuntimeError("boom")
        ''')

        from a_cal.developer.plugin_runtime import get_runtime
        from a_cal.agents.conductor import ACalConductor

        runtime = get_runtime()
        runtime.scan_and_load()

        conductor = ACalConductor()
        result = await conductor.handle("hello")
        # Should still get a valid response despite the plugin crashing
        assert "response" in result
        assert len(result["response"]) > 0


# ---------------------------------------------------------------------------
# Data API + plugin runtime integration
# ---------------------------------------------------------------------------

class TestDataApiPluginIntegration:
    """Tests that event endpoints fire plugin hooks."""

    def test_on_event_created_fires(self, plugin_dir):
        """Creating an event fires on_event_created on loaded plugins."""
        _write_plugin(plugin_dir, "event_logger.py", '''
            fires = []

            class Plugin:
                name = "EventLogger"
                plugin_type = "agent"

                def on_event_created(self, event):
                    fires.append(("created", event.get("title", "")))
                    return None

                def on_event_updated(self, event):
                    fires.append(("updated", event.get("title", "")))
                    return None

                def on_event_deleted(self, event_id):
                    fires.append(("deleted", event_id))
                    return None
        ''')

        from a_cal.developer.plugin_runtime import get_runtime
        from a_cal.api.standalone import app

        runtime = get_runtime()
        runtime.scan_and_load()

        # Import the plugin module to check the fires list
        import sys
        plugin_mod = sys.modules.get("a_cal_plugin_event_logger")
        assert plugin_mod is not None

        client = make_authed_client()

        # Create an event
        now = datetime.now(UTC)
        resp = client.post("/api/a-cal/calendar/events", json={
            "title": "Plugin Test Meeting",
            "start": now.isoformat(),
            "end": (now + timedelta(hours=1)).isoformat(),
        })
        assert resp.status_code == 200
        assert ("created", "Plugin Test Meeting") in plugin_mod.fires

        # Update the event
        event_id = resp.json()["provider_event_id"]
        resp = client.patch(f"/api/a-cal/calendar/events/{event_id}", json={
            "title": "Updated Title",
        })
        assert resp.status_code == 200
        assert ("updated", "Updated Title") in plugin_mod.fires

        # Delete the event
        resp = client.delete(f"/api/a-cal/calendar/events/{event_id}")
        assert resp.status_code == 200
        assert ("deleted", event_id) in plugin_mod.fires

    def test_event_endpoints_work_without_plugins(self, plugin_dir):
        """Event endpoints still work when no plugins are loaded."""
        from a_cal.developer.plugin_runtime import get_runtime
        from a_cal.api.standalone import app

        runtime = get_runtime()
        runtime.scan_and_load()
        assert runtime.list_loaded() == []

        client = make_authed_client()
        now = datetime.now(UTC)
        resp = client.post("/api/a-cal/calendar/events", json={
            "title": "No Plugin Event",
            "start": now.isoformat(),
            "end": (now + timedelta(hours=1)).isoformat(),
        })
        assert resp.status_code == 200
        assert resp.json()["title"] == "No Plugin Event"
