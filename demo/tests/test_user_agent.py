"""
User Agent (Aria) Tests

Tests the LAD-A2A discovery, A2A client functionality, and WebSocket chat.
"""

import pytest
from unittest.mock import AsyncMock, patch, MagicMock
from httpx import AsyncClient, ASGITransport
import json

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))


# ============== Fixtures ==============


@pytest.fixture
def mock_openai():
    """Mock OpenAI client for user agent."""
    with patch("user_agent.client") as mock_client:
        mock_response = MagicMock()
        mock_response.choices = [MagicMock()]
        mock_response.choices[0].message.content = "I can help you with that!"
        mock_client.chat.completions.create = AsyncMock(return_value=mock_response)
        yield mock_client


@pytest.fixture
def mock_routing_decision():
    """Mock routing to return 'handle locally'."""
    with patch("user_agent.client") as mock_client:
        mock_response = MagicMock()
        mock_response.choices = [MagicMock()]
        mock_response.choices[0].message.content = "NONE"
        mock_client.chat.completions.create = AsyncMock(return_value=mock_response)
        yield mock_client


@pytest.fixture
def user_app(mock_openai):
    """Create user agent app for testing."""
    from user_agent import app

    return app


@pytest.fixture
def sample_mdns_service():
    """Sample mDNS discovered service."""
    return {
        "name": "Grand Azure Hotel",
        "host": "127.0.0.1",
        "port": 8001,
        "url": "http://127.0.0.1:8001",
        "agent_card_url": "http://127.0.0.1:8001/.well-known/agent.json",
        "properties": {"path": "/.well-known/agent.json", "v": "1", "org": "GrandAzureHotel"},
    }


@pytest.fixture
def sample_agent_card():
    """Sample A2A AgentCard response."""
    return {
        "name": "Grand Azure Hotel",
        "description": "AI concierge for Grand Azure Hotel",
        "url": "http://localhost:8001",
        "provider": {"organization": "Grand Azure Hotel & Resort"},
        "version": "1.0.0",
        "protocolVersions": ["1.0"],
        "capabilities": {"streaming": False, "pushNotifications": False},
        "authentication": {"schemes": ["none"]},
        "defaultInputModes": ["text"],
        "defaultOutputModes": ["text"],
        "skills": [
            {"id": "hotel-info", "name": "Hotel Information", "description": "General hotel info", "tags": ["info"]},
            {"id": "dining", "name": "Dining", "description": "Restaurant info", "tags": ["food", "restaurant"]},
        ],
    }


@pytest.fixture
def sample_lad_discovery_response():
    """Sample LAD-A2A discovery response."""
    return {
        "version": "1.0",
        "network": {"ssid": "GrandAzure-Guest", "realm": "grandazurehotel.local"},
        "agents": [
            {
                "name": "Grand Azure Hotel",
                "description": "AI concierge for hotel services",
                "role": "hotel-concierge",
                "agent_card_url": "http://localhost:8001/.well-known/agent.json",
                "capabilities_preview": ["room-service", "spa-booking", "dining"],
            }
        ],
    }


# ============== DiscoveredAgent Model Tests ==============


class TestDiscoveredAgentModel:
    """Test DiscoveredAgent Pydantic model."""

    def test_discovered_agent_creation(self):
        """DiscoveredAgent can be created with required fields."""
        from user_agent import DiscoveredAgent

        agent = DiscoveredAgent(
            name="Test Agent",
            description="A test agent",
            url="http://localhost:8001",
            agent_card_url="http://localhost:8001/.well-known/agent.json",
            capabilities=["cap1", "cap2"],
        )

        assert agent.name == "Test Agent"
        assert agent.url == "http://localhost:8001"
        assert agent.a2a_endpoint is None  # Optional field

    def test_discovered_agent_with_a2a_endpoint(self):
        """DiscoveredAgent can include a2a_endpoint."""
        from user_agent import DiscoveredAgent

        agent = DiscoveredAgent(
            name="Test Agent",
            description="A test agent",
            url="http://localhost:8001",
            agent_card_url="http://localhost:8001/.well-known/agent.json",
            capabilities=["cap1", "cap2"],
            a2a_endpoint="http://localhost:8001",
        )

        assert agent.a2a_endpoint == "http://localhost:8001"


# ============== A2AServiceListener Tests ==============


