# Specification Overview

LAD-A2A defines how AI agents discover each other on local networks.

## Current Version

**v0.1.0-draft** (January 2025)

## Core Concepts

### Discovery Mechanisms

LAD-A2A supports multiple discovery paths with automatic fallback:

| Priority | Mechanism | Use Case |
|----------|-----------|----------|
| 1 | **mDNS/DNS-SD** | Zero-config LAN discovery via `_a2a._tcp` |
| 2 | **Well-Known Endpoint** | HTTP-based via `/.well-known/lad/agents` |
| 3 | **DHCP Option** | Enterprise networks |
| 4 | **QR/NFC** | Human-assisted fallback |

### Security Model

Local networks are **hostile by default**. LAD-A2A mandates:

| Requirement | Description |
|-------------|-------------|
| TLS Required | All endpoints must use HTTPS |
| Signed AgentCards | JWS or DID-based verification |
| User Consent | Explicit approval before connection |
| Capability Scopes | Least-privilege enforcement |

### Discovery Flow

```
1. Device joins network
2. Client queries mDNS (_a2a._tcp) or well-known endpoint
3. Discovery response includes AgentCard URL
4. Client fetches and verifies AgentCard
5. User approves connection
6. Standard A2A session begins
```

## Documents

- [Full Specification](spec.md) - Complete protocol details
- [JSON Schemas](schemas.md) - Response format definitions

## Related Protocols

| Protocol | Role | Link |
|----------|------|------|
| A2A | Agent-to-Agent Communication | [a2a-protocol.org](https://a2a-protocol.org) |
| MCP | Agent-to-Tools/Data | [modelcontextprotocol.io](https://modelcontextprotocol.io) |
