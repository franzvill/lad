# Security Policy

LAD-A2A is a discovery-and-trust bootstrap protocol whose threat model assumes
**local networks are hostile by default** (see [spec §1.4](spec/spec.md#14-threat-model)).
Security reports are therefore taken seriously and prioritized.

## Supported Versions

The protocol and reference implementation are pre-1.0 and evolving. Security
fixes are applied to the `main` branch and the latest tagged draft.

| Component | Version | Supported |
|-----------|---------|-----------|
| Specification | `0.1.0-draft` | ✅ |
| Reference implementation | `0.1.x` | ✅ |
| Older drafts / tags | < `0.1.0` | ❌ |

## Reporting a Vulnerability

**Please do not open a public GitHub issue for security vulnerabilities.**

Report privately through one of:

1. **GitHub Security Advisories** (preferred) — open a draft advisory at
   <https://github.com/franzvill/lad/security/advisories/new>.
2. **Email** — send details to the maintainer listed on the repository profile,
   with `LAD-A2A SECURITY` in the subject line.

Please include:

- A description of the issue and the component affected (spec, server, client,
  signing, demo).
- Steps to reproduce or a proof of concept.
- The impact you foresee (e.g. spoofed agent accepted, unverified card marked
  verified, MITM downgrade).

### What to expect

- **Acknowledgement** within 5 business days.
- An assessment and, where accepted, a remediation plan with a target timeline.
- Public disclosure coordinated with you once a fix is available, with credit if
  desired.

## Scope

In scope:

- Trust-model soundness in the reference client/server (verification,
  consent, signing) — e.g. an unverified agent being reported as `verified`.
- Discovery-path weaknesses (mDNS spoofing, well-known/captive-portal
  injection, TLS downgrade) that the spec claims to defend against.
- Signing/verification flaws in `common/signing.py`.

Out of scope:

- Vulnerabilities in upstream dependencies (report those upstream; we will bump
  the pin once a fix ships).
- The demo application's LLM backend or API keys — the demo is illustrative and
  not intended for production use.
- Denial of service from an on-path attacker who already controls the local
  network beyond what the threat model covers.

## Security Expectations for Deployers

The reference implementation ships with safe defaults (TLS verification on,
unverified agents denied by the default consent callback). Before deploying,
follow [PRODUCTION-CHECKLIST.md](PRODUCTION-CHECKLIST.md).
