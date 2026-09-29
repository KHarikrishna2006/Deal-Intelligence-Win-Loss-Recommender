from __future__ import annotations

from tests.conftest import ADMIN_EMAIL, login


def test_memory_status_reports_hindsight_disabled(client, seed):
    headers = login(client, ADMIN_EMAIL)
    body = client.get("/api/memory/status", headers=headers).json()
    assert body["enabled"] is False
    assert body["available"] is False
    assert body["reason"]
    assert body["bank_id"]


def test_deal_memory_degrades_to_empty_recall(client, seed):
    headers = login(client, ADMIN_EMAIL)
    body = client.get(f"/api/deals/{seed['open_id']}/memory", headers=headers).json()
    assert body["status"]["available"] is False
    assert body["recalled"] == []
    assert isinstance(body["references"], list)
    assert body["recall_status"]["available"] is False


def test_similar_deals_do_not_require_hindsight(client, seed):
    headers = login(client, ADMIN_EMAIL)
    body = client.get(f"/api/deals/{seed['open_id']}/similar", headers=headers).json()
    assert set(body) >= {"deal_id", "similar_deals", "memory_hits", "memory_status"}
    assert body["memory_status"]["available"] is False
    assert body["structured_count"] >= 1, "structured similarity must work without memory"


def test_memory_search_returns_local_rows_without_hindsight(client, seed):
    headers = login(client, ADMIN_EMAIL)
    body = client.get("/api/memory/search?q=pricing", headers=headers).json()
    assert body["query"] == "pricing"
    assert isinstance(body["local"], list)
    assert body["remote_status"]["available"] is False


def test_memory_timeline_requires_deal_id(client, seed):
    headers = login(client, ADMIN_EMAIL)
    assert client.get("/api/memory/timeline", headers=headers).status_code == 404
    ok = client.get(
        f"/api/memory/timeline?deal_id={seed['open_id']}", headers=headers
    )
    assert ok.status_code == 200
    assert isinstance(ok.json()["items"], list)
