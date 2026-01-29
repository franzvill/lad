"""
LAD-A2A Reference Server

Provides:
- mDNS/DNS-SD advertisement via _a2a._tcp
- /.well-known/lad/agents discovery endpoint
- Mock A2A AgentCard at /.well-known/agent.json

Security Notes:
- TLS is mandatory for production (spec section 4.1)
- Use --ssl-certfile and --ssl-keyfile for HTTPS
- See PRODUCTION-CHECKLIST.md for deployment guidance
"""

import argparse
import logging
import os
import socket
from contextlib import asynccontextmanager
from typing import Any, Optional

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, PlainTextResponse
from pydantic import BaseModel, Field
from zeroconf import ServiceInfo, Zeroconf

# Import signing utilities (optional - gracefully handle if not available)
try:
    from common.signing import SigningConfig, sign_agent_card
    SIGNING_AVAILABLE = True
except ImportError:
    SIGNING_AVAILABLE = False
    SigningConfig = None

# Configure logging
logger = logging.getLogger("lad_a2a.server")


def configure_logging(level: str = "INFO") -> None:
    """Configure logging for the LAD-A2A server."""
    log_level = getattr(logging, level.upper(), logging.INFO)
    logging.basicConfig(
        level=log_level,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )
    logger.setLevel(log_level)


class TLSConfig(BaseModel):
    """TLS configuration for secure endpoints."""
    enabled: bool = False
    certfile: Optional[str] = None
    keyfile: Optional[str] = None

    def validate_paths(self) -> bool:
        """Validate that certificate files exist when TLS is enabled."""
        if not self.enabled:
            return True
        if not self.certfile or not self.keyfile:
            logger.error("TLS enabled but certfile/keyfile not provided")
            return False
        if not os.path.exists(self.certfile):
            logger.error(f"TLS certificate file not found: {self.certfile}")
            return False
        if not os.path.exists(self.keyfile):
            logger.error(f"TLS key file not found: {self.keyfile}")
            return False
        return True


class AuthConfig(BaseModel):
    """Authentication configuration for AgentCard.

    Per spec section 4.5, auth requirements MUST be declared in the AgentCard.
    Supports OAuth 2.0, OIDC, API key, and no-auth configurations.
    """
    # Authentication method: "none", "oauth2", "oidc", "api_key", "bearer"
    method: str = "none"

    # OAuth2/OIDC configuration (when method is "oauth2" or "oidc")
    authorization_url: Optional[str] = None  # For authorization code flow
    token_url: Optional[str] = None  # For obtaining tokens
    scopes: Optional[list[str]] = None  # Required scopes
    client_id: Optional[str] = None  # Public client ID (for PKCE flows)

    # OIDC-specific (when method is "oidc")
    issuer: Optional[str] = None  # OIDC issuer URL
    jwks_uri: Optional[str] = None  # JSON Web Key Set URL

    # API key configuration (when method is "api_key")
    api_key_header: Optional[str] = None  # Header name for API key (e.g., "X-API-Key")

    # Documentation
    documentation_url: Optional[str] = None  # URL to auth setup documentation

    def to_agent_card_field(self) -> Optional[dict]:
        """Convert to AgentCard authentication field.

        Returns None if no authentication is required.
        """
        if self.method == "none":
            return None

        auth = {
            "type": self.method,
        }

        # OAuth2/OIDC fields
        if self.method in ("oauth2", "oidc"):
            if self.authorization_url:
                auth["authorizationUrl"] = self.authorization_url
            if self.token_url:
                auth["tokenUrl"] = self.token_url
            if self.scopes:
                auth["scopes"] = self.scopes
            if self.client_id:
                auth["clientId"] = self.client_id

            # OIDC-specific
            if self.method == "oidc":
                if self.issuer:
                    auth["issuer"] = self.issuer
                if self.jwks_uri:
                    auth["jwksUri"] = self.jwks_uri

        # API key fields
        elif self.method == "api_key":
            if self.api_key_header:
                auth["headerName"] = self.api_key_header
            else:
                auth["headerName"] = "X-API-Key"

        # Bearer token (simple auth header)
        elif self.method == "bearer":
            auth["headerName"] = "Authorization"
            auth["scheme"] = "Bearer"

        # Documentation URL
        if self.documentation_url:
            auth["documentationUrl"] = self.documentation_url

        return auth


