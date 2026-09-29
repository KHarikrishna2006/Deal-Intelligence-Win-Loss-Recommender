from __future__ import annotations

import random
import sys
import uuid
from datetime import datetime, timedelta
from decimal import Decimal
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.config import settings
from app.core.security import hash_password
from app.models import (
    Competitor,
    Contact,
    Customer,
    Deal,
    DealCompetitor,
    DealEvent,
    DealObjection,
    DealStageCatalog,
    Interaction,
    InteractionParticipant,
    MemoryKind,
    MemoryReference,
    Objection,
    Organization,
    User,
)
from app.models.enums import (
    DealEventType,
    DealOutcome,
    DealStage,
    DealStatus,
    InteractionType,
    Role,
)
from app.services.memory_service import MemoryService

DEMO_SLUG = "northwind"

DEMO_USERS = [
    ("admin@northwind-analytics.com", "Avery Nakamura", Role.ADMIN, "VP Revenue Operations"),
    ("manager@northwind-analytics.com", "Priya Raman", Role.SALES_MANAGER, "Sales Manager, Enterprise"),
    ("rep@northwind-analytics.com", "Marcus Ellery", Role.SALES_REP, "Account Executive"),
]

STAGES = [
    (DealStage.LEAD, "Lead", 10, False, False),
    (DealStage.QUALIFICATION, "Qualification", 25, False, False),
    (DealStage.DISCOVERY, "Discovery", 40, False, False),
    (DealStage.PROPOSAL, "Proposal", 60, False, False),
    (DealStage.NEGOTIATION, "Negotiation", 80, False, False),
    (DealStage.CLOSED_WON, "Closed Won", 100, True, False),
    (DealStage.CLOSED_LOST, "Closed Lost", 0, False, True),
]

CUSTOMERS = [
    ("Acme Manufacturing", "acme-mfg.com", "Manufacturing", "Enterprise", "EMEA", 4200),
    ("Bluepeak Financial", "bluepeak.financial", "Financial Services", "Enterprise", "AMER", 8800),
    ("Cedar Health", "cedarhealth.org", "Healthcare", "Mid-Market", "AMER", 1500),
    ("Driftline Logistics", "driftline.io", "Logistics", "Mid-Market", "APAC", 950),
    ("Everline Retail", "everline.com", "Retail", "Enterprise", "EMEA", 12000),
    ("Fernwood Energy", "fernwood.energy", "Energy", "Mid-Market", "EMEA", 2400),
    ("Granite Insurance", "granite-ins.com", "Insurance", "Enterprise", "AMER", 6100),
    ("Helios Media", "helios.media", "Media", "SMB", "APAC", 380),
    ("Ironbark Systems", "ironbark.systems", "Technology", "Mid-Market", "AMER", 1900),
    ("Juniper Foods", "juniperfoods.com", "Consumer Goods", "SMB", "EMEA", 620),
]

COMPETITORS = [
    ("Salesforce", "Suite"),
    ("HubSpot", "SMB Suite"),
    ("Outreach", "Sales Engagement"),
    ("Gong", "Revenue Intelligence"),
    ("Clari", "Forecasting"),
    ("Insider", "Vertical Incumbent"),
]

OBJECTIONS = [
    ("Budget frozen until next quarter", "Pricing"),
    ("Incumbent contract not expired", "Timing"),
    ("Security review incomplete", "Security"),
    ("Implementation bandwidth", "Capacity"),
    ("Missing required integration", "Product"),
    ("Champion left the company", "Relationship"),
    ("Price higher than competitor", "Pricing"),
    ("Unclear ROI", "Value"),
]

