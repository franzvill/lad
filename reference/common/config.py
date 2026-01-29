"""
LAD-A2A Configuration Module

Supports loading configuration from YAML files and environment variables.

Usage:
    # Load from file
    config = load_server_config("config.yaml")
    server = LADServer(**config.to_server_kwargs())

    # Or with environment variable overrides
    config = load_server_config("config.yaml", env_prefix="LAD_")
"""

import logging
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional

logger = logging.getLogger("lad_a2a.config")

# Try to import YAML support
try:
    import yaml
    YAML_AVAILABLE = True
except ImportError:
    YAML_AVAILABLE = False


@dataclass
class AuthConfigData:
    """Authentication configuration data."""
    method: str = "none"  # "none", "oauth2", "oidc", "api_key", "bearer"
    token_url: Optional[str] = None
    authorization_url: Optional[str] = None
    scopes: Optional[list[str]] = None
    issuer: Optional[str] = None
    jwks_uri: Optional[str] = None
    client_id: Optional[str] = None
    api_key_header: Optional[str] = None
    documentation_url: Optional[str] = None


@dataclass
class ServerConfig:
    """Configuration for LAD-A2A server."""

    # Agent configuration
    name: str = "LAD-A2A Agent"
    description: str = "LAD-A2A discovery agent"
    role: str = "generic"
    capabilities: list[str] = field(default_factory=lambda: ["info"])
    version: str = "1.0.0"

    # Network configuration
    host: str = "0.0.0.0"
    port: int = 8080
    network_ssid: Optional[str] = None
    network_realm: Optional[str] = None

    # mDNS configuration
    enable_mdns: bool = True

    # TLS configuration
    tls_enabled: bool = False
    tls_certfile: Optional[str] = None
    tls_keyfile: Optional[str] = None

    # Signing configuration
    signing_enabled: bool = False
    signing_key: Optional[str] = None
    signing_key_id: Optional[str] = None

    # Authentication configuration
    auth_method: str = "none"
    auth_token_url: Optional[str] = None
    auth_authorization_url: Optional[str] = None
    auth_scopes: Optional[list[str]] = None
    auth_issuer: Optional[str] = None
    auth_client_id: Optional[str] = None
    auth_docs_url: Optional[str] = None

    # Logging
    log_level: str = "INFO"

    def to_server_kwargs(self) -> dict[str, Any]:
        """Convert to kwargs for LADServer constructor."""
        from server.lad_server import AgentConfig, TLSConfig, AuthConfig

        # Build auth config if method is not "none"
        auth_config = None
        if self.auth_method and self.auth_method != "none":
            auth_config = AuthConfig(
                method=self.auth_method,
                token_url=self.auth_token_url,
                authorization_url=self.auth_authorization_url,
                scopes=self.auth_scopes,
                issuer=self.auth_issuer,
                client_id=self.auth_client_id,
                documentation_url=self.auth_docs_url,
            )

        agent_config = AgentConfig(
            name=self.name,
            description=self.description,
            role=self.role,
            capabilities_preview=self.capabilities,
            version=self.version,
            auth_config=auth_config,
        )

        tls_config = TLSConfig(
            enabled=self.tls_enabled,
            certfile=self.tls_certfile,
            keyfile=self.tls_keyfile,
        )

        signing_config = None
        if self.signing_enabled and self.signing_key:
            try:
                from common.signing import SigningConfig
                signing_config = SigningConfig(
                    enabled=True,
                    private_key_path=self.signing_key,
                    key_id=self.signing_key_id,
                )
            except ImportError:
                logger.warning("Signing requested but module not available")

        return {
            "agent_config": agent_config,
            "host": self.host,
            "port": self.port,
            "network_ssid": self.network_ssid,
            "network_realm": self.network_realm,
            "enable_mdns": self.enable_mdns,
            "tls_config": tls_config,
            "signing_config": signing_config,
        }


@dataclass
class ClientConfig:
    """Configuration for LAD-A2A client."""

    # Discovery configuration
    mdns_timeout: float = 3.0
    http_timeout: float = 10.0
    fallback_url: Optional[str] = None
    try_mdns: bool = True

    # TLS configuration
    verify_tls: bool = True
    ca_bundle: Optional[str] = None

    # Signing verification
    signing_public_key: Optional[str] = None

    # Behavior
    require_verified: bool = False
    fetch_cards: bool = True

    # Logging
    log_level: str = "INFO"

    def to_client_kwargs(self) -> dict[str, Any]:
        """Convert to kwargs for LADClient constructor."""
        return {
            "mdns_timeout": self.mdns_timeout,
            "http_timeout": self.http_timeout,
            "verify_tls": self.verify_tls,
            "ca_bundle": self.ca_bundle,
            "signing_public_key": self.signing_public_key,
        }

    def to_discover_kwargs(self) -> dict[str, Any]:
        """Convert to kwargs for LADClient.discover()."""
        return {
            "fallback_url": self.fallback_url,
            "try_mdns": self.try_mdns,
            "fetch_cards": self.fetch_cards,
            "require_verified": self.require_verified,
        }