class AgentConfig(BaseModel):
    """Configuration for an agent to advertise."""
    name: str
    description: str
    role: str
    capabilities_preview: list[str]
    version: str = "1.0.0"
    auth_config: Optional[AuthConfig] = None


# OpenAPI Response Models


class NetworkInfo(BaseModel):
    """Network information in discovery response."""
    ssid: Optional[str] = Field(None, description="Network SSID (e.g., 'GrandHotel-Guest')")
    realm: Optional[str] = Field(None, description="Network realm/domain (e.g., 'grandhotel.com')")


class DiscoveredAgentInfo(BaseModel):
    """Agent information in discovery response."""
    name: str = Field(..., description="Human-readable agent name")
    description: str = Field(..., description="Agent description")
    role: str = Field(..., description="Agent role (e.g., 'hotel-concierge', 'assistant')")
    agent_card_url: str = Field(..., description="URL to fetch the full A2A AgentCard")
    capabilities_preview: list[str] = Field(
        default_factory=list,
        description="Preview of agent capabilities for UI display"
    )


class DiscoveryResponse(BaseModel):
    """LAD-A2A discovery endpoint response.

    Per LAD-A2A spec section 3.2, this endpoint returns a list of
    discoverable agents on the network.
    """
    version: str = Field("1.0", description="LAD-A2A protocol version")
    network: Optional[NetworkInfo] = Field(None, description="Network information")
    agents: list[DiscoveredAgentInfo] = Field(
        default_factory=list,
        description="List of discoverable agents"
    )

    model_config = {
        "json_schema_extra": {
            "example": {
                "version": "1.0",
                "network": {
                    "ssid": "GrandHotel-Guest",
                    "realm": "grandhotel.com"
                },
                "agents": [
                    {
                        "name": "Hotel Concierge",
                        "description": "AI concierge for hotel services",
                        "role": "hotel-concierge",
                        "agent_card_url": "https://concierge.grandhotel.com/.well-known/agent.json",
                        "capabilities_preview": ["info", "dining", "spa", "reservations"]
                    }
                ]
            }
        }
    }


class HealthResponse(BaseModel):
    """Health check endpoint response."""
    status: str = Field(..., description="Server status ('ok' if healthy)")
    agent: str = Field(..., description="Name of the agent being served")
    mdns_enabled: Optional[bool] = Field(None, description="Whether mDNS advertisement is enabled")
    tls_enabled: Optional[bool] = Field(None, description="Whether TLS is enabled")
    signing_enabled: Optional[bool] = Field(None, description="Whether AgentCard signing is enabled")

    model_config = {
        "json_schema_extra": {
            "example": {
                "status": "ok",
                "agent": "Hotel Concierge",
                "mdns_enabled": True,
                "tls_enabled": True,
                "signing_enabled": True
            }
        }
    }


