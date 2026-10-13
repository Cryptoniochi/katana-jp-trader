"""Read-only broker open-order conflict guard for live protective exits."""
from __future__ import annotations
from dataclasses import dataclass
from enum import StrEnum
from typing import Any, Protocol

class LiveExitOrderConflictDecision(StrEnum):
    CLEAR="clear"
    BLOCKED="blocked"

@dataclass(frozen=True, slots=True)
class LiveOpenOrderConflict:
    broker_order_id:str
    code:str
    side:str
    state:int
    remaining_quantity:float|None

@dataclass(frozen=True, slots=True)
class LiveExitOrderConflictCheck:
    decision:LiveExitOrderConflictDecision
    code:str
    conflicts:tuple[LiveOpenOrderConflict,...]
    message:str
    @property
    def is_clear(self)->bool:
        return self.decision is LiveExitOrderConflictDecision.CLEAR

class BrokerOrderReader(Protocol):
    def orders(self, *, product:int=0)->tuple[dict[str,Any],...]: ...

class LiveExitOrderConflictService:
    """Block a new exit while any same-symbol broker order is unfinished."""
    def __init__(self, *, order_reader:BrokerOrderReader)->None:
        self.order_reader=order_reader

    def check(self, *, code:str)->LiveExitOrderConflictCheck:
        code=self._code(code)
        try:
            rows=self.order_reader.orders(product=0)
            if rows is None: raise ValueError("orders are missing")
            conflicts=[]
            for row in rows:
                if not isinstance(row,dict): raise ValueError("order row is not an object")
                symbol=str(row.get("Symbol") or row.get("symbol") or "").strip()
                if symbol!=code: continue
                state=self._state(row)
                if state==5: continue
                if state not in {1,2,3,4}: raise ValueError(f"unknown State={state}")
                side=str(row.get("Side") or row.get("side") or "").strip()
                if side not in {"1","2"}: raise ValueError(f"unknown Side={side!r}")
                oid=str(row.get("ID") or row.get("OrderId") or "").strip()
                if not oid: raise ValueError("active order has no id")
                remaining=self._remaining(row)
                conflicts.append(LiveOpenOrderConflict(oid,code,side,state,remaining))
        except Exception as exc:
            return LiveExitOrderConflictCheck(
                LiveExitOrderConflictDecision.BLOCKED,code,(),
                f"Live broker order state is unavailable or ambiguous: {exc}",
            )
        if conflicts:
            return LiveExitOrderConflictCheck(
                LiveExitOrderConflictDecision.BLOCKED,code,tuple(conflicts),
                "Unfinished broker order exists; protective exit is blocked.",
            )
        return LiveExitOrderConflictCheck(
            LiveExitOrderConflictDecision.CLEAR,code,(),
            "No unfinished broker order exists.",
        )

    @staticmethod
    def _state(row):
        value=row.get("State",row.get("state"))
        if isinstance(value,bool) or value is None: raise ValueError("invalid State")
        return int(value)

    @staticmethod
    def _remaining(row):
        for key in ("LeavesQty","leaves_qty","RemainingQty","remaining_quantity"):
            if key in row and row[key] is not None:
                value=float(row[key])
                if value<0: raise ValueError("negative remaining quantity")
                return value
        return None

    @staticmethod
    def _code(code):
        value=code.strip()
        if not value.isdigit() or len(value) not in {4,5}:
            raise ValueError("code must be a 4- or 5-digit symbol")
        return value
