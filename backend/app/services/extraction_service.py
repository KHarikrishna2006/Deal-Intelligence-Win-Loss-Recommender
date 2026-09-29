from __future__ import annotations

import re
from dataclasses import dataclass, field
from decimal import Decimal, InvalidOperation
from typing import Any, Optional

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Competitor, Objection
from app.services.llm_service import LLMService, LLMUnavailableError, extract_json

_MONEY = re.compile(
    r"(?P<amount>\$?\s?\d{1,3}(?:[,\s]\d{3})*(?:\.\d+)?|\d+(?:\.\d+)?)\s?"
    r"(?P<unit>k|m|K|M|thousand|million|USD|usd)?"
)

_NEGATIVE = [
    "expensive", "too costly", "over budget", "cheaper", "discount", "objection",
    "concern", "worried", "not sure", "declined", "pushback", "reject", "no",
    "procurement rejected", "risk", "delay", "stall", "competitor",
]
_POSITIVE = [
    "excited", "ready to sign", "approved", "great", "move forward", "yes",
    "budget approved", "champion", "timeline confirmed", "sign this quarter",
]

_PROCUREMENT_TERMS = [
    "procurement", "vendor approval", "supplier onboarding", "purchase order",
    "security review", "legal review", "dpa", "msa", "rfp", "vendor form",
]


@dataclass
class ExtractionResult:
    objections: list[str] = field(default_factory=list)
    competitors: list[str] = field(default_factory=list)
    requirements: list[str] = field(default_factory=list)
    commitments: list[str] = field(default_factory=list)
    pricing: dict[str, Any] = field(default_factory=dict)
    sentiment: Optional[str] = None
    procurement_mentioned: bool = False
    decision_maker_mentioned: bool = False
    method: str = "deterministic"
    warnings: list[str] = field(default_factory=list)

    def as_dict(self) -> dict[str, Any]:
        return {
            "objections": self.objections,
            "competitors": self.competitors,
            "requirements": self.requirements,
            "commitments": self.commitments,
            "pricing": self.pricing,
            "sentiment": self.sentiment,
            "procurement_mentioned": self.procurement_mentioned,
            "decision_maker_mentioned": self.decision_maker_mentioned,
            "method": self.method,
            "warnings": self.warnings,
        }


