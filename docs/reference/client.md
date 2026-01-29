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
| `--no-verify-tls` | Disable TLS verification (development only) | False |
| `--ca-bundle` | Custom CA bundle for TLS verification | None |
| `--signing-public-key` | Public key for AgentCard signature verification | None |
| `--require-verified` | Only return verified agents | False |
| `--with-consent` | Enable interactive consent flow | False |
| `--config` | Path to YAML configuration file | None |
| `--log-level` | Logging level (DEBUG, INFO, WARNING, ERROR) | INFO |

## Configuration Files

Use YAML configuration files for complex setups:

```bash
# Start with config file
python -m client.lad_client --config lad-config.yaml
```

### Example Configuration

```yaml
client:
  # Discovery settings
  mdns_timeout: 3.0
  http_timeout: 10.0
  fallback_url: "https://agent.example.com"
  try_mdns: true

  # TLS verification (required for production)
  verify_tls: true
  ca_bundle: null  # Use system CA bundle

  # Signature verification
  signing_public_key: "/path/to/public.pem"

  # Behavior
  require_verified: false
  fetch_cards: true

  # Logging
  log_level: "INFO"
```

### Environment Variable Overrides

Config file values can be overridden via environment variables with `LAD_` prefix:

```bash
# Override timeout from config file
LAD_MDNS_TIMEOUT=5.0 python -m client.lad_client --config lad-config.yaml

# Disable TLS verification (development only!)
LAD_VERIFY_TLS=false python -m client.lad_client --config lad-config.yaml
```

### Installing Config Support

Configuration file support requires PyYAML:

```bash
pip install 'lad-a2a-reference[config]'
```

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

    # Security verification status
    verified: bool  # True if agent passed verification
    verification_method: Optional[str]  # "tls", "domain", "jws", "did"
    verification_error: Optional[str]  # Error message if verification failed
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

## Verified Discovery

For production use, require verified agents:

```python
client = LADClient(
    verify_tls=True,  # Default: verify TLS certificates
    signing_public_key="path/to/public.pem",  # Optional: verify signatures
)

result = await client.discover(
    fallback_url="https://hotel.example.com",
    require_verified=True,  # Only return verified agents
)

for agent in result.agents:
    print(f"{agent.name}: verified={agent.verified} ({agent.verification_method})")
```

## User Consent Flow

Per spec section 4.3, clients MUST obtain explicit user consent before first contact with discovered agents.

### Interactive CLI Consent

```bash
python -m client.lad_client --url http://localhost:8080 --with-consent
```

### Programmatic Consent

```python
from client.lad_client import (
    LADClient,
    ConsentRequest,
    ConsentResponse,
    ConsentDecision,
)

async def my_consent_ui(request: ConsentRequest) -> ConsentResponse:
    """Custom consent UI implementation."""
    # Display agent info to user
    print(f"Agent: {request.agent.name}")
    print(f"Verified: {request.verified}")
    print(f"Capabilities: {request.capabilities}")

    # Get user decision (your UI logic here)
    user_approved = await show_consent_dialog(request.to_display_dict())

    if user_approved:
        return ConsentResponse(decision=ConsentDecision.APPROVED)
    return ConsentResponse(decision=ConsentDecision.DENIED)

# Use with discovery
client = LADClient()
result = await client.discover_with_consent(
    consent_callback=my_consent_ui,
    fallback_url="https://hotel.example.com",
)

# Only approved agents are returned
for agent in result.agents:
    print(f"User approved: {agent.name}")
```

### ConsentRequest Fields

```python
@dataclass
class ConsentRequest:
    agent: DiscoveredAgent
    verified: bool
    verification_method: Optional[str]  # "tls", "domain", "jws"
    capabilities: list[str]
```

### ConsentDecision Values

| Decision | Meaning |
|----------|---------|
| `APPROVED` | User consents to connect |
| `DENIED` | User refuses connection |
| `DEFERRED` | Ask again later |

## Error Handling

```python
result = await client.discover(fallback_url="http://localhost:8080")

if result.errors:
    for error in result.errors:
        print(f"Warning: {error}")

if not result.agents:
    print("No agents discovered")

# Check verification status
for agent in result.agents:
    if not agent.verified:
        print(f"Warning: {agent.name} is unverified: {agent.verification_error}")
```
