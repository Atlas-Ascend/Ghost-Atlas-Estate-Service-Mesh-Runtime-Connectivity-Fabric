# GA-HYPERNET-GLOBAL-RESOLUTION-006 // PLATFORM FEDERATION

Canonical cross-platform node federation for the Ghost Atlas estate.

## Verified inventory at seal

- GitHub: 81 explicit repository nodes + 1 platform anchor
- Vercel: 18 project nodes + 1 platform anchor
- Render: 24 visible service nodes + 1 platform anchor
- Neon: 5 project nodes + 1 platform anchor
- Durable federation rows: 132

## Identity grammar

- `ga://repo/<repo>`
- `ga://node/vercel/<project>`
- `ga://node/render/<service>`
- `ga://node/neon/<project>`
- `ga://platform/<provider>`

## Runtime binding state

Render services receive:

- `GA_HYPERNET_NODE_ID`
- `GA_HYPERNET_FEDERATION_ID=GA-HYPERNET-GLOBAL-RESOLUTION-006`
- `GA_HYPERNET_FEDERATION_REGISTRY`

The Render update operation triggers service redeployment where supported.

Neon project `ghost-atlas-estate-registry` persists the federation in `hypernet_platform_nodes`.

Vercel projects are registered as addressable nodes in the canonical federation registry and durable Neon lookup plane. The currently connected Vercel action surface exposes project/deployment inspection and deploy-current-project operations but not arbitrary project environment-variable mutation, so Vercel registration is canonical/durable rather than falsely reported as an injected runtime env binding.

GitHub repositories are explicitly represented in the durable registry and covered by `Atlas-Ascend/*` federation discovery. Repository identity is authoritative even when a repository does not contain a local node marker file.

## Invariant

Registration is not runtime proof. A node becomes runtime-verified only after its deployment/heartbeat/health contract is observed successfully.
