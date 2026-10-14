"""Durable single-shot live cancel and broker-state reconciliation."""
from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import Any, Protocol

from app.live.live_cancel_journal_repository import (
    LiveCancelJournalState,
    SQLiteLiveCancelJournalRepository,
)


class LiveCancelDecision(StrEnum):
    CANCELLED = "cancelled"
    BLOCKED = "blocked"


@dataclass(frozen=True, slots=True)
class LiveCancelResult:
    decision: LiveCancelDecision
    broker_order_id: str
    message: str

    @property
    def is_cancelled(self) -> bool:
        return self.decision is LiveCancelDecision.CANCELLED


class CancelClient(Protocol):
    def cancel_order(self, order_id: str) -> dict[str, Any]: ...
    def orders(self, *, product: int = 0) -> tuple[dict[str, Any], ...]: ...


class LiveProtectiveCancelService:
    """Persist intent before cancel; never resend a durable ambiguous attempt."""

    def __init__(
        self,
        *,
        client: CancelClient,
        journal_repository: SQLiteLiveCancelJournalRepository,
    ) -> None:
        self.client = client
        self.journal_repository = journal_repository

    def cancel_and_reconcile(self, *, broker_order_id: str) -> LiveCancelResult:
        oid = broker_order_id.strip()
        if not oid:
            return self._blocked(oid, "Missing broker order id.")

        try:
            record, created = self.journal_repository.begin_once(oid)
        except Exception as exc:
            return self._blocked(oid, f"Cancel journal is unavailable: {exc}")

        if not created:
            if record.state is LiveCancelJournalState.CANCELLED:
                return LiveCancelResult(
                    LiveCancelDecision.CANCELLED,
                    oid,
                    "Durable journal already records cancellation.",
                )
            # A prior process may have crashed or timed out after sending the
            # irreversible cancel.  Never send it again.  Only a read-only
            # /orders observation may resolve the durable ambiguity.
            return self._reconcile_existing_attempt(oid)

        try:
            self.client.cancel_order(oid)
        except Exception as exc:
            message = f"Cancel outcome is ambiguous: {exc}"
            try:
                self.journal_repository.mark_unknown(oid, message)
            except Exception:
                pass
            return self._blocked(oid, message)

        try:
            rows = self.client.orders(product=0)
            matched = [
                row
                for row in rows
                if isinstance(row, dict)
                and str(row.get("ID") or row.get("OrderId") or "").strip().lower()
                == oid.lower()
            ]
            if len(matched) != 1:
                raise ValueError(f"expected one broker order, found {len(matched)}")
            state = matched[0].get("State")
            if isinstance(state, bool) or state is None:
                raise ValueError("invalid State")
            if int(state) != 5:
                message = f"Order remains non-terminal after cancel: State={state}"
                self.journal_repository.mark_unknown(oid, message)
                return self._blocked(oid, message)
        except Exception as exc:
            message = f"Cancel reconciliation failed: {exc}"
            try:
                self.journal_repository.mark_unknown(oid, message)
            except Exception:
                pass
            return self._blocked(oid, message)

        try:
            self.journal_repository.mark_cancelled(
                oid, "Broker order is terminal after cancel."
            )
        except Exception as exc:
            return self._blocked(
                oid, f"Cancellation succeeded but durable completion failed: {exc}"
            )
        return LiveCancelResult(
            LiveCancelDecision.CANCELLED,
            oid,
            "Broker order is terminal after cancel.",
        )

    def _reconcile_existing_attempt(self, oid: str) -> LiveCancelResult:
        try:
            rows = self.client.orders(product=0)
            matched = [
                row
                for row in rows
                if isinstance(row, dict)
                and str(row.get("ID") or row.get("OrderId") or "").strip().lower()
                == oid.lower()
            ]
            if len(matched) != 1:
                return self._blocked(
                    oid,
                    "Existing durable cancel remains ambiguous: "
                    f"expected one broker order, found {len(matched)}.",
                )
            state = matched[0].get("State")
            if isinstance(state, bool) or state is None:
                return self._blocked(
                    oid, "Existing durable cancel remains ambiguous: invalid State."
                )
            if int(state) != 5:
                return self._blocked(
                    oid,
                    "Existing durable cancel remains ambiguous; "
                    f"broker order is non-terminal: State={state}.",
                )
        except Exception as exc:
            return self._blocked(
                oid, f"Read-only cancel recovery failed: {exc}"
            )

        try:
            self.journal_repository.recover_cancelled(
                oid,
                "Read-only broker reconciliation proved the order terminal.",
            )
        except Exception as exc:
            return self._blocked(
                oid,
                "Broker proves cancellation terminal but durable recovery failed: "
                f"{exc}",
            )
        return LiveCancelResult(
            LiveCancelDecision.CANCELLED,
            oid,
            "Read-only broker reconciliation proved the order terminal; "
            "cancel was not re-sent.",
        )

    @staticmethod
    def _blocked(oid: str, message: str) -> LiveCancelResult:
        return LiveCancelResult(LiveCancelDecision.BLOCKED, oid, message)
