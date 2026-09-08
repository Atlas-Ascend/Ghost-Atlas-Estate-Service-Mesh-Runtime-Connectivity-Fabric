from __future__ import annotations

import asyncio
import hashlib
import hmac
import json
import time
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

import httpx

from .models import CircuitSnapshot, InvokeRequest, MeshPolicy, ResolveRequest


class MeshError(RuntimeError):
    def __init__(self, status_code: int, detail: str):
        super().__init__(detail)
        self.status_code = status_code
        self.detail = detail


@dataclass
class _CircuitState:
    failures: int = 0
    state: str = "closed"
    opened_at: float | None = None


class CircuitBreaker:
    def __init__(self) -> None:
        self._states: dict[str, _CircuitState] = {}

    def can_attempt(self, service_id: str, policy: MeshPolicy) -> bool:
        state = self._states.setdefault(service_id, _CircuitState())
        if state.state != "open":
            return True
        if state.opened_at is None:
            return False
        if time.monotonic() - state.opened_at >= policy.recovery_seconds:
            state.state = "half-open"
            return True
        return False

    def success(self, service_id: str) -> None:
        self._states[service_id] = _CircuitState()

    def failure(self, service_id: str, policy: MeshPolicy) -> None:
        state = self._states.setdefault(service_id, _CircuitState())
        state.failures += 1
        if state.state == "half-open" or state.failures >= policy.circuit_failure_threshold:
            state.state = "open"
            state.opened_at = time.monotonic()

    def reset(self, service_id: str) -> None:
        self._states[service_id] = _CircuitState()

    def snapshot(self) -> list[dict[str, Any]]:
        return [
            CircuitSnapshot(
                service_id=service_id,
                failures=state.failures,
                state=state.state,  # type: ignore[arg-type]
                opened_at=state.opened_at,
            ).model_dump()
            for service_id, state in sorted(self._states.items())
        ]


class EventBus:
    def __init__(self, max_events: int = 1000) -> None:
        self.max_events = max_events
        self.events: list[dict[str, Any]] = []
        self.subscribers: set[asyncio.Queue[dict[str, Any]]] = set()

    def emit(self, event_type: str, correlation_id: str, payload: dict[str, Any]) -> dict[str, Any]:
        event = {
            "event_id": f"GA-MESH-EVT-{uuid.uuid4().hex[:16]}",
            "event_type": event_type,
            "source": "estate.service-mesh",
            "occurred_at": datetime.now(timezone.utc).isoformat(),
            "correlation_id": correlation_id,
            "payload": payload,
        }
        self.events.append(event)
        if len(self.events) > self.max_events:
            self.events = self.events[-self.max_events :]
        for queue in tuple(self.subscribers):
            try:
                queue.put_nowait(event)
            except asyncio.QueueFull:
                pass
        return event

    def subscribe(self) -> asyncio.Queue[dict[str, Any]]:
        queue: asyncio.Queue[dict[str, Any]] = asyncio.Queue(maxsize=100)
        self.subscribers.add(queue)
        return queue

    def unsubscribe(self, queue: asyncio.Queue[dict[str, Any]]) -> None:
        self.subscribers.discard(queue)


