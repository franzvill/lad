"""
LAD-A2A Reference Client

Provides:
- mDNS/DNS-SD discovery via _a2a._tcp
- Well-known endpoint fallback
- AgentCard fetching and validation

Security Notes:
- TLS verification is enabled by default for production safety
- Use verify_tls=False only for local development
- See PRODUCTION-CHECKLIST.md for deployment guidance
"""

import asyncio
import logging
import ssl
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Awaitable, Callable, Optional, Protocol, Union
from urllib.parse import urljoin, urlparse

import httpx
from zeroconf import ServiceBrowser, ServiceListener, Zeroconf

# Import signing utilities (optional - gracefully handle if not available)
try:
    from common.signing import verify_agent_card, is_signed_agent_card, VerificationResult
    SIGNING_AVAILABLE = True
except ImportError:
    SIGNING_AVAILABLE = False

# Configure logging
logger = logging.getLogger("lad_a2a.client")


def configure_logging(level: str = "INFO") -> None:
    """Configure logging for the LAD-A2A client."""
    log_level = getattr(logging, level.upper(), logging.INFO)
    logging.basicConfig(
        level=log_level,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )
    logger.setLevel(log_level)


@dataclass
class DiscoveredAgent:
    """An agent discovered via LAD-A2A."""
    name: str
    description: str
    role: str
    agent_card_url: str
    capabilities_preview: list[str] = field(default_factory=list)
    source: str = "unknown"  # "mdns" or "wellknown"

    # Populated after fetching AgentCard
    agent_card: Optional[dict] = None

    # Security verification status
    verified: bool = False
    verification_method: Optional[str] = None  # "tls", "domain", "jws", "did"
    verification_error: Optional[str] = None


@dataclass
class DiscoveryResult:
    """Result of a LAD-A2A discovery operation."""
    agents: list[DiscoveredAgent] = field(default_factory=list)
    network_ssid: Optional[str] = None
    network_realm: Optional[str] = None
    discovery_method: str = "none"
    errors: list[str] = field(default_factory=list)


# User Consent Types (spec section 4.3)


class ConsentDecision(Enum):
    """User's consent decision for an agent."""
    APPROVED = "approved"
    DENIED = "denied"
    DEFERRED = "deferred"  # Ask again later


@dataclass
class ConsentRequest:
    """Information presented to user for consent decision.

    Per spec section 4.3, clients MUST obtain explicit user consent
    before initiating first contact with a discovered agent.
    """
    agent: DiscoveredAgent
    verified: bool
    verification_method: Optional[str]
    capabilities: list[str]

    def to_display_dict(self) -> dict[str, Any]:
        """Convert to a dictionary suitable for UI display."""
        return {
            "agent_name": self.agent.name,
            "agent_description": self.agent.description,
            "agent_role": self.agent.role,
            "verified": self.verified,
            "verification_method": self.verification_method or "none",
            "capabilities": self.capabilities,
            "source": self.agent.source,
        }


@dataclass
class ConsentResponse:
    """User's response to a consent request."""
    decision: ConsentDecision
    remember: bool = False  # Remember this decision for future sessions
    scope: Optional[list[str]] = None  # Approved capabilities (subset)


# Type alias for consent callback
# Callback receives ConsentRequest and returns ConsentResponse
# Can be sync or async
ConsentCallback = Callable[
    [ConsentRequest],
    Union[ConsentResponse, Awaitable[ConsentResponse]]
]


async def default_consent_callback(request: ConsentRequest) -> ConsentResponse:
    """Default consent callback that approves all verified agents.

    Production applications should implement their own consent UI.
    """
    if request.verified:
        logger.debug(f"Auto-approving verified agent: {request.agent.name}")
        return ConsentResponse(decision=ConsentDecision.APPROVED)
    else:
        logger.warning(
            f"Auto-denying unverified agent: {request.agent.name}. "
            "Implement a consent callback to allow manual approval."
        )
        return ConsentResponse(decision=ConsentDecision.DENIED)