class LADServer:
    """LAD-A2A Discovery Server."""

    def __init__(
        self,
        agent_config: AgentConfig,
        host: str = "0.0.0.0",
        port: int = 8080,
        network_ssid: Optional[str] = None,
        network_realm: Optional[str] = None,
        enable_mdns: bool = True,
        tls_config: Optional[TLSConfig] = None,
        signing_config: Optional["SigningConfig"] = None,
    ):
        self.agent_config = agent_config
        self.host = host
        self.port = port
        self.network_ssid = network_ssid
        self.network_realm = network_realm or socket.gethostname() or "local"
        self.enable_mdns = enable_mdns
        self.tls_config = tls_config or TLSConfig()
        self.signing_config = signing_config
        self.zeroconf: Optional[Zeroconf] = None
        self.service_info: Optional[ServiceInfo] = None

        # Validate signing config if provided
        if self.signing_config and self.signing_config.enabled:
            if not SIGNING_AVAILABLE:
                logger.error(
                    "AgentCard signing requested but signing module not available. "
                    "Install with: pip install pyjwt cryptography"
                )
                self.signing_config.enabled = False
            elif not self.signing_config.validate():
                logger.error("AgentCard signing configuration invalid. Disabling signing.")
                self.signing_config.enabled = False
            else:
                logger.info("AgentCard signing enabled")

        logger.debug(
            f"Initializing LADServer: agent={agent_config.name}, "
            f"host={host}, port={port}, tls={self.tls_config.enabled}, "
            f"signing={self.signing_config.enabled if self.signing_config else False}"
        )

    def _get_url_scheme(self) -> str:
        """Get URL scheme based on TLS configuration."""
        return "https" if self.tls_config.enabled else "http"

    def _get_local_ip(self) -> str:
        """Get local IP address for network advertisement.

        Uses UDP socket trick to determine the local IP that would be used
        to reach external networks. Falls back to localhost if unavailable.
        """
        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            # Use Google DNS to determine outbound interface
            # This doesn't actually send data, just determines routing
            s.connect(("8.8.8.8", 80))
            ip = s.getsockname()[0]
            s.close()
            logger.debug(f"Detected local IP: {ip}")
            return ip
        except OSError as e:
            logger.warning(
                f"Failed to detect local IP (may be offline or air-gapped): {e}. "
                "Falling back to 127.0.0.1"
            )
            return "127.0.0.1"

    def start_mdns(self) -> None:
        """Start mDNS advertisement."""
        if not self.enable_mdns:
            logger.info("mDNS disabled - using well-known endpoint only")
            return

        try:
            self.zeroconf = Zeroconf()
        except Exception as e:
            logger.error(f"Failed to initialize Zeroconf: {e}")
            return

        local_ip = self._get_local_ip()

        # TXT record per LAD-A2A spec
        txt_records = {
            "path": "/.well-known/agent.json",
            "v": "1",
            "org": self.network_realm,
        }

        self.service_info = ServiceInfo(
            "_a2a._tcp.local.",
            f"{self.agent_config.name}._a2a._tcp.local.",
            addresses=[socket.inet_aton(local_ip)],
            port=self.port,
            properties=txt_records,
            server=f"{socket.gethostname()}.local.",
        )

        try:
            self.zeroconf.register_service(self.service_info)
            logger.info(
                f"mDNS advertising: {self.agent_config.name}._a2a._tcp.local "
                f"on {local_ip}:{self.port}"
            )
        except Exception as e:
            logger.error(f"Failed to register mDNS service: {e}")

    def stop_mdns(self) -> None:
        """Stop mDNS advertisement."""
        if not self.enable_mdns:
            return
        if self.zeroconf and self.service_info:
            try:
                self.zeroconf.unregister_service(self.service_info)
                self.zeroconf.close()
                logger.info("mDNS service unregistered")
            except Exception as e:
                logger.warning(f"Error during mDNS cleanup: {e}")

    def get_discovery_response(self) -> dict[str, Any]:
        """Generate LAD-A2A discovery response."""
        scheme = self._get_url_scheme()
        base_url = f"{scheme}://{self._get_local_ip()}:{self.port}"

        response = {
            "version": "1.0",
            "agents": [
                {
                    "name": self.agent_config.name,
                    "description": self.agent_config.description,
                    "role": self.agent_config.role,
                    "agent_card_url": f"{base_url}/.well-known/agent.json",
                    "capabilities_preview": self.agent_config.capabilities_preview,
                }
            ]
        }

        # Add network info if available
        network = {}
        if self.network_ssid:
            network["ssid"] = self.network_ssid
        if self.network_realm:
            network["realm"] = self.network_realm
        if network:
            response["network"] = network

        logger.debug(f"Generated discovery response with {len(response['agents'])} agent(s)")
        return response

    def get_agent_card(self) -> dict[str, Any]:
        """Generate A2A AgentCard per A2A protocol specification."""
        scheme = self._get_url_scheme()
        base_url = f"{scheme}://{self._get_local_ip()}:{self.port}"

        card = {
            "name": self.agent_config.name,
            "description": self.agent_config.description,
            "url": base_url,  # A2A JSON-RPC endpoint (base URL per A2A spec)
            "version": self.agent_config.version,
            "protocolVersions": ["1.0"],  # Required by A2A spec
            "capabilities": {
                "streaming": False,
                "pushNotifications": False,
                "stateTransitionHistory": False,
            },
            "defaultInputModes": ["text"],  # A2A uses "text", not "text/plain"
            "defaultOutputModes": ["text"],
            "skills": [
                {
                    "id": skill,
                    "name": skill.replace("-", " ").title(),
                    "description": f"Provides {skill} functionality",
                    "tags": [skill],
                }
                for skill in self.agent_config.capabilities_preview
            ],
            "provider": {
                "organization": self.network_realm or self.agent_config.name,
            },
        }

        # Add authentication requirements if configured
        if self.agent_config.auth_config:
            auth_field = self.agent_config.auth_config.to_agent_card_field()
            if auth_field:
                card["authentication"] = auth_field

        logger.debug(f"Generated AgentCard for {self.agent_config.name}")
        return card

    def get_signed_agent_card(self) -> Optional[str]:
        """Generate a signed AgentCard (JWS token).

        Returns:
            JWS token string if signing is enabled, None otherwise.
        """
        if not self.signing_config or not self.signing_config.enabled:
            return None

        if not SIGNING_AVAILABLE:
            logger.warning("Signing requested but module not available")
            return None

        try:
            card = self.get_agent_card()
            signed = sign_agent_card(card, self.signing_config)
            logger.debug(f"Generated signed AgentCard for {self.agent_config.name}")
            return signed
        except Exception as e:
            logger.error(f"Failed to sign AgentCard: {e}")
            return None


