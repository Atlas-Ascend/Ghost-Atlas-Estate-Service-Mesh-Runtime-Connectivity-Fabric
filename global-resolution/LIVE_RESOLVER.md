# GA-HYPERNET-GLOBAL-RESOLUTION-002 // LIVE RESOLVER

This wave turns the GA-HYPERNET-GLOBAL-RESOLUTION-001 registry map into a runtime resolver.

## Runtime invariant

`authority -> security -> capability -> runtime -> resource -> transport -> execution -> observation -> verification -> proof -> memory -> reconciliation`

## API

- `GET /v1/global/validate` — validate all six canonical registries and cross-references.
- `POST /v1/global/reload` — reload registry state from disk.
- `POST /v1/global/advertise` — register a live node heartbeat plus capabilities/resources.
- `POST /v1/global/heartbeat` — refresh liveness and resource telemetry.
- `POST /v1/global/resolve` — resolve a capability to route + ranked runtime candidates.
- `GET /v1/global/topology` — return declared nodes, live state, and recent resolver events.
- `GET /v1/global/nodes/{node}` — inspect one node.
- `GET /v1/global/events` — inspect resolver-generated estate events.

## Capability resolution

A request such as:

```json
{
  "capability": "model.infer",
  "source": "ga://organ/atlas-mind",
  "io_class": "QUERY",
  "prefer_local": true
}
```

resolves against:

1. capability ownership
2. matching canonical route
3. declared node capability
4. live node advertisement/heartbeat state
5. security-class compatibility
6. runtime preference
7. resource `capacity_score`
8. transport metadata
9. ProofGrid terminal requirement

## Node advertisement

Nodes publish live state without mutating the canonical registry:

```json
{
  "canonical_id": "ga://node/eden",
  "capabilities": ["model.infer", "compute.execute"],
  "resources": {
    "capacity_score": 82,
    "cpu_free_pct": 71,
    "ram_free_mb": 24000,
    "gpu_free_mb": 6400
  },
  "health": "online"
}
```

Heartbeat state expires to `offline` when its TTL is exceeded. Canonical registry state remains preserved.

## Adapter boundary

The live resolver is the CrownGrid/Hypernet resolution primitive. Downstream adapters should consume the returned canonical IDs rather than hard-code node addresses:

- Packet OS adapter: packet capability -> `/v1/global/resolve`
- Workforce Spine adapter: selected execution target -> dispatch
- Estate Event Gateway adapter: resolver events -> estate event stream
- Thoth sink: resolution/dispatch/proof provenance
- ProofGrid sink: terminal receipt binding
- Runtime Observatory: `/v1/global/topology`

No action is considered canonical solely because it resolved. Execution still terminates through SECA -> DevOS -> ProofGrid -> Thoth.
