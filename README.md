<p align="center">
  <img src="assets/logo.png" alt="LAD-A2A Logo" width="120">
</p>

<h1 align="center">Local Agent Discovery for A2A (LAD-A2A)</h1>

<p align="center">
  <a href="LICENSE"><img src="https://img.shields.io/badge/License-Apache_2.0-blue.svg" alt="Apache License"></a>
  <a href="https://github.com/franzvill/lad/actions/workflows/tests.yml"><img src="https://github.com/franzvill/lad/actions/workflows/tests.yml/badge.svg" alt="Tests"></a>
  <a href="spec/spec.md"><img src="https://img.shields.io/badge/spec-draft-orange.svg" alt="Spec Version"></a>
  <a href="https://lad-a2a.org"><img src="https://img.shields.io/badge/docs-lad--a2a.org-blue.svg" alt="Documentation"></a>
</p>

<p align="center"><strong>An open protocol for discovering A2A-capable agents on local networks.</strong></p>

LAD-A2A addresses a critical gap in the AI agent ecosystem: when a device joins a network—hotel Wi-Fi, office LAN, cruise ship, hospital campus—how does the user's AI assistant discover and connect to local agents? While [A2A](https://a2a-protocol.org) defines agent-to-agent communication and [MCP](https://modelcontextprotocol.io) defines agent-to-tool integration, **LAD-A2A defines agent discovery**.

With LAD-A2A, agents can:

- **Automatically discover** local A2A agents when joining a network
- **Verify identity** through signed AgentCards and DIDs
- **Obtain user consent** before establishing connections
- **Negotiate capabilities** via standard A2A mechanisms

## See It In Action

<div align="center">

https://github.com/user-attachments/assets/a6a06e95-729b-465a-857c-6a87da52b302

<em>Real mDNS discovery → LAD-A2A protocol → A2A JSON-RPC communication</em>

</div>

## Why LAD-A2A?

AI agents are increasingly capable, but they remain isolated from their physical environment. A guest's AI assistant has no way to discover the hotel's concierge agent. An employee's assistant can't find the building's room booking agent. A patient's assistant doesn't know the hospital offers a wayfinding agent.

LAD-A2A solves this by providing:

