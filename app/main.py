from __future__ import annotations

import asyncio
import json
import os
from typing import Any, AsyncIterator

from fastapi import FastAPI, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from .dispatch import DispatchFabric
from .global_resolver import GlobalResolver, ResolutionError
from .mesh import MeshEngine, MeshError
from .models import InvokeRequest, MeshPolicy, ResolveRequest


def _int_env(name: str, default: int) -> int:
    try:
        return int(os.getenv(name, str(default)))
    except ValueError:
        return default


ENGINE = MeshEngine(
    registry_url=os.getenv("GA_SERVICE_REGISTRY_URL", "http://estate-registry:8000"),
    event_gateway_url=os.getenv("GA_EVENT_GATEWAY_URL", ""),
    shared_secret=os.getenv("GA_MESH_SHARED_SECRET", ""),
    max_capture_bytes=_int_env("GA_MESH_MAX_CAPTURE_BYTES", 65536),
)
RESOLVER = GlobalResolver()
DISPATCH = DispatchFabric(RESOLVER)

app = FastAPI(
    title="Ghost Atlas Estate Service Mesh / Runtime Connectivity Fabric",
    version="0.3.0",
)


class AdvertiseRequest(BaseModel):
    canonical_id: str = Field(min_length=1)
    capabilities: list[str] = Field(default_factory=list)
    resources: dict[str, Any] = Field(default_factory=dict)
    health: str = "online"
    metadata: dict[str, Any] = Field(default_factory=dict)


class HeartbeatRequest(BaseModel):
    canonical_id: str = Field(min_length=1)
    health: str = "online"
    resources: dict[str, Any] | None = None


class GlobalResolveRequest(BaseModel):
    capability: str = Field(min_length=1)
    source: str | None = None
    io_class: str | None = None
    security_class: str | None = None
    prefer_local: bool = True


class DispatchRequest(BaseModel):
    packet_id: str = Field(min_length=1)
    capability: str = Field(min_length=1)
    payload: dict[str, Any] = Field(default_factory=dict)
    source: str = "ga://organ/packet-os"
    io_class: str = "PACKET"
    security_class: str | None = None
    prefer_local: bool = True
    execute: bool = False


class DispatchStageRequest(BaseModel):
    organ: str = Field(min_length=1)
    evidence: dict[str, Any] = Field(default_factory=dict)


class DispatchFailRequest(BaseModel):
    reason: str = Field(min_length=1)
    retryable: bool = True


def _raise_mesh(exc: MeshError) -> None:
    raise HTTPException(status_code=exc.status_code, detail=exc.detail) from exc


def _raise_resolution(exc: ResolutionError) -> None:
    raise HTTPException(status_code=exc.status_code, detail=exc.detail) from exc


@app.get("/health")
def health() -> dict[str, Any]:
    validation = RESOLVER.validate()
    return {
        "status": "ok" if validation["status"] == "pass" else "degraded",
        "service": "estate.service-mesh",
        "registry_url": ENGINE.registry_url,
        "policies": len(ENGINE.policies),
        "events": len(ENGINE.events.events),
        "circuits": ENGINE.circuits.snapshot(),
        "service_identity_signing": bool(ENGINE.shared_secret),
        "global_resolution": validation,
        "dispatch_fabric": "GA-HYPERNET-GLOBAL-RESOLUTION-003",
        "dispatches": len(DISPATCH.records),
    }


@app.get("/ready")
def ready() -> dict[str, str]:
    validation = RESOLVER.validate()
    if validation["status"] != "pass":
        raise HTTPException(status_code=503, detail=validation)
    return {"status": "ready", "service": "estate.service-mesh", "resolver": "GA-HYPERNET-GLOBAL-RESOLUTION-003"}


@app.get("/v1/mesh/policies")
def list_policies() -> dict[str, Any]:
    return {"default": MeshPolicy().model_dump(), "overrides": {key: value.model_dump() for key, value in sorted(ENGINE.policies.items())}}


@app.put("/v1/mesh/policies/{capability_id}")
def set_policy(capability_id: str, policy: MeshPolicy) -> dict[str, Any]:
    ENGINE.set_policy(capability_id, policy)
    return {"capability_id": capability_id, "policy": policy.model_dump()}


@app.post("/v1/mesh/resolve")
async def resolve(request: ResolveRequest) -> dict[str, Any]:
    try:
        return await ENGINE.resolve(request)
    except MeshError as exc:
        _raise_mesh(exc)


@app.post("/v1/mesh/invoke")
async def invoke(request: InvokeRequest) -> dict[str, Any]:
    try:
        return await ENGINE.invoke(request)
    except MeshError as exc:
        _raise_mesh(exc)