class TestA2AServiceListener:
    """Test mDNS service listener."""

    def test_listener_initialization(self):
        """A2AServiceListener initializes correctly."""
        from user_agent import A2AServiceListener

        listener = A2AServiceListener()

        assert listener.services == []
        assert not listener.found_event.is_set()

    def test_listener_stores_services(self):
        """A2AServiceListener can store discovered services."""
        from user_agent import A2AServiceListener

        listener = A2AServiceListener()

        # Simulate adding a service
        service = {
            "name": "TestAgent",
            "host": "127.0.0.1",
            "port": 8001,
            "url": "http://127.0.0.1:8001",
            "agent_card_url": "http://127.0.0.1:8001/.well-known/agent.json",
            "properties": {},
        }
        listener.services.append(service)
        listener.found_event.set()

        assert len(listener.services) == 1
        assert listener.found_event.is_set()


# ============== Discovery Function Tests ==============


class TestDiscoveryFunctions:
    """Test discovery functions (mDNS and well-known)."""

    @pytest.mark.asyncio
    async def test_discover_via_mdns_fetches_agent_card_directly(
        self, sample_mdns_service, sample_agent_card
    ):
        """discover_agent_via_mdns fetches AgentCard directly using TXT record path."""
        from user_agent import discover_agent_via_mdns

        with patch("user_agent.httpx.AsyncClient") as MockClient:
            mock_http = AsyncMock()
            MockClient.return_value.__aenter__.return_value = mock_http

            # Only AgentCard fetch (no LAD endpoint call)
            card_response = MagicMock()
            card_response.status_code = 200
            card_response.json.return_value = sample_agent_card

            mock_http.get = AsyncMock(return_value=card_response)

            agent = await discover_agent_via_mdns(sample_mdns_service)

            # Verify only ONE HTTP call was made (AgentCard fetch)
            assert mock_http.get.call_count == 1
            call_url = mock_http.get.call_args[0][0]
            assert "/.well-known/agent.json" in call_url

        assert agent is not None
        assert agent.name == "Grand Azure Hotel"

    @pytest.mark.asyncio
    async def test_discover_via_wellknown_queries_lad_endpoint(
        self, sample_lad_discovery_response, sample_agent_card
    ):
        """discover_agent_via_wellknown queries LAD endpoint then fetches AgentCard."""
        from user_agent import discover_agent_via_wellknown

        with patch("user_agent.httpx.AsyncClient") as MockClient:
            mock_http = AsyncMock()
            MockClient.return_value.__aenter__.return_value = mock_http

            # Mock LAD discovery response
            lad_response = MagicMock()
            lad_response.status_code = 200
            lad_response.json.return_value = sample_lad_discovery_response

            # Mock AgentCard response
            card_response = MagicMock()
            card_response.status_code = 200
            card_response.json.return_value = sample_agent_card

            mock_http.get = AsyncMock(side_effect=[lad_response, card_response])

            agent = await discover_agent_via_wellknown("http://localhost:8001")

            # Verify TWO HTTP calls: LAD endpoint + AgentCard
            assert mock_http.get.call_count == 2

        assert agent is not None
        assert agent.name == "Grand Azure Hotel"

    @pytest.mark.asyncio
    async def test_discover_via_wellknown_returns_none_on_failure(self):
        """discover_agent_via_wellknown returns None when LAD endpoint fails."""
        from user_agent import discover_agent_via_wellknown

        with patch("user_agent.httpx.AsyncClient") as MockClient:
            mock_http = AsyncMock()
            MockClient.return_value.__aenter__.return_value = mock_http

            fail_response = MagicMock()
            fail_response.status_code = 404

            mock_http.get = AsyncMock(return_value=fail_response)

            agent = await discover_agent_via_wellknown("http://localhost:8001")

        assert agent is None

    @pytest.mark.asyncio
    async def test_fetch_agent_card_returns_none_on_failure(self):
        """fetch_agent_card returns None when fetch fails."""
        from user_agent import fetch_agent_card

        with patch("user_agent.httpx.AsyncClient") as MockClient:
            mock_http = AsyncMock()
            MockClient.return_value.__aenter__.return_value = mock_http

            fail_response = MagicMock()
            fail_response.status_code = 404

            mock_http.get = AsyncMock(return_value=fail_response)

            agent = await fetch_agent_card(
                "http://localhost:8001/.well-known/agent.json",
                "http://localhost:8001"
            )

        assert agent is None


# ============== A2A Query Tests ==============


