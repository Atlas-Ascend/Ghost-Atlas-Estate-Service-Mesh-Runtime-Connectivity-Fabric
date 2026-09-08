from __future__ import annotations

import asyncio
import json
import os
from typing import Any, AsyncIterator

from fastapi import FastAPI, HTTPException
from fastapi.responses import StreamingResponse

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

app = FastAPI(
    title="Ghost Atlas Estate Service Mesh / Runtime Connectivity Fabric",
    version="0.1.0",
)


def _raise_mesh(exc: MeshError) -> None:
    raise HTTPException(status_code=exc.status_code, detail=exc.detail) from exc


@app.get("/health")
def health() -> dict[str, Any]:
    return {
        "status": "ok",
        "service": "estate.service-mesh",
        "registry_url": ENGINE.registry_url,
        "policies": len(ENGINE.policies),
        "events": len(ENGINE.events.events),
        "circuits": ENGINE.circuits.snapshot(),
        "service_identity_signing": bool(ENGINE.shared_secret),
    }


@app.get("/ready")
def ready() -> dict[str, str]:
    return {"status": "ready", "service": "estate.service-mesh"}


@app.get("/v1/mesh/policies")
def list_policies() -> dict[str, Any]:
    return {
        "default": MeshPolicy().model_dump(),
        "overrides": {key: value.model_dump() for key, value in sorted(ENGINE.policies.items())},
    }


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
    return StreamingResponse(
        _event_stream(),
        media_type="text/event-stream",
        headers={"cache-control": "no-cache", "x-accel-buffering": "no"},
    )