class MeshEngine:
    def __init__(
        self,
        registry_url: str,
        event_gateway_url: str = "",
        shared_secret: str = "",
        max_capture_bytes: int = 65536,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self.registry_url = registry_url.rstrip("/")
        self.event_gateway_url = event_gateway_url.rstrip("/")
        self.shared_secret = shared_secret
        self.max_capture_bytes = max(1024, min(max_capture_bytes, 1_048_576))
        self.transport = transport
        self.policies: dict[str, MeshPolicy] = {}
        self.circuits = CircuitBreaker()
        self.events = EventBus()

    def get_policy(self, capability_id: str) -> MeshPolicy:
        return self.policies.get(capability_id, MeshPolicy())

    def set_policy(self, capability_id: str, policy: MeshPolicy) -> MeshPolicy:
        self.policies[capability_id] = policy
        return policy

    def _correlation_id(self, supplied: str | None) -> str:
        return supplied or f"GA-MESH-RUN-{uuid.uuid4().hex[:16]}"

    def _identity_headers(self, caller: str, correlation_id: str, method: str, url: str) -> dict[str, str]:
        timestamp = str(int(time.time()))
        headers = {
            "x-ga-caller-service": caller,
            "x-ga-correlation-id": correlation_id,
            "x-ga-mesh-timestamp": timestamp,
        }
        if self.shared_secret:
            canonical = "\n".join([caller, correlation_id, timestamp, method.upper(), url])
            signature = hmac.new(
                self.shared_secret.encode("utf-8"),
                canonical.encode("utf-8"),
                hashlib.sha256,
            ).hexdigest()
            headers["x-ga-mesh-signature"] = f"sha256={signature}"
        return headers

    async def _registry_candidates(self, request: ResolveRequest, policy: MeshPolicy) -> list[dict[str, Any]]:
        try:
            async with httpx.AsyncClient(transport=self.transport, timeout=5.0) as client:
                response = await client.post(
                    f"{self.registry_url}/v1/resolve",
                    json={
                        "capability_id": request.capability_id,
                        "environment": request.environment,
                        "allow_degraded": policy.allow_degraded,
                    },
                )
        except httpx.HTTPError as exc:
            raise MeshError(503, f"registry unavailable: {exc.__class__.__name__}") from exc

        if response.status_code == 404:
            raise MeshError(404, "capability not registered")
        if response.status_code >= 400:
            raise MeshError(503, "no health-qualified runtime provider available")

        payload = response.json()
        candidates = payload.get("candidates", [])
        if not isinstance(candidates, list) or not candidates:
            raise MeshError(503, "registry returned no runtime candidates")
        return candidates

    async def resolve(self, request: ResolveRequest) -> dict[str, Any]:
        correlation_id = self._correlation_id(request.correlation_id)
        policy = self.get_policy(request.capability_id)
        candidates = await self._registry_candidates(request, policy)
        eligible: list[dict[str, Any]] = []
        blocked: list[str] = []
        for candidate in candidates:
            service_id = candidate["service"]["id"]
            if self.circuits.can_attempt(service_id, policy):
                eligible.append(candidate)
            else:
                blocked.append(service_id)

        if not eligible:
            self.events.emit(
                "mesh.route.blocked",
                correlation_id,
                {"capability_id": request.capability_id, "blocked_by_open_circuit": blocked},
            )
            raise MeshError(503, "all health-qualified providers are blocked by open circuits")

        selected = eligible[0]
        self.events.emit(
            "mesh.route.resolved",
            correlation_id,
            {
                "capability_id": request.capability_id,
                "environment": request.environment,
                "selected_service": selected["service"]["id"],
                "candidate_count": len(eligible),
                "open_circuit_skips": blocked,
            },
        )
        return {
            "correlation_id": correlation_id,
            "capability_id": request.capability_id,
            "environment": request.environment,
            "selected": selected,
            "candidates": eligible,
            "policy": policy.model_dump(),
            "resolution": "ghost-atlas-mesh-v1",
        }

    def _target_url(self, endpoint: str, path: str) -> str:
        if not path:
            return endpoint
        return f"{endpoint.rstrip('/')}/{path.lstrip('/')}"

    def _captured_body(self, response: httpx.Response) -> Any:
        raw = response.content[: self.max_capture_bytes]
        content_type = response.headers.get("content-type", "")
        if "application/json" in content_type:
            try:
                return json.loads(raw.decode("utf-8"))
            except (UnicodeDecodeError, json.JSONDecodeError):
                pass
        return raw.decode("utf-8", errors="replace")

    async def _publish_event(self, event: dict[str, Any]) -> None:
        if not self.event_gateway_url:
            return
        try:
            async with httpx.AsyncClient(transport=self.transport, timeout=2.0) as client:
                await client.post(self.event_gateway_url, json=event)
        except httpx.HTTPError:
            return

    async def invoke(self, request: InvokeRequest) -> dict[str, Any]:
        correlation_id = self._correlation_id(request.correlation_id)
        policy = self.get_policy(request.capability_id)
        resolve_request = ResolveRequest(
            capability_id=request.capability_id,
            environment=request.environment,
            caller_service=request.caller_service,
            correlation_id=correlation_id,
        )
        candidates = await self._registry_candidates(resolve_request, policy)
        attempts: list[dict[str, Any]] = []

        start_event = self.events.emit(
            "mesh.invocation.started",
            correlation_id,
            {
                "capability_id": request.capability_id,
                "environment": request.environment,
                "caller_service": request.caller_service,
                "provider_candidates": [c["service"]["id"] for c in candidates],
            },
        )
        await self._publish_event(start_event)

        for candidate in candidates:
            service_id = candidate["service"]["id"]
            if not self.circuits.can_attempt(service_id, policy):
                attempts.append({"service_id": service_id, "result": "open-circuit-skip"})
                continue

            target_url = self._target_url(candidate["endpoint"], request.path)
            for attempt_number in range(1, policy.retries + 2):
                headers = dict(request.headers)
                headers.update(
                    self._identity_headers(
                        request.caller_service,
                        correlation_id,
                        request.method,
                        target_url,
                    )
                )
                started = time.monotonic()
                try:
                    async with httpx.AsyncClient(
                        transport=self.transport,
                        timeout=policy.timeout_ms / 1000,
                    ) as client:
                        response = await client.request(
                            request.method,
                            target_url,
                            params=request.query,
                            headers=headers,
                            json=request.body if request.body is not None else None,
                        )
                    latency_ms = round((time.monotonic() - started) * 1000, 2)

                    if response.status_code < 500:
                        self.circuits.success(service_id)
                        attempts.append(
                            {
                                "service_id": service_id,
                                "attempt": attempt_number,
                                "status_code": response.status_code,
                                "latency_ms": latency_ms,
                                "result": "completed",
                            }
                        )
                        event = self.events.emit(
                            "mesh.invocation.completed",
                            correlation_id,
                            {
                                "capability_id": request.capability_id,
                                "provider": service_id,
                                "status_code": response.status_code,
                                "latency_ms": latency_ms,
                                "attempts": attempts,
                            },
                        )
                        await self._publish_event(event)
                        return {
                            "correlation_id": correlation_id,
                            "capability_id": request.capability_id,
                            "provider": service_id,
                            "endpoint": target_url,
                            "status_code": response.status_code,
                            "response_headers": {
                                "content-type": response.headers.get("content-type", "")
                            },
                            "body": self._captured_body(response),
                            "attempts": attempts,
                            "mesh": "ghost-atlas-mesh-v1",
                        }

                    self.circuits.failure(service_id, policy)
                    attempts.append(
                        {
                            "service_id": service_id,
                            "attempt": attempt_number,
                            "status_code": response.status_code,
                            "latency_ms": latency_ms,
                            "result": "upstream-5xx",
                        }
                    )
                except (httpx.TimeoutException, httpx.NetworkError) as exc:
                    self.circuits.failure(service_id, policy)
                    attempts.append(
                        {
                            "service_id": service_id,
                            "attempt": attempt_number,
                            "result": exc.__class__.__name__,
                        }
                    )

                if not self.circuits.can_attempt(service_id, policy):
                    break

        event = self.events.emit(
            "mesh.invocation.failed",
            correlation_id,
            {
                "capability_id": request.capability_id,
                "attempts": attempts,
                "reason": "all providers exhausted",
            },
        )
        await self._publish_event(event)
        raise MeshError(502, "all mesh providers exhausted")