@app.get("/v1/mesh/circuits")
def circuits() -> dict[str, Any]:
    return {"items": ENGINE.circuits.snapshot()}


@app.post("/v1/mesh/circuits/{service_id}/reset")
def reset_circuit(service_id: str) -> dict[str, str]:
    ENGINE.circuits.reset(service_id)
    return {"service_id": service_id, "state": "closed"}


@app.get("/v1/mesh/events")
def events() -> dict[str, Any]:
    return {"items": list(ENGINE.events.events)}


@app.get("/v1/global/validate")
def global_validate() -> dict[str, Any]:
    return RESOLVER.validate()


@app.post("/v1/global/reload")
def global_reload() -> dict[str, Any]:
    try:
        return RESOLVER.reload()
    except ResolutionError as exc:
        _raise_resolution(exc)


@app.post("/v1/global/advertise")
def global_advertise(request: AdvertiseRequest) -> dict[str, Any]:
    try:
        return RESOLVER.advertise(request.canonical_id, request.capabilities, request.resources, request.health, request.metadata)
    except ResolutionError as exc:
        _raise_resolution(exc)


@app.post("/v1/global/heartbeat")
def global_heartbeat(request: HeartbeatRequest) -> dict[str, Any]:
    try:
        return RESOLVER.heartbeat(request.canonical_id, request.health, request.resources)
    except ResolutionError as exc:
        _raise_resolution(exc)


@app.post("/v1/global/resolve")
def global_resolve(request: GlobalResolveRequest) -> dict[str, Any]:
    try:
        return RESOLVER.resolve(request.capability, source=request.source, io_class=request.io_class, security_class=request.security_class, prefer_local=request.prefer_local)
    except ResolutionError as exc:
        _raise_resolution(exc)


@app.get("/v1/global/topology")
def global_topology() -> dict[str, Any]:
    return RESOLVER.topology()


@app.get("/v1/global/nodes/{node_id:path}")
def global_node(node_id: str) -> dict[str, Any]:
    canonical_id = node_id if node_id.startswith("ga://") else f"ga://node/{node_id}"
    try:
        return RESOLVER.node_snapshot(canonical_id)
    except ResolutionError as exc:
        _raise_resolution(exc)


@app.get("/v1/global/events")
def global_events() -> dict[str, Any]:
    return {"items": RESOLVER.events()}


@app.post("/v1/dispatch")
def dispatch(request: DispatchRequest) -> dict[str, Any]:
    try:
        return DISPATCH.dispatch(packet_id=request.packet_id, capability=request.capability, payload=request.payload, source=request.source, io_class=request.io_class, security_class=request.security_class, prefer_local=request.prefer_local, execute=request.execute)
    except ResolutionError as exc:
        _raise_resolution(exc)


@app.post("/v1/dispatch/{dispatch_id}/execute")
def dispatch_execute(dispatch_id: str) -> dict[str, Any]:
    try:
        return DISPATCH.execute(dispatch_id)
    except ResolutionError as exc:
        _raise_resolution(exc)


@app.post("/v1/dispatch/{dispatch_id}/stage")
def dispatch_stage(dispatch_id: str, request: DispatchStageRequest) -> dict[str, Any]:
    try:
        return DISPATCH.complete_stage(dispatch_id, request.organ, request.evidence)
    except ResolutionError as exc:
        _raise_resolution(exc)


@app.post("/v1/dispatch/{dispatch_id}/fail")
def dispatch_fail(dispatch_id: str, request: DispatchFailRequest) -> dict[str, Any]:
    try:
        return DISPATCH.fail(dispatch_id, request.reason, request.retryable)
    except ResolutionError as exc:
        _raise_resolution(exc)


@app.get("/v1/dispatch/{dispatch_id}")
def dispatch_get(dispatch_id: str) -> dict[str, Any]:
    try:
        return DISPATCH.snapshot(dispatch_id)
    except ResolutionError as exc:
        _raise_resolution(exc)


@app.get("/v1/dispatch")
def dispatch_topology() -> dict[str, Any]:
    return DISPATCH.topology()


async def _event_stream() -> AsyncIterator[str]:
    queue = ENGINE.events.subscribe()
    try:
        while True:
            try:
                event = await asyncio.wait_for(queue.get(), timeout=15)
                yield f"event: {event['event_type']}\ndata: {json.dumps(event, separators=(',', ':'))}\n\n"
            except asyncio.TimeoutError:
                yield ": keepalive\n\n"
    finally:
        ENGINE.events.unsubscribe(queue)


@app.get("/v1/mesh/events/stream")
async def event_stream() -> StreamingResponse:
    return StreamingResponse(_event_stream(), media_type="text/event-stream", headers={"cache-control": "no-cache", "x-accel-buffering": "no"})