class TestQueryAgentA2A:
    """Test query_agent_a2a function."""

    @pytest.mark.asyncio
    async def test_query_agent_sends_correct_request(self, sample_agent_card):
        """query_agent_a2a sends proper A2A SendMessage request."""
        from user_agent import query_agent_a2a, DiscoveredAgent

        agent = DiscoveredAgent(
            name="Test Agent",
            description="Test",
            url="http://localhost:8001",
            agent_card_url="http://localhost:8001/.well-known/agent.json",
            capabilities=["test"],
        )

        with patch("user_agent.httpx.AsyncClient") as MockClient:
            mock_http = AsyncMock()
            MockClient.return_value.__aenter__.return_value = mock_http

            mock_response = MagicMock()
            mock_response.status_code = 200
            mock_response.json.return_value = {
                "jsonrpc": "2.0",
                "result": {
                    "id": "task-123",
                    "status": {
                        "state": "completed",
                        "message": {
                            "role": "agent",
                            "parts": [{"type": "text", "text": "The answer is 42."}],
                        },
                    },
                },
                "id": "req-123",
            }

            mock_http.post = AsyncMock(return_value=mock_response)

            result = await query_agent_a2a(agent, "What is the answer?")

            # Verify the request was made correctly
            call_args = mock_http.post.call_args
            request_body = call_args.kwargs["json"]

            assert request_body["jsonrpc"] == "2.0"
            assert request_body["method"] == "SendMessage"
            assert request_body["params"]["message"]["role"] == "user"
            assert request_body["params"]["message"]["parts"][0]["type"] == "text"

        assert result == "The answer is 42."

    @pytest.mark.asyncio
    async def test_query_agent_handles_error_response(self):
        """query_agent_a2a handles JSON-RPC error response."""
        from user_agent import query_agent_a2a, DiscoveredAgent

        agent = DiscoveredAgent(
            name="Test Agent",
            description="Test",
            url="http://localhost:8001",
            agent_card_url="http://localhost:8001/.well-known/agent.json",
            capabilities=["test"],
        )

        with patch("user_agent.httpx.AsyncClient") as MockClient:
            mock_http = AsyncMock()
            MockClient.return_value.__aenter__.return_value = mock_http

            mock_response = MagicMock()
            mock_response.status_code = 200
            mock_response.json.return_value = {
                "jsonrpc": "2.0",
                "error": {"code": -32000, "message": "Internal error"},
                "id": "req-123",
            }

            mock_http.post = AsyncMock(return_value=mock_response)

            result = await query_agent_a2a(agent, "Query")

        assert result is None

    @pytest.mark.asyncio
    async def test_query_agent_handles_network_error(self):
        """query_agent_a2a handles network errors gracefully."""
        from user_agent import query_agent_a2a, DiscoveredAgent

        agent = DiscoveredAgent(
            name="Test Agent",
            description="Test",
            url="http://localhost:8001",
            agent_card_url="http://localhost:8001/.well-known/agent.json",
            capabilities=["test"],
        )

        with patch("user_agent.httpx.AsyncClient") as MockClient:
            mock_http = AsyncMock()
            MockClient.return_value.__aenter__.return_value = mock_http
            mock_http.post = AsyncMock(side_effect=Exception("Connection refused"))

            result = await query_agent_a2a(agent, "Query")

        assert result is None


# ============== Routing Decision Tests ==============


class TestDecideAgentRouting:
    """Test decide_agent_routing function."""

    @pytest.mark.asyncio
    async def test_routing_returns_none_with_no_agents(self, mock_openai):
        """decide_agent_routing returns None when no agents connected."""
        from user_agent import decide_agent_routing

        result = await decide_agent_routing("Hello", {})

        assert result is None

    @pytest.mark.asyncio
    async def test_routing_with_connected_agents(self):
        """decide_agent_routing uses LLM to decide routing."""
        from user_agent import decide_agent_routing

        agents = {
            "http://localhost:8001": {
                "name": "Hotel Agent",
                "description": "Hotel concierge",
                "capabilities": ["dining", "spa"],
            }
        }

        with patch("user_agent.client") as mock_client:
            mock_response = MagicMock()
            mock_response.choices = [MagicMock()]
            mock_response.choices[0].message.content = "http://localhost:8001"
            mock_client.chat.completions.create = AsyncMock(return_value=mock_response)

            result = await decide_agent_routing("What restaurants are nearby?", agents)

        assert result == "http://localhost:8001"

    @pytest.mark.asyncio
    async def test_routing_returns_none_for_general_query(self):
        """decide_agent_routing returns None for general queries."""
        from user_agent import decide_agent_routing

        agents = {
            "http://localhost:8001": {
                "name": "Hotel Agent",
                "description": "Hotel concierge",
                "capabilities": ["dining", "spa"],
            }
        }

        with patch("user_agent.client") as mock_client:
            mock_response = MagicMock()
            mock_response.choices = [MagicMock()]
            mock_response.choices[0].message.content = "NONE"
            mock_client.chat.completions.create = AsyncMock(return_value=mock_response)

            result = await decide_agent_routing("What is 2+2?", agents)

        assert result is None