- **Zero-Configuration Discovery:** Agents find each other automatically via mDNS/DNS-SD (`_lad-a2a._tcp`) and well-known endpoints.
- **An honest trust model:** Local networks are hostile by default. LAD-A2A carefully separates *channel authentication* (TLS proves you reached the host in the URL) from *identity verification* (domain/JWS/DID anchored to the org). TLS to an attacker-chosen host proves nothing about identity — see the **[Trust Model](https://lad-a2a.org/trust-model/)**.
- **Explicit user consent:** Human approval before first contact, keyed to a verified identity — never auto-approved.
- **Ecosystem Alignment:** LAD-A2A only handles discovery—once an agent is verified and approved, standard A2A communication takes over.

## How It Fits

<p align="center">
  <img src="assets/protocol-triangle.png" alt="Protocol Stack: LAD-A2A → A2A → MCP" width="350">
</p>

| Protocol | Role | Specification |
|----------|------|---------------|
| **LAD-A2A** | Discovery & Trust Bootstrap | [lad-a2a.org](https://lad-a2a.org) |
| **A2A** | Agent-to-Agent Communication | [a2a-protocol.org](https://a2a-protocol.org) |
| **MCP** | Agent-to-Tools/Data | [modelcontextprotocol.io](https://modelcontextprotocol.io) |

LAD-A2A is the **first handshake**. It answers "who's here?" so that A2A can answer "what can you do?" and MCP can answer "how do I do it?"

## Discovery Mechanisms

LAD-A2A supports multiple discovery paths with automatic fallback:

| Mechanism | Environment | Description |
|-----------|-------------|-------------|
| **mDNS/DNS-SD** | LAN, Consumer Wi-Fi | Zero-config discovery via the LAD-owned `_lad-a2a._tcp` service type |
| **Well-Known Endpoint** | Captive Portals, Web | `/.well-known/lad/agents` on the network domain |
| **DHCP Option** | Enterprise Networks | Custom option containing discovery URL |
| **QR/NFC** | Physical Fallback | Direct link to AgentCard for restricted networks |

## Getting Started

### Interactive Demo (Recommended)

Experience LAD-A2A with a fully working demo featuring two AI agents:

```bash
cd demo
cp .env.example .env
# Add your OpenAI API key to .env
./run_demo.sh
```

Open http://localhost:8000 to see:
- Real mDNS discovery (`_a2a._tcp.local`)
- LAD-A2A protocol in action
- A2A JSON-RPC 2.0 communication
- LLM-based query routing

See [demo/README.md](demo/README.md) for full documentation.

### Run Locally

```bash
cd reference
pip install -e .

# Start a discovery server (development only)
python -m server.lad_server --name "My Agent" --port 8080

# Discover agents (in another terminal). --no-verify-tls opts into plaintext for
# local dev; without it the client refuses non-https URLs as a discovery failure.
python -m client.lad_client --url http://localhost:8080 --no-verify-tls
```

> **Note:** The example above uses HTTP for local development. In production, **TLS is required** per the [security spec](spec/spec.md#4-security-requirements): all endpoints MUST use TLS 1.2+, and a non-https URL is a *discovery failure*, not merely an unverified agent.

## Example: Hotel Concierge

```
1. Guest device joins "ExampleHotel-Guest" Wi-Fi
2. Client queries mDNS for _lad-a2a._tcp.local AND the well-known endpoint,
   then aggregates + dedups by identity key
3. Discovery response includes an AgentCard URL (https) and a DID identity key
4. Client fetches the card over verified TLS and verifies IDENTITY
   (JWS/DID anchored to the org domain); a failed method is fatal
5. Client prompts the user, showing channel and identity separately:
   "Domain-authenticated: concierge.examplehotel.com — Connect?"
6. User approves → Standard A2A session begins (this is first contact)
7. User asks: "What time is breakfast?" → Agent responds via A2A
```

## Security Model

Local networks are **hostile by default** — a valid TLS certificate for an attacker-owned look-alike domain is part of the threat model, not a defense against it. LAD-A2A mandates:

| Requirement | Description |
|-------------|-------------|
| **Channel ≠ identity** | Verified TLS authenticates the *channel*; it never, on its own, marks an agent "verified" |
| **Anchored identity** | Domain / JWS / DID, each bound to the org domain; a failed stronger method is fatal (no weaker fallback) |
| **Fresh signed cards** | JWS AgentCards carry a short `exp`; expired/replayed cards are rejected |
| **Explicit consent** | Human approval before first contact, keyed to the verified identity — never auto-approved |
| **Limits & privacy** | Bounded discovery responses; no wildcard CORS; data minimization before consent |

See the **[Trust Model](https://lad-a2a.org/trust-model/)** for why the channel/identity split is the crux.

## Documentation

**📚 Full documentation at [lad-a2a.org](https://lad-a2a.org)**

| Resource | Description |
|----------|-------------|
| 📖 [Specification](https://lad-a2a.org/spec/spec/) | Full protocol specification with JSON schemas |
| 🔧 [Reference Implementation](https://lad-a2a.org/reference/) | Python server and client libraries |
| 🎮 [Interactive Demo](https://lad-a2a.org/demo/) | Full working demo with mDNS + A2A |
| 📚 [Examples](https://lad-a2a.org/examples/) | Integration scenarios and use cases |

## Use Cases

| Environment | Example Interaction |
|-------------|---------------------|
| **Hotels** | "What's the spa schedule?" / "Request late checkout" |
| **Cruise Ships** | "Where's tonight's show?" / "Book shore excursion" |
| **Offices** | "Book conference room 4B" / "Find available desks" |
| **Hospitals** | "Navigate to radiology" / "Check appointment status" |
| **Stadiums** | "Find my seat" / "Order food to section 112" |
| **Smart Cities** | "Next bus to downtown?" / "Find parking near me" |

## Contributing

We welcome contributions to enhance the LAD-A2A protocol.

- **Questions & Discussions:** [GitHub Discussions](https://github.com/franzvill/lad/discussions)
- **Issues & Feedback:** [GitHub Issues](https://github.com/franzvill/lad/issues)
- **Contribution Guide:** [CONTRIBUTING.md](CONTRIBUTING.md)

## License

This project is licensed under the [Apache License 2.0](LICENSE).
