# GA-HYPERNET-GLOBAL-RESOLUTION-011 // LIVE RUNTIME EVIDENCE HARVESTER

This wave turns industry-conformance declarations into runtime evidence.

## Invariants

- 82 office bundles are evaluated every harvest.
- Missing evidence is never interpreted as PASS.
- Registration is not liveness proof.
- Configuration certification and runtime certification remain distinct.
- Safe canaries are opt-in and dispatch-only; they do not perform destructive actions.
- Repair output is a bounded target list, not automatic production mutation.

## Evidence flow

`82 offices -> health/readiness -> executors -> topology -> events -> dispatch state -> optional safe canary -> runtime certification -> repair targets -> ProofGrid-compatible receipt`

## Runtime variables

- `GA_HYPERNET_URL`: base URL of the canonical service mesh runtime.
- `GA_HYPERNET_TOKEN`: optional bearer token.
- `GA_ENABLE_SAFE_CANARY`: defaults false. When true, creates a non-executing `model.infer` dispatch packet to verify the dispatch boundary without arbitrary shell or destructive behavior.

## Outputs

- `runtime-evidence-report.json`: raw/shared and per-office evidence status.
- `runtime-certification-report.json`: evidence-aware control results.
- `repair-targets.json`: bounded missing-evidence targets for later Packet OS repair planning.
- `runtime-evidence-receipt.json`: harvest receipt.

## Certification interpretation

`PASS` means the implemented runtime probes required by this profile are actually evidenced.

`PARTIAL` means some runtime evidence exists but controls remain unproven or require a dedicated probe.

`FAIL` means blocking runtime evidence is unavailable or the runtime is not demonstrably reachable.

Wave 011 does not claim all 20 industry controls are runtime-proven yet. It creates the evidence harvester and makes the gap measurable. Future probe packs can graduate each declared control into independently observed proof.
