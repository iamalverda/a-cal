"""Tests for the developer API endpoints — plugins, agents, config export/import."""

from __future__ import annotations

from fastapi import FastAPI
from fastapi.testclient import TestClient

from a_cal.api.developer_routes import router as developer_router

app = FastAPI()
app.include_router(developer_router)

client = TestClient(app)


def _register_plugin(name: str = "Test Plugin") -> dict:
    resp = client.post("/api/a-cal/developer/plugins", json={
        "name": name,
        "plugin_type": "agent",
        "version": "1.0.0",
        "description": "A test plugin",
        "config_schema": {"setting": {"type": "string"}},
        "default_config": {"setting": "default"},
    })
    assert resp.status_code == 200
    return resp.json()


def _create_agent(name: str = "my_custom_agent") -> dict:
    resp = client.post("/api/a-cal/developer/agents", json={
        "name": name,
        "display_name": "My Custom Agent",
        "description": "A custom test agent",
        "system_prompt": "You are a custom agent for testing.",
        "tools": ["find_open_slots"],
        "default_tier": "standard",
        "can_negotiate": False,
        "privacy_force_local": False,
        "capabilities": ["scheduling"],
    })
    assert resp.status_code == 200
    return resp.json()


class TestPlugins:
    def test_register_plugin(self):
        data = _register_plugin()
        assert data["name"] == "Test Plugin"
        assert data["id"]

    def test_list_plugins(self):
        _register_plugin("Plugin A")
        resp = client.get("/api/a-cal/developer/plugins")
        assert resp.status_code == 200
        assert len(resp.json()) >= 1

    def test_list_plugins_filtered_by_type(self):
        _register_plugin("Agent Plugin")
        resp = client.get("/api/a-cal/developer/plugins?plugin_type=agent")
        assert resp.status_code == 200
        for p in resp.json():
            assert p["plugin_type"] == "agent"

    def test_enable_disable_plugin(self):
        plugin = _register_plugin("Toggle Plugin")
        pid = plugin["id"]

        # Disable
        resp = client.post(f"/api/a-cal/developer/plugins/{pid}/disable")
        assert resp.status_code == 200
        assert resp.json()["enabled"] is False

        # Enable
        resp = client.post(f"/api/a-cal/developer/plugins/{pid}/enable")
        assert resp.status_code == 200
        assert resp.json()["enabled"] is True

    def test_update_plugin_config(self):
        plugin = _register_plugin("Config Plugin")
        resp = client.patch(f"/api/a-cal/developer/plugins/{plugin['id']}/config", json={
            "config": {"new_setting": "value"},
        })
        assert resp.status_code == 200
        assert resp.json()["default_config"]["new_setting"] == "value"

    def test_unregister_plugin(self):
        plugin = _register_plugin("Delete Me")
        resp = client.delete(f"/api/a-cal/developer/plugins/{plugin['id']}")
        assert resp.status_code == 200
        assert resp.json()["deleted"] is True

    def test_unregister_nonexistent(self):
        resp = client.delete("/api/a-cal/developer/plugins/nonexistent")
        assert resp.status_code == 404