DEAL_BLUEPRINTS = [
    # (customer index, name, stage, outcome, amount, days_ago_close, competitors, objections)
    (0, "Acme - Plant analytics rollout", DealStage.CLOSED_WON, DealOutcome.WON, 185000, 64, ["Clari"], ["Unclear ROI"]),
    (1, "Bluepeak - Advisor productivity", DealStage.CLOSED_WON, DealOutcome.WON, 240000, 41, ["Salesforce"], ["Security review incomplete"]),
    (2, "Cedar - Care team expansion", DealStage.CLOSED_LOST, DealOutcome.LOST, 96000, 88, ["Salesforce", "HubSpot"], ["Budget frozen until next quarter"]),
    (3, "Driftline - Fleet visibility", DealStage.CLOSED_LOST, DealOutcome.LOST, 74000, 55, ["Insider"], ["Price higher than competitor"]),
    (4, "Everline - Store operations", DealStage.CLOSED_WON, DealOutcome.WON, 310000, 27, ["Salesforce"], ["Incumbent contract not expired"]),
    (5, "Fernfield - Field sales rebuild", DealStage.CLOSED_LOST, DealOutcome.LOST, 61000, 119, ["Outreach", "Gong"], ["Budget frozen until next quarter", "Missing required integration"]),
    (6, "Granite - Underwriter workspace", DealStage.CLOSED_WON, DealOutcome.WON, 275000, 33, ["Clari", "Gong"], ["Security review incomplete"]),
    (7, "Helios - Agency pipeline", DealStage.CLOSED_LOST, DealOutcome.LOST, 38000, 76, ["HubSpot"], ["Champion left the company"]),
    (8, "Ironbark - Solutions engineering", DealStage.CLOSED_WON, DealOutcome.WON, 128000, 15, ["Gong"], ["Unclear ROI"]),
    (9, "Juniper - Broker network", DealStage.CLOSED_LOST, DealOutcome.LOST, 45000, 97, ["HubSpot", "Insider"], ["Implementation bandwidth"]),
    (0, "Acme - Supplier quality module", DealStage.NEGOTIATION, None, 143000, None, ["Insider"], ["Budget frozen until next quarter"]),
    (1, "Bluepeak - Risk desk expansion", DealStage.PROPOSAL, None, 198000, None, ["Clari"], ["Security review incomplete"]),
    (4, "Everline - Loyalty workspace", DealStage.DISCOVERY, None, 122000, None, ["Salesforce"], ["Missing required integration"]),
    (6, "Granite - Claims automation", DealStage.QUALIFICATION, None, 167000, None, ["Salesforce"], []),
    (8, "Ironbark - Partner portal", DealStage.PROPOSAL, None, 88000, None, ["Outreach"], ["Implementation bandwidth"]),
    (2, "Cedar - Revenue cycle pilot", DealStage.DISCOVERY, None, 52000, None, ["HubSpot"], ["Unclear ROI"]),
    (3, "Driftline - Yard scheduling", DealStage.LEAD, None, 34000, None, [], []),
    (5, "Fernfield - Contractor CRM", DealStage.QUALIFICATION, None, 71000, None, ["HubSpot"], ["Price higher than competitor"]),
]

INTERACTION_TEMPLATES: dict[str, list[tuple[str, str, str]]] = {
    "DISCOVERY": [
        (
            "Discovery call",
            "MEETING",
            "Mapped the current workflow, the number of reps affected and how they "
            "measure adoption today. Buyer asked for a security packet and a rough "
            "implementation timeline.",
        ),
        (
            "Technical deep dive",
            "MEETING",
            "Walked through SSO, data residency and the export API. Engineering lead "
            "confirmed the integration path, flagged one gap in the webhook payload.",
        ),
    ],
    "PROPOSAL": [
        (
            "Proposal walkthrough",
            "MEETING",
            "Presented the commercial proposal with a three-year ramp. Procurement "
            "asked for a discount ladder and payment terms tied to rollout milestones.",
        ),
        (
            "Proposal sent",
            "EMAIL",
            "Shared the proposal deck, pricing sheet and the reference architecture. "
            "Asked for feedback before the procurement review.",
        ),
    ],
    "NEGOTIATION": [
        (
            "Pricing negotiation",
            "PRICING_DISCUSSION",
            "Buyer pushed back on list price and asked for a 15 percent uplift cap. "
            "Legal redlines received on the master agreement.",
        ),
    ],
    "QUALIFICATION": [
        (
            "Qualification call",
            "CALL",
            "Confirmed budget owner, timeline and the reason for change. Deal is a "
            "reasonable fit but there is no executive sponsor yet.",
        ),
    ],
    "LEAD": [
        (
            "Inbound follow-up",
            "EMAIL",
            "Responded to the inbound request and proposed a short intro call next week.",
        ),
    ],
}