class MDNSListener(ServiceListener):
    """Listener for mDNS service discovery."""

    def __init__(self, use_https: bool = False):
        self.agents: list[DiscoveredAgent] = []
        self._agents_by_name: dict[str, DiscoveredAgent] = {}
        self._discovered_event = asyncio.Event()
        self._use_https = use_https

    def update_service(self, zc: Zeroconf, type_: str, name: str) -> None:
        """Handle service updates (e.g., IP/port changes)."""
        logger.debug(f"mDNS service update: {name}")
        info = zc.get_service_info(type_, name)
        if info and name in self._agents_by_name:
            # Update existing agent with new info
            addresses = info.parsed_addresses()
            if addresses:
                host = addresses[0]
                port = info.port
                properties = {
                    k.decode() if isinstance(k, bytes) else k:
                    v.decode() if isinstance(v, bytes) else v
                    for k, v in info.properties.items()
                }
                path = properties.get("path", "/.well-known/agent.json")
                scheme = "https" if self._use_https else "http"
                new_url = f"{scheme}://{host}:{port}{path}"

                agent = self._agents_by_name[name]
                if agent.agent_card_url != new_url:
                    logger.info(f"mDNS service {name} updated: {new_url}")
                    agent.agent_card_url = new_url
                    # Reset verification since URL changed
                    agent.verified = False
                    agent.agent_card = None

    def remove_service(self, zc: Zeroconf, type_: str, name: str) -> None:
        """Handle service removal."""
        logger.debug(f"mDNS service removed: {name}")
        if name in self._agents_by_name:
            agent = self._agents_by_name.pop(name)
            if agent in self.agents:
                self.agents.remove(agent)
                logger.info(f"Removed agent from discovery: {agent.name}")

    def add_service(self, zc: Zeroconf, type_: str, name: str) -> None:
        """Handle new service discovery."""
        logger.debug(f"mDNS service discovered: {name}")
        info = zc.get_service_info(type_, name)
        if info:
            # Extract TXT records
            properties = {
                k.decode() if isinstance(k, bytes) else k:
                v.decode() if isinstance(v, bytes) else v
                for k, v in info.properties.items()
            }

            # Build agent card URL from service info
            addresses = info.parsed_addresses()
            if addresses:
                host = addresses[0]
                port = info.port
                path = properties.get("path", "/.well-known/agent.json")
                scheme = "https" if self._use_https else "http"
                agent_card_url = f"{scheme}://{host}:{port}{path}"

                # Extract agent name from service name
                agent_name = name.replace("._a2a._tcp.local.", "")

                agent = DiscoveredAgent(
                    name=agent_name,
                    description=f"Discovered via mDNS from {properties.get('org', 'unknown')}",
                    role=properties.get("role", "unknown"),
                    agent_card_url=agent_card_url,
                    source="mdns",
                )
                self.agents.append(agent)
                self._agents_by_name[name] = agent
                self._discovered_event.set()
                logger.info(f"Discovered agent via mDNS: {agent_name} at {agent_card_url}")


