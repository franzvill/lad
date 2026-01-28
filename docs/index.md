# Local Agent Discovery for A2A

**An open protocol for discovering A2A-capable agents on local networks.**

<p align="center">
  <img src="assets/discovery-flow.png" alt="LAD-A2A Discovery Flow" width="500">
</p>

---

## The Problem

When a device joins a network—hotel Wi-Fi, office LAN, cruise ship, hospital campus—how does the user's AI assistant discover and connect to local agents?

- [A2A](https://a2a-protocol.org) defines agent-to-agent communication
- [MCP](https://modelcontextprotocol.io) defines agent-to-tool integration
- **LAD-A2A defines agent discovery**

## The Solution

LAD-A2A provides:

- **Zero-Configuration Discovery** via mDNS/DNS-SD, well-known endpoints, or DHCP
- **Defense in Depth** with TLS, signed AgentCards, DIDs, and user consent
- **Graceful Degradation** from consumer Wi-Fi to enterprise networks
- **Ecosystem Alignment** that hands off to standard A2A once discovery completes

## How It Fits

<p align="center">
  <img src="assets/protocol-triangle.png" alt="Protocol Stack" width="350">
</p>

| Protocol | Role |
|----------|------|
| **LAD-A2A** | Discovery & Trust Bootstrap |
| **A2A** | Agent-to-Agent Communication |
| **MCP** | Agent-to-Tools/Data |

LAD-A2A is the **first handshake**. It answers "who's here?" so that A2A can answer "what can you do?"

## Quick Start

### Try the Network Simulation

```bash
cd reference/simulation
./run.sh
```

### Run Locally

```bash
cd reference
pip install -e .

# Start a discovery server
python -m server.lad_server --name "My Agent" --port 8080

# Discover agents
python -m client.lad_client --url http://localhost:8080
```

## Use Cases

| Environment | Example |
|-------------|---------|
| **Hotels** | "What's the spa schedule?" |
| **Cruise Ships** | "Where's tonight's show?" |
| **Offices** | "Book conference room 4B" |
| **Hospitals** | "Navigate to radiology" |
| **Stadiums** | "Find my seat" |
| **Smart Cities** | "Next bus to downtown?" |

## Next Steps

- [Read the Specification](spec/spec.md)
- [Try the Reference Implementation](reference/index.md)
- [See Examples](examples.md)
