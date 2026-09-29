from __future__ import annotations

import uuid
from typing import Any, Optional

from sqlalchemy.orm import Session

from app.core.logging import get_logger
from app.models import Deal, Recommendation
from app.models.enums import EvidenceLevel, RecommendationKind, RecommendationSource
from app.repositories.recommendation_repository import RecommendationRepository
from app.services.llm_service import LLMService, LLMUnavailableError
from app.services.memory_service import MemoryService
from app.services.risk_service import RiskService
from app.services.similarity_service import SimilarDealService

logger = get_logger(__name__)

_INSUFFICIENT = "Insufficient historical evidence."

_ANALYSIS_SYSTEM = (
    "You are a B2B sales deal analyst. You are given a current deal, a set of "
    "historical deals with recorded outcomes, detected risks, and recalled "
    "memories from prior customer conversations.\n"
    "Rules:\n"
    "- Every recommendation MUST cite specific historical deals from the supplied "
    "evidence by their exact deal_name.\n"
    "- Never invent deals, customers, amounts, quotes or outcomes.\n"
    "- If the supplied evidence does not support a recommendation, say "
    "'Insufficient historical evidence.' instead of guessing.\n"
    "- Do not produce confidence percentages.\n"
    "- Return ONLY JSON with keys: summary (string), similar_patterns (array of "
    "strings), recommended_actions (array of objects with title, rationale, "
    "evidence_deals (array of exact deal_name strings), unknowns (array of strings))."
)

_ANALYSIS_SCHEMA = {
    "type": "object",
    "properties": {
        "summary": {"type": "string"},
        "similar_patterns": {"type": "array", "items": {"type": "string"}},
        "recommended_actions": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "title": {"type": "string"},
                    "rationale": {"type": "string"},
                    "evidence_deals": {"type": "array", "items": {"type": "string"}},
                },
                "required": ["title", "rationale", "evidence_deals"],
            },
        },
        "unknowns": {"type": "array", "items": {"type": "string"}},
    },
    "required": ["summary", "recommended_actions"],
}


def existing_actions(record: Recommendation) -> list[dict[str, Any]]:
    """Rehydrate the action list stored with a persisted recommendation."""
    stored = record.actions
    if isinstance(stored, list) and stored:
        return stored
    if not record.title:
        return []
    return [
        {
            "title": record.title,
            "rationale": record.rationale,
            "evidence": record.evidence or [],
            "evidence_deals": [
                str(item.get("deal_name")) for item in (record.evidence or []) if item
            ],
        }
    ]