class LADClient:
    """LAD-A2A Discovery Client."""

    def __init__(
        self,
        mdns_timeout: float = 3.0,
        http_timeout: float = 10.0,
        verify_tls: bool = True,
        ca_bundle: Optional[str] = None,
        signing_public_key: Optional[str] = None,
    ):
        """Initialize LAD-A2A client.

        Args:
            mdns_timeout: Timeout for mDNS discovery in seconds.
            http_timeout: Timeout for HTTP requests in seconds.
            verify_tls: Whether to verify TLS certificates (default: True).
                        Set to False only for local development.
            ca_bundle: Path to custom CA bundle for certificate verification.
            signing_public_key: Path to public key for AgentCard signature verification.
        """
        self.mdns_timeout = mdns_timeout
        self.http_timeout = http_timeout
        self.verify_tls = verify_tls
        self.ca_bundle = ca_bundle
        self.signing_public_key = signing_public_key

        if not verify_tls:
            logger.warning(
                "TLS verification is DISABLED. This is acceptable for local "
                "development only. Production deployments MUST enable TLS verification."
            )

        if signing_public_key and not SIGNING_AVAILABLE:
            logger.warning(
                "Signature verification requested but dependencies not installed. "
                "Install with: pip install pyjwt cryptography"
            )

        logger.debug(
            f"LADClient initialized: mdns_timeout={mdns_timeout}, "
            f"http_timeout={http_timeout}, verify_tls={verify_tls}, "
            f"has_signing_key={bool(signing_public_key)}"
        )

    def _get_http_client(self) -> httpx.AsyncClient:
        """Create an HTTP client with appropriate TLS settings."""
        verify: bool | str = self.verify_tls
        if self.verify_tls and self.ca_bundle:
            verify = self.ca_bundle

        return httpx.AsyncClient(
            timeout=self.http_timeout,
            verify=verify,
        )

    async def discover_mdns(self, use_https: bool = False) -> list[DiscoveredAgent]:
        """Discover agents via mDNS/DNS-SD.

        Args:
            use_https: If True, construct HTTPS URLs for discovered agents.
        """
        agents = []
        logger.info(f"Starting mDNS discovery (timeout: {self.mdns_timeout}s)")

        try:
            zeroconf = Zeroconf()
        except Exception as e:
            logger.error(f"Failed to initialize Zeroconf: {e}")
            return agents

        listener = MDNSListener(use_https=use_https)

        try:
            browser = ServiceBrowser(zeroconf, "_a2a._tcp.local.", listener)

            # Wait for discoveries or timeout
            await asyncio.sleep(self.mdns_timeout)

            agents = listener.agents
            logger.info(f"mDNS discovery complete: found {len(agents)} agent(s)")
        except Exception as e:
            logger.error(f"mDNS discovery failed: {e}")
        finally:
            zeroconf.close()

        return agents

    async def discover_wellknown(
        self,
        base_url: str,
    ) -> list[DiscoveredAgent]:
        """Discover agents via well-known endpoint."""
        agents = []
        discovery_url = urljoin(base_url.rstrip("/") + "/", ".well-known/lad/agents")
        logger.info(f"Discovering agents via well-known endpoint: {discovery_url}")

        async with self._get_http_client() as client:
            try:
                response = await client.get(discovery_url)
                response.raise_for_status()
                data = response.json()

                # Check if TLS was used (for verification status)
                used_tls = discovery_url.startswith("https://")

                for agent_data in data.get("agents", []):
                    agent = DiscoveredAgent(
                        name=agent_data["name"],
                        description=agent_data.get("description", ""),
                        role=agent_data.get("role", "unknown"),
                        agent_card_url=agent_data["agent_card_url"],
                        capabilities_preview=agent_data.get("capabilities_preview", []),
                        source="wellknown",
                        verified=used_tls and self.verify_tls,
                        verification_method="tls" if (used_tls and self.verify_tls) else None,
                    )
                    agents.append(agent)
                    logger.debug(f"Discovered agent: {agent.name}")

                logger.info(f"Well-known discovery complete: found {len(agents)} agent(s)")
            except httpx.HTTPStatusError as e:
                logger.error(f"HTTP error during well-known discovery: {e}")
                raise
            except httpx.RequestError as e:
                logger.error(f"Request error during well-known discovery: {e}")
                raise

        return agents

    async def fetch_agent_card(
        self,
        agent: DiscoveredAgent,
        verify_domain: bool = True,
        prefer_signed: bool = True,
    ) -> dict[str, Any]:
        """Fetch the A2A AgentCard for a discovered agent.

        Args:
            agent: The discovered agent to fetch the card for.
            verify_domain: If True, verify the AgentCard URL domain matches
                          the provider organization (basic domain verification).
            prefer_signed: If True and signing key is configured, request signed
                          AgentCard and verify signature.

        Returns:
            The fetched AgentCard dictionary.

        Raises:
            httpx.HTTPError: If the fetch fails.
            ValueError: If domain verification fails.
        """
        logger.debug(f"Fetching AgentCard from {agent.agent_card_url}")

        async with self._get_http_client() as client:
            try:
                # Build headers - request signed format if we can verify it
                headers = {}
                if prefer_signed and self.signing_public_key and SIGNING_AVAILABLE:
                    headers["Accept"] = "application/jose, application/json"

                response = await client.get(agent.agent_card_url, headers=headers)
                response.raise_for_status()

                # Check if we got a signed response
                content_type = response.headers.get("content-type", "")
                if "application/jose" in content_type:
                    # Signed AgentCard - verify signature
                    await self._verify_signed_agent_card(agent, response.text)
                else:
                    # Unsigned JSON AgentCard
                    agent.agent_card = response.json()

                    # Update verification status based on TLS
                    used_tls = agent.agent_card_url.startswith("https://")
                    if used_tls and self.verify_tls:
                        agent.verified = True
                        agent.verification_method = "tls"
                        logger.debug(f"AgentCard verified via TLS: {agent.name}")

                # Optional domain verification
                if verify_domain and agent.agent_card:
                    await self._verify_domain(agent)

                logger.info(f"Fetched AgentCard for {agent.name} (verified={agent.verified})")
                return agent.agent_card

            except httpx.HTTPStatusError as e:
                agent.verification_error = f"HTTP error: {e.response.status_code}"
                logger.error(f"Failed to fetch AgentCard for {agent.name}: {e}")
                raise
            except httpx.RequestError as e:
                agent.verification_error = f"Request error: {e}"
                logger.error(f"Failed to fetch AgentCard for {agent.name}: {e}")
                raise

    async def _verify_signed_agent_card(
        self,
        agent: DiscoveredAgent,
        token: str,
    ) -> None:
        """Verify a signed AgentCard (JWS token).

        Args:
            agent: The agent to update with verification results.
            token: The JWS token containing the signed AgentCard.
        """
        if not SIGNING_AVAILABLE:
            logger.warning("Received signed AgentCard but verification not available")
            agent.verification_error = "Signature verification not available"
            return

        if not self.signing_public_key:
            logger.warning("Received signed AgentCard but no public key configured")
            agent.verification_error = "No public key for signature verification"
            return

        result = verify_agent_card(token, public_key_path=self.signing_public_key)

        if result.valid:
            agent.agent_card = result.agent_card
            agent.verified = True
            agent.verification_method = "jws"
            logger.info(
                f"AgentCard signature verified for {agent.name} "
                f"(signed_at={result.signed_at}, key_id={result.key_id})"
            )
        else:
            agent.verification_error = f"Signature verification failed: {result.error}"
            logger.warning(f"AgentCard signature invalid for {agent.name}: {result.error}")
            # Still try to decode the payload for the card
            try:
                import jwt
                # Decode without verification to get the card
                payload = jwt.decode(token, options={"verify_signature": False})
                agent.agent_card = payload.get("agent_card")
            except Exception:
                pass

    async def _verify_domain(self, agent: DiscoveredAgent) -> None:
        """Verify that the AgentCard domain matches claimed organization.

        This implements basic domain verification per spec section 4.2.
        """
        if not agent.agent_card:
            return

        card_url = urlparse(agent.agent_card_url)
        card_domain = card_url.netloc.split(":")[0]  # Remove port if present

        # Check if provider organization matches the domain
        provider = agent.agent_card.get("provider", {})
        organization = provider.get("organization", "")

        # Simple domain matching: organization should be part of the domain
        # e.g., "grandhotel.com" matches "ai.grandhotel.com"
        if organization and card_domain:
            org_normalized = organization.lower().replace(" ", "")
            domain_normalized = card_domain.lower()

            if org_normalized in domain_normalized or domain_normalized.endswith(org_normalized):
                if agent.verification_method != "tls":
                    agent.verification_method = "domain"
                    agent.verified = True
                logger.debug(f"Domain verification passed for {agent.name}: {organization}")
            else:
                logger.warning(
                    f"Domain mismatch for {agent.name}: "
                    f"organization='{organization}', domain='{card_domain}'"
                )

    async def discover(
        self,
        fallback_url: Optional[str] = None,
        try_mdns: bool = True,
        fetch_cards: bool = True,
        require_verified: bool = False,
    ) -> DiscoveryResult:
        """
        Perform LAD-A2A discovery using the layered approach.

        1. Try mDNS first (if enabled)
        2. Fall back to well-known endpoint (if provided)
        3. Optionally fetch AgentCards for all discovered agents
        4. Optionally filter to only verified agents

        Args:
            fallback_url: URL to try if mDNS fails.
            try_mdns: Whether to attempt mDNS discovery.
            fetch_cards: Whether to fetch AgentCards after discovery.
            require_verified: If True, only return verified agents.

        Returns:
            DiscoveryResult containing discovered agents and any errors.
        """
        logger.info("Starting LAD-A2A discovery")
        result = DiscoveryResult()

        # Determine if we should use HTTPS for mDNS-discovered agents
        use_https = fallback_url.startswith("https://") if fallback_url else False

        # Step 1: Try mDNS
        if try_mdns:
            try:
                mdns_agents = await self.discover_mdns(use_https=use_https)
                if mdns_agents:
                    result.agents.extend(mdns_agents)
                    result.discovery_method = "mdns"
                    logger.info(f"mDNS discovery found {len(mdns_agents)} agent(s)")
            except Exception as e:
                error_msg = f"mDNS discovery failed: {e}"
                result.errors.append(error_msg)
                logger.warning(error_msg)

        # Step 2: Fall back to well-known if no mDNS results
        if not result.agents and fallback_url:
            try:
                wellknown_agents = await self.discover_wellknown(fallback_url)
                if wellknown_agents:
                    result.agents.extend(wellknown_agents)
                    result.discovery_method = "wellknown"
                    logger.info(f"Well-known discovery found {len(wellknown_agents)} agent(s)")
            except Exception as e:
                error_msg = f"Well-known discovery failed: {e}"
                result.errors.append(error_msg)
                logger.warning(error_msg)

        # Step 3: Fetch AgentCards
        if fetch_cards and result.agents:
            logger.info(f"Fetching AgentCards for {len(result.agents)} agent(s)")
            for agent in result.agents:
                try:
                    await self.fetch_agent_card(agent)
                except Exception as e:
                    error_msg = f"Failed to fetch AgentCard for {agent.name}: {e}"
                    result.errors.append(error_msg)
                    logger.warning(error_msg)

        # Step 4: Filter to verified agents if requested
        if require_verified:
            original_count = len(result.agents)
            result.agents = [a for a in result.agents if a.verified]
            filtered_count = original_count - len(result.agents)
            if filtered_count > 0:
                logger.warning(
                    f"Filtered out {filtered_count} unverified agent(s) "
                    f"(require_verified=True)"
                )

        logger.info(
            f"Discovery complete: {len(result.agents)} agent(s), "
            f"{len(result.errors)} error(s), method={result.discovery_method}"
        )
        return result

    async def discover_with_consent(
        self,
        consent_callback: Optional[ConsentCallback] = None,
        fallback_url: Optional[str] = None,
        try_mdns: bool = True,
        fetch_cards: bool = True,
        require_verified: bool = False,
    ) -> DiscoveryResult:
        """
        Perform LAD-A2A discovery with user consent flow.

        This method implements the consent requirement from spec section 4.3:
        "Clients MUST obtain explicit user consent before initiating first
        contact with a discovered agent."

        1. Discover agents using standard flow
        2. For each agent, invoke consent callback
        3. Return only agents that user approved

        Args:
            consent_callback: Callback to request user consent. If None, uses
                             default callback (approves verified, denies unverified).
            fallback_url: URL to try if mDNS fails.
            try_mdns: Whether to attempt mDNS discovery.
            fetch_cards: Whether to fetch AgentCards after discovery.
            require_verified: If True, only present verified agents for consent.

        Returns:
            DiscoveryResult containing only user-approved agents.

        Example:
            async def my_consent_ui(request: ConsentRequest) -> ConsentResponse:
                # Display UI to user
                approved = await show_consent_dialog(
                    agent_name=request.agent.name,
                    verified=request.verified,
                    capabilities=request.capabilities,
                )
                if approved:
                    return ConsentResponse(decision=ConsentDecision.APPROVED)
                return ConsentResponse(decision=ConsentDecision.DENIED)

            result = await client.discover_with_consent(
                consent_callback=my_consent_ui,
                fallback_url="https://hotel.example.com",
            )
        """
        callback = consent_callback or default_consent_callback

        # Step 1: Standard discovery
        result = await self.discover(
            fallback_url=fallback_url,
            try_mdns=try_mdns,
            fetch_cards=fetch_cards,
            require_verified=require_verified,
        )

        if not result.agents:
            return result

        # Step 2: Request consent for each agent
        approved_agents = []
        for agent in result.agents:
            consent_request = ConsentRequest(
                agent=agent,
                verified=agent.verified,
                verification_method=agent.verification_method,
                capabilities=agent.capabilities_preview,
            )

            logger.debug(f"Requesting consent for agent: {agent.name}")

            # Call the callback (handle both sync and async)
            response = callback(consent_request)
            if asyncio.iscoroutine(response):
                response = await response

            if response.decision == ConsentDecision.APPROVED:
                logger.info(f"User approved agent: {agent.name}")
                approved_agents.append(agent)
            elif response.decision == ConsentDecision.DENIED:
                logger.info(f"User denied agent: {agent.name}")
            else:  # DEFERRED
                logger.info(f"User deferred decision for agent: {agent.name}")

        # Update result with only approved agents
        denied_count = len(result.agents) - len(approved_agents)
        result.agents = approved_agents

        if denied_count > 0:
            logger.info(f"Consent flow: {len(approved_agents)} approved, {denied_count} denied/deferred")

        return result

    def create_consent_request(self, agent: DiscoveredAgent) -> ConsentRequest:
        """Create a consent request for an agent.

        Useful when implementing custom consent flows outside of
        discover_with_consent().

        Args:
            agent: The discovered agent to create request for.

        Returns:
            ConsentRequest ready for user presentation.
        """
        return ConsentRequest(
            agent=agent,
            verified=agent.verified,
            verification_method=agent.verification_method,
            capabilities=agent.capabilities_preview,
        )