CLOSED_TEMPLATES = [
    (
        "Executive alignment",
        "MEETING",
        "Sponsor signed off on the business case and confirmed the rollout window for "
        "the coming quarter.",
    ),
    (
        "Final commercial review",
        "MEETING",
        "Reviewed the final order form, support tier and success plan. No open "
        "commercial issues remained.",
    ),
]


def _stage_catalog(session: Session) -> None:
    existing = {s.key for s in session.execute(select(DealStageCatalog)).scalars()}
    for index, (stage, label, _prob, won, lost) in enumerate(STAGES):
        if stage.value in existing:
            continue
        session.add(
            DealStageCatalog(
                key=stage.value,
                label=label,
                position=index,
                is_won=won,
                is_lost=lost,
                description=f"{label} stage of the standard B2B pipeline.",
            )
        )
    session.flush()


def _one(session: Session, model: Any, **filters: Any) -> Any | None:
    stmt = select(model)
    for key, value in filters.items():
        stmt = stmt.where(getattr(model, key) == value)
    return session.execute(stmt).scalars().first()


def seed_demo_data(session: Session, *, retain_memory: bool = True) -> dict[str, Any]:
    """Creates a self-contained demo organisation.

    Idempotent: running it twice does not duplicate anything.
    """
    password_hash = hash_password(settings.seed_demo_password)
    rng = random.Random(20260928)

    org = _one(session, Organization, slug=DEMO_SLUG)
    if org is None:
        org = Organization(
            name="Northwind Analytics",
            slug=DEMO_SLUG,
            industry="Software",
            is_demo=True,
        )
        session.add(org)
        session.flush()

    _stage_catalog(session)

    users: dict[str, User] = {}
    for email, name, role, title in DEMO_USERS:
        user = _one(session, User, email=email)
        if user is None:
            user = User(
                organization_id=org.id,
                email=email,
                full_name=name,
                password_hash=password_hash,
                role=role.value,
                title=title,
                is_active=True,
            )
            session.add(user)
            session.flush()
        users[role.value] = user

    owner = users[Role.SALES_REP.value]
    manager = users[Role.SALES_MANAGER.value]

    customers: list[Customer] = []
    for name, domain, industry, segment, region, employees in CUSTOMERS:
        customer = _one(session, Customer, organization_id=org.id, name=name)
        if customer is None:
            customer = Customer(
                organization_id=org.id,
                name=name,
                domain=domain,
                industry=industry,
                segment=segment,
                region=region,
                employee_count=employees,
                is_demo=True,
                notes=f"Seeded demo account in the {industry} vertical.",
            )
            session.add(customer)
            session.flush()
            session.add(
                Contact(
                    organization_id=org.id,
                    customer_id=customer.id,
                    full_name=f"Jordan Reyes - {name.split()[0]}",
                    title="VP Operations",
                    email=f"jordan.reyes@{domain}",
                    is_decision_maker=True,
                    influence="HIGH",
                )
            )
            session.add(
                Contact(
                    organization_id=org.id,
                    customer_id=customer.id,
                    full_name=f"Sam Okafor - {name.split()[0]}",
                    title="Procurement Lead",
                    email=f"sam.okafor@{domain}",
                    is_procurement=True,
                    influence="MEDIUM",
                )
            )
        customers.append(customer)

    competitors: dict[str, Competitor] = {}
    for name, category in COMPETITORS:
        row = _one(session, Competitor, organization_id=org.id, name=name)
        if row is None:
            row = Competitor(organization_id=org.id, name=name, category=category)
            session.add(row)
            session.flush()
        competitors[name] = row

    objections: dict[str, Objection] = {}
    for label, category in OBJECTIONS:
        row = _one(session, Objection, organization_id=org.id, label=label)
        if row is None:
            row = Objection(organization_id=org.id, label=label, category=category)
            session.add(row)
            session.flush()
        objections[label] = row

    now = datetime.utcnow()
    deals: list[Deal] = []
    for blueprint in DEAL_BLUEPRINTS:
        cust_index, deal_name, stage, outcome, amount, days_ago, comp_names, objection_names = blueprint
        deal = _one(session, Deal, organization_id=org.id, name=deal_name)
        if deal is not None:
            deals.append(deal)
            continue

        closed = outcome is not None
        close_days = days_ago if days_ago is not None else rng.randint(20, 160)
        close_dt = now - timedelta(days=close_days) if closed else None
        start_days = close_days + rng.randint(30, 120)
        opened = now - timedelta(days=start_days)

        deal = Deal(
            organization_id=org.id,
            customer_id=customers[cust_index].id,
            owner_id=owner.id if closed else (owner.id if rng.random() > 0.4 else manager.id),
            name=deal_name,
            description=(
                f"{customers[cust_index].name} evaluated the platform for a "
                f"{stage.value.lower().replace('_', ' ')} motion."
            ),
            amount=Decimal(amount),
            currency="USD",
            stage=stage.value,
            probability={
                DealStage.LEAD: 10,
                DealStage.QUALIFICATION: 25,
                DealStage.DISCOVERY: 40,
                DealStage.PROPOSAL: 60,
                DealStage.NEGOTIATION: 80,
                DealStage.CLOSED_WON: 100,
                DealStage.CLOSED_LOST: 0,
            }[stage],
            expected_close_date=(close_dt.date() if closed else (now + timedelta(days=rng.randint(10, 80))).date()),
            status=DealStatus.CLOSED.value if closed else DealStatus.OPEN.value,
            outcome=outcome.value if outcome else None,
            win_reason=(
                "Strong executive sponsor and a clear measurable ROI case."
                if outcome == DealOutcome.WON
                else None
            ),
            loss_reason=(
                "Lost on commercial terms after a competitor offered a lower entry price."
                if outcome == DealOutcome.LOST
                else None
            ),
            closed_at=close_dt,
            last_activity_at=close_dt or (now - timedelta(days=rng.randint(1, 20))),
            next_action=None if closed else "Confirm the economic buyer and the decision date.",
            is_demo=True,
        )
        session.add(deal)
        session.flush()
        deals.append(deal)

        for name in comp_names:
            session.add(
                DealCompetitor(
                    deal_id=deal.id,
                    competitor_id=competitors[name].id,
                    strength="HIGH" if outcome == DealOutcome.LOST else "MEDIUM",
                    notes=f"{name} was actively evaluated in this cycle.",
                )
            )
        for label in objection_names:
            session.add(
                DealObjection(
                    deal_id=deal.id,
                    objection_id=objections[label].id,
                    status="OPEN" if not closed else "RESOLVED",
                    raised_at=opened + timedelta(days=rng.randint(5, 40)),
                    resolution=None if not closed else "Addressed during the commercial review.",
                )
            )
        session.flush()

        # --- interactions -------------------------------------------------
        templates = list(INTERACTION_TEMPLATES.get(stage.value, INTERACTION_TEMPLATES["QUALIFICATION"]))
        if closed:
            templates = templates + CLOSED_TEMPLATES
        span_days = max(1, ((close_dt or now) - opened).days)
        for position, (title, itype, body) in enumerate(templates[:4]):
            occurred = opened + timedelta(days=int(span_days * (position + 1) / (len(templates) + 1)))
            price = None
            if itype == InteractionType.PRICING_DISCUSSION.value or position == len(templates) - 1:
                price = Decimal(amount) * Decimal(str(rng.uniform(0.92, 1.08))).quantize(Decimal("0.01"))
            interaction = Interaction(
                organization_id=org.id,
                deal_id=deal.id,
                author_id=owner.id,
                customer_id=customers[cust_index].id,
                interaction_type=itype,
                title=title,
                body=body,
                channel="video" if itype == "MEETING" else "email",
                direction="OUTBOUND" if position % 2 == 0 else "INBOUND",
                duration_minutes=rng.randint(20, 55) if itype == "MEETING" else None,
                sentiment=(
                    "NEGATIVE" if outcome == DealOutcome.LOST and position == len(templates) - 1
                    else "POSITIVE" if position == 0 else "NEUTRAL"
                ),
                price_discussed=price,
                currency="USD" if price else None,
                commitments=[f"Send {title.lower()} follow-up within 3 business days"],
                requirements=["SSO", "Audit log export"],
                source="SEED",
                occurred_at=occurred,
                is_demo=True,
            )
            session.add(interaction)
            session.flush()
            session.add(
                InteractionParticipant(
                    interaction_id=interaction.id,
                    name=users[Role.SALES_REP.value].full_name,
                    role="Account Executive",
                    side="INTERNAL",
                )
            )
            session.add(
                InteractionParticipant(
                    interaction_id=interaction.id,
                    contact_id=session.execute(
                        select(Contact.id).where(Contact.customer_id == customers[cust_index].id)
                    ).scalars().first(),
                    name=f"Jordan Reyes - {customers[cust_index].name.split()[0]}",
                    role="VP Operations",
                    side="CUSTOMER",
                )
            )

        session.add(
            DealEvent(
                deal_id=deal.id,
                organization_id=org.id,
                actor_id=owner.id,
                event_type=DealEventType.DEAL_CREATED.value,
                title=f"Deal created: {deal.name}",
                detail=f"Opened in the {stage.value} stage for {deal.amount} {deal.currency}.",
                occurred_at=opened,
            )
        )
        if closed:
            session.add(
                DealEvent(
                    deal_id=deal.id,
                    organization_id=org.id,
                    actor_id=manager.id,
                    event_type=DealEventType.OUTCOME_RECORDED.value,
                    title=f"Outcome recorded: {outcome.value}",
                    detail=deal.win_reason or deal.loss_reason or "Outcome recorded.",
                    payload={"outcome": outcome.value},
                    occurred_at=close_dt,
                )
            )

    session.flush()

    summary = {
        "organization": org.name,
        "users": [u for u, *_ in DEMO_USERS],
        "customers": len(customers),
        "deals": len(deals),
        "memory_retained": 0,
    }

    if retain_memory:
        summary["memory_retained"] = _retain_demo_memory(session, org, deals)

    return summary