class TestAgentSpecCRUD:
    def test_list_includes_builtins(self):
        resp = client.get("/api/a-cal/developer/agents")
        assert resp.status_code == 200
        names = [a["name"] for a in resp.json()]
        assert "a_cal_conductor" in names

    def test_create_custom_agent(self):
        data = _create_agent("unique_test_agent")
        assert data["name"] == "unique_test_agent"
        assert data["display_name"] == "My Custom Agent"

    def test_create_conflict_with_builtin(self):
        resp = client.post("/api/a-cal/developer/agents", json={
            "name": "a_cal_conductor",
            "display_name": "Fake",
            "description": "Fake",
            "system_prompt": "Fake",
        })
        assert resp.status_code == 409

    def test_update_custom_agent(self):
        _create_agent("updatable_agent")
        resp = client.patch("/api/a-cal/developer/agents/updatable_agent", json={
            "display_name": "Updated Name",
            "system_prompt": "New prompt",
        })
        assert resp.status_code == 200
        assert resp.json()["display_name"] == "Updated Name"

    def test_update_builtin_forbidden(self):
        resp = client.patch("/api/a-cal/developer/agents/a_cal_conductor", json={
            "display_name": "Hacked",
        })
        assert resp.status_code == 403

    def test_delete_custom_agent(self):
        _create_agent("deletable_agent")
        resp = client.delete("/api/a-cal/developer/agents/deletable_agent")
        assert resp.status_code == 200
        assert resp.json()["deleted"] is True

    def test_delete_builtin_forbidden(self):
        resp = client.delete("/api/a-cal/developer/agents/a_cal_conductor")
        assert resp.status_code == 403

    def test_delete_nonexistent(self):
        resp = client.delete("/api/a-cal/developer/agents/nonexistent_agent")
        assert resp.status_code == 404


class TestConfigExportImport:
    def test_export_config(self):
        resp = client.post("/api/a-cal/developer/config/export", json={
            "include_sub_accounts": True,
            "include_plugins": True,
            "include_custom_agents": True,
        })
        assert resp.status_code == 200
        data = resp.json()
        assert data["schema_version"]
        assert "mode" in data
        assert "model_routing" in data

    def test_import_config(self):
        # First export
        export_resp = client.post("/api/a-cal/developer/config/export", json={
            "include_sub_accounts": False,
            "include_plugins": False,
            "include_custom_agents": False,
        })
        exported = export_resp.json()

        # Then import it back
        resp = client.post("/api/a-cal/developer/config/import", json={
            "config": exported,
        })
        assert resp.status_code == 200
        data = resp.json()
        assert "imported" in data
        assert data["errors"] == []

    def test_import_with_warnings(self):
        resp = client.post("/api/a-cal/developer/config/import", json={
            "config": {"schema_version": "0.0.0"},
        })
        assert resp.status_code == 200
        data = resp.json()
        assert len(data["warnings"]) > 0


# --- P1-1: Plugin runtime gated behind A_CAL_ENABLE_PLUGINS flag -----------

class TestPluginRuntimeFlag:
    """Plugin runtime endpoints return 404 when the flag is off."""

    def test_endpoints_404_when_flag_off(self):
        """All /plugins/runtime/* endpoints return 404 when flag is off."""
        import os
        from fastapi.testclient import TestClient
        from a_cal.api.standalone import app

        # Ensure flag is not set
        old = os.environ.get("A_CAL_ENABLE_PLUGINS")
        os.environ.pop("A_CAL_ENABLE_PLUGINS", None)
        try:
            client = TestClient(app)
            client.post("/api/a-cal/auth/demo-login")
            assert client.get("/api/a-cal/developer/plugins/runtime/list").status_code == 404
            assert client.post("/api/a-cal/developer/plugins/runtime/scan").status_code == 404
            assert client.get("/api/a-cal/developer/plugins/runtime/hooks").status_code == 404
        finally:
            if old is not None:
                os.environ["A_CAL_ENABLE_PLUGINS"] = old

    def test_endpoints_accessible_when_flag_on(self):
        """Plugin runtime endpoints work when A_CAL_ENABLE_PLUGINS=1."""
        import os
        from fastapi.testclient import TestClient
        from a_cal.api.standalone import app

        old = os.environ.get("A_CAL_ENABLE_PLUGINS")
        os.environ["A_CAL_ENABLE_PLUGINS"] = "1"
        try:
            client = TestClient(app)
            client.post("/api/a-cal/auth/demo-login")
            r = client.get("/api/a-cal/developer/plugins/runtime/hooks")
            assert r.status_code == 200
            assert "hooks" in r.json()
        finally:
            if old is not None:
                os.environ["A_CAL_ENABLE_PLUGINS"] = old
            else:
                os.environ.pop("A_CAL_ENABLE_PLUGINS", None)
