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
| `--ssl-certfile` | TLS certificate file (enables HTTPS) | None |
| `--ssl-keyfile` | TLS private key file | None |
| `--signing-key` | Private key for AgentCard signing (enables JWS) | None |
| `--signing-key-id` | Key ID for signed AgentCards | None |
| `--config` | Path to YAML configuration file | None |
| `--generate-config` | Generate example config file and exit | False |
| `--auth-method` | Authentication method (none, oauth2, oidc, api_key, bearer) | none |
| `--auth-token-url` | OAuth2/OIDC token endpoint URL | None |
| `--auth-authorization-url` | OAuth2/OIDC authorization endpoint URL | None |
| `--auth-scopes` | Required OAuth2/OIDC scopes (space-separated) | None |
| `--auth-client-id` | OAuth2/OIDC public client ID (for PKCE flows) | None |
| `--auth-issuer` | OIDC issuer URL | None |
| `--auth-jwks-uri` | OIDC JSON Web Key Set URL | None |
| `--auth-docs-url` | URL to authentication documentation | None |
| `--log-level` | Logging level (DEBUG, INFO, WARNING, ERROR) | INFO |

## API Documentation

The server provides interactive API documentation via OpenAPI:

- **Swagger UI**: `http://localhost:8080/docs`
- **ReDoc**: `http://localhost:8080/redoc`
- **OpenAPI JSON**: `http://localhost:8080/openapi.json`

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
  "url": "http://192.168.1.100:8080",
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

## TLS Configuration

!!! warning "TLS Required in Production"
    All production deployments **MUST** use TLS 1.2+ per the specification.

```bash
# Start server with TLS
python -m server.lad_server \
  --name "Secure Agent" \
  --ssl-certfile /path/to/cert.pem \
  --ssl-keyfile /path/to/key.pem \
  --port 443
```

## AgentCard Signing

Enable cryptographic signing of AgentCards for identity verification:

```bash
# Generate signing keys (one-time)
python -c "
from common.signing import generate_signing_keys
generate_signing_keys('keys/')
"

# Start server with signing enabled
python -m server.lad_server \
  --name "Signed Agent" \
  --signing-key keys/private.pem \
  --signing-key-id "agent-v1"
```

Clients can request signed AgentCards by sending `Accept: application/jose` header.

## Authentication Configuration

Per spec section 4.5, AgentCards MUST declare authentication requirements. Configure authentication for your agent:

### OAuth 2.0

```bash
python -m server.lad_server \
  --name "Secure Agent" \
  --auth-method oauth2 \
  --auth-token-url "https://auth.example.com/oauth/token" \
  --auth-authorization-url "https://auth.example.com/oauth/authorize" \
  --auth-scopes agent:read agent:write \
  --auth-docs-url "https://docs.example.com/auth"
```

### OpenID Connect (OIDC)

```bash
python -m server.lad_server \
  --name "OIDC Agent" \
  --auth-method oidc \
  --auth-issuer "https://auth.example.com" \
  --auth-token-url "https://auth.example.com/oauth/token" \
  --auth-scopes openid profile agent:access
```

### API Key

```bash
python -m server.lad_server \
  --name "API Agent" \
  --auth-method api_key \
  --auth-docs-url "https://docs.example.com/api-key"
```

### AgentCard Authentication Field

When authentication is configured, the AgentCard includes an `authentication` field:

```json
{
  "name": "Secure Agent",
  "authentication": {
    "type": "oauth2",
    "tokenUrl": "https://auth.example.com/oauth/token",
    "authorizationUrl": "https://auth.example.com/oauth/authorize",
    "scopes": ["agent:read", "agent:write"],
    "documentationUrl": "https://docs.example.com/auth"
  }
}
```

## Configuration Files

Use YAML configuration files for complex setups:

```bash
# Generate example configuration
python -m server.lad_server --generate-config

# Start with config file
python -m server.lad_server --config lad-config.yaml
```

### Example Configuration

```yaml
server:
  # Agent identity
  name: "My Agent"
  description: "LAD-A2A discovery agent"
  role: "service"
  capabilities:
    - info
    - service

  # Network
  host: "0.0.0.0"
  port: 8080
  network_ssid: "MyNetwork-Guest"
  network_realm: "example.com"

  # mDNS advertisement
  enable_mdns: true

  # TLS (required for production)
  tls_enabled: false
  tls_certfile: "/path/to/cert.pem"
  tls_keyfile: "/path/to/key.pem"

  # AgentCard signing (recommended for production)
  signing_enabled: false
  signing_key: "/path/to/private.pem"
  signing_key_id: "key-v1"

  # Logging
  log_level: "INFO"
```

### Environment Variable Overrides

Config file values can be overridden via environment variables with `LAD_` prefix:

```bash
# Override port from config file
LAD_PORT=9090 python -m server.lad_server --config lad-config.yaml

# Enable TLS via environment
LAD_TLS_ENABLED=true python -m server.lad_server --config lad-config.yaml
```

### Installing Config Support

Configuration file support requires PyYAML:

```bash
pip install 'lad-a2a-reference[config]'
```

## Programmatic Usage

```python
from server.lad_server import LADServer, AgentConfig, TLSConfig, create_app

config = AgentConfig(
    name="My Agent",
    description="Agent description",
    role="my-role",
    capabilities_preview=["cap1", "cap2"]
)

# Optional: TLS configuration
tls_config = TLSConfig(
    enabled=True,
    certfile="/path/to/cert.pem",
    keyfile="/path/to/key.pem",
)

server = LADServer(
    agent_config=config,
    port=8080,
    network_ssid="MyNetwork",
    network_realm="example.com",
    tls_config=tls_config,
)

app = create_app(server)

# Run with uvicorn
import uvicorn
uvicorn.run(
    app,
    host="0.0.0.0",
    port=8080,
    ssl_certfile="/path/to/cert.pem",
    ssl_keyfile="/path/to/key.pem",
)
```
