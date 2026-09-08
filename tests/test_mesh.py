from __future__ import annotations

import httpx
import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.mesh import MeshEngine, MeshError
from app.models import InvokeRequest, MeshPolicy, ResolveRequest


def _registry_payload() -> dict:
    return {
        "capability": {"id": "estate.release.deploy"},
        "environment": "production",
        "selected": {
            "service": {"id": "estate.release-control"},
            "runtime": {"priority": 10},
            "endpoint": "http://svc1.local/deploy",
        },
        "candidates": [
            {
                "service": {"id": "estate.release-control"},
                "runtime": {"priority": 10},
                "endpoint": "http://svc1.local/deploy",
            },
            {
                "service": {"id": "estate.release-control-secondary"},
                "runtime": {"priority": 20},
                "endpoint": "http://svc2.local/deploy",
            },
        ],
        "resolution": "health-qualified-runtime-v1",
    }


@pytest.mark.asyncio
async def test_resolve_consumes_canonical_registry_candidates():
    async def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/v1/resolve"
        return httpx.Response(200, json=_registry_payload())

    engine = MeshEngine(
        registry_url="http://registry.local",
        transport=httpx.MockTransport(handler),
    )
    result = await engine.resolve(
        ResolveRequest(capability_id="estate.release.deploy", environment="production")
    )

    assert result["selected"]["service"]["id"] == "estate.release-control"
    assert result["resolution"] == "ghost-atlas-mesh-v1"
    assert result["correlation_id"].startswith("GA-MESH-RUN-")


@pytest.mark.asyncio
async def test_invoke_fails_over_after_5xx_and_opens_circuit():
    seen: list[tuple[str, str | None, str | None]] = []

    async def handler(request: httpx.Request) -> httpx.Response:
        if request.url.host == "registry.local":
            return httpx.Response(200, json=_registry_payload())
        seen.append(
            (
                request.url.host or "",
                request.headers.get("x-ga-caller-service"),
                request.headers.get("x-ga-mesh-signature"),
            )
        )
        if request.url.host == "svc1.local":
            return httpx.Response(503, json={"error": "down"})
        return httpx.Response(200, json={"deployed": True})

    engine = MeshEngine(
        registry_url="http://registry.local",
        shared_secret="test-secret",
        transport=httpx.MockTransport(handler),
    )
    engine.set_policy(
        "estate.release.deploy",
        MeshPolicy(retries=0, circuit_failure_threshold=1, recovery_seconds=60),
    )

    result = await engine.invoke(
        InvokeRequest(
            capability_id="estate.release.deploy",
            caller_service="estate.command-center",
            body={"release_id": "GA-REL-1"},
        )
    )

    assert result["provider"] == "estate.release-control-secondary"
    assert result["status_code"] == 200
    assert result["body"] == {"deployed": True}
    assert [entry["result"] for entry in result["attempts"]] == [
        "upstream-5xx",
        "completed",
    ]
    assert seen[0][1] == "estate.command-center"
    assert seen[0][2] is not None and seen[0][2].startswith("sha256=")

    circuits = {item["service_id"]: item for item in engine.circuits.snapshot()}
    assert circuits["estate.release-control"]["state"] == "open"
    assert circuits["estate.release-control-secondary"]["state"] == "closed"


@pytest.mark.asyncio
async def test_application_4xx_is_returned_without_failover():
    calls: list[str] = []

    async def handler(request: httpx.Request) -> httpx.Response:
        if request.url.host == "registry.local":
            return httpx.Response(200, json=_registry_payload())
        calls.append(request.url.host or "")
        return httpx.Response(409, json={"detail": "conflict"})

    engine = MeshEngine(
        registry_url="http://registry.local",
        transport=httpx.MockTransport(handler),
    )
    result = await engine.invoke(
        InvokeRequest(capability_id="estate.release.deploy")
    )

    assert result["status_code"] == 409
    assert result["provider"] == "estate.release-control"
    assert calls == ["svc1.local"]


@pytest.mark.asyncio
async def test_open_circuit_is_skipped_during_resolution():
    async def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=_registry_payload())

    engine = MeshEngine(
        registry_url="http://registry.local",
        transport=httpx.MockTransport(handler),
    )
    policy = MeshPolicy(circuit_failure_threshold=1, recovery_seconds=60)
    engine.set_policy("estate.release.deploy", policy)
    engine.circuits.failure("estate.release-control", policy)

    result = await engine.resolve(
        ResolveRequest(capability_id="estate.release.deploy")
    )
    assert result["selected"]["service"]["id"] == "estate.release-control-secondary"


@pytest.mark.asyncio
async def test_registry_failure_fails_closed():
    async def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(503, json={"detail": "no provider"})

    engine = MeshEngine(
        registry_url="http://registry.local",
        transport=httpx.MockTransport(handler),
    )
    with pytest.raises(MeshError) as exc:
        await engine.resolve(ResolveRequest(capability_id="estate.release.deploy"))
    assert exc.value.status_code == 503


def test_http_health_and_policy_surface():
    client = TestClient(app)
    health = client.get("/health")
    assert health.status_code == 200
    assert health.json()["service"] == "estate.service-mesh"

    policy = client.put(
        "/v1/mesh/policies/estate.release.deploy",
        json={
            "timeout_ms": 2500,
            "retries": 1,
            "circuit_failure_threshold": 2,
            "recovery_seconds": 15,
            "allow_degraded": False,
        },
    )
    assert policy.status_code == 200
    assert policy.json()["policy"]["timeout_ms"] == 2500


def test_policy_bounds_fail_validation():
    with pytest.raises(ValueError):
        MeshPolicy(retries=100)