def _apply_env_overrides(
    config: dict[str, Any],
    env_prefix: str,
) -> dict[str, Any]:
    """Apply environment variable overrides to config dict.

    Environment variables are mapped as:
    - LAD_NAME -> name
    - LAD_TLS_ENABLED -> tls_enabled
    - LAD_PORT -> port (converted to int)
    """
    result = config.copy()

    for key in list(result.keys()):
        env_key = f"{env_prefix}{key.upper()}"
        env_value = os.environ.get(env_key)

        if env_value is not None:
            # Type conversion based on existing value type
            current_value = result[key]
            if isinstance(current_value, bool):
                result[key] = env_value.lower() in ("true", "1", "yes")
            elif isinstance(current_value, int):
                result[key] = int(env_value)
            elif isinstance(current_value, float):
                result[key] = float(env_value)
            elif isinstance(current_value, list):
                result[key] = env_value.split(",")
            else:
                result[key] = env_value

            logger.debug(f"Config override from {env_key}: {key}={result[key]}")

    return result


def load_server_config(
    config_path: Optional[str] = None,
    env_prefix: str = "LAD_",
) -> ServerConfig:
    """Load server configuration from file and environment.

    Args:
        config_path: Path to YAML configuration file (optional).
        env_prefix: Prefix for environment variable overrides.

    Returns:
        ServerConfig with merged configuration.
    """
    config_dict: dict[str, Any] = {}

    # Load from file if provided
    if config_path:
        path = Path(config_path)
        if path.exists():
            if not YAML_AVAILABLE:
                raise ImportError(
                    "PyYAML required for config files. Install with: pip install pyyaml"
                )
            with open(path) as f:
                file_config = yaml.safe_load(f) or {}
                # Handle nested 'server' key
                if "server" in file_config:
                    config_dict = file_config["server"]
                else:
                    config_dict = file_config
                logger.info(f"Loaded configuration from {config_path}")
        else:
            logger.warning(f"Config file not found: {config_path}")

    # Apply environment overrides
    if env_prefix:
        config_dict = _apply_env_overrides(config_dict, env_prefix)

    # Create config object with defaults
    return ServerConfig(**{
        k: v for k, v in config_dict.items()
        if hasattr(ServerConfig, k)
    })


def load_client_config(
    config_path: Optional[str] = None,
    env_prefix: str = "LAD_",
) -> ClientConfig:
    """Load client configuration from file and environment.

    Args:
        config_path: Path to YAML configuration file (optional).
        env_prefix: Prefix for environment variable overrides.

    Returns:
        ClientConfig with merged configuration.
    """
    config_dict: dict[str, Any] = {}

    # Load from file if provided
    if config_path:
        path = Path(config_path)
        if path.exists():
            if not YAML_AVAILABLE:
                raise ImportError(
                    "PyYAML required for config files. Install with: pip install pyyaml"
                )
            with open(path) as f:
                file_config = yaml.safe_load(f) or {}
                # Handle nested 'client' key
                if "client" in file_config:
                    config_dict = file_config["client"]
                else:
                    config_dict = file_config
                logger.info(f"Loaded configuration from {config_path}")
        else:
            logger.warning(f"Config file not found: {config_path}")

    # Apply environment overrides
    if env_prefix:
        config_dict = _apply_env_overrides(config_dict, env_prefix)

    # Create config object with defaults
    return ClientConfig(**{
        k: v for k, v in config_dict.items()
        if hasattr(ClientConfig, k)
    })


# Example configuration file template
EXAMPLE_CONFIG = """# LAD-A2A Configuration File
# See PRODUCTION-CHECKLIST.md for deployment guidance

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

  # Authentication (per spec section 4.5)
  # method: "none", "oauth2", "oidc", "api_key", "bearer"
  auth_method: "none"
  # OAuth2/OIDC settings (when auth_method is oauth2 or oidc)
  # auth_token_url: "https://auth.example.com/oauth/token"
  # auth_authorization_url: "https://auth.example.com/oauth/authorize"
  # auth_scopes:
  #   - "agent:read"
  #   - "agent:write"
  # auth_issuer: "https://auth.example.com"  # OIDC only
  # auth_client_id: "public-client-id"
  # auth_docs_url: "https://docs.example.com/auth"

  # Logging
  log_level: "INFO"

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
"""


def generate_example_config(output_path: str = "lad-config.yaml") -> str:
    """Generate an example configuration file.

    Args:
        output_path: Path to write the example config.

    Returns:
        Path to the generated file.
    """
    with open(output_path, "w") as f:
        f.write(EXAMPLE_CONFIG)
    logger.info(f"Generated example config at {output_path}")
    return output_path
