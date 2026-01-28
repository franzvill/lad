"""
LAD-A2A Reference Implementation Tests

Tests the server and client implementations for conformance with the spec.
"""

import asyncio
import pytest
from httpx import AsyncClient, ASGITransport

import sys
sys.path.insert(0, str(__file__).rsplit("/", 2)[0])

from server.lad_server import LADServer, AgentConfig, create_app
from client.lad_client import LADClient, DiscoveredAgent


# Test fixtures

@pytest.fixture
def agent_config():
    return AgentConfig(
        name="Test Hotel Concierge",
        description="Test agent for LAD-A2A conformance",
        role="hotel-concierge",
        capabilities_preview=["info", "dining", "reservations"],
    )


@pytest.fixture
def lad_server(agent_config):
    return LADServer(
        agent_config=agent_config,
        port=8080,
        network_ssid="TestHotel-Guest",
        network_realm="testhotel.com",
    )


@pytest.fixture
def app(lad_server):
    # Create app without mDNS lifecycle for testing
    from fastapi import FastAPI
    from fastapi.middleware.cors import CORSMiddleware
    from fastapi.responses import JSONResponse

    app = FastAPI()
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_methods=["GET", "OPTIONS"],
        allow_headers=["Content-Type"],
    )

    @app.get("/.well-known/lad/agents")
    async def discovery_endpoint():
        return JSONResponse(
            content=lad_server.get_discovery_response(),
            headers={"Cache-Control": "max-age=300, must-revalidate"},
        )

    @app.get("/.well-known/agent.json")
    async def agent_card():
        return lad_server.get_agent_card()

    return app


# Discovery Endpoint Tests

class TestDiscoveryEndpoint:
    """Test /.well-known/lad/agents endpoint."""

    @pytest.mark.asyncio
    async def test_discovery_returns_valid_json(self, app):
        """Discovery endpoint returns valid JSON."""
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            response = await client.get("/.well-known/lad/agents")

        assert response.status_code == 200
        assert response.headers["content-type"] == "application/json"

        data = response.json()
        assert "version" in data
        assert "agents" in data

    @pytest.mark.asyncio
    async def test_discovery_has_required_fields(self, app):
        """Discovery response includes all required fields per spec."""
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            response = await client.get("/.well-known/lad/agents")

        data = response.json()

        # Version is required
        assert data["version"] == "1.0"

        # Agents array is required
        assert isinstance(data["agents"], list)
        assert len(data["agents"]) >= 1

        # Each agent must have required fields
        agent = data["agents"][0]
        assert "name" in agent
        assert "agent_card_url" in agent

    @pytest.mark.asyncio
    async def test_discovery_has_cors_headers(self, app):
        """Discovery endpoint includes CORS headers."""
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            # Send a request with Origin header to trigger CORS response
            response = await client.get(
                "/.well-known/lad/agents",
                headers={"Origin": "http://example.com"}
            )

        # CORS should be enabled - check for allow-origin header
        assert "access-control-allow-origin" in response.headers

    @pytest.mark.asyncio
    async def test_discovery_has_cache_control(self, app):
        """Discovery endpoint includes Cache-Control header."""
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            response = await client.get("/.well-known/lad/agents")

        assert "cache-control" in response.headers
        assert "max-age" in response.headers["cache-control"]

    @pytest.mark.asyncio
    async def test_discovery_includes_network_info(self, app):
        """Discovery response includes network metadata when configured."""
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            response = await client.get("/.well-known/lad/agents")

        data = response.json()
        assert "network" in data
        assert data["network"]["ssid"] == "TestHotel-Guest"
        assert data["network"]["realm"] == "testhotel.com"

    @pytest.mark.asyncio
    async def test_agent_card_url_uses_a2a_path(self, app):
        """Agent card URL points to A2A standard path."""
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            response = await client.get("/.well-known/lad/agents")

        data = response.json()
        agent_card_url = data["agents"][0]["agent_card_url"]

        # Should use A2A standard path, not LAD-specific
        assert "/.well-known/agent.json" in agent_card_url
        assert "/.well-known/lad/" not in agent_card_url


# AgentCard Endpoint Tests

