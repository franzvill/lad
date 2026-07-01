# Production Deployment Checklist

The LAD-A2A reference implementation ships with development-friendly defaults
(plain HTTP is allowed, mDNS is on). Local networks are **hostile by default**
([spec §1.4](spec/spec.md#14-threat-model)), so a production deployment MUST
harden the items below before advertising an agent.

## Transport (spec §4.1)

- [ ] **TLS 1.2+ on every endpoint.** Start the server with `--ssl-certfile` and
      `--ssl-keyfile`. Discovery and AgentCard URLs are then emitted as `https://`.
- [ ] **Use a certificate from a trusted CA.** Self-signed certificates are not
      acceptable for production (spec §4.1); clients that verify TLS will reject them.
- [ ] **Clients keep TLS verification on.** Never ship a client with
      `--no-verify-tls` / `verify_tls=False`. Use `--ca-bundle` only for a private
      CA you control.
- [ ] Terminate TLS as close to the agent as possible; if a reverse proxy
      terminates TLS, ensure the proxy→agent hop is also trusted.

## Identity & Verification (spec §4.2)

- [ ] **Sign AgentCards (JWS).** Start the server with `--signing-key` (and a
      stable `--signing-key-id` for rotation). Distribute the public key to clients
      (`--signing-public-key`) out of band.
- [ ] **Rotate signing keys** on a schedule and on suspected compromise; the
      `kid` header supports overlapping keys during rotation.
- [ ] **Understand domain verification.** A domain match is only trustworthy over
      verified TLS — the reference client will *not* mark an agent `verified` from a
      domain match on a plain-HTTP or unverified connection. Do not rely on domain
      verification without TLS.
- [ ] **Set a real organization domain.** Configure `--realm` to the registrable
      domain that serves the card (e.g. `grandhotel.com`) so `provider.organization`
      is a verifiable domain, not a machine hostname or free-text label.
- [ ] Prefer verified clients: run discovery with `--require-verified` so
      unverified agents are dropped rather than surfaced.

## User Consent (spec §4.3)

- [ ] **Require explicit consent before first contact.** Use `--with-consent` or
      implement a `ConsentCallback`. Do not auto-approve in a real UI.
- [ ] Do not rely on `default_consent_callback` in production — it auto-approves
      verified agents and is intended for demos/tests only.
- [ ] Present the verification status and capabilities to the user honestly;
      surface "not verified" prominently.

## Authorization (spec §4.5)

- [ ] **Declare auth requirements in the AgentCard** for anything beyond
      read-only public info (`--auth-method oauth2|oidc|api_key|bearer` plus the
      relevant `--auth-*` flags).
- [ ] Enforce least privilege based on AgentCard-declared capabilities/scopes.

## Network & Operations

- [ ] Decide on mDNS exposure. The LAD-owned `_lad-a2a._tcp` advertisement is
      convenient on trusted LANs; disable it with `--no-mdns` where multicast is
      untrusted or unwanted, and rely on the well-known endpoint instead.
- [ ] **Do not send `Access-Control-Allow-Origin: *`** on the discovery endpoint
      (spec §3.1): the discovery body reveals the venue and local agent inventory,
      so a wildcard turns any visited web page into a local-agent scanner. Offer
      cross-origin access, if at all, via an explicit trusted-origin allowlist, and
      omit location-revealing `network.ssid`/`network.realm` from cross-origin
      responses.
- [ ] Run behind a process manager with health checks against `/health`.
- [ ] Set an appropriate log level (`--log-level`) and ship logs; avoid `DEBUG`
      in production.
- [ ] Pin and monitor dependencies (`reference/pyproject.toml`) and apply
      security updates promptly.

## Pre-flight verification

- [ ] `pytest tests/` passes in the deployment environment.
- [ ] `curl https://<host>/.well-known/lad/agents` returns valid JSON over TLS.
- [ ] A client with `--require-verified --signing-public-key <key>` discovers and
      verifies the agent end to end.
- [ ] An intentionally wrong public key or a plain-HTTP endpoint results in the
      agent being reported **unverified** (fail-closed).