# ============== Health Endpoint Tests ==============


class TestHealthEndpoint:
    """Test /health endpoint."""

    @pytest.mark.asyncio
    async def test_health_returns_status(self, user_app):
        """Health endpoint returns healthy status."""
        async with AsyncClient(
            transport=ASGITransport(app=user_app), base_url="http://test"
        ) as client:
            response = await client.get("/health")

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "healthy"
        assert data["agent"] == "Aria"
        assert "connected_agents" in data


# ============== ChatMessage Model Tests ==============


class TestChatMessageModel:
    """Test ChatMessage Pydantic model."""

    def test_chat_message_creation(self):
        """ChatMessage can be created with required fields."""
        from user_agent import ChatMessage

        msg = ChatMessage(type="message", content="Hello")

        assert msg.type == "message"
        assert msg.content == "Hello"
        assert msg.agent_url is None

    def test_chat_message_discover_type(self):
        """ChatMessage supports discover type."""
        from user_agent import ChatMessage

        msg = ChatMessage(type="discover")

        assert msg.type == "discover"
        assert msg.content is None

    def test_chat_message_connect_type(self):
        """ChatMessage supports connect type with agent_url."""
        from user_agent import ChatMessage

        msg = ChatMessage(type="connect", agent_url="http://localhost:8001")

        assert msg.type == "connect"
        assert msg.agent_url == "http://localhost:8001"


# ============== Integration Tests ==============


class TestIntegration:
    """Integration tests for user agent workflow."""

    @pytest.mark.asyncio
    async def test_full_mdns_discovery_flow(
        self, sample_mdns_service, sample_agent_card
    ):
        """Test mDNS discovery flow: mDNS TXT record -> direct AgentCard fetch."""
        from user_agent import discover_agent_via_mdns

        with patch("user_agent.httpx.AsyncClient") as MockClient:
            mock_http = AsyncMock()
            MockClient.return_value.__aenter__.return_value = mock_http

            # Only AgentCard fetch (mDNS provides path directly)
            card_response = MagicMock()
            card_response.status_code = 200
            card_response.json.return_value = sample_agent_card

            mock_http.get = AsyncMock(return_value=card_response)

            agent = await discover_agent_via_mdns(sample_mdns_service)

        assert agent is not None
        assert agent.name == "Grand Azure Hotel"
        assert agent.url == "http://localhost:8001"
        assert len(agent.capabilities) > 0

    @pytest.mark.asyncio
    async def test_full_query_flow(self, sample_agent_card):
        """Test complete query flow: routing -> A2A -> response."""
        from user_agent import query_agent_a2a, decide_agent_routing, DiscoveredAgent

        agent = DiscoveredAgent(
            name="Hotel Agent",
            description="Hotel concierge",
            url="http://localhost:8001",
            agent_card_url="http://localhost:8001/.well-known/agent.json",
            capabilities=["dining", "spa"],
        )

        connected_agents = {
            "http://localhost:8001": {
                "name": "Hotel Agent",
                "description": "Hotel concierge",
                "url": "http://localhost:8001",
                "capabilities": ["dining", "spa"],
                "a2a_endpoint": "http://localhost:8001",
            }
        }

        with patch("user_agent.client") as mock_llm:
            # Mock routing decision
            routing_response = MagicMock()
            routing_response.choices = [MagicMock()]
            routing_response.choices[0].message.content = "http://localhost:8001"
            mock_llm.chat.completions.create = AsyncMock(return_value=routing_response)

            routed_url = await decide_agent_routing(
                "What time is checkout?", connected_agents
            )

        assert routed_url == "http://localhost:8001"

        # Now test A2A query
        with patch("user_agent.httpx.AsyncClient") as MockClient:
            mock_http = AsyncMock()
            MockClient.return_value.__aenter__.return_value = mock_http

            mock_response = MagicMock()
            mock_response.status_code = 200
            mock_response.json.return_value = {
                "jsonrpc": "2.0",
                "result": {
                    "id": "task-123",
                    "status": {
                        "state": "completed",
                        "message": {
                            "role": "agent",
                            "parts": [
                                {"type": "text", "text": "Checkout is at 11:00 AM."}
                            ],
                        },
                    },
                },
                "id": "req-123",
            }
            mock_http.post = AsyncMock(return_value=mock_response)

            response = await query_agent_a2a(agent, "What time is checkout?")

        assert response == "Checkout is at 11:00 AM."


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
