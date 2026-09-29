from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Iterable, Optional

from app.config import settings
from app.core.exceptions import UpstreamUnavailableError
from app.core.logging import get_logger

logger = get_logger(__name__)


class HindsightUnavailableError(UpstreamUnavailableError):
    code = "hindsight_unavailable"


@dataclass
class MemoryHit:
    id: str
    text: str
    type: Optional[str]
    context: Optional[str]
    occurred_at: Optional[str]
    tags: list[str]
    metadata: dict[str, str]
    score: Optional[float]

    def as_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "text": self.text,
            "type": self.type,
            "context": self.context,
            "occurred_at": self.occurred_at,
            "tags": self.tags,
            "metadata": self.metadata,
            "score": self.score,
        }


class HindsightService:
    """Single point of contact with Hindsight.

    Every memory operation in the application goes through this class so that
    bank naming (organization isolation), metadata conventions and failure
    handling stay in one place.
    """

    def __init__(self, base_url: str | None = None, api_key: str | None = None):
        self.base_url = (base_url or settings.hindsight_url).rstrip("/")
        self.api_key = api_key if api_key is not None else settings.hindsight_api_key
        self._client: Any = None
        self._client_error: str | None = None

    # ------------------------------------------------------------------ setup
    @property
    def enabled(self) -> bool:
        return settings.hindsight_enabled

    def _get_client(self) -> Any:
        if not self.enabled:
            raise HindsightUnavailableError("Hindsight integration is disabled by configuration.")
        if self._client is not None:
            return self._client
        if self._client_error:
            raise HindsightUnavailableError(
                "Hindsight client could not be initialised.", details={"reason": self._client_error}
            )
        try:
            from hindsight_client import Hindsight
        except ImportError as exc:
            self._client_error = "hindsight-client is not installed"
            raise HindsightUnavailableError(self._client_error) from exc
        try:
            self._client = Hindsight(
                base_url=self.base_url,
                api_key=self.api_key or None,
                timeout=settings.hindsight_timeout_seconds,
            )
        except Exception as exc:  # noqa: BLE001
            self._client_error = f"{type(exc).__name__}: {exc}"
            raise HindsightUnavailableError("Hindsight client could not be initialised.") from exc
        return self._client

    @staticmethod
    def bank_id(organization_id: uuid.UUID | str) -> str:
        """One memory bank per organization - strict isolation by construction."""
        return f"{settings.hindsight_bank_prefix}-{organization_id}"

    # ----------------------------------------------------------------- status
    def status(self, organization_id: uuid.UUID | str | None = None) -> dict[str, Any]:
        info: dict[str, Any] = {
            "configured_url": self.base_url,
            "enabled": self.enabled,
            "available": False,
            "bank_id": self.bank_id(organization_id) if organization_id else None,
        }
        if not self.enabled:
            info["reason"] = "disabled"
            return info
        try:
            client = self._get_client()
            version = client.get_version()
            info["available"] = True
            info["version"] = getattr(version, "version", None) or str(version)
        except Exception as exc:  # noqa: BLE001 - status must never raise
            info["reason"] = getattr(exc, "message", None) or f"{type(exc).__name__}"
            info["code"] = getattr(exc, "code", "hindsight_unavailable")
        return info

    # ------------------------------------------------------------------ banks
    def ensure_bank(self, organization_id: uuid.UUID | str, name: str, mission: str | None = None) -> str:
        bank = self.bank_id(organization_id)
        client = self._get_client()
        try:
            client.create_bank(bank, name=name, mission=mission)
        except Exception as exc:  # noqa: BLE001
            message = str(exc).lower()
            if "already" in message or "conflict" in message or "409" in message:
                return bank
            raise HindsightUnavailableError(
                "Could not create the Hindsight memory bank.", details={"error": str(exc)[:400]}
            ) from exc
        return bank

    # ----------------------------------------------------------------- retain
    def retain_memory(
        self,
        organization_id: uuid.UUID | str,
        content: str,
        *,
        context: str | None = None,
        metadata: dict[str, str] | None = None,
        tags: list[str] | None = None,
        timestamp: datetime | None = None,
    ) -> dict[str, Any]:
        bank = self.bank_id(organization_id)
        client = self._get_client()
        meta = {k: str(v) for k, v in (metadata or {}).items() if v is not None}
        meta["organization_id"] = str(organization_id)
        try:
            response = client.retain(
                bank_id=bank,
                content=content,
                context=context,
                metadata=meta,
                tags=tags or [],
                timestamp=timestamp,
            )
        except Exception as exc:  # noqa: BLE001
            raise HindsightUnavailableError(
                "Hindsight could not retain the memory.", details={"error": str(exc)[:400]}
            ) from exc
        return {
            "success": bool(getattr(response, "success", False)),
            "bank_id": getattr(response, "bank_id", bank),
            "items_count": getattr(response, "items_count", 0),
            "operation_id": getattr(response, "operation_id", None),
        }

    # ----------------------------------------------------------------- recall
    @staticmethod
    def _to_hit(result: Any) -> MemoryHit:
        score = None
        scores = getattr(result, "scores", None)
        if scores is not None:
            for attr in ("final", "score", "rrf", "combined"):
                value = getattr(scores, attr, None)
                if isinstance(value, (int, float)):
                    score = float(value)
                    break
            if score is None and hasattr(scores, "model_dump"):
                dumped = scores.model_dump()
                numeric = [v for v in dumped.values() if isinstance(v, (int, float))]
                if numeric:
                    score = float(max(numeric))
        return MemoryHit(
            id=getattr(result, "id", "") or "",
            text=getattr(result, "text", "") or "",
            type=getattr(result, "type", None),
            context=getattr(result, "context", None),
            occurred_at=getattr(result, "occurred_start", None),
            tags=list(getattr(result, "tags", None) or []),
            metadata=dict(getattr(result, "metadata", None) or {}),
            score=score,
        )

    def recall_memory(
        self,
        organization_id: uuid.UUID | str,
        query: str,
        *,
        max_tokens: int = 3000,
        budget: str = "mid",
        tags: list[str] | None = None,
        types: list[str] | None = None,
    ) -> list[MemoryHit]:
        bank = self.bank_id(organization_id)
        client = self._get_client()
        try:
            response = client.recall(
                bank_id=bank,
                query=query,
                max_tokens=max_tokens,
                budget=budget,
                tags=tags or None,
                types=types or None,
            )
        except Exception as exc:  # noqa: BLE001
            raise HindsightUnavailableError(
                "Hindsight could not run the recall.", details={"error": str(exc)[:400]}
            ) from exc
        return [self._to_hit(r) for r in (getattr(response, "results", None) or [])]

    # ---------------------------------------------------------------- reflect
    def reflect_on_memory(
        self,
        organization_id: uuid.UUID | str,
        query: str,
        *,
        context: str | None = None,
        budget: str = "low",
        response_schema: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        bank = self.bank_id(organization_id)
        client = self._get_client()
        try:
            response = client.reflect(
                bank_id=bank,
                query=query,
                context=context,
                budget=budget,
                response_schema=response_schema,
            )
        except Exception as exc:  # noqa: BLE001
            raise HindsightUnavailableError(
                "Hindsight could not run the reflection.", details={"error": str(exc)[:400]}
            ) from exc
        structured = getattr(response, "structured_output", None)
        return {
            "text": getattr(response, "text", "") or "",
            "structured": structured if isinstance(structured, dict) else None,
            "structured_output_error": getattr(response, "structured_output_error", None),
        }

    # ------------------------------------------------------------ deal search
    def search_deal_history(
        self,
        organization_id: uuid.UUID | str,
        *,
        queries: Iterable[str],
        max_tokens: int = 3000,
    ) -> list[MemoryHit]:
        """Runs several recall queries and de-duplicates the merged results."""
        seen: dict[str, MemoryHit] = {}
        for query in queries:
            if not query or not query.strip():
                continue
            try:
                for hit in self.recall_memory(organization_id, query, max_tokens=max_tokens):
                    if hit.id and hit.id not in seen:
                        seen[hit.id] = hit
            except HindsightUnavailableError:
                raise
        return sorted(
            seen.values(), key=lambda h: (h.score if h.score is not None else 0.0), reverse=True
        )

    # ------------------------------------------------------------ maintenance
    def list_memories(
        self,
        organization_id: uuid.UUID | str,
        *,
        search_query: str | None = None,
        start_date: str | None = None,
        end_date: str | None = None,
        type_: str | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> dict[str, Any]:
        bank = self.bank_id(organization_id)
        client = self._get_client()
        try:
            response = client.list_memories(
                bank_id=bank,
                search_query=search_query,
                start_date=start_date,
                end_date=end_date,
                type=type_,
                limit=limit,
                offset=offset,
            )
        except Exception as exc:  # noqa: BLE001
            raise HindsightUnavailableError(
                "Hindsight could not list memories.", details={"error": str(exc)[:400]}
            ) from exc
        items = []
        for item in getattr(response, "items", None) or []:
            dump = item.model_dump() if hasattr(item, "model_dump") else dict(item)
            items.append(dump)
        return {
            "items": items,
            "total": getattr(response, "total", len(items)),
            "limit": getattr(response, "limit", limit),
            "offset": getattr(response, "offset", offset),
        }


hindsight_service = HindsightService()
