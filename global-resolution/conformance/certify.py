from __future__ import annotations

import json
import pathlib
import sys
from dataclasses import dataclass
from typing import Any

import yaml

ROOT = pathlib.Path(__file__).resolve().parents[2]
OFFICE_MANIFEST = ROOT / "global-resolution/cognitive-office-mesh/bundles.yaml"
CONTROL_FILE = ROOT / "global-resolution/conformance/controls.yaml"
BASELINE_FILE = ROOT / "global-resolution/industry-standard/production-baseline.yaml"
OUTPUT = ROOT / "global-resolution/conformance/certification-report.json"


@dataclass
class Result:
    control_id: str
    status: str
    evidence: list[str]
    missing: list[str]


def load_yaml(path: pathlib.Path) -> Any:
    with path.open("r", encoding="utf-8") as fh:
        return yaml.safe_load(fh)


def flatten(obj: Any, prefix: str = "") -> set[str]:
    found: set[str] = set()
    if isinstance(obj, dict):
        for key, value in obj.items():
            name = f"{prefix}.{key}" if prefix else str(key)
            found.add(str(key))
            found.add(name)
            found |= flatten(value, name)
    elif isinstance(obj, list):
        for value in obj:
            if isinstance(value, str):
                found.add(value)
            found |= flatten(value, prefix)
    elif isinstance(obj, str):
        found.add(obj)
    return found


def evidence_status(required: list[str], corpus: set[str]) -> Result:
    present = [item for item in required if item in corpus or any(item in token for token in corpus)]
    missing = [item for item in required if item not in present]
    if not missing:
        status = "PASS"
    elif present:
        status = "PARTIAL"
    else:
        status = "FAIL"
    return Result("", status, present, missing)


def normalize_bundles(raw: Any) -> list[dict[str, Any]]:
    if isinstance(raw, dict):
        for key in ("bundles", "offices", "items"):
            if isinstance(raw.get(key), list):
                return raw[key]
    if isinstance(raw, list):
        return raw
    raise ValueError("office bundle manifest does not contain a list")


def main() -> int:
    controls = load_yaml(CONTROL_FILE)
    baseline = load_yaml(BASELINE_FILE)
    bundles = normalize_bundles(load_yaml(OFFICE_MANIFEST))
    if len(bundles) != 82:
        raise SystemExit(f"CERTIFICATION_INPUT_FAIL expected 82 offices, found {len(bundles)}")

    common = flatten(baseline) | flatten(controls)
    office_reports = []
    for office in bundles:
        office_id = office.get("office") or office.get("office_id")
        office_corpus = common | flatten(office)
        results = []
        counts = {"PASS": 0, "PARTIAL": 0, "FAIL": 0, "NOT_APPLICABLE": 0}
        critical_fail = 0
        high_fail = 0
        for control in controls["controls"]:
            result = evidence_status(control.get("evidence", []), office_corpus)
            result.control_id = control["id"]
            counts[result.status] += 1
            if result.status == "FAIL" and control.get("severity") == "critical":
                critical_fail += 1
            if result.status == "FAIL" and control.get("severity") == "high":
                high_fail += 1
            results.append({
                "control_id": result.control_id,
                "status": result.status,
                "present": result.evidence,
                "missing": result.missing,
            })
        total = len(controls["controls"])
        pass_pct = round((counts["PASS"] / total) * 100, 2)
        rules = controls["certification"]
        if critical_fail == 0 and high_fail == 0 and pass_pct >= rules["pass"]["minimum_pass_percent"]:
            certification = "PASS"
        elif pass_pct >= rules["partial"]["minimum_pass_percent"]:
            certification = "PARTIAL"
        else:
            certification = "FAIL"
        office_reports.append({
            "office_id": office_id,
            "chatbot_id": office.get("chatbot") or office.get("chatbot_id"),
            "role_id": office.get("role") or office.get("role_id"),
            "certification": certification,
            "pass_percent": pass_pct,
            "counts": counts,
            "controls": results,
        })

    summary = {state: sum(1 for r in office_reports if r["certification"] == state) for state in ("PASS", "PARTIAL", "FAIL")}
    report = {
        "resolution_id": "GA-HYPERNET-GLOBAL-RESOLUTION-010",
        "standard": "Ghost Atlas Industry Conformance Profile v1",
        "office_count": len(office_reports),
        "control_count": len(controls["controls"]),
        "summary": summary,
        "truth_rule": "declaration_is_not_runtime_proof",
        "offices": office_reports,
    }
    OUTPUT.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"office_count": len(office_reports), "control_count": len(controls["controls"]), "summary": summary}))
    return 1 if summary["FAIL"] else 0


if __name__ == "__main__":
    sys.exit(main())
