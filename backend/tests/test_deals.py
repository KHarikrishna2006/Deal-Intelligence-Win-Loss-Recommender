from __future__ import annotations

from tests.conftest import ADMIN_EMAIL, OTHER_ORG_EMAIL, REP_EMAIL, login


def test_deal_list_is_scoped_to_organisation(client, seed):
    headers = login(client, ADMIN_EMAIL)
    body = client.get("/api/deals?limit=100", headers=headers).json()
    names = {item["name"] for item in body["items"]}
    assert "Globex phase two" in names
    assert "Initech rollout" not in names


def test_other_organisation_cannot_read_deal(client, seed):
    headers = login(client, OTHER_ORG_EMAIL)
    response = client.get(f"/api/deals/{seed['open_id']}", headers=headers)
    assert response.status_code == 404


def test_deal_detail_returns_evidence_context(client, seed):
    headers = login(client, ADMIN_EMAIL)
    body = client.get(f"/api/deals/{seed['open_id']}", headers=headers).json()
    assert body["name"] == "Globex phase two"
    assert body["customer_name"] == "Globex"
    assert "Vectora" in body["competitor_names"]
    assert "Security review incomplete" in body["objection_labels"]
    assert body["interaction_count"] == 1


def test_create_and_patch_deal(client, seed):
    headers = login(client, ADMIN_EMAIL)
    created = client.post(
        "/api/deals",
        headers=headers,
        json={
            "name": "Globex pilot",
            "customer_id": str(seed["customer_id"]),
            "amount": 42000,
            "stage": "DISCOVERY",
        },
    )
    assert created.status_code in {200, 201}, created.text
    deal_id = created.json()["id"]

    patched = client.patch(
        f"/api/deals/{deal_id}",
        headers=headers,
        json={"amount": 45000, "next_action": "Send security pack"},
    )
    assert patched.status_code == 200
    assert float(patched.json()["amount"]) == 45000
    assert patched.json()["next_action"] == "Send security pack"


def test_recording_outcome_moves_deal_to_closed(client, seed):
    headers = login(client, ADMIN_EMAIL)
    created = client.post(
        "/api/deals",
        headers=headers,
        json={
            "name": "Temp close test",
            "customer_id": str(seed["customer_id"]),
            "amount": 10000,
            "stage": "NEGOTIATION",
        },
    ).json()

    response = client.post(
        f"/api/deals/{created['id']}/outcome",
        headers=headers,
        json={"outcome": "WON", "reason": "Fastest security review"},
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["outcome"] == "WON"
    assert body["status"] == "CLOSED"


def test_rep_can_read_but_pipeline_aggregates_open_only(client, seed):
    headers = login(client, REP_EMAIL)
    pipeline = client.get("/api/deals/pipeline", headers=headers).json()
    assert pipeline["open_count"] >= 1
    assert float(pipeline["total_open_amount"]) > 0
    assert all(float(stage["total_amount"]) >= 0 for stage in pipeline["stages"])


def test_dashboard_and_win_loss(client, seed):
    headers = login(client, ADMIN_EMAIL)
    dashboard = client.get("/api/dashboard", headers=headers).json()
    assert dashboard["kpis"]["active_deals"] >= 1
    by_label = {row["label"]: row["value"] for row in dashboard["win_loss"]}
    assert by_label["Won"] >= 1
    assert by_label["Lost"] >= 1

    win_loss = client.get("/api/analytics/win-loss", headers=headers).json()
    assert win_loss["sufficient_data"] is True
    assert win_loss["kpis"]["won_deals"] >= 1
    assert win_loss["kpis"]["lost_deals"] >= 1
    assert isinstance(win_loss["loss_reasons"], list)


def test_search_finds_deals(client, seed):
    headers = login(client, ADMIN_EMAIL)
    body = client.get("/api/search?q=Globex", headers=headers).json()
    assert body["total"] >= 1