def create_app(server: LADServer) -> FastAPI:
    """Create FastAPI application with LAD-A2A endpoints."""

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        # Start mDNS on startup
        server.start_mdns()
        yield
        # Stop mDNS on shutdown
        server.stop_mdns()

    app = FastAPI(
        title="LAD-A2A Reference Server",
        description="""
## Local Agent Discovery for A2A

This server implements the LAD-A2A protocol for discovering A2A-capable AI agents on local networks.

### Endpoints

- **Discovery** (`/.well-known/lad/agents`): List available agents
- **AgentCard** (`/.well-known/agent.json`): Get full A2A AgentCard
- **Health** (`/health`): Server health check

### Security

Per LAD-A2A specification:
- TLS 1.2+ is **required** for production deployments
- AgentCard signing (JWS) is **recommended** for identity verification
- User consent is **required** before connecting to discovered agents

### Documentation

- [LAD-A2A Specification](https://github.com/lad-a2a/spec)
- [A2A Protocol](https://github.com/google/a2a-protocol)
""",
        version="0.1.0",
        lifespan=lifespan,
        openapi_tags=[
            {
                "name": "discovery",
                "description": "LAD-A2A discovery endpoints for finding agents on the network",
            },
            {
                "name": "a2a",
                "description": "A2A protocol endpoints for agent communication",
            },
            {
                "name": "operations",
                "description": "Operational endpoints for monitoring and health checks",
            },
        ],
    )

    # CORS middleware per LAD-A2A spec
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_methods=["GET", "OPTIONS"],
        allow_headers=["Content-Type", "Accept"],
    )

    @app.get(
        "/.well-known/lad/agents",
        response_model=DiscoveryResponse,
        tags=["discovery"],
        summary="Discover available agents",
        description="""
Returns a list of A2A-capable agents available on this network.

Per LAD-A2A spec section 3.2, this endpoint:
- Returns agents with their capabilities preview
- Includes network information (SSID, realm) when available
- Provides AgentCard URLs for fetching full agent details

**Caching**: Responses are cached for 5 minutes (max-age=300).
""",
    )
    async def discovery_endpoint():
        response = JSONResponse(
            content=server.get_discovery_response(),
            headers={
                "Cache-Control": "max-age=300, must-revalidate",
            }
        )
        return response

    @app.get(
        "/.well-known/agent.json",
        tags=["a2a"],
        summary="Get A2A AgentCard",
        description="""
Returns the A2A AgentCard for this agent.

**Content Negotiation**: The response format depends on the `Accept` header:
- `application/json` (default): Returns unsigned JSON AgentCard
- `application/jose` or `text/plain`: Returns signed JWS token (if signing is enabled)

**Signed AgentCards** include:
- Cryptographic signature for identity verification
- Timestamp of when the card was signed
- Key ID for key rotation support
""",
        responses={
            200: {
                "description": "A2A AgentCard",
                "content": {
                    "application/json": {
                        "example": {
                            "name": "Hotel Concierge",
                            "description": "AI concierge for hotel services",
                            "url": "https://concierge.grandhotel.com",
                            "version": "1.0.0",
                            "capabilities": {"streaming": False},
                            "skills": [{"id": "info", "name": "Info"}],
                        }
                    },
                    "application/jose": {
                        "example": "eyJhbGciOiJFUzI1NiIsInR5cCI6IkpXVCJ9..."
                    },
                },
            }
        },
    )
    async def agent_card(request: Request):
        # Check if client prefers signed format
        accept_header = request.headers.get("accept", "application/json")
        wants_signed = (
            "application/jose" in accept_header or
            "text/plain" in accept_header
        )

        if wants_signed and server.signing_config and server.signing_config.enabled:
            signed = server.get_signed_agent_card()
            if signed:
                return PlainTextResponse(
                    content=signed,
                    media_type="application/jose",
                )

        # Default: return unsigned JSON
        return server.get_agent_card()

    @app.get(
        "/health",
        response_model=HealthResponse,
        tags=["operations"],
        summary="Health check",
        description="""
Returns the health status of the LAD-A2A server.

Use this endpoint for:
- Load balancer health checks
- Monitoring and alerting
- Verifying server configuration
""",
    )
    async def health():
        return HealthResponse(
            status="ok",
            agent=server.agent_config.name,
            mdns_enabled=server.enable_mdns,
            tls_enabled=server.tls_config.enabled if server.tls_config else False,
            signing_enabled=(
                server.signing_config.enabled
                if server.signing_config
                else False
            ),
        )

    return app