async def main():
    """Demo client discovery."""
    import argparse

    parser = argparse.ArgumentParser(description="LAD-A2A Reference Client")
    parser.add_argument("--url", help="Base URL for well-known fallback")
    parser.add_argument("--no-mdns", action="store_true", help="Skip mDNS discovery")
    parser.add_argument("--timeout", type=float, help="mDNS timeout in seconds")

    # Config file options
    parser.add_argument(
        "--config",
        help="Path to YAML configuration file (requires: pip install pyyaml)"
    )

    # TLS options
    parser.add_argument(
        "--no-verify-tls",
        action="store_true",
        help="Disable TLS certificate verification (development only)"
    )
    parser.add_argument(
        "--ca-bundle",
        help="Path to custom CA bundle for TLS verification"
    )
    parser.add_argument(
        "--require-verified",
        action="store_true",
        help="Only return verified agents"
    )
    parser.add_argument(
        "--with-consent",
        action="store_true",
        help="Enable interactive consent flow"
    )

    # Signing verification options
    parser.add_argument(
        "--signing-public-key",
        help="Path to public key for AgentCard signature verification"
    )

    # Logging options
    parser.add_argument(
        "--log-level",
        default="INFO",
        choices=["DEBUG", "INFO", "WARNING", "ERROR"],
        help="Logging level (default: INFO)"
    )

    args = parser.parse_args()

    # Load configuration from file if provided
    config = None
    if args.config:
        try:
            from common.config import load_client_config
            config = load_client_config(args.config)
            logger.info(f"Loaded configuration from {args.config}")
        except ImportError:
            print("Error: Configuration files require PyYAML.")
            print("Install with: pip install 'lad-a2a-reference[config]'")
            return
        except Exception as e:
            print(f"Error loading config: {e}")
            return

    # Merge CLI args with config file (CLI takes precedence)
    mdns_timeout = args.timeout
    if mdns_timeout is None:
        mdns_timeout = config.mdns_timeout if config else 3.0

    verify_tls = not args.no_verify_tls
    if config and not args.no_verify_tls:
        verify_tls = config.verify_tls

    ca_bundle = args.ca_bundle
    if ca_bundle is None and config:
        ca_bundle = config.ca_bundle

    signing_public_key = args.signing_public_key
    if signing_public_key is None and config:
        signing_public_key = config.signing_public_key

    log_level = args.log_level
    if log_level == "INFO" and config:
        log_level = config.log_level

    # Configure logging
    configure_logging(log_level)

    client = LADClient(
        mdns_timeout=mdns_timeout,
        http_timeout=config.http_timeout if config else 10.0,
        verify_tls=verify_tls,
        ca_bundle=ca_bundle,
        signing_public_key=signing_public_key,
    )

    # Merge discovery options from config
    fallback_url = args.url
    if fallback_url is None and config:
        fallback_url = config.fallback_url

    try_mdns = not args.no_mdns
    if config and not args.no_mdns:
        try_mdns = config.try_mdns

    require_verified = args.require_verified
    if not require_verified and config:
        require_verified = config.require_verified

    fetch_cards = config.fetch_cards if config else True

    logger.info("Starting LAD-A2A discovery...")
    logger.info(f"mDNS enabled: {try_mdns}")
    if fallback_url:
        logger.info(f"Fallback URL: {fallback_url}")

    # Interactive consent callback for CLI
    async def cli_consent_callback(request: ConsentRequest) -> ConsentResponse:
        """Interactive CLI consent flow."""
        print(f"\n{'='*50}")
        print(f"AGENT DISCOVERED: {request.agent.name}")
        print(f"{'='*50}")
        print(f"  Description: {request.agent.description}")
        print(f"  Role: {request.agent.role}")
        print(f"  Verified: {'Yes' if request.verified else 'No'} ({request.verification_method or 'none'})")
        print(f"  Capabilities: {', '.join(request.capabilities)}")
        print(f"  Source: {request.agent.source}")

        if not request.verified:
            print("\n  ⚠️  WARNING: This agent is NOT verified!")

        while True:
            response = input("\n  Connect to this agent? [y/n/skip]: ").strip().lower()
            if response in ('y', 'yes'):
                return ConsentResponse(decision=ConsentDecision.APPROVED)
            elif response in ('n', 'no'):
                return ConsentResponse(decision=ConsentDecision.DENIED)
            elif response in ('s', 'skip'):
                return ConsentResponse(decision=ConsentDecision.DEFERRED)
            print("  Please enter 'y' (yes), 'n' (no), or 'skip'")

    if args.with_consent:
        result = await client.discover_with_consent(
            consent_callback=cli_consent_callback,
            fallback_url=fallback_url,
            try_mdns=try_mdns,
            fetch_cards=fetch_cards,
            require_verified=require_verified,
        )
    else:
        result = await client.discover(
            fallback_url=fallback_url,
            try_mdns=try_mdns,
            fetch_cards=fetch_cards,
            require_verified=require_verified,
        )

    print(f"\n[Discovery Method] {result.discovery_method}")
    print(f"[Agents Found] {len(result.agents)}")

    for agent in result.agents:
        print(f"\n  Agent: {agent.name}")
        print(f"    Description: {agent.description}")
        print(f"    Role: {agent.role}")
        print(f"    AgentCard URL: {agent.agent_card_url}")
        print(f"    Capabilities: {agent.capabilities_preview}")
        print(f"    Source: {agent.source}")
        print(f"    Verified: {agent.verified} ({agent.verification_method or 'none'})")
        if agent.verification_error:
            print(f"    Verification Error: {agent.verification_error}")
        if agent.agent_card:
            print(f"    AgentCard fetched: Yes")
            print(f"    Skills: {[s['id'] for s in agent.agent_card.get('skills', [])]}")

    if result.errors:
        print(f"\n[Errors]")
        for error in result.errors:
            print(f"  - {error}")


if __name__ == "__main__":
    asyncio.run(main())
