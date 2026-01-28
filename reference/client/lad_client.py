"""
LAD-A2A Reference Client

Provides:
- mDNS/DNS-SD discovery via _a2a._tcp
- Well-known endpoint fallback
- AgentCard fetching and validation
"""

import asyncio
from dataclasses import dataclass, field
from typing import Optional
from urllib.parse import urljoin

import httpx
from zeroconf import ServiceBrowser, ServiceListener, Zeroconf


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


@dataclass
class DiscoveryResult:
    """Result of a LAD-A2A discovery operation."""
    agents: list[DiscoveredAgent] = field(default_factory=list)
    network_ssid: Optional[str] = None
    network_realm: Optional[str] = None
    discovery_method: str = "none"
    errors: list[str] = field(default_factory=list)


class MDNSListener(ServiceListener):
    """Listener for mDNS service discovery."""

    def __init__(self):
        self.agents: list[DiscoveredAgent] = []
        self._discovered_event = asyncio.Event()

    def update_service(self, zc: Zeroconf, type_: str, name: str) -> None:
        pass

    def remove_service(self, zc: Zeroconf, type_: str, name: str) -> None:
        pass

    def add_service(self, zc: Zeroconf, type_: str, name: str) -> None:
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
                agent_card_url = f"http://{host}:{port}{path}"

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
                self._discovered_event.set()


class LADClient:
    """LAD-A2A Discovery Client."""

    def __init__(
        self,
        mdns_timeout: float = 3.0,
        http_timeout: float = 10.0,
    ):
        self.mdns_timeout = mdns_timeout
        self.http_timeout = http_timeout

    async def discover_mdns(self) -> list[DiscoveredAgent]:
        """Discover agents via mDNS/DNS-SD."""
        agents = []
        zeroconf = Zeroconf()
        listener = MDNSListener()

        try:
            browser = ServiceBrowser(zeroconf, "_a2a._tcp.local.", listener)

            # Wait for discoveries or timeout
            await asyncio.sleep(self.mdns_timeout)

            agents = listener.agents
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

        async with httpx.AsyncClient(timeout=self.http_timeout) as client:
            response = await client.get(discovery_url)
            response.raise_for_status()
            data = response.json()

            for agent_data in data.get("agents", []):
                agent = DiscoveredAgent(
                    name=agent_data["name"],
                    description=agent_data.get("description", ""),
                    role=agent_data.get("role", "unknown"),
                    agent_card_url=agent_data["agent_card_url"],
                    capabilities_preview=agent_data.get("capabilities_preview", []),
                    source="wellknown",
                )
                agents.append(agent)

        return agents

    async def fetch_agent_card(self, agent: DiscoveredAgent) -> dict:
        """Fetch the A2A AgentCard for a discovered agent."""
        async with httpx.AsyncClient(timeout=self.http_timeout) as client:
            response = await client.get(agent.agent_card_url)
            response.raise_for_status()
            agent.agent_card = response.json()
            return agent.agent_card

    async def discover(
        self,
        fallback_url: Optional[str] = None,
        try_mdns: bool = True,
        fetch_cards: bool = True,
    ) -> DiscoveryResult:
        """
        Perform LAD-A2A discovery using the layered approach.

        1. Try mDNS first (if enabled)
        2. Fall back to well-known endpoint (if provided)
        3. Optionally fetch AgentCards for all discovered agents
        """
        result = DiscoveryResult()

        # Step 1: Try mDNS
        if try_mdns:
            try:
                mdns_agents = await self.discover_mdns()
                if mdns_agents:
                    result.agents.extend(mdns_agents)
                    result.discovery_method = "mdns"
            except Exception as e:
                result.errors.append(f"mDNS discovery failed: {e}")

        # Step 2: Fall back to well-known if no mDNS results
        if not result.agents and fallback_url:
            try:
                wellknown_agents = await self.discover_wellknown(fallback_url)
                if wellknown_agents:
                    result.agents.extend(wellknown_agents)
                    result.discovery_method = "wellknown"
            except Exception as e:
                result.errors.append(f"Well-known discovery failed: {e}")

        # Step 3: Fetch AgentCards
        if fetch_cards and result.agents:
            for agent in result.agents:
                try:
                    await self.fetch_agent_card(agent)
                except Exception as e:
                    result.errors.append(f"Failed to fetch AgentCard for {agent.name}: {e}")

        return result


async def main():
    """Demo client discovery."""
    import argparse

    parser = argparse.ArgumentParser(description="LAD-A2A Reference Client")
    parser.add_argument("--url", help="Base URL for well-known fallback")
    parser.add_argument("--no-mdns", action="store_true", help="Skip mDNS discovery")
    parser.add_argument("--timeout", type=float, default=3.0, help="mDNS timeout in seconds")

    args = parser.parse_args()

    client = LADClient(mdns_timeout=args.timeout)

    print("[LAD-A2A Client] Starting discovery...")
    print(f"[LAD-A2A Client] mDNS enabled: {not args.no_mdns}")
    if args.url:
        print(f"[LAD-A2A Client] Fallback URL: {args.url}")

    result = await client.discover(
        fallback_url=args.url,
        try_mdns=not args.no_mdns,
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
        if agent.agent_card:
            print(f"    AgentCard fetched: Yes")
            print(f"    Skills: {[s['id'] for s in agent.agent_card.get('skills', [])]}")

    if result.errors:
        print(f"\n[Errors]")
        for error in result.errors:
            print(f"  - {error}")


if __name__ == "__main__":
    asyncio.run(main())
