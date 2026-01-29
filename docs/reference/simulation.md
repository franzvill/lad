# Network Simulation Guide

This guide explains how to simulate LAD-A2A discovery scenarios for testing and development.

## Overview

The LAD-A2A reference implementation includes tools for simulating various network discovery scenarios without requiring actual network infrastructure. This is useful for:

- Testing discovery fallback behavior
- Developing client applications
- Validating protocol compliance
- Demonstrating LAD-A2A capabilities

## Quick Start

### Single Agent Simulation

```bash
# Terminal 1: Start a simulated hotel agent
cd reference
python -m server.lad_server \
  --name "Grand Hotel Concierge" \
  --description "Your AI concierge for hotel services" \
  --role hotel-concierge \
  --capabilities info dining spa reservations \
  --port 8001 \
  --realm grandhotel.com \
  --ssid "GrandHotel-Guest"

# Terminal 2: Discover agents
python -m client.lad_client --url http://localhost:8001
```

### Multi-Agent Simulation

Simulate an enterprise network with multiple agents:

```bash
# Terminal 1: IT Helpdesk
python -m server.lad_server \
  --name "IT Helpdesk" \
  --role it-support \
  --capabilities tickets knowledge-base asset-info \
  --port 8001 \
  --realm corp.example.com

# Terminal 2: Facilities
python -m server.lad_server \
  --name "Facilities Agent" \
  --role facilities \
  --capabilities room-booking maintenance parking \
  --port 8002 \
  --realm corp.example.com

# Terminal 3: Discover all agents via mDNS
python -m client.lad_client --timeout 5
```

## Discovery Scenarios

### Scenario 1: mDNS Discovery (Primary)

mDNS is the primary discovery mechanism for local networks.

```python
import asyncio
from client.lad_client import LADClient

async def mdns_discovery():
    client = LADClient(mdns_timeout=5.0)

    # mDNS only - no fallback URL
    result = await client.discover(try_mdns=True, fetch_cards=True)

    print(f"Discovery method: {result.discovery_method}")
    for agent in result.agents:
        print(f"  {agent.name} ({agent.source})")

asyncio.run(mdns_discovery())
```

### Scenario 2: Well-Known Fallback

When mDNS is unavailable (e.g., captive portal networks), fall back to well-known endpoint.

```python
async def wellknown_fallback():
    client = LADClient()

    # Try mDNS first, fall back to well-known
    result = await client.discover(
        fallback_url="http://localhost:8001",
        try_mdns=True,
    )

    if result.discovery_method == "wellknown":
        print("mDNS unavailable, used well-known fallback")

asyncio.run(wellknown_fallback())
```

### Scenario 3: No mDNS (Direct Well-Known)

For networks where mDNS is blocked or unavailable.

```bash
# Skip mDNS entirely
python -m client.lad_client \
  --url http://localhost:8001 \
  --no-mdns
```

### Scenario 4: TLS Verification

Simulate production TLS requirements.

```bash
# Generate self-signed certificates for testing
openssl req -x509 -newkey rsa:4096 -keyout key.pem -out cert.pem -days 365 -nodes \
  -subj "/CN=localhost"

# Start server with TLS
python -m server.lad_server \
  --name "Secure Agent" \
  --ssl-certfile cert.pem \
  --ssl-keyfile key.pem \
  --port 8443

# Client with TLS verification disabled (for self-signed certs)
python -m client.lad_client \
  --url https://localhost:8443 \
  --no-verify-tls
```

### Scenario 5: Signed AgentCards

Simulate JWS signature verification.

```bash
# Generate signing keys
python -c "
from common.signing import generate_signing_keys
generate_signing_keys('keys/')
"

# Start server with signing enabled
python -m server.lad_server \
  --name "Signed Agent" \
  --signing-key keys/private.pem \
  --port 8001

# Client with signature verification
python -m client.lad_client \
  --url http://localhost:8001 \
  --signing-public-key keys/public.pem \
  --require-verified
```

## Programmatic Simulation

### Creating Test Fixtures

```python
from server.lad_server import LADServer, AgentConfig, create_app
from client.lad_client import LADClient

def create_test_server(name: str, port: int) -> LADServer:
    config = AgentConfig(
        name=name,
        description=f"Test agent: {name}",
        role="test",
        capabilities_preview=["test-cap"],
    )
    return LADServer(
        agent_config=config,
        port=port,
        enable_mdns=False,  # Disable for isolated testing
    )
```

