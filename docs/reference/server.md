# Server Reference

The LAD-A2A server provides agent discovery via mDNS and HTTP endpoints.

## Installation

```bash
cd reference
pip install -e .
```

## Usage

!!! warning "TLS Required in Production"
    Examples use HTTP for local development. In production, **all endpoints MUST use TLS 1.2+** per the [security requirements](../spec/spec.md#4-security-requirements).

### Basic

```bash
python -m server.lad_server --name "My Agent" --port 8080
```

### Full Options

```bash
python -m server.lad_server \
  --name "Hotel Concierge" \
  --description "Your AI concierge for hotel services" \
  --role "hotel-concierge" \
  --capabilities info dining spa reservations \
  --port 8080 \
  --ssid "GrandHotel-Guest" \
  --realm "grandhotel.com"
```

### Options

| Option | Description | Default |
|--------|-------------|---------|
| `--name` | Agent name | "Demo Agent" |
| `--description` | Agent description | "LAD-A2A demo agent" |
| `--role` | Agent role | "demo" |
| `--capabilities` | Capability list | ["info", "demo"] |
| `--host` | Bind host | "0.0.0.0" |
| `--port` | Bind port | 8080 |
| `--ssid` | Network SSID | None |
| `--realm` | Network realm | hostname |
| `--no-mdns` | Disable mDNS | False |

## Endpoints

### Discovery Endpoint

**GET** `/.well-known/lad/agents`

Returns list of discoverable agents.

```json
{
  "version": "1.0",
  "network": {
    "ssid": "GrandHotel-Guest",
    "realm": "grandhotel.com"
  },
  "agents": [
    {
      "name": "Hotel Concierge",
      "description": "Your AI concierge for hotel services",
      "role": "hotel-concierge",
      "agent_card_url": "http://192.168.1.100:8080/.well-known/agent.json",
      "capabilities_preview": ["info", "dining", "spa", "reservations"]
    }
  ]
}
```

### AgentCard Endpoint

**GET** `/.well-known/agent.json`

Returns A2A-compatible AgentCard.

```json
{
  "name": "Hotel Concierge",
  "description": "Your AI concierge for hotel services",
  "version": "1.0.0",
  "url": "http://192.168.1.100:8080/a2a",
  "capabilities": {
    "streaming": false,
    "pushNotifications": false
  },
  "skills": [
    {"id": "info", "name": "Info", "description": "Provides info functionality"},
    {"id": "dining", "name": "Dining", "description": "Provides dining functionality"}
  ]
}
```

## mDNS Advertisement

When mDNS is enabled, the server advertises:

- **Service Type:** `_a2a._tcp`
- **Service Name:** `{name}._a2a._tcp.local`
- **TXT Records:** `path`, `v`, `org`

## Programmatic Usage

```python
from server.lad_server import LADServer, AgentConfig, create_app

config = AgentConfig(
    name="My Agent",
    description="Agent description",
    role="my-role",
    capabilities_preview=["cap1", "cap2"]
)

server = LADServer(
    agent_config=config,
    port=8080,
    network_ssid="MyNetwork",
    network_realm="example.com"
)

app = create_app(server)

# Run with uvicorn
import uvicorn
uvicorn.run(app, host="0.0.0.0", port=8080)
```
