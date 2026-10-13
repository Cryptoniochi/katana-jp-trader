"""Single-shot live cancel and broker-state reconciliation."""
from __future__ import annotations
from dataclasses import dataclass
from enum import StrEnum
from typing import Any, Protocol

class LiveCancelDecision(StrEnum):
    CANCELLED="cancelled"
    BLOCKED="blocked"

@dataclass(frozen=True, slots=True)
class LiveCancelResult:
    decision:LiveCancelDecision
    broker_order_id:str
    message:str
    @property
    def is_cancelled(self)->bool:
        return self.decision is LiveCancelDecision.CANCELLED

class CancelClient(Protocol):
    def cancel_order(self, order_id:str)->dict[str,Any]: ...
    def orders(self, *, product:int=0)->tuple[dict[str,Any],...]: ...

class LiveProtectiveCancelService:
    """Cancel once; never retry an ambiguous cancel; require terminal State=5."""
    def __init__(self, *, client:CancelClient)->None:
        self.client=client

    def cancel_and_reconcile(self, *, broker_order_id:str)->LiveCancelResult:
        oid=broker_order_id.strip()
        if not oid:
            return self._blocked(oid,"Missing broker order id.")
        try:
            self.client.cancel_order(oid)
        except Exception as exc:
            return self._blocked(oid,f"Cancel outcome is ambiguous: {exc}")
        try:
            rows=self.client.orders(product=0)
            matched=[
                row for row in rows
                if isinstance(row,dict)
                and str(row.get("ID") or row.get("OrderId") or "").strip().lower()
                == oid.lower()
            ]
            if len(matched)!=1:
                raise ValueError(f"expected one broker order, found {len(matched)}")
            state=matched[0].get("State")
            if isinstance(state,bool) or state is None:
                raise ValueError("invalid State")
            if int(state)!=5:
                return self._blocked(
                    oid,f"Order remains non-terminal after cancel: State={state}"
                )
        except Exception as exc:
            return self._blocked(oid,f"Cancel reconciliation failed: {exc}")
        return LiveCancelResult(
            LiveCancelDecision.CANCELLED,oid,
            "Broker order is terminal after cancel."
        )

    @staticmethod
    def _blocked(oid:str,message:str)->LiveCancelResult:
        return LiveCancelResult(LiveCancelDecision.BLOCKED,oid,message)