def main():
    """Run the LAD-A2A server."""
    parser = argparse.ArgumentParser(description="LAD-A2A Reference Server")

    # Configuration file
    parser.add_argument(
        "--config", "-c",
        help="Path to YAML configuration file"
    )
    parser.add_argument(
        "--generate-config",
        action="store_true",
        help="Generate example configuration file and exit"
    )

    # Agent options (can be overridden by config file)
    parser.add_argument("--name", default="Demo Agent", help="Agent name")
    parser.add_argument("--description", default="LAD-A2A demo agent", help="Agent description")
    parser.add_argument("--role", default="demo", help="Agent role")
    parser.add_argument("--capabilities", nargs="+", default=["info", "demo"], help="Capabilities")
    parser.add_argument("--host", default="0.0.0.0", help="Host to bind")
    parser.add_argument("--port", type=int, default=8080, help="Port to bind")
    parser.add_argument("--ssid", help="Network SSID")
    parser.add_argument("--realm", help="Network realm/domain")
    parser.add_argument("--no-mdns", action="store_true", help="Disable mDNS advertisement")

    # TLS options
    parser.add_argument(
        "--ssl-certfile",
        help="Path to TLS certificate file (enables HTTPS)"
    )
    parser.add_argument(
        "--ssl-keyfile",
        help="Path to TLS private key file"
    )

    # Signing options
    parser.add_argument(
        "--signing-key",
        help="Path to private key for AgentCard signing (enables JWS)"
    )
    parser.add_argument(
        "--signing-key-id",
        help="Key ID (kid) for signed AgentCards"
    )

    # Authentication options
    parser.add_argument(
        "--auth-method",
        choices=["none", "oauth2", "oidc", "api_key", "bearer"],
        default="none",
        help="Authentication method required for this agent"
    )
    parser.add_argument(
        "--auth-token-url",
        help="OAuth2/OIDC token endpoint URL"
    )
    parser.add_argument(
        "--auth-authorization-url",
        help="OAuth2/OIDC authorization endpoint URL"
    )
    parser.add_argument(
        "--auth-scopes",
        nargs="+",
        help="Required OAuth2/OIDC scopes"
    )
    parser.add_argument(
        "--auth-client-id",
        help="OAuth2/OIDC public client ID (for PKCE flows)"
    )
    parser.add_argument(
        "--auth-issuer",
        help="OIDC issuer URL"
    )
    parser.add_argument(
        "--auth-jwks-uri",
        help="OIDC JSON Web Key Set URL"
    )
    parser.add_argument(
        "--auth-docs-url",
        help="URL to authentication documentation"
    )

    # Logging options
    parser.add_argument(
        "--log-level",
        default="INFO",
        choices=["DEBUG", "INFO", "WARNING", "ERROR"],
        help="Logging level (default: INFO)"
    )

    args = parser.parse_args()

    # Handle --generate-config
    if args.generate_config:
        try:
            from common.config import generate_example_config
            output_path = generate_example_config("lad-config.yaml")
            print(f"Generated example configuration: {output_path}")
        except ImportError:
            print("Config module not available")
        return

    # Configure logging first
    configure_logging(args.log_level)

    # Load configuration from file if provided
    server_config = None
    if args.config:
        try:
            from common.config import load_server_config
            server_config = load_server_config(args.config)
            logger.info(f"Loaded configuration from {args.config}")
        except ImportError:
            logger.warning("Config module not available, using CLI arguments only")
        except Exception as e:
            logger.error(f"Failed to load config: {e}")

    # CLI arguments override config file
    if server_config:
        # Use config file values as defaults, CLI overrides
        name = args.name if args.name != "Demo Agent" else server_config.name
        description = args.description if args.description != "LAD-A2A demo agent" else server_config.description
        role = args.role if args.role != "demo" else server_config.role
        capabilities = args.capabilities if args.capabilities != ["info", "demo"] else server_config.capabilities
        host = args.host if args.host != "0.0.0.0" else server_config.host
        port = args.port if args.port != 8080 else server_config.port
        ssid = args.ssid or server_config.network_ssid
        realm = args.realm or server_config.network_realm
        enable_mdns = not args.no_mdns and server_config.enable_mdns
        ssl_certfile = args.ssl_certfile or server_config.tls_certfile
        ssl_keyfile = args.ssl_keyfile or server_config.tls_keyfile
        signing_key = args.signing_key or server_config.signing_key
        signing_key_id = args.signing_key_id or server_config.signing_key_id
    else:
        name = args.name
        description = args.description
        role = args.role
        capabilities = args.capabilities
        host = args.host
        port = args.port
        ssid = args.ssid
        realm = args.realm
        enable_mdns = not args.no_mdns
        ssl_certfile = args.ssl_certfile
        ssl_keyfile = args.ssl_keyfile
        signing_key = args.signing_key
        signing_key_id = args.signing_key_id

    # Configure TLS
    tls_config = TLSConfig(
        enabled=bool(ssl_certfile),
        certfile=ssl_certfile,
        keyfile=ssl_keyfile,
    )

    if tls_config.enabled and not tls_config.validate_paths():
        logger.error("TLS configuration invalid. Exiting.")
        return

    # Configure signing
    signing_config = None
    if signing_key and SIGNING_AVAILABLE:
        from common.signing import SigningConfig
        signing_config = SigningConfig(
            enabled=True,
            private_key_path=signing_key,
            key_id=signing_key_id,
        )
    elif signing_key and not SIGNING_AVAILABLE:
        logger.warning(
            "AgentCard signing requested but dependencies not installed. "
            "Install with: pip install pyjwt cryptography"
        )

    # Configure authentication
    auth_config = None
    if args.auth_method and args.auth_method != "none":
        auth_config = AuthConfig(
            method=args.auth_method,
            token_url=args.auth_token_url,
            authorization_url=args.auth_authorization_url,
            scopes=args.auth_scopes,
            client_id=args.auth_client_id,
            issuer=args.auth_issuer,
            jwks_uri=args.auth_jwks_uri,
            documentation_url=args.auth_docs_url,
        )
        logger.info(f"Authentication configured: {args.auth_method}")

    config = AgentConfig(
        name=name,
        description=description,
        role=role,
        capabilities_preview=capabilities,
        auth_config=auth_config,
    )

    server = LADServer(
        agent_config=config,
        host=host,
        port=port,
        network_ssid=ssid,
        network_realm=realm,
        enable_mdns=enable_mdns,
        tls_config=tls_config,
        signing_config=signing_config,
    )

    app = create_app(server)

    import uvicorn

    scheme = "https" if tls_config.enabled else "http"
    logger.info(f"Starting LAD-A2A server on {scheme}://{host}:{port}")
    logger.info(f"Discovery endpoint: {scheme}://localhost:{port}/.well-known/lad/agents")
    logger.info(f"AgentCard endpoint: {scheme}://localhost:{port}/.well-known/agent.json")

    if not tls_config.enabled:
        logger.warning(
            "TLS is DISABLED. This is acceptable for local development only. "
            "Production deployments MUST use TLS (--ssl-certfile and --ssl-keyfile)."
        )

    uvicorn_kwargs = {
        "host": host,
        "port": port,
        "log_level": args.log_level.lower(),
    }

    if tls_config.enabled:
        uvicorn_kwargs["ssl_certfile"] = tls_config.certfile
        uvicorn_kwargs["ssl_keyfile"] = tls_config.keyfile

    uvicorn.run(app, **uvicorn_kwargs)


if __name__ == "__main__":
    main()
