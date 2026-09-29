from __future__ import annotations

import uuid
from typing import Any, Callable

from sqlalchemy.orm import Session

from app.core.logging import get_logger
from app.models import Deal
from app.services.llm_service import LLMService, LLMUnavailableError
from app.services.memory_service import MemoryService
from app.services.recommendation_service import RecommendationService
from app.services.similarity_service import SimilarDealService
from app.services.win_loss_service import WinLossService

logger = get_logger(__name__)

_COPILOT_SYSTEM = (
    "You are the Deal Copilot inside a B2B sales intelligence tool.\n"
    "You are looking at ONE deal. Answer the user's question about that deal.\n"
    "Rules:\n"
    "- Your first sentence must be the direct answer: the recommended next action for "
    "this deal, or a plain statement that the data does not support one.\n"
    "- Do not open with a summary of the tool output, and do not recite organisation-wide "
    "KPIs (pipeline totals, win rates, loss counts) unless the question asks for them.\n"
    "- Use organisation-wide statistics only to justify a point about this deal.\n"
    "- Cite supporting records inline using [deal: <deal_name>] or [memory: <n>].\n"
    "- If the tool output does not contain the answer, say so plainly and name what "
    "is missing. Never guess.\n"
    "- Never invent deal names, amounts, quotes, dates or outcomes.\n"
    "- Keep the answer under 180 words and end with 'Next step: <one concrete action>'."
)

# Order matters: the model reads the top of the prompt most carefully.
_SECTION_PRIORITY = [
    "deal",
    "recommendation",
    "risks",
    "similar_deals",
    "objection_history",
    "competitor_outcomes",
    "memory_hits",
    "win_loss",
    "memory_status",
    "warnings",
]

_SECTION_LIMIT = {
    "deal": 4000,
    "recommendation": 4000,
    "risks": 1500,
    "similar_deals": 3500,
    "memory_hits": 2500,
    "objection_history": 1200,
    "competitor_outcomes": 1200,
    "win_loss": 800,
}


