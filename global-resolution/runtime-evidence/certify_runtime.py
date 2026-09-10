from __future__ import annotations

import json
import pathlib
import sys
from typing import Any

import yaml

ROOT = pathlib.Path(__file__).resolve().parents[2]
CONTROLS = ROOT / "global-resolution/conformance/controls.yaml"
RUNTIME = ROOT / "global-resolution/runtime-evidence/runtime-evidence-report.json"
OUTPUT = ROOT / "global-resolution/runtime-evidence/runtime-certification-report.json"

# Runtime probes that can materially prove each control. Controls absent from this
# map remain DECLARED_ONLY/PARTIAL until a dedicated runtime probe is implemented.
RUNTIME_REQUIREMENTS: dict[str, list[str]] = {
    "AI-01": ["topology", "safe_canary"],
    "OBS-01": ["events"],
    "OBS-02": ["events"],
    "OPS-01": ["health", "readiness"],
    "PRF-01": ["dispatches", "events"],
    "LOOP-01": ["topology", "dispatches"],
}


def load_yaml(path: pathlib.Path) -> Any:
    with path.open("r", encoding="utf-8") as fh:
        return yaml.safe_load(fh)


def main() -> int:
    controls = load_yaml(CONTROLS)["controls"]
    runtime = json.loads(RUNTIME.read_text(encoding="utf-8"))
    offices = runtime.get("offices", [])
    if len(offices) != 82:
        raise SystemExit(f"RUNTIME_CERTIFICATION_INPUT_FAIL expected 82 offices, found {len(offices)}")

    reports = []
    for office in offices:
        evidence = office.get("evidence", {})
        control_results = []
        counts = {"PASS": 0, "PARTIAL": 0, "FAIL": 0}
        blocking_failures = []
        for control in controls:
            cid = control["id"]
            required = RUNTIME_REQUIREMENTS.get(cid)
            if not required:
                status = "PARTIAL"
                reason = "declared_control_requires_dedicated_runtime_probe"
                missing = ["runtime_probe"]
            else:
                proven = [name for name in required if evidence.get(name) in {"PROVEN", "OBSERVED"}]
                missing = [name for name in required if name not in proven]
                if not missing:
                    status = "PASS"
                    reason = "runtime_evidence_present"
                elif proven:
                    status = "PARTIAL"
                    reason = "runtime_evidence_incomplete"
                else:
                    status = "FAIL"
                    reason = "runtime_evidence_missing"
            counts[status] += 1
            if status == "FAIL" and control.get("severity") in {"critical", "high"}:
                blocking_failures.append(cid)
            control_results.append({
                "control_id": cid,
                "domain": control["domain"],
                "severity": control["severity"],
                "status": status,
                "reason": reason,
                "required_runtime_evidence": required or [],
                "missing": missing,
            })
        pass_pct = round(counts["PASS"] / len(controls) * 100, 2)
        # Runtime certification is intentionally stricter than configuration certification.
        if not blocking_failures and pass_pct >= 95:
            certification = "PASS"
        elif pass_pct >= 30 and office.get("runtime_state") in {"LIVE", "DEGRADED"}:
            certification = "PARTIAL"
        else:
            certification = "FAIL"
        reports.append({
            "office_id": office.get("office_id"),
            "runtime_state": office.get("runtime_state"),
            "certification": certification,
            "pass_percent": pass_pct,
            "counts": counts,
            "blocking_failures": blocking_failures,
            "controls": control_results,
        })

    summary = {state: sum(1 for r in reports if r["certification"] == state) for state in ("PASS", "PARTIAL", "FAIL")}
    output = {
        "resolution_id": "GA-HYPERNET-GLOBAL-RESOLUTION-011",
        "mode": "runtime-evidence-aware",
        "office_count": 82,
        "control_count": len(controls),
        "summary": summary,
        "truth_rule": "declared_controls_remain_partial_until_runtime_proven",
        "offices": reports,
    }
    OUTPUT.write_text(json.dumps(output, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"office_count": 82, "control_count": len(controls), "summary": summary}))
    # Report truth without making absence of external secrets/connectivity fail code CI.
    return 0


if __name__ == "__main__":
    sys.exit(main())
