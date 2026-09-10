from __future__ import annotations

import hashlib
import json
import time
from dataclasses import dataclass, field
from pathlib import Path
from threading import RLock
from typing import Any

import yaml


REGISTRY_ROOT = Path(__file__).resolve().parents[1] / "global-resolution" / "registry"


class ResolutionError(RuntimeError):
    def __init__(self, detail: str, status_code: int = 400) -> None:
        super().__init__(detail)
        self.detail = detail
        self.status_code = status_code


@dataclass
class NodeState:
    canonical_id: str
    last_seen: float
    health: str = "online"
    resources: dict[str, Any] = field(default_factory=dict)
    capabilities: set[str] = field(default_factory=set)
    metadata: dict[str, Any] = field(default_factory=dict)


class GlobalResolver:
    """Live resolver for GA-HYPERNET-GLOBAL-RESOLUTION-002.

    Resolution order:
    authority -> security -> capability -> runtime -> resource -> transport -> proof.
    """

    registry_files = (
        "nodes.yaml",
        "organs.yaml",
        "capabilities.yaml",
        "services.yaml",
        "repos.yaml",
        "routes.yaml",
    )

    def __init__(self, registry_root: Path | None = None) -> None:
        self.registry_root = registry_root or REGISTRY_ROOT
        self._lock = RLock()
        self._registries: dict[str, dict[str, Any]] = {}
        self._nodes: dict[str, NodeState] = {}
        self._events: list[dict[str, Any]] = []
        self.reload()

    def reload(self) -> dict[str, Any]:
        loaded: dict[str, dict[str, Any]] = {}
        for name in self.registry_files:
            path = self.registry_root / name
            if not path.exists():
                raise ResolutionError(f"missing registry: {name}", 500)
            payload = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
            if not isinstance(payload, dict):
                raise ResolutionError(f"invalid registry root: {name}", 500)
            loaded[name] = payload
        with self._lock:
            self._registries = loaded
        return self.validate()

    @staticmethod
    def _items(payload: dict[str, Any]) -> list[dict[str, Any]]:
        for key in ("nodes", "organs", "capabilities", "services", "repos", "routes"):
            value = payload.get(key)
            if isinstance(value, list):
                return [item for item in value if isinstance(item, dict)]
        return []

    def _index(self, registry: str) -> dict[str, dict[str, Any]]:
        return {
            str(item.get("canonical_id")): item
            for item in self._items(self._registries[registry])
            if item.get("canonical_id")
        }

    def validate(self) -> dict[str, Any]:
        errors: list[str] = []
        seen: dict[str, str] = {}
        counts: dict[str, int] = {}
        for name, payload in self._registries.items():
            items = self._items(payload)
            counts[name] = len(items)
            for item in items:
                cid = item.get("canonical_id")
                if not cid or not isinstance(cid, str) or not cid.startswith("ga://"):
                    errors.append(f"{name}: invalid canonical_id {cid!r}")
                    continue
                prior = seen.get(cid)
                if prior:
                    errors.append(f"duplicate canonical_id {cid}: {prior}, {name}")
                seen[cid] = name

        route_index = self._index("routes.yaml")
        known = set(seen)
        for route_id, route in route_index.items():
            for key in ("source", "proof", "fallback"):
                ref = route.get(key)
                if isinstance(ref, str) and ref.startswith("ga://") and ref not in known:
                    errors.append(f"{route_id}: unresolved {key} {ref}")
            for ref in route.get("path", []) or []:
                if isinstance(ref, str) and ref.startswith("ga://") and ref not in known:
                    errors.append(f"{route_id}: unresolved path member {ref}")

        digest = hashlib.sha256(
            json.dumps(self._registries, sort_keys=True, default=str).encode("utf-8")
        ).hexdigest()
        return {
            "status": "pass" if not errors else "fail",
            "resolution_id": "GA-HYPERNET-GLOBAL-RESOLUTION-002",
            "registry_digest": digest,
            "counts": counts,
            "errors": errors,
        }

    def advertise(
        self,
        canonical_id: str,
        capabilities: list[str],
        resources: dict[str, Any] | None = None,
        health: str = "online",
        metadata: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        known_nodes = self._index("nodes.yaml")
        if canonical_id not in known_nodes:
            raise ResolutionError(f"unknown node {canonical_id}", 404)

        declared = {str(x) for x in known_nodes[canonical_id].get("capabilities", [])}
        normalized = {self._normalize_capability(x) for x in capabilities}
        state = NodeState(
            canonical_id=canonical_id,
            last_seen=time.time(),
            health=health,
            resources=resources or {},
            capabilities=normalized | declared,
            metadata=metadata or {},
        )
        with self._lock:
            self._nodes[canonical_id] = state
        event = self._emit("estate.node.online", canonical_id, {"health": health})
        return {"node": self.node_snapshot(canonical_id), "event": event}

    def heartbeat(
        self,
        canonical_id: str,
        health: str = "online",
        resources: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        if canonical_id not in self._index("nodes.yaml"):
            raise ResolutionError(f"unknown node {canonical_id}", 404)
        with self._lock:
            state = self._nodes.get(canonical_id)
            if state is None:
                state = NodeState(canonical_id=canonical_id, last_seen=time.time())
                self._nodes[canonical_id] = state
            state.last_seen = time.time()
            state.health = health
            if resources is not None:
                state.resources = resources
        self._emit("estate.node.heartbeat", canonical_id, {"health": health})
        return self.node_snapshot(canonical_id)

    def expire(self, ttl_seconds: int = 90) -> list[str]:
        cutoff = time.time() - ttl_seconds
        expired: list[str] = []
        with self._lock:
            for node_id, state in self._nodes.items():
                if state.last_seen < cutoff and state.health != "offline":
                    state.health = "offline"
                    expired.append(node_id)
        for node_id in expired:
            self._emit("estate.node.offline", node_id, {"reason": "heartbeat-expired"})
        return expired

    def node_snapshot(self, canonical_id: str) -> dict[str, Any]:
        with self._lock:
            state = self._nodes.get(canonical_id)
            if state is None:
                declared = self._index("nodes.yaml").get(canonical_id)
                if declared is None:
                    raise ResolutionError(f"unknown node {canonical_id}", 404)
                return {"canonical_id": canonical_id, "health": "undiscovered", "declared": declared}
            return {
                "canonical_id": state.canonical_id,
                "health": state.health,
                "last_seen": state.last_seen,
                "resources": state.resources,
                "capabilities": sorted(state.capabilities),
                "metadata": state.metadata,
            }

    def topology(self) -> dict[str, Any]:
        self.expire()
        declared = self._index("nodes.yaml")
        return {
            "resolution_id": "GA-HYPERNET-GLOBAL-RESOLUTION-002",
            "nodes": [self.node_snapshot(node_id) for node_id in sorted(declared)],
            "events": self._events[-100:],
        }

    def resolve(
        self,
        capability: str,
        *,
        source: str | None = None,
        io_class: str | None = None,
        security_class: str | None = None,
        prefer_local: bool = True,
    ) -> dict[str, Any]:
        capability_id = self._normalize_capability(capability)
        capability_index = self._index("capabilities.yaml")
        spec = capability_index.get(capability_id)
        if spec is None:
            raise ResolutionError(f"unknown capability {capability_id}", 404)

        routes = list(self._index("routes.yaml").values())
        matching = [route for route in routes if route.get("capability") == capability_id]
        if source:
            exact_source = [route for route in matching if route.get("source") == source]
            if exact_source:
                matching = exact_source
        if io_class:
            io_class = io_class.upper()
            matching = [route for route in matching if io_class in (route.get("accepts") or [])]

        runtime_preference: list[str] = []
        for route in matching:
            runtime_preference.extend(route.get("runtime_preference") or [])
        runtime_preference = list(dict.fromkeys(runtime_preference))

        candidates = self._candidate_nodes(capability_id, runtime_preference, security_class)
        if prefer_local:
            candidates.sort(key=lambda x: (x["location"] != "sovereign-local", -x["score"]))
        else:
            candidates.sort(key=lambda x: -x["score"])

        selected = candidates[0] if candidates else None
        route = matching[0] if matching else None
        result = {
            "resolution_id": "GA-HYPERNET-GLOBAL-RESOLUTION-002",
            "capability": capability_id,
            "owner": spec.get("owner"),
            "source": source,
            "route": route,
            "selected": selected,
            "candidates": candidates,
            "proof": (route or {}).get("proof", "ga://organ/proofgrid"),
            "resolution_order": ["authority", "security", "capability", "runtime", "resource", "transport", "proof"],
        }
        self._emit("estate.route.resolved", source or "ga://organ/crowngrid", result)
        return result

    def _candidate_nodes(
        self,
        capability_id: str,
        runtime_preference: list[str],
        security_class: str | None,
    ) -> list[dict[str, Any]]:
        short = capability_id.removeprefix("ga://capability/")
        declared = self._index("nodes.yaml")
        result: list[dict[str, Any]] = []
        for node_id, node in declared.items():
            declared_caps = {str(x) for x in node.get("capabilities", [])}
            live = self._nodes.get(node_id)
            live_caps = live.capabilities if live else set()
            if short not in declared_caps and capability_id not in live_caps and short not in live_caps:
                continue
            if security_class and node.get("security_class") not in {security_class, "mixed"}:
                continue
            health = live.health if live else "undiscovered"
            if health in {"offline", "failed"}:
                continue
            score = 100 if health == "online" else 25
            if node_id in runtime_preference:
                score += max(1, 50 - runtime_preference.index(node_id) * 5)
            resources = live.resources if live else {}
            score += int(resources.get("capacity_score", 0) or 0)
            result.append({
                "canonical_id": node_id,
                "score": score,
                "health": health,
                "runtime": node.get("runtime"),
                "location": node.get("location"),
                "transport": node.get("transport", []),
                "security_class": node.get("security_class"),
                "resources": resources,
            })
        return result

    @staticmethod
    def _normalize_capability(value: str) -> str:
        if value.startswith("ga://capability/"):
            return value
        return f"ga://capability/{value}"

    def _emit(self, event_type: str, source: str, payload: dict[str, Any]) -> dict[str, Any]:
        event = {
            "event_type": event_type,
            "source": source,
            "timestamp": time.time(),
            "payload": payload,
        }
        with self._lock:
            self._events.append(event)
            if len(self._events) > 1000:
                del self._events[:-1000]
        return event

    def events(self) -> list[dict[str, Any]]:
        with self._lock:
            return list(self._events)
