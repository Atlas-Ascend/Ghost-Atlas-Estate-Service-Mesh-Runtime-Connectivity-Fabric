from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field


class MeshPolicy(BaseModel):
    timeout_ms: int = Field(default=5000, ge=100, le=30000)
    retries: int = Field(default=2, ge=0, le=5)
    circuit_failure_threshold: int = Field(default=3, ge=1, le=20)
    recovery_seconds: int = Field(default=30, ge=1, le=300)
    allow_degraded: bool = False


class ResolveRequest(BaseModel):
    capability_id: str = Field(min_length=1)
    environment: str = Field(default="production", min_length=1)
    caller_service: str = Field(default="estate.mesh", min_length=1)
    correlation_id: str | None = None


class InvokeRequest(BaseModel):
    capability_id: str = Field(min_length=1)
    environment: str = Field(default="production", min_length=1)
    method: Literal["GET", "POST", "PUT", "PATCH", "DELETE"] = "POST"
    path: str = ""
    query: dict[str, str] = Field(default_factory=dict)
    headers: dict[str, str] = Field(default_factory=dict)
    body: Any = None
    caller_service: str = Field(default="estate.mesh", min_length=1)
    correlation_id: str | None = None


class CircuitSnapshot(BaseModel):
    service_id: str
    failures: int = 0
    state: Literal["closed", "open", "half-open"] = "closed"
    opened_at: float | None = None
