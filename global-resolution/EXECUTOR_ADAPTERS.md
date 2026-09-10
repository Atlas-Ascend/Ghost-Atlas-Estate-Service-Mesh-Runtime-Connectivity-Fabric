# GA-HYPERNET-GLOBAL-RESOLUTION-004 // Executor Adapter Fabric

This wave binds selected Hypernet nodes to bounded execution mechanisms without introducing arbitrary-shell fallback.

## Bindings

- `ga://node/eden` -> local argv adapter via `GA_EDEN_EXECUTOR_ARGV`
- `ga://node/t5810-01` -> HTTP worker via `GA_T5810_01_EXECUTOR_URL`
- `ga://node/t5810-02` -> HTTP worker via `GA_T5810_02_EXECUTOR_URL`
- `ga://node/odin` -> HTTP/Termux bridge via `GA_ODIN_EXECUTOR_URL`
- `ga://node/janus` -> operator bridge via `GA_JANUS_EXECUTOR_URL`
- `ga://node/render` -> remote worker via `GA_RENDER_EXECUTOR_URL`
- `ga://node/vercel` -> deployment bridge via `GA_VERCEL_EXECUTOR_URL`
- `ga://node/neon` -> persistence bridge via `GA_NEON_EXECUTOR_URL`

## Invariants

1. Missing endpoint/command configuration leaves a node explicitly unbound.
2. Local execution is argv-only with `shell=False`; packet payload arrives through JSON stdin.
3. Remote execution is explicit HTTP POST to `/v1/execute` and may require bearer credentials from environment variables.
4. Executor selection never bypasses Global Resolver routing.
5. Executor success is not packet completion; the SECA -> DevOS -> ProofGrid -> Thoth -> JANUS PRIME chain remains mandatory.

## Runtime inspection

`GET /v1/executors` returns bound and unbound nodes. `/health`, `/ready`, and `/v1/dispatch` include executor binding state.