class CopilotService:
    """Question answering over a single deal using controlled backend tools.

    The model never sees a database connection. It only sees the JSON produced
    by the small set of read-only tools below.
    """

    def __init__(self, session: Session, llm: LLMService | None = None):
        self.session = session
        self.llm = llm or LLMService()
        self.similarity = SimilarDealService(session)
        self.memory = MemoryService(session)
        self.win_loss = WinLossService(session)
        self.recommendations = RecommendationService(session, llm=llm)

    # --------------------------------------------------------------- intent
    @staticmethod
    def detect_intent(question: str) -> list[str]:
        q = question.lower()
        tools: list[str] = []
        if any(w in q for w in ("similar", "like this", "comparable", "same shape")):
            tools.append("similar_deals")
        if any(w in q for w in ("lose", "lost", "why did we lose", "failure")):
            tools.extend(["similar_deals", "win_loss"])
        if any(w in q for w in ("win", "won", "succeed", "worked")):
            tools.extend(["similar_deals", "win_loss"])
        if any(w in q for w in ("objection", "concern", "pushback", "expect")):
            tools.extend(["similar_deals", "objections"])
        if any(w in q for w in ("competitor", "salesforce", "versus", "vs ", "rival")):
            tools.append("competitors")
        if any(w in q for w in ("risk", "worry", "danger", "stall")):
            tools.append("recommendation")
        if any(w in q for w in ("next", "should i", "investigate", "recommend", "do next")):
            tools.append("recommendation")
        if any(w in q for w in ("remember", "said", "memory", "history", "past conversation")):
            tools.append("memories")
        if not tools:
            tools = ["deal_context", "similar_deals", "recommendation"]
        if "deal_context" not in tools:
            tools.insert(0, "deal_context")
        return list(dict.fromkeys(tools))

    # ---------------------------------------------------------------- tools
    def run_tools(
        self, organization_id: uuid.UUID, deal: Deal, tools: list[str]
    ) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
        trace: list[dict[str, Any]] = []
        payload: dict[str, Any] = {}

        if "deal_context" in tools:
            payload["deal"] = {
                "name": deal.name,
                "customer": deal.customer.name if deal.customer else None,
                "stage": deal.stage,
                "amount": float(deal.amount or 0),
                "currency": deal.currency,
                "probability": deal.probability,
                "expected_close_date": str(deal.expected_close_date or ""),
                "competitors": [dc.competitor.name for dc in deal.deal_competitors],
                "objections": [do.objection.label for do in deal.deal_objections],
                "description": deal.description or "",
                "next_action": deal.next_action or "",
                "outcome": deal.outcome,
            }
            trace.append({"tool": "deal_context", "rows": 1})

        similar: dict[str, Any] = {"similar_deals": [], "memory_hits": [], "memory_status": {}}
        if {"similar_deals", "objections", "competitors"} & set(tools):
            similar = self.similarity.find_similar(organization_id, deal, include_memory=True)
            payload["similar_deals"] = similar["similar_deals"][:8]
            payload["memory_hits"] = similar["memory_hits"][:8]
            payload["memory_status"] = similar["memory_status"]
            trace.append({"tool": "similar_deals", "rows": len(similar["similar_deals"])})
            trace.append(
                {
                    "tool": "recall_memories",
                    "rows": len(similar["memory_hits"]),
                    "available": bool(similar["memory_status"].get("available")),
                }
            )

        if "objections" in tools:
            payload["objection_history"] = self.win_loss.objection_stats(organization_id)
            trace.append({"tool": "objection_stats", "rows": len(payload["objection_history"])})

        if "competitors" in tools:
            stats = self.win_loss.analyze(organization_id)
            payload["competitor_outcomes"] = stats["competitor_outcomes"]
            trace.append(
                {"tool": "competitor_stats", "rows": len(stats["competitor_outcomes"])}
            )

        if "win_loss" in tools:
            stats = self.win_loss.analyze(organization_id)
            payload["win_loss"] = {
                "kpis": stats["kpis"],
                "loss_reasons": stats["loss_reasons"][:5],
                "win_reasons": stats["win_reasons"][:5],
                "insufficient_reason": stats["insufficient_reason"],
            }
            trace.append({"tool": "win_loss_stats", "rows": 1})

        if "recommendation" in tools:
            analysis = self.recommendations.analyze(organization_id, deal)
            payload["recommendation"] = {
                "title": analysis["recommendation"].title,
                "rationale": analysis["recommendation"].rationale,
                "evidence_level": analysis["recommendation"].evidence_level,
                "evidence": analysis["recommendation"].evidence,
                "summary": analysis["recommendation"].summary,
                "actions": analysis.get("actions") or [],
            }
            payload["risks"] = analysis["risks"]
            payload["warnings"] = analysis.get("warnings") or []
            trace.append({"tool": "get_recommendation", "rows": 1})

        # The copilot UI always shows the memory health badge, so the status is
        # reported even when no tool needed to recall from Hindsight.
        payload.setdefault("memory_status", self.memory.status(organization_id))

        for key, value in payload.items():
            _ = (key, value)
        return trace, [{"name": k, "data": v} for k, v in payload.items()]

    # -------------------------------------------------------------- answer
    def ask(
        self, organization_id: uuid.UUID, deal: Deal, question: str
    ) -> dict[str, Any]:
        tools = self.detect_intent(question)
        trace, sections = self.run_tools(organization_id, deal, tools)

        import json as _json

        ordered = sorted(
            sections,
            key=lambda s: _SECTION_PRIORITY.index(s["name"])
            if s["name"] in _SECTION_PRIORITY
            else len(_SECTION_PRIORITY),
        )
        budget = 14000
        blocks: list[str] = []
        for section in ordered:
            limit = _SECTION_LIMIT.get(section["name"], 1500)
            body = _json.dumps(section["data"], default=str)
            if len(body) > limit:
                body = body[:limit] + " …(truncated)"
            if len(body) > budget:
                body = body[:budget] + " …(truncated)"
            budget -= len(body)
            blocks.append(
                f"### TOOL OUTPUT: {section['name']}\n{body}"
                if section["name"] != "deal"
                else f"### THE DEAL BEING ASKED ABOUT\n{body}"
            )
            if budget <= 0:
                break
        tool_block = "\n\n".join(blocks)
        memory_status = next(
            (s["data"] for s in sections if s["name"] == "memory_status"), {}
        )

        try:
            result = self.llm.complete(
                [
                    {"role": "system", "content": _COPILOT_SYSTEM},
                    {
                        "role": "user",
                        "content": (
                            f"QUESTION: {question}\n\n{tool_block}\n\n"
                            "REMINDER: answer about THE DEAL BEING ASKED ABOUT, "
                            "not about the whole pipeline. End with 'Next step: <one "
                            "concrete action>'."
                        ),
                    },
                ],
                temperature=0.1,
                max_tokens=500,
            )
        except LLMUnavailableError as exc:
            return {
                "answer": self._deterministic_answer(question, sections),
                "citations": self._citations(sections),
                "tool_trace": trace,
                "available": False,
                "unavailable_reason": f"{exc.code}: {exc.message}",
                "model": None,
                "memory_status": memory_status,
            }
        except Exception as exc:  # noqa: BLE001
            logger.exception("Copilot LLM call failed")
            return {
                "answer": self._deterministic_answer(question, sections),
                "citations": self._citations(sections),
                "tool_trace": trace,
                "available": False,
                "unavailable_reason": f"llm_error: {type(exc).__name__}",
                "model": None,
                "memory_status": memory_status,
            }

        return {
            "answer": result.text.strip(),
            "citations": self._citations(sections),
            "tool_trace": trace,
            "available": True,
            "unavailable_reason": None,
            "model": result.model,
            "memory_status": memory_status,
        }

    @staticmethod
    def _citations(sections: list[dict[str, Any]]) -> list[dict[str, Any]]:
        citations: list[dict[str, Any]] = []
        for section in sections:
            if section["name"] == "similar_deals":
                for item in section["data"][:8]:
                    citations.append(
                        {
                            "type": "deal",
                            "id": str(item.get("deal_id")),
                            "label": item.get("deal_name"),
                            "outcome": item.get("outcome"),
                            "why": item.get("why_relevant"),
                        }
                    )
            elif section["name"] == "memory_hits":
                for hit in section["data"][:8]:
                    citations.append(
                        {
                            "type": "memory",
                            "id": hit.get("id"),
                            "label": (hit.get("text") or "")[:120],
                        }
                    )
            elif section["name"] == "recommendation":
                for item in section["data"].get("evidence") or []:
                    citations.append(
                        {
                            "type": "evidence",
                            "id": str(item.get("deal_id") or ""),
                            "label": item.get("deal_name"),
                            "why": item.get("why"),
                        }
                    )
        seen: set[tuple] = set()
        unique = []
        for c in citations:
            key = (c.get("type"), c.get("id"), c.get("label"))
            if key in seen:
                continue
            seen.add(key)
            unique.append(c)
        return unique

    @staticmethod
    def _deterministic_answer(question: str, sections: list[dict[str, Any]]) -> str:
        """Readable answer assembled from tool output when no LLM is reachable."""
        lookup = {s["name"]: s["data"] for s in sections}
        lines: list[str] = []
        similar = lookup.get("similar_deals") or []
        lost = [d for d in similar if d.get("outcome") == "LOST"]
        won = [d for d in similar if d.get("outcome") == "WON"]

        q = question.lower()
        if any(w in q for w in ("lose", "lost", "failure")):
            if lost:
                lines.append(f"{len(lost)} comparable deal(s) were lost:")
                for item in lost[:3]:
                    reason = item.get("loss_reason") or "reason not recorded"
                    lines.append(
                        f"- {item['deal_name']} ({item['customer_name']}): {reason} "
                        f"[deal: {item['deal_name']}]"
                    )
            else:
                lines.append("No comparable closed-lost deal is recorded yet.")
        elif any(w in q for w in ("win", "won", "worked")):
            if won:
                lines.append(f"{len(won)} comparable deal(s) were won:")
                for item in won[:3]:
                    reason = item.get("win_reason") or "reason not recorded"
                    lines.append(
                        f"- {item['deal_name']} ({item['customer_name']}): {reason} "
                        f"[deal: {item['deal_name']}]"
                    )
            else:
                lines.append("No comparable closed-won deal is recorded yet.")
        elif "competitor" in q:
            comps = lookup.get("competitor_outcomes") or []
            if comps:
                lines.append("Competitor outcomes across this organisation:")
                for c in comps[:5]:
                    lines.append(
                        f"- {c['competitor']}: {c['won']} won / {c['lost']} lost of {c['total']}"
                    )
            else:
                lines.append("No competitor history is recorded.")
        elif "objection" in q:
            stats = lookup.get("objection_history") or []
            if stats:
                lines.append("Objections observed in closed deals:")
                for s in stats[:6]:
                    lines.append(f"- {s['label']}: {s['total']} time(s), {s['lost']} lost")
            else:
                lines.append("No objection history is recorded.")
        else:
            rec = lookup.get("recommendation")
            if rec:
                lines.append(f"Recommendation: {rec['title']}")
                lines.append(rec["rationale"])
                for ev in (rec.get("evidence") or [])[:3]:
                    lines.append(f"- evidence: {ev.get('deal_name')} [deal: {ev.get('deal_name')}]")
            else:
                lines.append(
                    "No recommendation has been generated for this deal yet. "
                    "Run analysis first."
                )

        warnings = lookup.get("warnings") or []
        if warnings:
            lines.append("")
            lines.append("Note: " + " ".join(warnings))
        lines.append("")
        lines.append(
            "Answer assembled from recorded tool output (no LLM was reachable)."
        )
        return "\n".join(lines)