def _retain_demo_memory(session: Session, org: Organization, deals: list[Deal]) -> int:
    """Best effort: mirrors what the API does when an interaction is logged."""
    service = MemoryService(session)
    retained = 0
    already = session.execute(
        select(func.count()).select_from(MemoryReference).where(
            MemoryReference.organization_id == org.id
        )
    ).scalar_one()
    if already:
        return 0

    for deal in deals:
        try:
            service.retain(
                org.id,
                content=MemoryService.build_deal_context_memory(
                    deal, deal.customer.name if deal.customer else "unknown"
                ),
                kind=MemoryKind.DEAL_CONTEXT.value,
                deal=deal,
                context="Seeded deal context",
                tags=["seed", f"stage:{deal.stage}"],
            )
            retained += 1
            if deal.outcome:
                service.retain(
                    org.id,
                    content=MemoryService.build_outcome_memory(
                        deal, deal.customer.name if deal.customer else "unknown"
                    ),
                    kind=MemoryKind.OUTCOME.value,
                    deal=deal,
                    context="Seeded deal outcome",
                    tags=["seed", f"outcome:{deal.outcome}"],
                )
                retained += 1
        except Exception as exc:  # noqa: BLE001 - memory is optional during seeding
            print(f"  memory retain skipped for {deal.name}: {exc}")
            break
    return retained


def main() -> int:
    from app.db.session import SessionLocal

    if not settings.seed_demo_data:
        print("SEED_DEMO_DATA is disabled; skipping the demo seed.")
        return 0

    session = SessionLocal()
    try:
        summary = seed_demo_data(session)
        session.commit()
        print("Seed complete:")
        for key, value in summary.items():
            print(f"  {key}: {value}")
        print(f"  password: {settings.seed_demo_password}")
        return 0
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


if __name__ == "__main__":
    sys.exit(main())
