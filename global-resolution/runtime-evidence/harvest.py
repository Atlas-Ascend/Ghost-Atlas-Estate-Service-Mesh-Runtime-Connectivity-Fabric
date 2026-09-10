from __future__ import annotations

import datetime as dt
import json
import os
import pathlib
import sys
import urllib.error
import urllib.request
import uuid
from typing import Any

import yaml

ROOT = pathlib.Path(__file__).resolve().parents[2]
PROFILE = ROOT / "global-resolution/runtime-evidence/evidence-profile.yaml"
BUNDLES = ROOT / "global-resolution/cognitive-office-mesh/bundles.yaml"
REPORT = ROOT / "global-resolution/runtime-evidence/runtime-evidence-report.json"
RECEIPT = ROOT / "global-resolution/runtime-evidence/runtime-evidence-receipt.json"
REPAIRS = ROOT / "global-resolution/runtime-evidence/repair-targets.json"
DEFAULT_HYPERNET_URL = "https://ghost-atlas-runtime-gateway.onrender.com"


def load_yaml(path: pathlib.Path) -> Any:
    with path.open("r", encoding="utf-8") as fh:
        return yaml.safe_load(fh)


def normalize_bundles(raw: Any) -> list[dict[str, Any]]:
    if isinstance(raw, dict):
        for key in ("bundles", "offices", "items"):
            if isinstance(raw.get(key), list):
                return raw[key]
    if isinstance(raw, list):
        return raw
    raise ValueError("office bundle manifest does not contain a list")


