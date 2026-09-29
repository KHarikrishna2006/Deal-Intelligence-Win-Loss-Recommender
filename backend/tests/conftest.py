from __future__ import annotations

import os
import uuid

# These must be set before any application module is imported.
os.environ["DATABASE_URL"] = (
    "postgresql+psycopg2://deal:deal@localhost:5432/deal_intelligence_test"
)
os.environ["ENVIRONMENT"] = "test"
os.environ["SEED_DEMO_DATA"] = "false"
os.environ["HINDSIGHT_ENABLED"] = "false"
os.environ["HINDSIGHT_URL"] = "http://127.0.0.1:8888"
# A closed port so the LLM health probe fails fast and deterministically.
os.environ["LLM_BASE_URL"] = "http://127.0.0.1:9/v1"
os.environ["JWT_SECRET"] = "test-secret"
os.environ["LOG_LEVEL"] = "WARNING"

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402
from sqlalchemy import create_engine, text  # noqa: E402
from sqlalchemy.orm import sessionmaker  # noqa: E402

from app.config import settings  # noqa: E402
from app.db.base import Base, dumps  # noqa: E402
from app.db.session import get_db  # noqa: E402
from app.main import create_app  # noqa: E402
from app.models import (  # noqa: E402
    Competitor,
    Customer,
    Deal,
    DealCompetitor,
    DealObjection,
    Interaction,
    Objection,
    Organization,
    User,
)
from app.models.enums import DealStage, DealStatus, InteractionType, Role  # noqa: E402

ADMIN_EMAIL = "admin@acme.example.com"
REP_EMAIL = "rep@acme.example.com"
PASSWORD = "correct-horse-battery"
OTHER_ORG_EMAIL = "admin@rival.example.com"


@pytest.fixture(scope="session")
def engine():
    admin_engine = create_engine(
        "postgresql+psycopg2://deal:deal@localhost:5432/postgres",
        isolation_level="AUTOCOMMIT",
        future=True,
    )
    with admin_engine.connect() as conn:
        exists = conn.execute(
            text("SELECT 1 FROM pg_database WHERE datname = 'deal_intelligence_test'")
        ).scalar()
        if not exists:
            conn.execute(text("CREATE DATABASE deal_intelligence_test"))
    admin_engine.dispose()

    engine = create_engine(settings.database_url, future=True, json_serializer=dumps)
    Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)
    yield engine
    Base.metadata.drop_all(engine)
    engine.dispose()


@pytest.fixture()
def db(engine):
    TestingSession = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
    session = TestingSession()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


@pytest.fixture(scope="session")
def client(engine):
    app = create_app()
    TestingSession = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)

    def override_db():
        session = TestingSession()
        try:
            yield session
            session.commit()
        except Exception:
            session.rollback()
            raise
        finally:
            session.close()

    app.dependency_overrides[get_db] = override_db
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()


@pytest.fixture(scope="session")
def seed(engine):
    Session = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
    session = Session()

    org = Organization(name="Acme", slug=f"acme-{uuid.uuid4().hex[:8]}")
    rival = Organization(name="Rival", slug=f"rival-{uuid.uuid4().hex[:8]}")
    session.add_all([org, rival])
    session.flush()

    from app.core.security import hash_password

    admin = User(
        organization_id=org.id,
        email=ADMIN_EMAIL,
        password_hash=hash_password(PASSWORD),
        full_name="Ada Admin",
        role=Role.ADMIN.value,
    )
    rep = User(
        organization_id=org.id,
        email=REP_EMAIL,
        password_hash=hash_password(PASSWORD),
        full_name="Rory Rep",
        role=Role.SALES_REP.value,
    )
    rival_admin = User(
        organization_id=rival.id,
        email=OTHER_ORG_EMAIL,
        password_hash=hash_password(PASSWORD),
        full_name="Vic Rival",
        role=Role.ADMIN.value,
    )
    session.add_all([admin, rep, rival_admin])
    session.flush()

    customer = Customer(organization_id=org.id, name="Globex", segment="ENTERPRISE")
    other_customer = Customer(organization_id=rival.id, name="Initech")
    session.add_all([customer, other_customer])
    session.flush()

    security_review = Objection(organization_id=org.id, label="Security review incomplete")
    pricing = Objection(organization_id=org.id, label="Pricing too high")
    acme_competitor = Competitor(organization_id=org.id, name="Vectora")
    session.add_all([security_review, pricing, acme_competitor])
    session.flush()

    won = Deal(
        organization_id=org.id,
        customer_id=customer.id,
        owner_id=admin.id,
        name="Globex rollout",
        amount=120000,
        currency="USD",
        stage=DealStage.CLOSED_WON.value,
        status=DealStatus.CLOSED.value,
        outcome="WON",
        win_reason="Security review completed early",
        probability=1.0,
    )
    lost = Deal(
        organization_id=org.id,
        customer_id=customer.id,
        owner_id=admin.id,
        name="Globex expansion",
        amount=80000,
        currency="USD",
        stage=DealStage.CLOSED_LOST.value,
        status=DealStatus.CLOSED.value,
        outcome="LOST",
        loss_reason="Lost on pricing after a competitor offer",
        probability=0.0,
    )
    open_deal = Deal(
        organization_id=org.id,
        customer_id=customer.id,
        owner_id=rep.id,
        name="Globex phase two",
        amount=95000,
        currency="USD",
        stage=DealStage.PROPOSAL.value,
        status=DealStatus.OPEN.value,
        probability=0.5,
        description="Expansion into the risk desk.",
        next_action="Book the security review",
    )
    rival_deal = Deal(
        organization_id=rival.id,
        customer_id=other_customer.id,
        owner_id=rival_admin.id,
        name="Initech rollout",
        amount=50000,
        currency="USD",
        stage=DealStage.PROPOSAL.value,
        status=DealStatus.OPEN.value,
    )
    session.add_all([won, lost, open_deal, rival_deal])
    session.flush()

    session.add(
        DealCompetitor(deal_id=open_deal.id, competitor_id=acme_competitor.id)
    )
    session.add(
        DealObjection(deal_id=open_deal.id, objection_id=security_review.id)
    )
    session.add(
        Interaction(
            organization_id=org.id,
            deal_id=open_deal.id,
            customer_id=customer.id,
            author_id=admin.id,
            interaction_type=InteractionType.MEETING.value,
            title="Security workshop",
            body="Customer asked for the SOC 2 report before legal review.",
        )
    )
    session.commit()

    data = {
        "organization_id": org.id,
        "rival_organization_id": rival.id,
        "admin_id": admin.id,
        "rep_id": rep.id,
        "customer_id": customer.id,
        "won_id": won.id,
        "lost_id": lost.id,
        "open_id": open_deal.id,
        "rival_deal_id": rival_deal.id,
    }
    session.close()
    return data


def login(client: TestClient, email: str, password: str = PASSWORD) -> dict[str, str]:
    response = client.post("/api/auth/login", json={"email": email, "password": password})
    assert response.status_code == 200, response.text
    return {"Authorization": f"Bearer {response.json()['access_token']}"}
