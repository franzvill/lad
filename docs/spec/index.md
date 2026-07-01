# Specification Overview

LAD-A2A defines how AI agents discover each other on local networks.

## Current Version

**v0.2.0-draft** (July 2026) — a breaking security revision. See the [changelog](spec.md#appendix-b-changelog).

## Core Concepts

### Discovery Mechanisms

Clients query **every** available mechanism and aggregate + dedup the results (they do not stop at the first that answers — an unauthenticated mDNS record must never suppress the authenticated list):

| Mechanism | Use Case |
|-----------|----------|
| **mDNS/DNS-SD** | Zero-config LAN discovery via the LAD-owned `_lad-a2a._tcp` |
| **Well-Known Endpoint** | HTTPS via `/.well-known/lad/agents` |
| **Captive portal / DHCP** | *Non-normative* (future work); a network-supplied URL confers no trust |
| **QR/NFC** | Human-assisted; must carry a trust anchor, not just a URL |

### Security Model

Local networks are **hostile by default**, and the model rests on separating two axes — see the [Trust Model](../trust-model.md):

| Requirement | Description |
|-------------|-------------|
| Channel ≠ identity | Verified TLS authenticates the *channel*; it never, alone, makes an agent "verified" |
| Identity verification | Domain / JWS / DID, each **anchored to the org domain**; a failed stronger method is fatal |
| Fresh signed cards | Signed AgentCards carry a short `exp`; expired/replayed cards are rejected |
| Explicit consent | Human approval before first contact, keyed to the verified identity; never auto-approved |
| Resource & privacy limits | Bounded discovery responses; data minimization before consent |

### Discovery Flow

```
1. Device joins network
2. Client queries ALL mechanisms (mDNS _lad-a2a._tcp + well-known) and dedups
3. Client fetches each AgentCard over verified TLS (not "first contact")
4. Client verifies IDENTITY (domain/JWS/DID); a failed method is fatal
5. User gives explicit consent (channel and identity shown separately)
6. First contact: standard A2A session begins
```

## Documents

- [Full Specification](spec.md) - Complete protocol details
- [JSON Schemas](schemas.md) - Response format definitions

## Related Protocols

| Protocol | Role | Link |
|----------|------|------|
| A2A | Agent-to-Agent Communication | [a2a-protocol.org](https://a2a-protocol.org) |
| MCP | Agent-to-Tools/Data | [modelcontextprotocol.io](https://modelcontextprotocol.io) |
