# Client Reference

The LAD-A2A client discovers agents via mDNS and well-known endpoints.

## Installation

```bash
cd reference
pip install -e .
```

## CLI Usage

!!! warning "TLS Required in Production"
    Examples use HTTP for local development. In production, **all endpoints MUST use TLS 1.2+**.

### Discover via Well-Known

```bash
python -m client.lad_client --url http://localhost:8080
```

### Discover via mDNS

```bash
python -m client.lad_client
```

### Options

| Option | Description | Default |
|--------|-------------|---------|
| `--url` | Fallback URL for well-known | None |
| `--no-mdns` | Skip mDNS discovery | False |
| `--timeout` | mDNS timeout (seconds) | 3.0 |

## Programmatic Usage

### Basic Discovery

```python
import asyncio
from client.lad_client import LADClient

async def discover():
    client = LADClient()

    result = await client.discover(
        fallback_url="http://localhost:8080",
        try_mdns=True,
        fetch_cards=True
    )

    for agent in result.agents:
        print(f"Found: {agent.name}")
        print(f"  Role: {agent.role}")
        print(f"  Capabilities: {agent.capabilities_preview}")

        if agent.agent_card:
            print(f"  AgentCard verified: Yes")

asyncio.run(discover())
```

### Discovery Result

```python
@dataclass
class DiscoveryResult:
    agents: list[DiscoveredAgent]
    network_ssid: Optional[str]
    network_realm: Optional[str]
    discovery_method: str  # "mdns", "wellknown", or "none"
    errors: list[str]
```

### Discovered Agent

```python
@dataclass
class DiscoveredAgent:
    name: str
    description: str
    role: str
    agent_card_url: str
    capabilities_preview: list[str]
    source: str  # "mdns" or "wellknown"
    agent_card: Optional[dict]  # Populated after fetch
```

### Discovery Methods

#### mDNS Only

```python
agents = await client.discover_mdns()
```

#### Well-Known Only

```python
agents = await client.discover_wellknown("http://localhost:8080")
```

#### Fetch AgentCard

```python
agent_card = await client.fetch_agent_card(agent)
```

### With User Consent Flow

```python
async def discover_with_consent():
    client = LADClient()
    result = await client.discover(fallback_url="http://hotel.local:8080")

    for agent in result.agents:
        # Display consent UI
        print(f"\nFound: {agent.name}")
        print(f"Capabilities: {', '.join(agent.capabilities_preview)}")

        consent = input("Connect? [y/N]: ")
        if consent.lower() == 'y':
            # Proceed with A2A connection
            print(f"Connecting to {agent.name}...")
```

## Error Handling

```python
result = await client.discover(fallback_url="http://localhost:8080")

if result.errors:
    for error in result.errors:
        print(f"Warning: {error}")

if not result.agents:
    print("No agents discovered")
```