class ExtractionService:
    """Pulls structured facts out of free-text sales interactions.

    Uses the LLM when one is configured; otherwise falls back to deterministic
    catalog matching so ingestion never silently fails.
    """

    def __init__(self, session: Session, llm: LLMService | None = None):
        self.session = session
        self.llm = llm or LLMService()

    def _catalogs(self, organization_id) -> tuple[list[str], list[str]]:
        competitors = [
            c.name
            for c in self.session.execute(
                select(Competitor).where(Competitor.organization_id == organization_id)
            ).scalars()
        ]
        objections = [
            o.label
            for o in self.session.execute(
                select(Objection).where(Objection.organization_id == organization_id)
            ).scalars()
        ]
        return competitors, objections

    def extract(self, organization_id, body: str, *, deal_context: str = "") -> ExtractionResult:
        competitors, objections = self._catalogs(organization_id)
        result = ExtractionResult()

        llm_payload = self._try_llm(body, deal_context, competitors, objections, result)
        if llm_payload is None:
            self._deterministic(body, competitors, objections, result)
        else:
            self._apply_llm_payload(llm_payload, result)

        self._detect_pricing(body, result)
        if not result.sentiment:
            result.sentiment = self._sentiment(body)
        result.procurement_mentioned = any(t in body.lower() for t in _PROCUREMENT_TERMS)
        result.decision_maker_mentioned = bool(
            re.search(r"\b(cfo|cto|ceo|vp|vice president|head of|decision maker|sponsor)\b", body, re.I)
        )
        return result

    # ------------------------------------------------------------------- llm
    def _try_llm(
        self,
        body: str,
        deal_context: str,
        competitors: list[str],
        objections: list[str],
        result: ExtractionResult,
    ) -> dict[str, Any] | None:
        if not body.strip():
            return None
        system = (
            "You extract structured sales facts from a single customer interaction. "
            "Return ONLY JSON with keys: objections (array of short labels), "
            "competitors (array of names), requirements (array), commitments (array), "
            "pricing (object with amount/currency/terms or empty), sentiment "
            "(one of positive/neutral/negative/unknown). "
            "Use only facts present in the text. If something is absent, use an empty "
            "array or unknown. Never invent names, amounts or requirements."
        )
        user = (
            f"KNOWN COMPETITORS: {', '.join(competitors) or 'none recorded'}\n"
            f"KNOWN OBJECTIONS: {', '.join(objections) or 'none recorded'}\n"
            f"DEAL CONTEXT: {deal_context or 'n/a'}\n\n"
            f"INTERACTION TEXT:\n{body[:6000]}"
        )
        try:
            payload = self.llm.complete_json(
                [
                    {"role": "system", "content": system},
                    {"role": "user", "content": user},
                ],
                temperature=0.0,
            )
        except LLMUnavailableError as exc:
            result.warnings.append(f"LLM unavailable, used deterministic extraction: {exc.code}")
            return None
        except Exception as exc:  # noqa: BLE001
            result.warnings.append(
                f"LLM extraction failed, used deterministic extraction: {type(exc).__name__}"
            )
            return None
        result.method = "llm"
        return payload

    @staticmethod
    def _apply_llm_payload(payload: dict[str, Any], result: ExtractionResult) -> None:
        def as_str_list(value: Any) -> list[str]:
            if not isinstance(value, list):
                return []
            out: list[str] = []
            for item in value:
                if isinstance(item, str) and item.strip():
                    out.append(item.strip()[:200])
                elif isinstance(item, dict):
                    label = item.get("label") or item.get("name") or item.get("text")
                    if isinstance(label, str) and label.strip():
                        out.append(label.strip()[:200])
            return out

        result.objections = as_str_list(payload.get("objections"))
        result.competitors = as_str_list(payload.get("competitors"))
        result.requirements = as_str_list(payload.get("requirements"))
        result.commitments = as_str_list(payload.get("commitments"))
        pricing = payload.get("pricing")
        if isinstance(pricing, dict):
            result.pricing = {k: v for k, v in pricing.items() if v not in (None, "")}
        sentiment = payload.get("sentiment")
        if isinstance(sentiment, str) and sentiment.lower() in {
            "positive", "neutral", "negative", "unknown",
        }:
            result.sentiment = sentiment.lower()

    # --------------------------------------------------------- deterministic
    def _deterministic(
        self, body: str, competitors: list[str], objections: list[str], result: ExtractionResult
    ) -> None:
        lowered = body.lower()
        for name in competitors:
            if name.lower() in lowered:
                result.competitors.append(name)
        for label in objections:
            if label.lower() in lowered:
                result.objections.append(label)

        keyword_objections = {
            "annual pricing": ["annual pricing", "annual contract", "upfront annual"],
            "budget": ["over budget", "budget is tight", "budget constraint", "too expensive"],
            "procurement delay": ["procurement will", "procurement delay", "procurement process"],
            "security review": ["security review", "soc 2", "penetration test", "iso 27001"],
            "integration": ["integration", "does it integrate", "api access", "webhooks"],
            "timeline": ["timeline", "too long to implement", "rollout time"],
        }
        for label, needles in keyword_objections.items():
            if any(n in lowered for n in needles) and label not in result.objections:
                result.objections.append(label)

        for sentence in re.split(r"(?<=[.!?])\s+", body):
            low = sentence.lower()
            if any(k in low for k in ("we require", "they require", "must support", "needs to", "requires ")):
                cleaned = sentence.strip()
                if 3 < len(cleaned) < 240:
                    result.requirements.append(cleaned)

    def _detect_pricing(self, body: str, result: ExtractionResult) -> None:
        if result.pricing:
            return
        for match in _MONEY.finditer(body):
            raw = match.group("amount").replace(",", "").replace(" ", "").replace("$", "")
            unit = (match.group("unit") or "").lower()
            try:
                value = Decimal(raw)
            except InvalidOperation:
                continue
            if unit in ("k", "thousand"):
                value *= 1000
            elif unit in ("m", "million"):
                value *= 1_000_000
            if value < 100:
                continue
            result.pricing = {
                "amount": float(value),
                "currency": "USD",
                "terms": "annual" if "annual" in body.lower() else None,
                "source_text": match.group(0).strip(),
            }
            break

    @staticmethod
    def _sentiment(body: str) -> str:
        lowered = body.lower()
        neg = sum(1 for k in _NEGATIVE if k in lowered)
        pos = sum(1 for k in _POSITIVE if k in lowered)
        if neg > pos:
            return "negative"
        if pos > neg:
            return "positive"
        if neg or pos:
            return "neutral"
        return "unknown"
