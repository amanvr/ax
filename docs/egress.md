# Egress

A task runs as an Agent Substrate actor in a sandbox with **default-deny
egress**: it has no outbound network access until you grant it. Without a
policy the task cannot reach model APIs, Git hosts, or package registries, and
DNS for those hosts returns `NXDOMAIN`. AX does not create this policy for you —
it is a Substrate resource, attached per actor (the actor name equals the task
name).

This complements [Networking](networking.md), which covers *ingress* (reaching
a task through the `atenet-router`).

## Grant a task egress

Create an `EgressPolicy` for the task's actor with `kubectl ate` (from the
Substrate repo: `go install ./cmd/kubectl-ate`). Scope it to the hosts the task
needs:

```bash
kubectl ate create egress-policy <task-name> -a <atespace> -f - <<'EOF'
rules:
- https: {hostnames: ["generativelanguage.googleapis.com"]}
EOF
```

The policy is created once per actor and **persists across suspend/resume**. It
is removed when the task is deleted. The egress gateway caches a missing policy
as deny for ~10s, so allow a short delay between creating the policy and the
first outbound call.

## Local testing: allow all

For local development you can allow everything:

```bash
kubectl ate create egress-policy <task-name> -a <atespace> -f - <<'EOF'
rules:
- http:  {hostnames: ["*"], ports: {all: {}}}
- https: {hostnames: ["*"]}
EOF
```

This removes the containment Substrate provides, so use scoped hostnames
outside local testing.

### Let AX grant it automatically

Set `AX_ALLOW_ALL_EGRESS=true` on `ax-server` and the reconciler creates the
allow-all policy above for every task's actor at apply time — no per-task
`kubectl ate` step. Off by default; for local development only, as it disables
egress containment for all tasks.

## How it is enforced

All outbound traffic is mediated by the Substrate egress gateway
(`atenet-egress`), which checks each destination against the policy, gates DNS
the same way, and **terminates TLS (MITM)** on allowed HTTPS so policy can be
applied to encrypted traffic (and credentials injected out-of-band). A client
inside the sandbox that pins the public CA will see a certificate it does not
trust; use the gateway's trust bundle, or disable verification for a local
loopback that re-originates upstream.

See the Substrate docs for detail:
[egress-traffic](https://github.com/agent-substrate/substrate/blob/main/docs/egress-traffic.md),
[egress-credential-injection](https://github.com/agent-substrate/substrate/blob/main/docs/egress-credential-injection.md),
[egress-trust-bundle](https://github.com/agent-substrate/substrate/blob/main/docs/egress-trust-bundle.md).