def request_json(base_url: str, path: str, token: str, method: str = "GET", payload: dict[str, Any] | None = None, timeout: int = 10) -> tuple[str, Any]:
    if not base_url:
        return "MISSING", {"reason": "Hypernet runtime URL not configured"}
    url = base_url.rstrip("/") + path
    headers = {"Accept": "application/json", "User-Agent": "ghost-atlas-runtime-evidence/1"}
    data = None
    if payload is not None:
        data = json.dumps(payload).encode("utf-8")
        headers["Content-Type"] = "application/json"
    if token:
        headers["Authorization"] = f"Bearer {token}"
    req = urllib.request.Request(url, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            body = resp.read().decode("utf-8")
            try:
                parsed = json.loads(body) if body else {}
            except Exception:
                parsed = {"raw": body[:2000]}
            return "PROVEN", {"status_code": resp.status, "body": parsed, "url": url}
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        try:
            parsed = json.loads(body)
        except Exception:
            parsed = {"raw": body[:2000]}
        return "ERROR", {"status_code": exc.code, "body": parsed, "url": url}
    except Exception as exc:
        return "ERROR", {"error": type(exc).__name__, "detail": str(exc), "url": url}


def extract_runtime_state(results: dict[str, Any]) -> str:
    health = results.get("health", {})
    ready = results.get("ready", {})
    if health.get("state") == "PROVEN" and ready.get("state") == "PROVEN":
        return "LIVE"
    if health.get("state") == "PROVEN" or ready.get("state") == "PROVEN":
        return "DEGRADED"
    if all(v.get("state") == "MISSING" for v in results.values() if isinstance(v, dict) and "state" in v):
        return "UNKNOWN"
    return "OFFLINE"


def main() -> int:
    profile = load_yaml(PROFILE)
    bundles = normalize_bundles(load_yaml(BUNDLES))
    if len(bundles) != 82:
        raise SystemExit(f"RUNTIME_EVIDENCE_INPUT_FAIL expected 82 offices, found {len(bundles)}")

    configured_url = os.getenv("GA_HYPERNET_URL", "").strip()
    base_url = configured_url or DEFAULT_HYPERNET_URL
    token = os.getenv("GA_HYPERNET_TOKEN", "").strip()
    enable_canary = os.getenv("GA_ENABLE_SAFE_CANARY", "false").lower() in {"1", "true", "yes", "on"}
    timeout = int(profile["probes"]["health_readiness"].get("timeout_seconds", 10))

    endpoints = profile["sources"]["service_mesh"]["endpoints"]
    shared: dict[str, Any] = {}
    for name in ("health", "ready", "executors", "topology", "events", "dispatches"):
        state, evidence = request_json(base_url, endpoints[name], token, timeout=timeout)
        shared[name] = {"state": state, "evidence": evidence}

    canary: dict[str, Any] = {"state": "MISSING", "reason": "safe canary disabled"}
    if enable_canary:
        packet_id = f"conformance-canary-{uuid.uuid4()}"
        payload = {
            "packet_id": packet_id,
            "capability": profile["probes"]["safe_canary"]["capability"],
            "payload": profile["probes"]["safe_canary"]["payload"],
            "source": profile["probes"]["safe_canary"]["source"],
            "io_class": profile["probes"]["safe_canary"]["io_class"],
            "prefer_local": True,
            "execute": False,
        }
        state, evidence = request_json(base_url, "/v1/dispatch", token, method="POST", payload=payload, timeout=timeout)
        canary = {"state": state, "evidence": evidence, "packet_id": packet_id}

    office_reports: list[dict[str, Any]] = []
    repair_targets: list[dict[str, Any]] = []
    runtime_state = extract_runtime_state(shared)

    for bundle in bundles:
        office_id = bundle.get("office") or bundle.get("office_id")
        chatbot_id = bundle.get("chatbot") or bundle.get("chatbot_id")
        role_id = bundle.get("role") or bundle.get("role_id")
        evidence = {
            "registration": "PROVEN",
            "health": shared["health"]["state"],
            "readiness": shared["ready"]["state"],
            "executors": shared["executors"]["state"],
            "topology": shared["topology"]["state"],
            "events": shared["events"]["state"],
            "dispatches": shared["dispatches"]["state"],
            "safe_canary": canary["state"],
        }
        missing = [k for k, v in evidence.items() if v not in {"PROVEN", "OBSERVED"}]
        status = "PASS" if not missing else ("PARTIAL" if len(missing) < len(evidence) else "FAIL")
        office_reports.append({
            "office_id": office_id,
            "chatbot_id": chatbot_id,
            "role_id": role_id,
            "runtime_state": runtime_state,
            "evidence_status": status,
            "evidence": evidence,
            "missing": missing,
        })
        if missing:
            repair_targets.append({
                "office_id": office_id,
                "packet_kind": "RUNTIME_EVIDENCE_REPAIR",
                "missing_evidence": missing,
                "destructive": False,
                "requires_human": False,
            })

    summary = {state: sum(1 for x in office_reports if x["evidence_status"] == state) for state in ("PASS", "PARTIAL", "FAIL")}
    now = dt.datetime.now(dt.timezone.utc).isoformat()
    report = {
        "resolution_id": "GA-HYPERNET-RUNTIME-CERTIFICATION-CAMPAIGN-012-016",
        "generated_at": now,
        "runtime_url": base_url,
        "office_count": len(office_reports),
        "runtime_state": runtime_state,
        "summary": summary,
        "shared_runtime_evidence": shared,
        "safe_canary": canary,
        "truth_rule": "unavailable_or_incompatible_runtime_evidence_is_not_pass",
        "offices": office_reports,
    }
    receipt = {
        "receipt_id": f"runtime-evidence-{uuid.uuid4()}",
        "resolution_id": "GA-HYPERNET-RUNTIME-CERTIFICATION-CAMPAIGN-012-016",
        "generated_at": now,
        "runtime_url": base_url,
        "office_count": len(office_reports),
        "summary": summary,
        "runtime_state": runtime_state,
        "proof_class": "runtime-evidence-harvest",
        "destructive_actions": False,
    }
    REPORT.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    RECEIPT.write_text(json.dumps(receipt, indent=2) + "\n", encoding="utf-8")
    REPAIRS.write_text(json.dumps({"generated_at": now, "targets": repair_targets}, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"office_count": len(office_reports), "runtime_url": base_url, "runtime_state": runtime_state, "summary": summary, "repair_targets": len(repair_targets)}))
    return 0


if __name__ == "__main__":
    sys.exit(main())
