from __future__ import annotations

import uuid

from app.core.security import hash_password
from app.models import Customer, Deal, Organization, User
from app.models.enums import DealStage, DealStatus, Role
from tests.conftest import ADMIN_EMAIL, PASSWORD, login


def test_analyze_falls_back_to_deterministic_engine(client, seed):
    headers = login(client, ADMIN_EMAIL)
    response = client.post(
        f"/api/deals/{seed['open_id']}/analyze?regenerate=true",
        headers=headers,
        json={},
    )
    assert response.status_code == 200, response.text
    body = response.json()
    rec = body["recommendation"]

    assert rec["source"] == "DETERMINISTIC"
    assert rec["evidence_level"] in {"EVIDENCE_BASED", "LIMITED_EVIDENCE", "INSUFFICIENT_DATA"}
    assert rec["actions"], "at least one action must be returned"
    assert rec["rationale"]
    assert body["llm_status"]["available"] is False
    assert body["memory_status"]["available"] is False
    assert any("LLM" in warning for warning in body["warnings"])
    assert any("Memory-based intelligence" in warning for warning in body["warnings"])


def test_analysis_cites_real_records(client, seed):
    headers = login(client, ADMIN_EMAIL)
    body = client.post(
        f"/api/deals/{seed['open_id']}/analyze?regenerate=true",
        headers=headers,
        json={},
    ).json()

    evidence = body["recommendation"]["evidence"]
    assert isinstance(evidence, list)
    known = {str(seed["won_id"]), str(seed["lost_id"])}
    for item in evidence:
        assert item.get("deal_id") in known, "evidence must point at stored deals"
        assert item.get("deal_name")


def test_thin_history_reports_insufficient_data(client, seed, db):
    org = Organization(name="ThinCo", slug=f"thin-{uuid.uuid4().hex[:8]}")
    db.add(org)
    db.flush()
    owner = User(
        organization_id=org.id,
        email=f"thin-{uuid.uuid4().hex[:8]}@example.com",
        password_hash=hash_password(PASSWORD),
        full_name="Tina Thin",
        role=Role.ADMIN.value,
    )
    customer = Customer(organization_id=org.id, name="Thin Customer")
    db.add_all([owner, customer])
    db.flush()
    deal = Deal(
        organization_id=org.id,
        customer_id=customer.id,
        owner_id=owner.id,
        name="Thin deal",
        amount=1000,
        currency="USD",
        stage=DealStage.DISCOVERY.value,
        status=DealStatus.OPEN.value,
    )
    db.add(deal)
    db.commit()

    token = login(
        client,
        owner.email,
    )
    body = client.post(
        f"/api/deals/{deal.id}/analyze?regenerate=true",
        headers=token,
        json={},
    ).json()

    rec = body["recommendation"]
    assert rec["evidence_level"] == "INSUFFICIENT_DATA"
    assert rec["title"] == "Insufficient historical evidence."
    assert rec["evidence"] == []


def test_copilot_degrades_without_llm(client, seed):
    headers = login(client, ADMIN_EMAIL)
    response = client.post(
        f"/api/deals/{seed['open_id']}/copilot",
        headers=headers,
        json={"question": "What should I do next on this deal?"},
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["available"] is False
    assert body["answer"].strip()
    assert body["tool_trace"], "the tool trace must show what was consulted"
    assert any(step["tool"] == "deal_context" for step in body["tool_trace"])
    assert body["memory_status"]["available"] is False


def test_recommendations_are_listed_per_deal(client, seed):
    headers = login(client, ADMIN_EMAIL)
    client.post(
        f"/api/deals/{seed['open_id']}/analyze?regenerate=true",
        headers=headers,
        json={},
    )
    body = client.get(f"/api/deals/{seed['open_id']}/recommendations", headers=headers).json()
    assert body["total"] >= 1
    assert body["items"][0]["deal_id"] == str(seed["open_id"])


def test_feedback_is_recorded(client, seed):
    headers = login(client, ADMIN_EMAIL)
    client.post(
        f"/api/deals/{seed['open_id']}/analyze?regenerate=true",
        headers=headers,
        json={},
    )
    rec_id = client.get(
        f"/api/deals/{seed['open_id']}/recommendations", headers=headers
    ).json()["items"][0]["id"]
    response = client.post(
        f"/api/recommendations/{rec_id}/feedback",
        headers=headers,
        json={"feedback": "USEFUL", "comment": "Tied to real records"},
    )
    assert response.status_code == 201, response.text
    assert response.json()["feedback"] == "USEFUL"