### Integration Testing

```python
import pytest
from httpx import AsyncClient, ASGITransport

@pytest.mark.asyncio
async def test_discovery_simulation():
    # Create test server
    server = create_test_server("Test Agent", 8080)
    app = create_app(server)

    # Use ASGI transport for in-process testing
    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test"
    ) as client:
        response = await client.get("/.well-known/lad/agents")
        assert response.status_code == 200

        data = response.json()
        assert len(data["agents"]) == 1
        assert data["agents"][0]["name"] == "Test Agent"
```

## Network Simulation Tools

### Docker Compose Setup

For more realistic network simulation, use Docker:

```yaml
# docker-compose.yml
version: '3.8'

services:
  hotel-agent:
    build: ./reference
    command: >
      python -m server.lad_server
      --name "Hotel Concierge"
      --port 8080
    ports:
      - "8001:8080"
    networks:
      - hotel-network

  user-agent:
    build: ./reference
    command: >
      python -m client.lad_client
      --url http://hotel-agent:8080
      --no-mdns
    depends_on:
      - hotel-agent
    networks:
      - hotel-network

networks:
  hotel-network:
    driver: bridge
```

### Network Namespace Isolation (Linux)

For testing mDNS across isolated network namespaces:

```bash
# Create isolated network namespace
sudo ip netns add hotel-ns

# Create virtual ethernet pair
sudo ip link add veth-host type veth peer name veth-hotel
sudo ip link set veth-hotel netns hotel-ns

# Configure addresses
sudo ip addr add 10.0.0.1/24 dev veth-host
sudo ip netns exec hotel-ns ip addr add 10.0.0.2/24 dev veth-hotel

# Bring up interfaces
sudo ip link set veth-host up
sudo ip netns exec hotel-ns ip link set veth-hotel up

# Run server in namespace
sudo ip netns exec hotel-ns python -m server.lad_server --port 8080

# Discover from host
python -m client.lad_client --url http://10.0.0.2:8080
```

## Debugging

### Verbose Logging

```bash
# Server with debug logging
python -m server.lad_server --log-level DEBUG --name "Debug Agent"

# Client with debug logging
python -m client.lad_client --log-level DEBUG --url http://localhost:8080
```

### mDNS Debugging

```bash
# List all mDNS services (requires dns-sd or avahi-browse)
dns-sd -B _a2a._tcp local

# Or with avahi
avahi-browse -a
```

### HTTP Debugging

```bash
# Watch discovery requests
curl -v http://localhost:8080/.well-known/lad/agents

# Watch AgentCard requests
curl -v -H "Accept: application/jose" http://localhost:8080/.well-known/agent.json
```

## Common Simulation Patterns

### Hotel Check-in Flow

```python
async def hotel_checkin_simulation():
    """Simulate a user device joining a hotel network."""
    client = LADClient()

    # 1. Attempt mDNS discovery (as if joining hotel WiFi)
    result = await client.discover(
        fallback_url="http://portal.hotel.local:8080",
        try_mdns=True,
    )

    # 2. Display discovered agents for user consent
    for agent in result.agents:
        print(f"Found: {agent.name}")
        print(f"  Verified: {agent.verified}")
        print(f"  Capabilities: {agent.capabilities_preview}")

    # 3. User approves connection
    if result.agents:
        approved_agent = result.agents[0]
        print(f"Connecting to {approved_agent.name}...")
        # Continue with A2A protocol...
```

### Enterprise Network Discovery

```python
async def enterprise_discovery():
    """Simulate discovery on a corporate network."""
    client = LADClient(
        verify_tls=True,
        signing_public_key="corp-signing.pub",
    )

    result = await client.discover(
        fallback_url="https://discovery.corp.example.com",
        require_verified=True,  # Enterprise requires verification
    )

    # Filter by role
    it_agents = [a for a in result.agents if "it" in a.role]
    facilities_agents = [a for a in result.agents if "facilities" in a.role]
```

## Next Steps

- See [Server Reference](server.md) for server configuration
- See [Client Reference](client.md) for client options
- See [PRODUCTION-CHECKLIST.md](../../PRODUCTION-CHECKLIST.md) for production deployment