class TestAgentCardEndpoint:
    """Test /.well-known/agent.json endpoint."""

    @pytest.mark.asyncio
    async def test_agent_card_returns_valid_json(self, app):
        """AgentCard endpoint returns valid JSON."""
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            response = await client.get("/.well-known/agent.json")

        assert response.status_code == 200
        assert response.headers["content-type"] == "application/json"

    @pytest.mark.asyncio
    async def test_agent_card_has_a2a_fields(self, app):
        """AgentCard includes A2A-required fields."""
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            response = await client.get("/.well-known/agent.json")

        data = response.json()

        # A2A AgentCard required fields
        assert "name" in data
        assert "description" in data
        assert "url" in data
        assert "capabilities" in data
        assert "skills" in data
        assert "protocolVersions" in data  # Required by A2A spec
        assert "1.0" in data["protocolVersions"]

    @pytest.mark.asyncio
    async def test_agent_card_url_is_valid_endpoint(self, app):
        """AgentCard url field is a valid A2A JSON-RPC endpoint."""
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            response = await client.get("/.well-known/agent.json")

        data = response.json()

        # url should be a full URL (A2A JSON-RPC endpoint), not a relative path
        assert data["url"].startswith("http://") or data["url"].startswith("https://")
        assert "/a2a" not in data["url"]  # Should be base URL, not /a2a path

    @pytest.mark.asyncio
    async def test_agent_card_skills_match_capabilities_preview(self, app):
        """AgentCard skills align with discovery capabilities_preview."""
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            discovery_response = await client.get("/.well-known/lad/agents")
            card_response = await client.get("/.well-known/agent.json")

        discovery_data = discovery_response.json()
        card_data = card_response.json()

        preview = discovery_data["agents"][0].get("capabilities_preview", [])
        skill_ids = [s["id"] for s in card_data.get("skills", [])]

        # capabilities_preview should match skill IDs
        assert set(preview) == set(skill_ids)


# Client Tests

class TestLADClient:
    """Test LAD-A2A client discovery."""

    @pytest.mark.asyncio
    async def test_client_discovers_via_wellknown(self, app):
        """Client can discover agents via well-known endpoint."""
        # Create a test client that uses the app
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as http_client:
            response = await http_client.get("/.well-known/lad/agents")
            data = response.json()

            # Manually create discovered agent (simulating client behavior)
            agent_data = data["agents"][0]
            agent = DiscoveredAgent(
                name=agent_data["name"],
                description=agent_data.get("description", ""),
                role=agent_data.get("role", "unknown"),
                agent_card_url=agent_data["agent_card_url"],
                capabilities_preview=agent_data.get("capabilities_preview", []),
                source="wellknown",
            )

            assert agent.name == "Test Hotel Concierge"
            assert agent.role == "hotel-concierge"
            assert "info" in agent.capabilities_preview

    @pytest.mark.asyncio
    async def test_discovered_agent_dataclass(self):
        """DiscoveredAgent dataclass works correctly."""
        agent = DiscoveredAgent(
            name="Test Agent",
            description="A test agent",
            role="test",
            agent_card_url="http://example.com/.well-known/agent.json",
            capabilities_preview=["cap1", "cap2"],
            source="mdns",
        )

        assert agent.name == "Test Agent"
        assert agent.source == "mdns"
        assert agent.agent_card is None  # Not fetched yet


# Schema Validation Tests

class TestSchemaConformance:
    """Test conformance with LAD-A2A JSON schemas."""

    @pytest.mark.asyncio
    async def test_discovery_response_schema(self, app):
        """Discovery response conforms to schema."""
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            response = await client.get("/.well-known/lad/agents")

        data = response.json()

        # Required top-level fields
        assert isinstance(data.get("version"), str)
        assert isinstance(data.get("agents"), list)

        # Optional network field
        if "network" in data:
            network = data["network"]
            if "ssid" in network:
                assert isinstance(network["ssid"], str)
            if "realm" in network:
                assert isinstance(network["realm"], str)

        # Agent schema
        for agent in data["agents"]:
            assert isinstance(agent.get("name"), str)
            assert isinstance(agent.get("agent_card_url"), str)

            if "description" in agent:
                assert isinstance(agent["description"], str)
            if "role" in agent:
                assert isinstance(agent["role"], str)
            if "capabilities_preview" in agent:
                assert isinstance(agent["capabilities_preview"], list)
                for cap in agent["capabilities_preview"]:
                    assert isinstance(cap, str)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
