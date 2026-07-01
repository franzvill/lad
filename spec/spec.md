# LAD-A2A Specification

**Version:** 0.2.0-draft
**Status:** Draft
**Date:** 2026-07-01

> **v0.2 is a breaking security revision of v0.1.** It separates *channel authentication*
> from *identity verification*, removes trust that v0.1 granted to plain TLS, moves primary
> mDNS discovery to a LAD-owned service type, and tightens discovery, consent, and resource
> limits. See [Appendix B: Changelog](#appendix-b-changelog) for the full list.

## Abstract

LAD-A2A (Local Agent Discovery for A2A) defines mechanisms for discovering A2A-capable agents on local networks. It provides the discovery and trust bootstrap layer that enables A2A interactions when a client device joins a network.

The key words MUST, MUST NOT, SHOULD, SHOULD NOT, and MAY in this document are to be interpreted as described in [RFC 2119](https://datatracker.ietf.org/doc/html/rfc2119) and [RFC 8174](https://datatracker.ietf.org/doc/html/rfc8174).

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
| **Channel authentication** | Assurance, from verified TLS, that bytes reached the host named in a URL untampered. A property of the *transport*. It says nothing about *who* the agent is. |
| **Identity verification** | Cryptographic binding of an agent to a claimed organization (domain or DID). The only trust signal in this spec. |
| **Identity key** | A stable identifier for an agent — a DID when present, otherwise its verified organization domain — used to dedup discoveries and to pin remembered consent. |
| **First contact** | The first transmission of user data to, first authenticated request to, or opening of an A2A session with a provider. Fetching the public discovery response or AgentCard over verified TLS *solely to verify identity and render a consent prompt* is **not** first contact. |

### 1.4 Threat Model

Local networks are hostile by default. Security requirements in this spec assume an adversarial network environment.

#### 1.4.1 Threats to the client from the network

- Rogue access points and mDNS/DNS-SD spoofing
- Captive-portal and DHCP injection of attacker-chosen agent lists
- Man-in-the-middle and downgrade attacks
- A **valid TLS certificate for an attacker-owned domain** (e.g. a look-alike captive-portal host). TLS proves you reached *that* host; it does not prove the host is the venue the user is standing in.

#### 1.4.2 Threats to the client's own privacy

The discovering client's presence and intent are a protected asset, not just the provider's identity:

- mDNS browsing and eager AgentCard fetches **broadcast the user's presence** to the whole L2 segment and to every provider before the user has decided anything.
- Discovery responses carrying `network.ssid`/`network.realm` are **location-revealing**.
- Repeated TLS handshakes expose a fingerprint (e.g. JA3) usable for cross-network de-anonymization.

## 2. Discovery Mechanisms

Clients MUST query **every** discovery mechanism available to them and aggregate the results; they MUST NOT stop at the first mechanism that returns agents. mDNS is unauthenticated multicast, so letting a single spoofed mDNS answer suppress the authenticated well-known list would be a denial-of-discovery.

**Aggregation and trust precedence:**

- Clients MUST merge results and dedup by [identity key](#13-terminology). Two records are the same agent iff their identity keys match.
- An unauthenticated mDNS record MUST NOT outrank or suppress an identity-verified well-known record for the same agent.
- Mechanism order is a **latency hint only**, never a trust ordering. A client MAY skip multicast mDNS on a network the user has flagged untrusted.

### 2.1 mDNS/DNS-SD (LAN)

Providers SHOULD advertise using DNS-SD with the **LAD-owned** service type `_lad-a2a._tcp`; clients browse `_lad-a2a._tcp.local.`. Using a LAD-owned type (rather than A2A's `_a2a._tcp`) avoids colliding with A2A's own future mDNS conventions and lets LAD define its own TXT semantics. (See [§7](#7-iana-considerations). A `_lad._sub._a2a._tcp` subtype MAY be used *in addition*, but only once the A2A project formally owns the base type.)

**Service Advertisement:**
- Service type: `_lad-a2a._tcp`
- Domain: `.local`

**TXT Records** — the key set is **closed**; clients MUST ignore unknown keys and MUST NOT infer trust from any TXT value (it is unauthenticated):

| Key | Req? | Description | Example |
|-----|------|-------------|---------|
| `path` | Required | Path to the A2A AgentCard | `/.well-known/agent.json` |
| `v` | Required | LAD-A2A major version (integer) | `0` |
| `id` | Required | Stable identity key (DID) | `did:web:example.com#agent` |
| `org` | Optional | Display-only organization label (NOT an identity claim) | `ExampleHotel` |

> **Scheme:** DNS-SD conveys only host + port. Because [§4.1](#41-transport-security) requires TLS, clients MUST construct `https://<target>:<port><path>` and MUST NOT construct `http://` from an mDNS result. A provider reachable only over plaintext is a discovery failure.

> **`role` is not a TXT key.** An agent's role/category is available only from the fetched, verified AgentCard — never from an unauthenticated TXT record.

**Example:**
```
Service: Hotel Concierge._lad-a2a._tcp.local
Target: concierge.local
Port: 443
TXT: path=/.well-known/agent.json v=0 id=did:web:grandhotel.com#concierge org=ExampleHotel
```

### 2.2 Well-Known HTTP Endpoint

Providers MUST expose a discovery endpoint at:
```
https://<host>/.well-known/lad/agents
```

This endpoint returns a list of available agents (see Section 3).

### 2.3 Untrusted discovery sources (captive portal, DHCP) — non-normative

A discovery URL learned from a network-controlled channel (a captive portal, a DHCP option) confers **no trust whatsoever**: it is exactly the injection vector named in [§1.4.1](#141-threats-to-the-client-from-the-network). Agents discovered this way are untrusted-until-independently-verified per [§4.2](#42-identity-verification); they MUST NOT be auto-approved and MUST NOT be shown as "verified for `<realm>`" without an independent realm→host identity binding.

These mechanisms are **not** part of the normative discovery set in this draft. They are deferred to future work pending:
- an assigned and cited DHCPv4/DHCPv6 option code with a defined wire encoding, and
- [RFC 8910](https://datatracker.ietf.org/doc/html/rfc8910) (Captive-Portal API) as the source of the captive-portal domain.

### 2.4 Human-Assisted Fallback

When automated discovery fails, providers MAY offer QR codes or NFC tags. Because a printed code is trivially substituted by an adversary, such a code MUST carry a trust anchor (a DID or an org-bound key fingerprint), not merely an AgentCard URL; a client MUST still run [§4.2](#42-identity-verification) identity verification before first contact.

## 3. HTTP Resources

### 3.1 Discovery Endpoint

**Path:** `/.well-known/lad/agents`
**Method:** GET
**Content-Type:** `application/json`

**Required Headers:**
```
Cache-Control: max-age=300, must-revalidate
```

> **CORS:** `Access-Control-Allow-Origin: *` MUST NOT be sent. The discovery body reveals the venue (`network.ssid`/`realm`) and the local agent inventory; a wildcard makes any web page the user visits a local-agent scanner and location oracle. Cross-origin access, if offered at all, MUST use an explicit trusted-origin allowlist (never wildcard, never wildcard + credentials). `network.ssid`/`network.realm` are location-revealing and MUST be omitted from any cross-origin-readable response.

**Response:**
```json
{
  "version": "0.2",
  "network": {
    "ssid": "ExampleHotel-Guest",
    "realm": "examplehotel.com"
  },
  "agents": [
    {
      "id": "did:web:examplehotel.com#concierge",
      "name": "Example Hotel Concierge",
      "description": "Hotel services and information",
      "role": "hotel",
      "agent_card_url": "https://concierge.examplehotel.com/.well-known/agent.json",
      "capabilities_preview": ["property-info", "amenities", "housekeeping", "reservations"]
    }
  ]
}
```

- **`id`** is the [identity key](#13-terminology) (a DID). It SHOULD be present in this draft and is REQUIRED as of v1.0; clients use it to dedup and to pin consent.
- **`agent_card_url`** MUST be `https://` (see [§4.1](#41-transport-security)).
- **`capabilities_preview`** is an untrusted UI hint only. The authoritative skills are in the verified A2A AgentCard, and the consent UI MUST render capabilities from that card, not from this preview (see [§4.3](#43-user-consent)).

**Status, empty set, and redirects:**
- Zero agents MUST return HTTP `200` with `"agents": []` (not `404`/`204`).
- On a `4xx`/`5xx` from one mechanism, a client MUST fail *that mechanism* and continue with the others; it MUST NOT abort discovery.
- Clients MUST NOT follow cross-host or cross-scheme `3xx` redirects; a same-origin redirect MAY be followed once. A redirect never confers verification.

**Resource limits** (see [§4.6](#46-resource-limits-and-client-privacy)): providers MUST NOT exceed the caps in §4.6 and clients MUST enforce them.

See `schemas/discovery-response.json` for the full JSON Schema.

### 3.2 AgentCard Endpoint

LAD-A2A does NOT define an AgentCard endpoint. The `agent_card_url` in discovery responses MUST point to a valid A2A AgentCard endpoint, typically:
- `/.well-known/agent.json` (A2A v0.2.x)
- `/.well-known/agent-card.json` (A2A latest)

The AgentCard MUST conform to the A2A AgentCard schema, including A2A's singular `protocolVersion` string. LAD-A2A does not extend the AgentCard format; it only standardizes how to discover it. `agent_card_url` is the authoritative pointer to the card — clients MUST use it and MUST NOT assume a fixed path.

### 3.3 Protocol Versioning

There are three **distinct** version axes; do not conflate them:

| Axis | Where | Meaning |
|------|-------|---------|
| **LAD-A2A version** | discovery `version`, mDNS TXT `v` | version of *this* protocol |
| **AgentCard version** | card `version` | the agent's own release version |
| **A2A protocolVersion** | card `protocolVersion` | the A2A wire protocol version |

For the LAD-A2A version:

- The wire form is `MAJOR.MINOR` (e.g. `0.2`); the mDNS `v` carries the integer `MAJOR` only and MUST equal the discovery `version`'s MAJOR.
- Same MAJOR ⇒ compatible; a greater MINOR is tolerated (changes are additive-only within a MAJOR). An unknown or greater MAJOR MUST be ignored — the client MUST NOT fetch the card or connect.
- Clients MUST read and enforce the version. During this draft, wire values are on the pre-release track (`v=0`, `version="0.2"`); this is the wire MAJOR.MINOR and is distinct from the document's `0.2.0-draft` semver.

## 4. Security Requirements

### 4.0 Trust Model (the two axes)

LAD-A2A's security rests on keeping two things separate. Conflating them is the single most dangerous mistake an implementer can make.

| Axis | What it proves | What establishes it | Is it a trust signal? |
|------|----------------|---------------------|-----------------------|
| **Channel authentication** | Bytes reached the host named in the URL, untampered | Verified TLS (WebPKI) | **No.** On a hostile network the URL itself is attacker-supplied. |
| **Identity verification** | The agent is bound to a claimed organization | Domain / JWS / DID, each anchored to the org (§4.2) | **Yes.** This, and only this, may be shown as "verified". |

**Root of trust.** The root of trust in LAD-A2A is **the organization's domain, proven over WebPKI-verified TLS** (the `did:web` model — the domain *is* the name). Every identity method in §4.2 ultimately derives its assurance from that binding.

Normative consequences:

- Verified TLS to a host MUST NOT, on its own, set an agent's status to *verified*. It establishes channel authentication only.
- A green "verified" indication MUST NOT be shown for an agent whose identity was not established per §4.2.
- The self-asserted `provider.organization` label and any network-supplied field (mDNS TXT, discovery preview, captive portal) are inputs to be checked, never trust on their own.

### 4.1 Transport Security

- All discovery and AgentCard endpoints MUST use TLS 1.2 or higher, and clients MUST verify certificates against the public WebPKI.
- A non-`https` discovery or AgentCard URL is a **discovery failure**, not merely an unverified agent: clients MUST NOT fetch it (outside an explicit local-development opt-out).
- Self-signed certificates are NOT acceptable for production.

### 4.2 Identity Verification

An agent is *verified* only when its identity is cryptographically bound to its claimed organization by one of the methods below. **Every method's key/DID → organization binding MUST be established over WebPKI-verified TLS or DID resolution; a self-asserted key or organization carries no trust.**

**Method precedence and failure are strict:**

- If a card presents itself under a stronger method (served as `application/jose`, or referencing a DID) and that method **fails**, the client MUST treat the agent as unverified, MUST NOT retain or display the card's payload as trusted, and MUST NOT fall back to a weaker method to elevate the *same* card. `verified = true` and a non-empty verification error are mutually exclusive.
- An endpoint whose host is a bare IP literal MUST NOT be verified via TLS/domain alone; the client MUST first resolve a DID identity (§4.2.2).

#### 4.2.1 JWS Signature

The AgentCard is wrapped in a signed JWS envelope. To be treated as verified:

- The verifying key MUST be anchored to `provider.organization`, via **either** (a) a `did:web`/`did:key` referenced in the card and resolved per §4.2.2, **or** (b) a JWKS fetched over WebPKI-verified TLS from `https://<organization>/.well-known/jwks.json`, matched by registrable-suffix.
- A `kid` header is REQUIRED. A key supplied by the discovery response, mDNS TXT, or captive portal MUST NOT be used to verify.
- The payload MUST include `iat` and `exp`; `exp` MUST be short-lived (≤ 24h) to bound replay. Verifiers MUST reject expired cards and cards missing `exp`.
- The signed payload SHOULD bind to its serving origin (host + path, or a certificate hash); a verifier SHOULD reject a signed card served from a different URL than it names.
- Revocation/rotation is handled by short `exp` plus a key list resolvable from the org domain/DID.

> A pre-shared public key (out-of-band, e.g. a managed enterprise fleet) is a valid anchor **only** for that managed deployment and MUST NOT be presented as open-network verification.

#### 4.2.2 DID Binding

The AgentCard references a DID that resolves to its verification keys.

- Clients MUST accept at minimum `did:web`; DID methods not on the client's accepted list MUST NOT be treated as verified.
- `did:web` resolution MUST occur over the §4.1 WebPKI-verified TLS.
- The DID's registrable domain MUST equal or be a subdomain of the claimed `provider.organization` (registrable-suffix match). A card declaring org `grandhotel.com` but a DID of `did:web:attacker.com` MUST NOT be verified.

#### 4.2.3 Domain Authentication

The AgentCard is served over WebPKI-verified TLS from a host that matches the claimed organization domain (the `did:web` idea without an explicit DID document).

- The host MUST equal the organization domain or be a subdomain of it (e.g. `ai.grandhotel.com` for `grandhotel.com`). Substring matches (e.g. `nothotel.evil.com` for `hotel`) MUST NOT be accepted, and a free-text org label ("Grand Hotel") that is not a domain MUST NOT match.
- Because the binding is provided entirely by TLS, a match over a non-TLS or unverified connection carries **no** trust and MUST NOT mark an agent verified.

> **Why domain authentication is the weakest method.** It proves only "this host holds a valid cert for a domain matching the name it gave itself." It does **not** prove the domain is the venue the user is standing in. A look-alike domain with a valid certificate passes. Present it to the user as *"Domain-authenticated: `<host>`"*, never as an unqualified "Verified", and require [consent](#43-user-consent).

### 4.3 User Consent

Consent is the human gate on trust that cryptography cannot supply — that *this* agent is the one the user actually wants. It is REQUIRED before [first contact](#13-terminology).

1. **Explicit and human.** Clients MUST obtain explicit user consent before first contact. Automated approval (e.g. "auto-approve anything verified") does NOT satisfy this MUST. A client MAY pre-fetch and verify a card over TLS solely to render the prompt; it MUST NOT send user data, authenticate, or open an A2A session before consent.
2. **Two axes shown separately.** The prompt MUST distinguish channel ("Encrypted") from identity ("Domain-authenticated: `<host>`" / "DID-verified: `<did>`" / "Not verified"). It MUST NOT collapse them into a single green "Verified".
3. **Capabilities from the verified card.** The capabilities shown MUST come from the fetched, verified AgentCard — never from the network-supplied `capabilities_preview`. A preview shown before the card is fetched MUST be marked unverified, and a preview/card divergence MUST be surfaced as a warning.
4. **Consent binds to identity.** A remembered ("don't ask again") decision MUST be keyed to the agent's verified [identity key](#13-terminology) (DID or verified domain), never to its name, preview, or URL host — all of which an attacker can reuse. An unverified agent MUST receive session-scoped consent only.
5. **Revocation.** Persisted grants MUST be invalidated when the underlying key/certificate changes (a re-advertised service that does not re-prove identity MUST re-prompt), and the user MUST be able to revoke a grant, which ceases data sharing and tears down active sessions.
6. **"User data".** For the purpose of this section, *user data* includes PII, precise geolocation, credentials/tokens, and message content. Clients MUST practice data minimization: none of it is sent before consent, and only what the task needs afterward.

**Consent UI Example:**
```
Found "Example Hotel Concierge"
  Channel:  Encrypted (TLS)
  Identity: Domain-authenticated — concierge.examplehotel.com
            (this confirms the domain, NOT that this is your hotel)
  Capabilities (from verified card): property-info, amenities, housekeeping

[Connect] [Ignore]
```

### 4.4 Capability Scoping

- `capabilities_preview` in the discovery document is an **untrusted UI hint** served by the network side. It is not a security control and MUST NOT be used for authorization or shown to the user as authoritative.
- The authoritative capability/skill definitions are in the verified A2A AgentCard.
- Clients SHOULD enforce least privilege against the **verified** card's declared capabilities. Note that capabilities are still self-declared by the provider; scoping limits what the client *offers*, not what a malicious provider *claims*.

### 4.5 Authentication

For actions beyond read-only public information:
- Providers SHOULD require OAuth 2.0 or OIDC authentication.
- Auth requirements MUST be declared in the AgentCard.

### 4.6 Resource Limits and Client Privacy

**Resource limits** (the discovery document may be served by an adversary — bound it):

- Clients MUST enforce, and abort past: a max decoded body (RECOMMENDED 256 KiB), a max agent count (RECOMMENDED 100), a max number of outbound AgentCard fetches per discovery run (RECOMMENDED 8), and an overall discovery deadline (RECOMMENDED 30 s).
- Providers MUST NOT return more than 100 agents or exceed 256 KiB.

**Client privacy / data minimization** (see [§1.4.2](#142-threats-to-the-clients-own-privacy)):

- Clients MUST NOT disclose user identity, credentials, or precise location before consent.
- On an untrusted network, clients SHOULD prefer unicast well-known discovery over multicast mDNS, SHOULD NOT eagerly fetch every advertised card, and SHOULD minimize their fetch fingerprint (generic User-Agent, no cookies).

## 5. End-to-End Flow

```
┌────────┐         ┌─────────┐         ┌──────────┐
│ Client │         │ Network │         │ Provider │
└───┬────┘         └────┬────┘         └────┬─────┘
    │                   │                   │
    │  1. Join network  │                   │
    │ ─────────────────>│                   │
    │                   │                   │
    │  2. Query ALL mechanisms (mDNS _lad-a2a._tcp + well-known)
    │ ──────────────────────────────────────>
    │                   │                   │
    │  3. Aggregate + dedup by identity key │
    │ <──────────────────────────────────────
    │                   │                   │
    │  4. Fetch AgentCard over verified TLS │   ── not "first contact":
    │ ──────────────────────────────────────>     verification + prompt only
    │                   │                   │
    │  5. Verify identity (§4.2); reject on failure
    │ <──────────────────────────────────────
    │                   │                   │
    │  6. Explicit user consent  ◄──────────┤   ── GATE: nothing below happens
    │ ◄─────────────────┤                   │      without human approval
    │                   │                   │
    │  7. First contact: A2A session / user data
    │ ══════════════════════════════════════>
    │                   │                   │
```

> Steps 4–5 (fetching and verifying the public card over TLS) are explicitly **not** [first contact](#13-terminology): they carry no user data. Step 6 is the gate; **all** data-bearing contact happens at step 7 and only after approval.

## 6. Conformance

### 6.1 Provider Conformance

A conformant LAD-A2A provider MUST:
- Expose `/.well-known/lad/agents` over TLS returning valid JSON per schema (200 + `agents: []` when empty), within the §4.6 resource limits.
- NOT send `Access-Control-Allow-Origin: *` on the discovery endpoint (§3.1).
- Serve A2A-conformant AgentCards over TLS at the declared `agent_card_url`.
- Provide a verifiable identity anchored to its organization domain (§4.2), and NOT advertise a non-domain hostname as `provider.organization`.

A conformant provider SHOULD:
- Advertise via mDNS/DNS-SD on `_lad-a2a._tcp` with a `id` (DID) TXT record.
- Sign AgentCards (JWS) with a short `exp`.

### 6.2 Client Conformance

A conformant LAD-A2A client MUST:
- Query all available discovery mechanisms and aggregate + dedup by identity key; never let an unauthenticated mDNS record suppress a verified one (§2).
- Treat non-`https` discovery/card URLs as discovery failures (§4.1).
- Establish identity per §4.2 before marking an agent verified; keep channel authentication and identity strictly separate (§4.0); treat a failed stronger method as fatal.
- Obtain explicit user consent before first contact, key remembered consent to the verified identity, and never auto-approve (§4.3).
- Enforce the §4.6 resource limits and validate responses against the JSON schemas.

## 7. IANA Considerations

This specification requests:
- Registration of the DNS-SD service type **`_lad-a2a._tcp`** (LAD-owned; see [RFC 6763](https://datatracker.ietf.org/doc/html/rfc6763)). LAD-A2A does not squat A2A's `_a2a._tcp`; an optional `_lad._sub._a2a._tcp` subtype may be pursued only if the A2A project formally defines and owns the base type.
- Registration of the well-known URI **name `lad`** in the IANA Well-Known URIs registry ([RFC 8615](https://datatracker.ietf.org/doc/html/rfc8615) §3.1). LAD-A2A defines `/.well-known/lad/agents` beneath it, following the `/.well-known/est/` subtree precedent of [RFC 7030](https://datatracker.ietf.org/doc/html/rfc7030). (The registry registers the single-segment name `lad`, not the slash-bearing path `lad/agents`.)
- *(Deferred, non-normative)* a DHCPv4/DHCPv6 option code for a discovery URL — pending a defined wire encoding (§2.3).

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
  "version": "0.2",
  "network": {
    "ssid": "GrandHotel-Guest",
    "realm": "grandhotel.com"
  },
  "agents": [
    {
      "id": "did:web:grandhotel.com#concierge",
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
  "version": "0.2",
  "network": {
    "realm": "corp.example.com"
  },
  "agents": [
    {
      "id": "did:web:corp.example.com#helpdesk",
      "name": "IT Helpdesk Agent",
      "description": "Technical support and IT services",
      "role": "it-support",
      "agent_card_url": "https://helpdesk.corp.example.com/.well-known/agent.json",
      "capabilities_preview": ["tickets", "knowledge-base", "asset-info"]
    },
    {
      "id": "did:web:corp.example.com#facilities",
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

### v0.2.0-draft (2026-07-01)

Breaking security revision following a hostile-network audit. Trust-model changes:

- **Channel vs identity split (§4.0).** Verified TLS is now *channel authentication* only and MUST NOT set an agent to "verified". Identity is a separate axis established solely via §4.2.
- **Identity methods anchored (§4.2).** JWS keys and DIDs MUST be bound to the organization domain (JWKS-over-TLS or `did:web`); `did:web` domain must match the claimed org; a failed stronger method is fatal and MUST NOT fall back to domain matching. Signed cards MUST carry a short `exp`. Domain authentication is reframed as the weakest, non-endorsing method.
- **Consent rebuilt (§4.3).** Explicit human consent, no auto-approve; consent keyed to the verified identity; capabilities shown from the verified card; revocation and a "user data" definition added. "First contact" defined (§1.3).
- **Discovery integrity (§2).** Clients query *all* mechanisms and aggregate/dedup by identity key; mDNS can no longer suppress the authenticated list. Primary mDNS moved to the LAD-owned **`_lad-a2a._tcp`** type; mDNS URLs are `https`-only; `id` (DID) added. Captive-portal/DHCP demoted to non-normative (§2.3).
- **Privacy & DoS (§1.4.2, §4.6).** Client-side threat model added; wildcard CORS removed (§3.1); response resource limits and data-minimization requirements added.
- **Interop (§3.2, §3.3).** AgentCard must use A2A's singular `protocolVersion`; three version axes disambiguated; wire version on the `0.x` pre-release track. IANA framing corrected (§7).

### v0.1.0-draft (2026-01-28)
- Initial draft specification
