# LAD-A2A Specification

**Version:** 0.1.0-draft
**Status:** Draft
**Date:** 2025-01-28

## Abstract

LAD-A2A (Local Agent Discovery for A2A) defines mechanisms for discovering A2A-capable agents on local networks. It provides the discovery and trust bootstrap layer that enables A2A interactions when a client device joins a network.

## 1. Introduction

### 1.1 Purpose

When a client device joins a network (hotel Wi-Fi, office LAN, ship network), a "home" agent needs to:
1. Discover one or more A2A-capable agents on the network
2. Retrieve their A2A AgentCards
3. Establish trust before proceeding with A2A interactions

LAD-A2A standardizes this discovery process.

### 1.2 Scope

**In scope:**
- Discovery mechanisms for finding A2A agents on local networks
- Trust bootstrap and identity verification
- Well-known endpoints and response formats

**Out of scope:**
- A2A messaging protocol (defined by A2A)
- Tool/resource adapters (defined by MCP)
- Agent implementation details

### 1.3 Terminology

| Term | Definition |
|------|------------|
| **Client** | The discovering agent (e.g., user's home agent) |
| **Provider** | An A2A-capable agent advertising on the network |
| **AgentCard** | A2A's standard agent metadata document |
| **Discovery Endpoint** | A well-known URL returning available agents |

### 1.4 Threat Model

Local networks are hostile by default:
- Rogue access points
- mDNS spoofing
- Captive portal injection
- Man-in-the-middle attacks

All security requirements in this spec assume an adversarial network environment.

## 2. Discovery Mechanisms

Clients MUST attempt discovery in the following order, falling back to the next mechanism on failure:

### 2.1 mDNS/DNS-SD (Primary for LAN)

Providers SHOULD advertise using DNS-SD with service type `_a2a._tcp`.

**Service Advertisement:**
- Service type: `_a2a._tcp`
- Domain: `.local`

**Required TXT Records:**
| Key | Description | Example |
|-----|-------------|---------|
| `path` | Path to AgentCard | `/.well-known/agent.json` |
| `v` | LAD-A2A version | `1` |

> **Note:** The `path` value SHOULD use the A2A-standard AgentCard path (`/.well-known/agent.json` or `/.well-known/agent-card.json`).

**Optional TXT Records:**
| Key | Description | Example |
|-----|-------------|---------|
| `org` | Organization name | `ExampleHotel` |
| `id` | Agent DID | `did:web:example.com#agent` |

**Example:**
```
Service: Hotel Concierge._a2a._tcp.local
Target: concierge.local
Port: 443
TXT: path=/.well-known/agent.json v=1 org=ExampleHotel
```

> **Note:** The `_a2a._tcp` service type registration SHOULD be coordinated with the A2A project maintainers.

### 2.2 Well-Known HTTP Endpoint

Providers MUST expose a discovery endpoint at:
```
https://<host>/.well-known/lad/agents
```

This endpoint returns a list of available agents (see Section 3).

**Discovery via Captive Portal:**
When mDNS is unavailable, clients SHOULD attempt discovery on the network's captive portal domain.

### 2.3 DHCP Option (Enterprise)

For controlled networks, a DHCP option MAY provide the discovery URL:
```
a2a_discovery_url=https://net.example/.well-known/lad/agents
```

**Note:** DHCP option number pending IANA registration.

### 2.4 Human-Assisted Fallback

When automated discovery fails, providers MAY offer:
- QR codes linking directly to the AgentCard URL
- NFC tags with AgentCard URL

## 3. HTTP Resources

### 3.1 Discovery Endpoint

**Path:** `/.well-known/lad/agents`
**Method:** GET
**Content-Type:** `application/json`

**Required Headers:**
```
Access-Control-Allow-Origin: *
Access-Control-Allow-Methods: GET, OPTIONS
Access-Control-Allow-Headers: Content-Type
Cache-Control: max-age=300, must-revalidate
```

> **Note:** CORS headers are required to support browser-based agent clients.

**Response:**
```json
{
  "version": "1.0",
  "network": {
    "ssid": "ExampleHotel-Guest",
    "realm": "examplehotel.com"
  },
  "agents": [
    {
      "name": "Example Hotel Concierge",
      "description": "Hotel services and information",
      "role": "hotel",
      "agent_card_url": "https://concierge.examplehotel.com/.well-known/agent.json",
      "capabilities_preview": ["property-info", "amenities", "housekeeping", "reservations"]
    }
  ]
}
```

> **Note:** The `capabilities_preview` field is a lightweight summary for discovery UI. The full capability/skill definitions are in the A2A AgentCard itself.

See `schemas/discovery-response.json` for the full JSON Schema.

### 3.2 AgentCard Endpoint

LAD-A2A does NOT define an AgentCard endpoint. The `agent_card_url` in discovery responses MUST point to a valid A2A AgentCard endpoint, typically:
- `/.well-known/agent.json` (A2A v0.2.x)
- `/.well-known/agent-card.json` (A2A latest)

LAD-A2A does not extend the AgentCard format; it only standardizes how to discover it.

## 4. Security Requirements

### 4.1 Transport Security

- All HTTP endpoints MUST use TLS 1.2 or higher
- Clients MUST verify TLS certificates
- Self-signed certificates are NOT acceptable for production use

### 4.2 Identity Verification

AgentCards MUST be verifiable through one of:

1. **JWS Signature:** AgentCard wrapped in a signed JWS envelope
2. **DID Binding:** AgentCard references a DID that resolves to verification keys
3. **Domain Verification:** AgentCard served from a domain matching the claimed organization (similar to did:web)

### 4.3 User Consent

Clients MUST obtain explicit user consent before:
- Initiating first contact with a discovered agent
- Sharing any user data with the agent

**Consent UI Example:**
```
Found "Example Hotel Concierge"
Verified for: examplehotel.com
Capabilities: property-info, amenities, housekeeping, reservations

[Connect] [Ignore]
```

### 4.4 Capability Scoping

- Discovery responses SHOULD include `capabilities_preview` as a summary for UI display
- The authoritative capability/skill definitions are in the A2A AgentCard
- Clients SHOULD enforce least-privilege based on AgentCard-declared capabilities

### 4.5 Authentication

For actions beyond read-only public information:
- Providers SHOULD require OAuth 2.0 or OIDC authentication
- Auth requirements MUST be declared in the AgentCard

## 5. End-to-End Flow

```
┌────────┐         ┌─────────┐         ┌──────────┐
│ Client │         │ Network │         │ Provider │
└───┬────┘         └────┬────┘         └────┬─────┘
    │                   │                   │
    │  1. Join network  │                   │
    │ ─────────────────>│                   │
    │                   │                   │
    │  2. mDNS query    │                   │
    │   _a2a._tcp.local │                   │
    │ ──────────────────────────────────────>
    │                   │                   │
    │  3. mDNS response │                   │
    │   (or fallback to well-known)         │
    │ <──────────────────────────────────────
    │                   │                   │
    │  4. Fetch AgentCard                   │
    │ ──────────────────────────────────────>
    │                   │                   │
    │  5. Verify identity                   │
    │ <──────────────────────────────────────
    │                   │                   │
    │  6. User consent  │                   │
    │ ◄─────────────────┤                   │
    │                   │                   │
    │  7. A2A session   │                   │
    │ ══════════════════════════════════════>
    │                   │                   │
```

## 6. Conformance

### 6.1 Provider Conformance

A conformant LAD-A2A provider MUST:
- Expose `/.well-known/lad/agents` returning valid JSON per schema
- Include required CORS headers on discovery endpoints
- Serve A2A AgentCards at declared URLs (using A2A-standard paths)
- Use TLS for all endpoints
- Provide verifiable identity

A conformant provider SHOULD:
- Advertise via mDNS/DNS-SD
- Support DHCP option in enterprise deployments

### 6.2 Client Conformance

A conformant LAD-A2A client MUST:
- Attempt discovery mechanisms in specified order
- Verify provider identity before connection
- Obtain user consent before first contact
- Validate responses against JSON schemas

## 7. IANA Considerations

This specification requests:
- Registration of `_a2a._tcp` service type (to be coordinated with A2A project)
- Allocation of DHCP option for `lad_discovery_url`
- Registration of `/.well-known/lad/` URI prefix per RFC 8615

## 8. References

- [A2A Protocol Specification](https://a2a-protocol.org)
- [RFC 6762 - Multicast DNS](https://datatracker.ietf.org/doc/html/rfc6762)
- [RFC 6763 - DNS-SD](https://datatracker.ietf.org/doc/html/rfc6763)
- [RFC 8615 - Well-Known URIs](https://datatracker.ietf.org/doc/html/rfc8615)
- [DID Core Specification](https://www.w3.org/TR/did-core/)

## Appendix A: Example Implementations

### A.1 Hotel Network

```json
{
  "version": "1.0",
  "network": {
    "ssid": "GrandHotel-Guest",
    "realm": "grandhotel.com"
  },
  "agents": [
    {
      "name": "Grand Hotel Concierge",
      "description": "Your AI concierge for hotel services",
      "role": "hotel-concierge",
      "agent_card_url": "https://ai.grandhotel.com/.well-known/agent.json",
      "capabilities_preview": ["info", "dining", "spa", "housekeeping", "reservations"]
    }
  ]
}
```

### A.2 Enterprise Campus

```json
{
  "version": "1.0",
  "network": {
    "realm": "corp.example.com"
  },
  "agents": [
    {
      "name": "IT Helpdesk Agent",
      "description": "Technical support and IT services",
      "role": "it-support",
      "agent_card_url": "https://helpdesk.corp.example.com/.well-known/agent.json",
      "capabilities_preview": ["tickets", "knowledge-base", "asset-info"]
    },
    {
      "name": "Facilities Agent",
      "description": "Building and workspace services",
      "role": "facilities",
      "agent_card_url": "https://facilities.corp.example.com/.well-known/agent.json",
      "capabilities_preview": ["room-booking", "maintenance", "parking"]
    }
  ]
}
```

## Appendix B: Changelog

### v0.1.0-draft (2025-01-28)
- Initial draft specification
