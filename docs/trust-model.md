---
title: LAD-A2A Trust Model — channel vs. identity on a hostile network
description: How LAD-A2A separates channel authentication (TLS) from identity verification (domain/JWS/DID), why the distinction matters on hostile local networks, and what "verified" does and does not mean.
---

# Trust Model

LAD-A2A runs in the one place you should trust least: a network you just joined. A hotel Wi-Fi, an airport LAN, a conference floor. **Local networks are hostile by default** — rogue access points, mDNS spoofing, and captive-portal injection are the normal case, not the exception.

Everything in LAD-A2A's security rests on keeping **two questions apart**:

| | Question | Answered by | A trust signal? |
|---|---|---|---|
| **Channel authentication** | Did these bytes reach the host in the URL, untampered? | Verified TLS (WebPKI) | **No** |
| **Identity verification** | *Who* is this agent — is it bound to a real organization? | Domain / JWS / DID, anchored to the org | **Yes** |

## Why TLS is not identity here

TLS proves you reached *the host named in the URL*. On a hostile network, **the attacker chooses the URL.** A rogue captive portal can register `grandhotel-guest-portal.com`, obtain a perfectly valid Let's Encrypt certificate, and serve you an agent list. TLS "succeeds." The green padlock is real. And none of it proves this is the hotel you are standing in.

So LAD-A2A treats "arrived over HTTPS" as **channel authentication only**. It never, on its own, makes an agent *verified*.

!!! danger "The mistake that breaks everything"
    Conflating "the channel was encrypted" with "the agent's identity is verified," and then auto-approving the result. A valid certificate for an attacker-owned look-alike domain sails straight through. LAD-A2A's v0.2 revision exists to close exactly this gap.

## The root of trust: the domain

The actual root of trust is the **organization's domain, proven over WebPKI TLS** — the `did:web` idea, where the domain *is* the name. The three identity methods all ultimately anchor to it:

- **Domain authentication** — the card is served over verified TLS from a host that is (a subdomain of) the claimed organization domain. *Weakest:* it proves the host holds a cert for a domain matching the name it gave itself — not that the domain is the venue you're in. Shown as **"Domain-authenticated: `host`"**, never a bare "Verified."
- **JWS signature** — the card is signed, and the verifying key is anchored to the org domain (a `did:web`/`did:key` in the card, or a JWKS fetched over TLS from `https://<org>/.well-known/jwks.json`). Signed cards are short-lived (`exp` ≤ 24h) so a captured card can't be replayed forever. A signature that fails is **fatal** — the card is not trusted and is not "rescued" by falling back to domain matching.
- **DID binding** — the card references a DID (at minimum `did:web`) whose registrable domain must match the claimed organization.

A card that is merely "signed" with a key nobody can anchor to a domain is **not** trusted. Signed ≠ trusted.

## Consent: the human gate cryptography can't replace

Even a perfectly domain-authenticated agent might not be the one you want. Only a person can decide "yes, *this* is my hotel's concierge." So consent is required before **first contact** (any user data, any authenticated request, any A2A session):

- **Explicit and human** — no auto-approval of "verified" agents.
- **Two axes shown separately** — *Channel: Encrypted* and *Identity: Domain-authenticated / DID-verified / Not verified*. Never one green "Verified."
- **Capabilities from the verified card** — never from the network-supplied `capabilities_preview`, which an attacker controls.
- **Consent binds to identity** — a remembered decision is keyed to the verified identity (DID or domain), never to a name or URL an attacker can reuse, and is revoked when the key/cert changes.

```
Found "Grand Hotel Concierge"
  Channel:  Encrypted (TLS)
  Identity: Domain-authenticated — concierge.grandhotel.com
            (confirms the domain, NOT that this is your hotel)
  Capabilities (from verified card): info, dining, spa

            [ Connect ]   [ Ignore ]
```

## Protecting the client, too

The threat model runs both ways. Your assistant browsing for agents and eagerly fetching every card **broadcasts your presence and intent** to the whole segment and to every provider — before you've decided anything. LAD-A2A therefore asks clients to minimize data before consent, prefer unicast well-known over multicast mDNS on untrusted networks, and bound how much of an attacker-served discovery document they'll ingest.

## What "verified" does and does not mean

| Badge | Means | Does **not** mean |
|---|---|---|
| Encrypted | The transport is TLS to the URL's host | The agent is who it claims |
| Domain-authenticated | Valid cert for a host matching the claimed org domain | This is the venue you're physically in |
| DID-verified / JWS-verified | Identity cryptographically bound to the org domain | You should connect — that's the user's call |

See the [full specification, §4 Security Requirements](spec/spec.md#4-security-requirements) for the normative rules.
