from __future__ import annotations

import time
import uuid
from dataclasses import dataclass, field
from typing import Any, Callable

from .global_resolver import GlobalResolver, ResolutionError


@dataclass
class DispatchRecord:
    dispatch_id: str
    packet_id: str
    capability: str
    source: str
    target: str | None
    route: dict[str, Any] | None
    state: str
    created_at: float
    updated_at: float
    payload: dict[str, Any] = field(default_factory=dict)
    result: dict[str, Any] | None = None
    proof_chain: list[str] = field(default_factory=list)
    error: str | None = None


class DispatchFabric:
    """Active command-to-proof dispatch fabric for GA-HYPERNET-GLOBAL-RESOLUTION-003.

    Packet OS -> Global Resolver -> Workforce Spine -> CrownGrid -> runtime target
    -> Estate Event Gateway -> SECA -> DevOS -> ProofGrid -> Thoth -> JANUS PRIME.
    """

    proof_chain = [
        "ga://organ/seca",
        "ga://organ/devos",
        "ga://organ/proofgrid",
        "ga://organ/thoth",
        "ga://organ/janus-prime",
    ]

    def __init__(self, resolver: GlobalResolver) -> None:
        self.resolver = resolver
        self.records: dict[str, DispatchRecord] = {}
        self.executors: dict[str, Callable[[DispatchRecord], dict[str, Any]]] = {}
        self.events: list[dict[str, Any]] = []

    def register_executor(self, node_id: str, executor: Callable[[DispatchRecord], dict[str, Any]]) -> None:
        self.executors[node_id] = executor

    def dispatch(
        self,
        *,
        packet_id: str,
        capability: str,
        payload: dict[str, Any] | None = None,
        source: str = "ga://organ/packet-os",
        io_class: str = "PACKET",
        security_class: str | None = None,
        prefer_local: bool = True,
        execute: bool = False,
    ) -> dict[str, Any]:
        resolution = self.resolver.resolve(
            capability,
            source=source,
            io_class=io_class,
            security_class=security_class,
            prefer_local=prefer_local,
        )
        selected = resolution.get("selected")
        if not selected:
            raise ResolutionError(f"no eligible execution target for {capability}", 503)

        now = time.time()
        record = DispatchRecord(
            dispatch_id=f"dispatch-{uuid.uuid4().hex[:16]}",
            packet_id=packet_id,
            capability=resolution["capability"],
            source=source,
            target=selected["canonical_id"],
            route=resolution.get("route"),
            state="DISPATCHED",
            created_at=now,
            updated_at=now,
            payload=payload or {},
        )
        self.records[record.dispatch_id] = record
        self._emit("estate.packet.dispatched", record, {"selected": selected})

        if execute:
            self.execute(record.dispatch_id)
        return self.snapshot(record.dispatch_id)

    def execute(self, dispatch_id: str) -> dict[str, Any]:
        record = self._get(dispatch_id)
        if record.state not in {"DISPATCHED", "RETRYABLE"}:
            raise ResolutionError(f"dispatch {dispatch_id} cannot execute from {record.state}", 409)
        executor = self.executors.get(record.target or "")
        if executor is None:
            record.state = "AWAITING_EXECUTOR"
            record.updated_at = time.time()
            self._emit("estate.worker.awaiting-executor", record, {})
            return self.snapshot(dispatch_id)

        record.state = "RUNNING"
        record.updated_at = time.time()
        self._emit("estate.worker.busy", record, {})
        try:
            record.result = executor(record)
            record.state = "EXECUTED"
            record.updated_at = time.time()
            self._emit("estate.packet.executed", record, {"result": record.result})
        except Exception as exc:  # executor boundary
            record.state = "FAILED"
            record.error = str(exc)
            record.updated_at = time.time()
            self._emit("estate.packet.failed", record, {"error": record.error})
        return self.snapshot(dispatch_id)

    def complete_stage(self, dispatch_id: str, organ: str, evidence: dict[str, Any] | None = None) -> dict[str, Any]:
        record = self._get(dispatch_id)
        if record.state not in {"EXECUTED", "VERIFYING", "PROVING", "REMEMBERING", "RECONCILING"}:
            raise ResolutionError(f"dispatch {dispatch_id} is not eligible for proof-chain advancement", 409)

        expected = self.proof_chain[len(record.proof_chain)] if len(record.proof_chain) < len(self.proof_chain) else None
        if expected is None:
            return self.snapshot(dispatch_id)
        if organ != expected:
            raise ResolutionError(f"proof-chain violation: expected {expected}, received {organ}", 409)

        record.proof_chain.append(organ)
        record.updated_at = time.time()
        state_by_organ = {
            "ga://organ/seca": "VERIFYING",
            "ga://organ/devos": "PROVING",
            "ga://organ/proofgrid": "REMEMBERING",
            "ga://organ/thoth": "RECONCILING",
            "ga://organ/janus-prime": "COMPLETED",
        }
        record.state = state_by_organ[organ]
        self._emit("estate.dispatch.stage-completed", record, {"organ": organ, "evidence": evidence or {}})
        if record.state == "COMPLETED":
            self._emit("estate.packet.completed", record, {"proof_chain": list(record.proof_chain)})
        return self.snapshot(dispatch_id)

    def fail(self, dispatch_id: str, reason: str, retryable: bool = True) -> dict[str, Any]:
        record = self._get(dispatch_id)
        record.error = reason
        record.state = "RETRYABLE" if retryable else "FAILED"
        record.updated_at = time.time()
        self._emit("estate.packet.failed", record, {"error": reason, "retryable": retryable})
        return self.snapshot(dispatch_id)

    def snapshot(self, dispatch_id: str) -> dict[str, Any]:
        record = self._get(dispatch_id)
        return {
            "resolution_id": "GA-HYPERNET-GLOBAL-RESOLUTION-003",
            "dispatch_id": record.dispatch_id,
            "packet_id": record.packet_id,
            "capability": record.capability,
            "source": record.source,
            "target": record.target,
            "route": record.route,
            "state": record.state,
            "payload": record.payload,
            "result": record.result,
            "proof_chain": list(record.proof_chain),
            "next_proof_stage": self.proof_chain[len(record.proof_chain)] if len(record.proof_chain) < len(self.proof_chain) else None,
            "error": record.error,
            "created_at": record.created_at,
            "updated_at": record.updated_at,
        }

    def topology(self) -> dict[str, Any]:
        return {
            "resolution_id": "GA-HYPERNET-GLOBAL-RESOLUTION-003",
            "active_dispatches": [self.snapshot(k) for k in sorted(self.records)],
            "executors": sorted(self.executors),
            "events": self.events[-100:],
        }

    def _get(self, dispatch_id: str) -> DispatchRecord:
        record = self.records.get(dispatch_id)
        if record is None:
            raise ResolutionError(f"unknown dispatch {dispatch_id}", 404)
        return record

    def _emit(self, event_type: str, record: DispatchRecord, payload: dict[str, Any]) -> None:
        event = {
            "event_type": event_type,
            "timestamp": time.time(),
            "dispatch_id": record.dispatch_id,
            "packet_id": record.packet_id,
            "source": record.source,
            "target": record.target,
            "payload": payload,
        }
        self.events.append(event)
        self.resolver._emit(event_type, record.source, event)
