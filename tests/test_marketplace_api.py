"""Tests for the marketplace API endpoints.

Uses FastAPI's TestClient to verify the HTTP layer: list, get, search,
publish, install, remix, rate.
"""

from __future__ import annotations

from fastapi import FastAPI
from fastapi.testclient import TestClient

from a_cal.api.marketplace_routes import router as marketplace_router

app = FastAPI()
app.include_router(marketplace_router)

client = TestClient(app)


def _publish_item(name: str = "Test Agent") -> dict:
    """Helper: publish an item and return the response."""
    resp = client.post("/api/a-cal/marketplace/items", json={
        "name": name,
        "item_type": "agent_spec",
        "description": "A test agent",
        "provenance": {
            "summary": "Test summary",
            "what_it_does": "Does things",
            "gaps_and_limits": "Limited",
            "integration_notes": "Plugs in here",
        },
        "config": {"prompt": "You are a test agent"},
        "tags": ["test", "agent"],
    })
    assert resp.status_code == 200
    return resp.json()


class TestListItems:
    def test_list_returns_seeded_items(self):
        resp = client.get("/api/a-cal/marketplace/items")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data) >= 3  # seeded built-ins

    def test_list_filter_by_type(self):
        resp = client.get("/api/a-cal/marketplace/items?item_type=agent_spec")
        assert resp.status_code == 200
        data = resp.json()
        assert all(i["item_type"] == "agent_spec" for i in data)

    def test_list_filter_by_tag(self):
        resp = client.get("/api/a-cal/marketplace/items?tag=focus")
        assert resp.status_code == 200
        data = resp.json()
        assert all("focus" in i["tags"] for i in data)


class TestGetItem:
    def test_get_existing_item(self):
        items = client.get("/api/a-cal/marketplace/items").json()
        item_id = items[0]["id"]

        resp = client.get(f"/api/a-cal/marketplace/items/{item_id}")
        assert resp.status_code == 200
        assert resp.json()["id"] == item_id

    def test_get_nonexistent_returns_404(self):
        resp = client.get("/api/a-cal/marketplace/items/nonexistent")
        assert resp.status_code == 404


class TestSearch:
    def test_search_finds_items(self):
        resp = client.get("/api/a-cal/marketplace/search?q=focus")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data) >= 1

    def test_search_no_results(self):
        resp = client.get("/api/a-cal/marketplace/search?q=zzzznonexistent")
        assert resp.status_code == 200
        assert len(resp.json()) == 0


class TestPublish:
    def test_publish_item(self):
        data = _publish_item("My Custom Agent")
        assert data["name"] == "My Custom Agent"
        assert data["item_type"] == "agent_spec"
        assert data["id"]  # UUID assigned

    def test_published_item_appears_in_list(self):
        _publish_item("Unique Name for Listing Test")
        items = client.get("/api/a-cal/marketplace/items").json()
        names = [i["name"] for i in items]
        assert "Unique Name for Listing Test" in names


class TestInstall:
    def test_install_item(self):
        item = _publish_item("Installable Agent")
        resp = client.post(f"/api/a-cal/marketplace/items/{item['id']}/install")
        assert resp.status_code == 200
        data = resp.json()
        assert data["item_id"] == item["id"]
        assert data["installed_config"] == item["config"]

    def test_install_nonexistent_returns_404(self):
        resp = client.post("/api/a-cal/marketplace/items/nonexistent/install")
        assert resp.status_code == 404

    def test_get_user_installs(self):
        item = _publish_item("Another Installable")
        client.post(f"/api/a-cal/marketplace/items/{item['id']}/install")

        resp = client.get("/api/a-cal/marketplace/installs")
        assert resp.status_code == 200
        data = resp.json()
        assert any(r["item_id"] == item["id"] for r in data)

    def test_install_increments_count(self):
        item = _publish_item("Count Test")
        client.post(f"/api/a-cal/marketplace/items/{item['id']}/install")
        client.post(f"/api/a-cal/marketplace/items/{item['id']}/install")

        updated = client.get(f"/api/a-cal/marketplace/items/{item['id']}").json()
        assert updated["install_count"] == 2


class TestRemix:
    def test_remix_item(self):
        parent = _publish_item("Original for Remix")
        resp = client.post(f"/api/a-cal/marketplace/items/{parent['id']}/remix", json={
            "parent_item_id": parent["id"],
            "name": "Remixed Version",
            "description": "My improved version",
            "config_overrides": {"new_key": "new_value"},
            "changes_summary": "Added new_key",
        })
        assert resp.status_code == 200
        data = resp.json()
        assert data["name"] == "Remixed Version"
        assert data["remixed_from"] == parent["id"]
        assert data["config"]["new_key"] == "new_value"

    def test_remix_nonexistent_returns_404(self):
        resp = client.post("/api/a-cal/marketplace/items/nonexistent/remix", json={
            "parent_item_id": "nonexistent",
            "name": "Test",
            "description": "",
            "config_overrides": {},
        })
        assert resp.status_code == 404

    def test_get_remixes_of_item(self):
        parent = _publish_item("Parent for Remix List")
        client.post(f"/api/a-cal/marketplace/items/{parent['id']}/remix", json={
            "parent_item_id": parent["id"],
            "name": "Remix 1",
            "description": "",
            "config_overrides": {},
        })
        client.post(f"/api/a-cal/marketplace/items/{parent['id']}/remix", json={
            "parent_item_id": parent["id"],
            "name": "Remix 2",
            "description": "",
            "config_overrides": {},
        })

        resp = client.get(f"/api/a-cal/marketplace/items/{parent['id']}/remixes")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data) == 2

    def test_remix_chain(self):
        grandparent = _publish_item("GP")
        parent = client.post(f"/api/a-cal/marketplace/items/{grandparent['id']}/remix", json={
            "parent_item_id": grandparent["id"],
            "name": "Parent",
            "description": "",
            "config_overrides": {},
        }).json()
        child = client.post(f"/api/a-cal/marketplace/items/{parent['id']}/remix", json={
            "parent_item_id": parent["id"],
            "name": "Child",
            "description": "",
            "config_overrides": {},
        }).json()

        resp = client.get(f"/api/a-cal/marketplace/items/{child['id']}/remix-chain")
        assert resp.status_code == 200
        chain = resp.json()
        assert len(chain) == 2


class TestRate:
    def test_rate_item(self):
        item = _publish_item("Rateable Agent")
        resp = client.post(f"/api/a-cal/marketplace/items/{item['id']}/rate", json={
            "stars": 4.5,
        })
        assert resp.status_code == 200
        data = resp.json()
        assert data["rating_count"] == 1
        assert data["rating"] == 4.5

    def test_rate_nonexistent_returns_404(self):
        resp = client.post("/api/a-cal/marketplace/items/nonexistent/rate", json={
            "stars": 3.0,
        })
        assert resp.status_code == 404