class RecommendationService:
    def __init__(self, session: Session, llm: LLMService | None = None):
        self.session = session
        self.llm = llm or LLMService()
        self.similarity = SimilarDealService(session)
        self.risks = RiskService(session)
        self.memory = MemoryService(session)
        self.recommendations = RecommendationRepository(session)
        self._llm_probe: dict[str, Any] | None = None

    # ------------------------------------------------------------------ probe
    def llm_status(self) -> dict[str, Any]:
        if self._llm_probe is None:
            self._llm_probe = self.llm.health()
        return self._llm_probe

    # -------------------------------------------------------------- analyze
    def analyze(
        self,
        organization_id: uuid.UUID,
        deal: Deal,
        *,
        include_memory: bool = True,
        regenerate: bool = False,
        actor_id: uuid.UUID | None = None,
    ) -> dict[str, Any]:
        similar = self.similarity.find_similar(
            organization_id, deal, include_memory=include_memory
        )
        risks = self.risks.detect(organization_id, deal)
        memory_hits = similar["memory_hits"]
        memory_status = similar["memory_status"]
        llm_status = self.llm_status()
        warnings: list[str] = []
        if not memory_status.get("available") and include_memory:
            warnings.append(
                "Memory-based intelligence is temporarily unavailable: "
                f"{memory_status.get('reason') or 'Hindsight did not respond'}."
            )

        existing = None if regenerate else self.recommendations.latest_for_deal(deal.id)
        if existing is not None:
            return self._assemble(
                deal,
                existing,
                similar["similar_deals"],
                risks,
                memory_hits,
                memory_status,
                llm_status,
                warnings,
                actions=existing_actions(existing),
                all_patterns=existing.similar_patterns or [],
            )

        evidence = self._evidence_from_similar(similar["similar_deals"])
        method = RecommendationSource.DETERMINISTIC.value
        analysis: dict[str, Any] | None = None

        if llm_status.get("available"):
            try:
                analysis = self._llm_analyze(deal, similar, risks, memory_hits)
                method = RecommendationSource.LLM.value
            except LLMUnavailableError as exc:
                warnings.append(
                    "LLM analysis unavailable, fell back to the deterministic evidence engine: "
                    f"{exc.message}"
                )
            except Exception as exc:  # noqa: BLE001
                logger.exception("LLM analysis failed")
                warnings.append(
                    f"LLM analysis failed, fell back to the deterministic evidence engine: "
                    f"{type(exc).__name__}."
                )
        else:
            warnings.append(
                "No LLM is reachable, recommendations were produced by the deterministic "
                "evidence engine."
            )

        if analysis is not None:
            actions = self._validated_actions(analysis.get("recommended_actions"), evidence)
            summary = str(analysis.get("summary") or "").strip()
            patterns = [str(p) for p in analysis.get("similar_patterns") or []][:8]
            unknowns = [str(u) for u in analysis.get("unknowns") or []][:8]
            if not actions:
                warnings.append(
                    "The model produced recommendations that could not be tied to recorded "
                    "evidence, so they were discarded."
                )
        else:
            actions, summary, patterns, unknowns = self._deterministic_analysis(deal, similar, risks)

        if not actions:
            actions = [
                {
                    "title": _INSUFFICIENT,
                    "rationale": (
                        "No historical deal in this organisation both matches this opportunity "
                        "and has a recorded outcome, so there is nothing to generalise from."
                    ),
                    "evidence": [],
                    "evidence_deals": [],
                }
            ]

        evidence_level = self._evidence_level(actions)
        primary = actions[0]
        record = Recommendation(
            organization_id=organization_id,
            deal_id=deal.id,
            kind=RecommendationKind.NEXT_ACTION.value,
            title=primary["title"],
            rationale=primary["rationale"],
            summary=summary,
            actions=actions,
            evidence=primary.get("evidence") or [],
            similar_patterns=patterns,
            risks=risks,
            unknowns=unknowns,
            evidence_level=evidence_level.value,
            source=method,
            model=self.llm.model if method == RecommendationSource.LLM.value else None,
            status="ACTIVE",
        )
        self.recommendations.mark_stale_for_deal(deal.id)
        self.recommendations.add(record)
        self.session.flush()

        return self._assemble(
            deal,
            record,
            similar["similar_deals"],
            risks,
            memory_hits,
            memory_status,
            llm_status,
            warnings,
            actions=actions,
            all_patterns=patterns,
        )

    # ---------------------------------------------------------------- helpers
    @staticmethod
    def _evidence_from_similar(similar: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
        """Index usable evidence by exact deal name.

        Only closed deals with a recorded outcome can support a claim about what
        worked or what failed.
        """
        index: dict[str, dict[str, Any]] = {}
        for item in similar:
            if not item.get("outcome"):
                continue
            index[item["deal_name"]] = item
        return index

    def _validated_actions(
        self, raw_actions: Any, evidence_index: dict[str, dict[str, Any]]
    ) -> list[dict[str, Any]]:
        if not isinstance(raw_actions, list):
            return []
        validated: list[dict[str, Any]] = []
        for item in raw_actions:
            if not isinstance(item, dict):
                continue
            title = str(item.get("title") or "").strip()
            rationale = str(item.get("rationale") or "").strip()
            if not title or not rationale:
                continue
            cited = [
                str(name)
                for name in item.get("evidence_deals") or []
                if isinstance(name, (str, uuid.UUID))
            ]
            matched = [evidence_index[name] for name in cited if name in evidence_index]
            if not matched:
                continue
            validated.append(
                {
                    "title": title,
                    "rationale": rationale,
                    "evidence_deals": [m["deal_name"] for m in matched],
                    "evidence": [
                        {
                            "deal_id": m.get("deal_id"),
                            "deal_name": m["deal_name"],
                            "customer_name": m.get("customer_name"),
                            "outcome": m.get("outcome"),
                            "stage": m.get("stage"),
                            "amount": m.get("amount"),
                            "why": m.get("why_relevant", ""),
                            "source": "database",
                        }
                        for m in matched
                    ],
                }
            )
        return validated

    @staticmethod
    def _evidence_level(actions: list[dict[str, Any]]) -> EvidenceLevel:
        count = sum(len(a.get("evidence") or []) for a in actions)
        if count >= 2:
            return EvidenceLevel.EVIDENCE_BASED
        if count == 1:
            return EvidenceLevel.LIMITED_EVIDENCE
        return EvidenceLevel.INSUFFICIENT_DATA

    def _llm_analyze(
        self,
        deal: Deal,
        similar: dict[str, Any],
        risks: list[dict[str, Any]],
        memory_hits: list[dict[str, Any]],
    ) -> dict[str, Any]:
        similar_lines = []
        for item in similar["similar_deals"][:8]:
            similar_lines.append(
                f"- {item['deal_name']} | {item['customer_name']} | {item['amount']} "
                f"{item['currency']} | stage {item['stage']} | outcome {item['outcome']} | "
                f"why relevant: {item['why_relevant']}"
                + (f" | loss reason: {item['loss_reason']}" if item.get("loss_reason") else "")
                + (f" | win reason: {item['win_reason']}" if item.get("win_reason") else "")
            )
        memory_lines = [f"- {h['text'][:300]}" for h in memory_hits[:8]]
        risk_lines = [f"- {r['title']}: {r['evidence']}" for r in risks[:8]]

        user = (
            f"CURRENT DEAL\n"
            f"name: {deal.name}\n"
            f"customer: {deal.customer.name if deal.customer else 'unknown'}\n"
            f"stage: {deal.stage}\namount: {deal.amount} {deal.currency}\n"
            f"probability: {deal.probability}%\n"
            f"expected close: {deal.expected_close_date}\n"
            f"competitors: {', '.join(dc.competitor.name for dc in deal.deal_competitors) or 'none'}\n"
            f"objections: {', '.join(do.objection.label for do in deal.deal_objections) or 'none'}\n"
            f"description: {deal.description or 'n/a'}\n\n"
            f"HISTORICAL DEALS (the ONLY allowed evidence):\n"
            + ("\n".join(similar_lines) or "- none")
            + "\n\nDETECTED RISKS:\n"
            + ("\n".join(risk_lines) or "- none")
            + "\n\nRECALLED MEMORIES:\n"
            + ("\n".join(memory_lines) or "- none or unavailable")
            + "\n\nRespond with JSON only."
        )

        payload = self.llm.complete_json(
            [
                {"role": "system", "content": _ANALYSIS_SYSTEM},
                {"role": "user", "content": user},
            ],
            schema_hint=str(_ANALYSIS_SCHEMA),
            temperature=0.1,
        )
        return payload

    def _deterministic_analysis(
        self, deal: Deal, similar: dict[str, Any], risks: list[dict[str, Any]]
    ) -> tuple[list[dict[str, Any]], str, list[str], list[str]]:
        """Evidence-driven fallback used when no LLM is reachable.

        Every action below is derived from recorded outcomes - it is a rule
        engine over real rows, not a generated opinion.
        """
        items = similar["similar_deals"]
        closed = [i for i in items if i.get("outcome")]
        lost = [i for i in closed if i["outcome"] == "LOST"]
        won = [i for i in closed if i["outcome"] == "WON"]
        actions: list[dict[str, Any]] = []

        def add(title: str, rationale: str, matches: list[dict[str, Any]]) -> None:
            if not matches:
                return
            actions.append(
                {
                    "title": title,
                    "rationale": rationale,
                    "evidence_deals": [m["deal_name"] for m in matches],
                    "evidence": [
                        {
                            "deal_id": m.get("deal_id"),
                            "deal_name": m["deal_name"],
                            "customer_name": m.get("customer_name"),
                            "outcome": m.get("outcome"),
                            "stage": m.get("stage"),
                            "amount": m.get("amount"),
                            "why": m.get("why_relevant", ""),
                            "source": "database",
                        }
                        for m in matches
                    ],
                }
            )

        procurement_losses = [
            m
            for m in lost
            if any("procurement" in o.lower() for o in m.get("key_objections") or [])
            or "procurement" in (m.get("loss_reason") or "").lower()
        ]
        if procurement_losses:
            add(
                "Clarify procurement requirements before offering another discount.",
                f"{len(procurement_losses)} comparable deal(s) hit procurement objections late "
                "and were lost after pricing concessions failed to resolve them.",
                procurement_losses[:3],
            )

        pricing_losses = [
            m
            for m in lost
            if any(
                o.lower().startswith(("pricing", "budget", "cost"))
                for o in m.get("key_objections") or []
            )
            or any(
                word in (m.get("loss_reason") or "").lower()
                for word in ("pricing", "budget", "cost", "discount")
            )
        ]
        if pricing_losses:
            add(
                "Establish the cost justification before discussing a lower price.",
                f"{len(pricing_losses)} similar deal(s) were lost on price. In those cases the "
                "value case was not settled before the commercial conversation.",
                pricing_losses[:3],
            )

        competitor_names = {dc.competitor.name.lower() for dc in deal.deal_competitors}
        competitor_losses = [
            m
            for m in lost
            if competitor_names & {c.lower() for c in m.get("competitors") or []}
        ]
        if competitor_losses:
            add(
                "Pre-empt the competitive comparison in the next technical session.",
                f"{len(competitor_losses)} deal(s) against the same competitor were lost; "
                "differentiation was raised too late in those cycles.",
                competitor_losses[:3],
            )

        unresolved = [
            do.objection.label
            for do in deal.deal_objections
            if (do.status or "OPEN").upper() in ("OPEN", "RAISED")
        ]
        unresolved_losses = [
            m for m in lost if set(map(str.lower, m.get("key_objections") or [])) & {u.lower() for u in unresolved}
        ]
        if unresolved and unresolved_losses:
            add(
                f"Resolve the open '{unresolved[0]}' objection with evidence, not a concession.",
                f"The same objection is open here and appears in {len(unresolved_losses)} lost "
                "deal(s).",
                unresolved_losses[:3],
            )

        no_decision_risk = next((r for r in risks if r["key"] in ("unclear_decision_maker", "no_contacts")), None)
        stakeholder_evidence = won[:2]
        if no_decision_risk and stakeholder_evidence:
            add(
                "Map the economic buyer before the proposal stage.",
                "Deals in this organisation that were won had a named decision maker on file; "
                "this one does not.",
                stakeholder_evidence,
            )

        if not actions and won:
            add(
                "Repeat the motion that worked on comparable won deals.",
                f"{len(won)} comparable deal(s) were won; the shared pattern in those records "
                "should be verified against this opportunity.",
                won[:3],
            )

        patterns: list[str] = []
        if won:
            top_win = max(
                {m.get("win_reason") or "reason not recorded" for m in won},
                key=lambda r: sum(1 for m in won if (m.get("win_reason") or "reason not recorded") == r),
            )
            patterns.append(f"Most recorded win reason among similar deals: {top_win}")
        if lost:
            top_loss = max(
                {m.get("loss_reason") or "reason not recorded" for m in lost},
                key=lambda r: sum(1 for m in lost if (m.get("loss_reason") or "reason not recorded") == r),
            )
            patterns.append(f"Most recorded loss reason among similar deals: {top_loss}")
        if closed:
            patterns.append(
                f"{len(won)} won / {len(lost)} lost across {len(closed)} comparable closed deal(s)."
            )

        unknowns: list[str] = []
        if not closed:
            unknowns.append("No closed deal matches this profile.")
        if not deal.description:
            unknowns.append("Deal description is empty, so scope could not be compared.")
        contacts = list(deal.customer.contacts) if deal.customer else []
        if contacts and not any(c.is_decision_maker for c in contacts):
            unknowns.append("Decision maker is unknown.")
        elif not contacts:
            unknowns.append("No contacts are recorded for this customer.")
        if not (deal.next_action or "").strip():
            unknowns.append("No committed next action exists for this deal.")

        if closed:
            summary = (
                f"Compared against {len(closed)} comparable closed deal(s): "
                f"{len(won)} won, {len(lost)} lost."
            )
        else:
            summary = _INSUFFICIENT

        return actions, summary, patterns, unknowns

    def _assemble(
        self,
        deal: Deal,
        record: Recommendation,
        similar: list[dict[str, Any]],
        risks: list[dict[str, Any]],
        memory_hits: list[dict[str, Any]],
        memory_status: dict[str, Any],
        llm_status: dict[str, Any],
        warnings: list[str],
        *,
        actions: list[dict[str, Any]] | None = None,
        all_patterns: list[str] | None = None,
    ) -> dict[str, Any]:
        return {
            "recommendation": record,
            "actions": actions or [],
            "similar_deals": similar,
            "risks": risks or (record.risks or []),
            "memory_hits": memory_hits,
            "memory_status": memory_status,
            "llm_status": llm_status,
            "method": record.source,
            "warnings": warnings,
            "patterns": all_patterns if all_patterns is not None else (record.similar_patterns or []),
        }
