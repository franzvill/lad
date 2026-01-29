# LAD-A2A Production Deployment Checklist

This checklist covers the security and operational requirements for deploying LAD-A2A in production environments.

## Security Requirements

Per the LAD-A2A specification, all production deployments MUST implement:

### 1. Transport Security (TLS)

- [ ] **TLS 1.2+ Required** - All endpoints MUST use HTTPS
- [ ] **Valid Certificates** - Use certificates from a trusted CA (not self-signed)
- [ ] **Certificate Rotation** - Plan for certificate renewal before expiration

```bash
# Server with TLS
python -m server.lad_server \
  --ssl-certfile /path/to/cert.pem \
  --ssl-keyfile /path/to/key.pem \
  --port 443
```

### 2. AgentCard Signing (Recommended)

- [ ] **Generate Signing Keys** - Use ECDSA P-256 (ES256) keys
- [ ] **Secure Key Storage** - Protect private keys with appropriate file permissions
- [ ] **Key Rotation Plan** - Use key IDs to support rotation

```bash
# Generate signing keys
python -c "from common.signing import generate_signing_keys; generate_signing_keys('keys/')"

# Server with signing
python -m server.lad_server \
  --signing-key keys/private.pem \
  --signing-key-id "v1"
```

### 3. Identity Verification

Clients MUST verify agent identity through at least one of:

- [ ] **TLS Certificate Verification** - Verify server certificates against trusted CAs
- [ ] **Domain Verification** - AgentCard provider matches request domain
- [ ] **JWS Signature Verification** - Verify signed AgentCards with trusted public keys
- [ ] **DID Verification** - (Future) Verify via Decentralized Identifiers

### 4. User Consent

Per spec section 4.3:

- [ ] **Explicit Consent Required** - Obtain user approval before connecting to discovered agents
- [ ] **Display Verification Status** - Show whether agent is verified
- [ ] **Display Capabilities** - Show what capabilities the agent requests

```bash
# Client with consent flow
python -m client.lad_client --with-consent
```

## Configuration

### Server Configuration

```yaml
# lad-config.yaml
server:
  name: "Production Agent"
  host: "0.0.0.0"
  port: 443

  # TLS (required)
  tls_enabled: true
  tls_certfile: "/etc/ssl/certs/agent.pem"
  tls_keyfile: "/etc/ssl/private/agent.key"

  # Signing (recommended)
  signing_enabled: true
  signing_key: "/etc/lad/signing/private.pem"
  signing_key_id: "prod-v1"

  # Authentication (if required)
  auth_method: "oauth2"
  auth_token_url: "https://auth.example.com/token"
  auth_scopes:
    - "agent:access"

  log_level: "INFO"
```

### Client Configuration

```yaml
# lad-config.yaml
client:
  # TLS verification (required)
  verify_tls: true
  # ca_bundle: "/path/to/ca-bundle.pem"  # Optional custom CA

  # Signature verification (recommended)
  signing_public_key: "/etc/lad/signing/public.pem"

  # Require verified agents in production
  require_verified: true

  log_level: "INFO"
```

## Operational Checklist

### Deployment

- [ ] **Use Configuration Files** - Avoid hardcoding secrets in scripts
- [ ] **Environment Variables** - Use `LAD_` prefix for sensitive overrides
- [ ] **Log Level** - Set appropriate level (INFO for production, DEBUG for troubleshooting)

### Monitoring

- [ ] **Health Checks** - Monitor `/health` endpoint
- [ ] **Log Aggregation** - Collect logs from all agents
- [ ] **Certificate Expiry** - Alert before TLS certificates expire

### Network

- [ ] **Firewall Rules** - Allow mDNS (UDP 5353) for local discovery
- [ ] **CORS Configuration** - Restrict origins in production if needed
- [ ] **Rate Limiting** - Consider adding rate limiting for public deployments

## Development vs Production

| Feature | Development | Production |
|---------|-------------|------------|
| TLS | Optional (`http://`) | **Required** (`https://`) |
| TLS Verification | Can disable (`--no-verify-tls`) | **Must enable** |
| AgentCard Signing | Optional | **Recommended** |
| User Consent | Optional | **Required** |
| Logging | DEBUG | INFO or WARNING |

## Quick Security Check

```bash
# Verify TLS is working
curl -v https://your-agent.example.com/.well-known/lad/agents

# Verify signed AgentCard
curl -H "Accept: application/jose" https://your-agent.example.com/.well-known/agent.json

# Client with full verification
python -m client.lad_client \
  --url https://your-agent.example.com \
  --signing-public-key /path/to/public.pem \
  --require-verified
```

## References

- [LAD-A2A Specification](spec/spec.md) - Full protocol specification
- [Server Reference](docs/reference/server.md) - Server configuration options
- [Client Reference](docs/reference/client.md) - Client configuration options
- [Security Section](spec/spec.md#4-security-requirements) - Spec security requirements
