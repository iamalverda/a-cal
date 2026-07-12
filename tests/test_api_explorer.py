"""Tests for the API Explorer endpoint.

GET /api/a-cal/developer/api-routes — lists all registered FastAPI routes
with method, path, summary, tag, and parameter metadata for the Developer
Studio's API Explorer panel.
"""

from __future__ import annotations

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from a_cal.api.developer_routes import router as developer_router


@pytest.fixture
def client():
    """Test client with developer routes mounted on a standalone app."""
    from a_cal.api.standalone import app
    return TestClient(app)


class TestApiExplorer:
    """Tests for the /developer/api-routes endpoint."""

    def test_returns_routes(self, client):
        """GET /developer/api-routes returns a non-empty list."""
        resp = client.get("/api/a-cal/developer/api-routes")
        assert resp.status_code == 200
        data = resp.json()
        assert isinstance(data, list)
        assert len(data) > 10  # we have 100+ routes

    def test_route_has_required_fields(self, client):
        """Each route has method, path, summary, tag, and param fields."""
        resp = client.get("/api/a-cal/developer/api-routes")
        data = resp.json()
        for route in data[:5]:
            assert "method" in route
            assert "path" in route
            assert "summary" in route
            assert "description" in route
            assert "tag" in route
            assert "path_params" in route
            assert "query_params" in route
            assert "body_schema" in route

    def test_includes_known_endpoints(self, client):
        """Known A-Cal endpoints appear in the route list."""
        resp = client.get("/api/a-cal/developer/api-routes")
        paths = {r["path"] for r in resp.json()}
        assert "/api/a-cal/conductor/chat" in paths
        assert "/api/a-cal/agents" in paths
        assert "/api/a-cal/developer/api-routes" in paths

    def test_routes_grouped_by_tag(self, client):
        """Routes have tags from the router definitions."""
        resp = client.get("/api/a-cal/developer/api-routes")
        tags = {r["tag"] for r in resp.json()}
        assert "a-cal-agents" in tags
        assert "a-cal-developer" in tags

    def test_post_routes_have_body_schema(self, client):
        """POST endpoints with Pydantic body models have body_schema."""
        resp = client.get("/api/a-cal/developer/api-routes")
        post_routes = [r for r in resp.json() if r["method"] == "POST"]
        # At least some POST routes should have body_schema
        with_body = [r for r in post_routes if r["body_schema"] is not None]
        assert len(with_body) > 0

    def test_path_params_detected(self, client):
        """Routes with path parameters detect them correctly."""
        resp = client.get("/api/a-cal/developer/api-routes")
        # Find a route with a path param (e.g. /event-types/{event_type_id})
        with_params = [r for r in resp.json() if len(r["path_params"]) > 0]
        assert len(with_params) > 0
        for r in with_params[:3]:
            for p in r["path_params"]:
                assert p["required"] is True
                assert p["in"] == "path"

    def test_health_route_included(self, client):
        """The /health endpoint is included."""
        resp = client.get("/api/a-cal/developer/api-routes")
        paths = {r["path"] for r in resp.json()}
        assert "/health" in paths

    def test_routes_sorted_by_tag_then_path(self, client):
        """Routes are sorted by tag then path."""
        resp = client.get("/api/a-cal/developer/api-routes")
        data = resp.json()
        for i in range(1, len(data)):
            key_prev = (data[i - 1]["tag"], data[i - 1]["path"])
            key_curr = (data[i]["tag"], data[i]["path"])
            assert key_prev <= key_curr
