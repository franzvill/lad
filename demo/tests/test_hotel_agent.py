"""
Hotel Agent Tests

Tests the LAD-A2A discovery and A2A JSON-RPC endpoints for the hotel agent.
"""

import pytest
from unittest.mock import AsyncMock, patch, MagicMock
from httpx import AsyncClient, ASGITransport
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))


# Create a test app without mDNS lifecycle
@pytest.fixture
def mock_openai():
    """Mock OpenAI client for hotel agent."""
    with patch("hotel_agent.client") as mock_client:
        mock_response = MagicMock()
        mock_response.choices = [MagicMock()]
        mock_response.choices[0].message.content = "Checkout is at 11:00 AM. Late checkout until 2:00 PM is complimentary for suite guests."
        mock_client.chat.completions.create = AsyncMock(return_value=mock_response)
        yield mock_client


@pytest.fixture
def hotel_app(mock_openai):
    """Create hotel agent app for testing (without mDNS lifecycle)."""
    from hotel_agent import (
        lad_discovery,
        agent_card,
        a2a_jsonrpc,
        health,
        HOTEL_NAME,
    )

    app = FastAPI(title=f"{HOTEL_NAME} Agent Test")
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # Mount endpoints
    app.get("/.well-known/lad/agents")(lad_discovery)
    app.get("/.well-known/agent.json")(agent_card)
    app.post("/")(a2a_jsonrpc)
    app.get("/health")(health)

    return app


# ============== LAD-A2A Discovery Tests ==============


class TestLADDiscoveryEndpoint:
    """Test /.well-known/lad/agents endpoint."""

    @pytest.mark.asyncio
    async def test_discovery_returns_valid_json(self, hotel_app):
        """Discovery endpoint returns valid JSON."""
        async with AsyncClient(
            transport=ASGITransport(app=hotel_app), base_url="http://test"
        ) as client:
            response = await client.get("/.well-known/lad/agents")

        assert response.status_code == 200
        assert response.headers["content-type"] == "application/json"

        data = response.json()
        assert "version" in data
        assert "agents" in data

    @pytest.mark.asyncio
    async def test_discovery_has_required_fields(self, hotel_app):
        """Discovery response includes all required fields per spec."""
        async with AsyncClient(
            transport=ASGITransport(app=hotel_app), base_url="http://test"
        ) as client:
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
    async def test_discovery_has_cors_headers(self, hotel_app):
        """Discovery endpoint includes CORS headers."""
        async with AsyncClient(
            transport=ASGITransport(app=hotel_app), base_url="http://test"
        ) as client:
            response = await client.get(
                "/.well-known/lad/agents", headers={"Origin": "http://example.com"}
            )

        assert "access-control-allow-origin" in response.headers

    @pytest.mark.asyncio
    async def test_discovery_has_cache_control(self, hotel_app):
        """Discovery endpoint includes Cache-Control header."""
        async with AsyncClient(
            transport=ASGITransport(app=hotel_app), base_url="http://test"
        ) as client:
            response = await client.get("/.well-known/lad/agents")

        assert "cache-control" in response.headers
        assert "max-age" in response.headers["cache-control"]

    @pytest.mark.asyncio
    async def test_discovery_includes_network_info(self, hotel_app):
        """Discovery response includes network metadata."""
        async with AsyncClient(
            transport=ASGITransport(app=hotel_app), base_url="http://test"
        ) as client:
            response = await client.get("/.well-known/lad/agents")

        data = response.json()
        assert "network" in data
        assert "ssid" in data["network"]
        assert "realm" in data["network"]

    @pytest.mark.asyncio
    async def test_discovery_agent_has_capabilities_preview(self, hotel_app):
        """Discovery agent includes capabilities_preview."""
        async with AsyncClient(
            transport=ASGITransport(app=hotel_app), base_url="http://test"
        ) as client:
            response = await client.get("/.well-known/lad/agents")

        data = response.json()
        agent = data["agents"][0]

        assert "capabilities_preview" in agent
        assert isinstance(agent["capabilities_preview"], list)
        assert len(agent["capabilities_preview"]) > 0

    @pytest.mark.asyncio
    async def test_discovery_agent_has_role(self, hotel_app):
        """Discovery agent includes role field."""
        async with AsyncClient(
            transport=ASGITransport(app=hotel_app), base_url="http://test"
        ) as client:
            response = await client.get("/.well-known/lad/agents")

        data = response.json()
        agent = data["agents"][0]

        assert "role" in agent
        assert agent["role"] == "hotel-concierge"


# ============== A2A AgentCard Tests ==============


class TestAgentCardEndpoint:
    """Test /.well-known/agent.json endpoint."""

    @pytest.mark.asyncio
    async def test_agent_card_returns_valid_json(self, hotel_app):
        """AgentCard endpoint returns valid JSON."""
        async with AsyncClient(
            transport=ASGITransport(app=hotel_app), base_url="http://test"
        ) as client:
            response = await client.get("/.well-known/agent.json")

        assert response.status_code == 200
        assert response.headers["content-type"] == "application/json"

    @pytest.mark.asyncio
    async def test_agent_card_has_a2a_required_fields(self, hotel_app):
        """AgentCard includes A2A-required fields."""
        async with AsyncClient(
            transport=ASGITransport(app=hotel_app), base_url="http://test"
        ) as client:
            response = await client.get("/.well-known/agent.json")

        data = response.json()

        # A2A AgentCard required fields
        assert "name" in data
        assert "description" in data
        assert "url" in data
        assert "capabilities" in data
        assert "skills" in data
        assert "protocolVersions" in data
        assert "1.0" in data["protocolVersions"]

    @pytest.mark.asyncio
    async def test_agent_card_has_provider(self, hotel_app):
        """AgentCard includes provider information."""
        async with AsyncClient(
            transport=ASGITransport(app=hotel_app), base_url="http://test"
        ) as client:
            response = await client.get("/.well-known/agent.json")

        data = response.json()

        assert "provider" in data
        assert "organization" in data["provider"]

    @pytest.mark.asyncio
    async def test_agent_card_skills_have_required_fields(self, hotel_app):
        """AgentCard skills have required fields per A2A spec."""
        async with AsyncClient(
            transport=ASGITransport(app=hotel_app), base_url="http://test"
        ) as client:
            response = await client.get("/.well-known/agent.json")

        data = response.json()

        assert len(data["skills"]) > 0
        for skill in data["skills"]:
            assert "id" in skill
            assert "name" in skill
            assert "description" in skill

    @pytest.mark.asyncio
    async def test_agent_card_has_authentication(self, hotel_app):
        """AgentCard includes authentication configuration."""
        async with AsyncClient(
            transport=ASGITransport(app=hotel_app), base_url="http://test"
        ) as client:
            response = await client.get("/.well-known/agent.json")

        data = response.json()

        assert "authentication" in data
        assert "schemes" in data["authentication"]

    @pytest.mark.asyncio
    async def test_agent_card_has_input_output_modes(self, hotel_app):
        """AgentCard includes input/output modes."""
        async with AsyncClient(
            transport=ASGITransport(app=hotel_app), base_url="http://test"
        ) as client:
            response = await client.get("/.well-known/agent.json")

        data = response.json()

        assert "defaultInputModes" in data
        assert "defaultOutputModes" in data
        assert "text" in data["defaultInputModes"]
        assert "text" in data["defaultOutputModes"]


# ============== A2A JSON-RPC Tests ==============


class TestA2AJsonRpcEndpoint:
    """Test A2A JSON-RPC 2.0 endpoint."""

    @pytest.mark.asyncio
    async def test_send_message_returns_task(
        self, hotel_app, sample_a2a_send_message_request
    ):
        """SendMessage returns a valid task response."""
        async with AsyncClient(
            transport=ASGITransport(app=hotel_app), base_url="http://test"
        ) as client:
            response = await client.post("/", json=sample_a2a_send_message_request)

        assert response.status_code == 200
        data = response.json()

        # JSON-RPC 2.0 response format
        assert data["jsonrpc"] == "2.0"
        assert "result" in data
        assert data["id"] == sample_a2a_send_message_request["id"]

        # Task structure
        task = data["result"]
        assert "id" in task
        assert "status" in task

    @pytest.mark.asyncio
    async def test_send_message_task_has_status(
        self, hotel_app, sample_a2a_send_message_request
    ):
        """SendMessage task includes proper status."""
        async with AsyncClient(
            transport=ASGITransport(app=hotel_app), base_url="http://test"
        ) as client:
            response = await client.post("/", json=sample_a2a_send_message_request)

        data = response.json()
        task = data["result"]
        status = task["status"]

        assert "state" in status
        assert status["state"] == "completed"
        assert "message" in status
        assert "timestamp" in status

    @pytest.mark.asyncio
    async def test_send_message_response_has_agent_message(
        self, hotel_app, sample_a2a_send_message_request
    ):
        """SendMessage response includes agent's message."""
        async with AsyncClient(
            transport=ASGITransport(app=hotel_app), base_url="http://test"
        ) as client:
            response = await client.post("/", json=sample_a2a_send_message_request)

        data = response.json()
        task = data["result"]
        message = task["status"]["message"]

        assert message["role"] == "agent"
        assert "parts" in message
        assert len(message["parts"]) > 0
        assert message["parts"][0]["type"] == "text"
        assert len(message["parts"][0]["text"]) > 0

    @pytest.mark.asyncio
    async def test_send_message_includes_history(
        self, hotel_app, sample_a2a_send_message_request
    ):
        """SendMessage response includes conversation history."""
        async with AsyncClient(
            transport=ASGITransport(app=hotel_app), base_url="http://test"
        ) as client:
            response = await client.post("/", json=sample_a2a_send_message_request)

        data = response.json()
        task = data["result"]

        assert "history" in task
        assert len(task["history"]) >= 2  # User message + agent response

        # First should be user message
        assert task["history"][0]["role"] == "user"
        # Second should be agent response
        assert task["history"][1]["role"] == "agent"

    @pytest.mark.asyncio
    async def test_send_message_empty_text_returns_error(self, hotel_app):
        """SendMessage with empty text returns error."""
        request = {
            "jsonrpc": "2.0",
            "method": "SendMessage",
            "params": {"message": {"role": "user", "parts": []}},
            "id": "test-1",
        }

        async with AsyncClient(
            transport=ASGITransport(app=hotel_app), base_url="http://test"
        ) as client:
            response = await client.post("/", json=request)

        data = response.json()
        assert "error" in data
        assert data["error"]["code"] == -32602

    @pytest.mark.asyncio
    async def test_get_task_returns_task(self, hotel_app, sample_a2a_send_message_request):
        """GetTask returns a previously created task."""
        async with AsyncClient(
            transport=ASGITransport(app=hotel_app), base_url="http://test"
        ) as client:
            # First create a task
            send_response = await client.post("/", json=sample_a2a_send_message_request)
            task_id = send_response.json()["result"]["id"]

            # Then get it
            get_request = {
                "jsonrpc": "2.0",
                "method": "GetTask",
                "params": {"taskId": task_id},
                "id": "get-1",
            }
            response = await client.post("/", json=get_request)

        data = response.json()
        assert "result" in data
        assert data["result"]["id"] == task_id

    @pytest.mark.asyncio
    async def test_get_task_not_found(self, hotel_app):
        """GetTask returns error for non-existent task."""
        request = {
            "jsonrpc": "2.0",
            "method": "GetTask",
            "params": {"taskId": "non-existent-task"},
            "id": "get-1",
        }

        async with AsyncClient(
            transport=ASGITransport(app=hotel_app), base_url="http://test"
        ) as client:
            response = await client.post("/", json=request)

        data = response.json()
        assert "error" in data
        assert data["error"]["code"] == -32001

    @pytest.mark.asyncio
    async def test_cancel_task_success(self, hotel_app, sample_a2a_send_message_request):
        """CancelTask cancels a task."""
        async with AsyncClient(
            transport=ASGITransport(app=hotel_app), base_url="http://test"
        ) as client:
            # First create a task
            send_response = await client.post("/", json=sample_a2a_send_message_request)
            task_id = send_response.json()["result"]["id"]

            # Then cancel it
            cancel_request = {
                "jsonrpc": "2.0",
                "method": "CancelTask",
                "params": {"taskId": task_id},
                "id": "cancel-1",
            }
            response = await client.post("/", json=cancel_request)

        data = response.json()
        assert "result" in data
        assert data["result"]["success"] is True

    @pytest.mark.asyncio
    async def test_unknown_method_returns_error(self, hotel_app):
        """Unknown method returns method not found error."""
        request = {
            "jsonrpc": "2.0",
            "method": "UnknownMethod",
            "params": {},
            "id": "test-1",
        }

        async with AsyncClient(
            transport=ASGITransport(app=hotel_app), base_url="http://test"
        ) as client:
            response = await client.post("/", json=request)

        data = response.json()
        assert "error" in data
        assert data["error"]["code"] == -32601

    @pytest.mark.asyncio
    async def test_invalid_json_returns_parse_error(self, hotel_app):
        """Invalid JSON returns parse error."""
        async with AsyncClient(
            transport=ASGITransport(app=hotel_app), base_url="http://test"
        ) as client:
            response = await client.post(
                "/",
                content="not valid json",
                headers={"Content-Type": "application/json"},
            )

        assert response.status_code == 400
        data = response.json()
        assert "error" in data
        assert data["error"]["code"] == -32700


# ============== Health Endpoint Tests ==============


class TestHealthEndpoint:
    """Test /health endpoint."""

    @pytest.mark.asyncio
    async def test_health_returns_status(self, hotel_app):
        """Health endpoint returns healthy status."""
        async with AsyncClient(
            transport=ASGITransport(app=hotel_app), base_url="http://test"
        ) as client:
            response = await client.get("/health")

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "healthy"
        assert "agent" in data
        assert "protocol" in data


# ============== Schema Conformance Tests ==============


class TestSchemaConformance:
    """Test conformance with LAD-A2A and A2A schemas."""

    @pytest.mark.asyncio
    async def test_discovery_response_schema(self, hotel_app):
        """Discovery response conforms to LAD-A2A schema."""
        async with AsyncClient(
            transport=ASGITransport(app=hotel_app), base_url="http://test"
        ) as client:
            response = await client.get("/.well-known/lad/agents")

        data = response.json()

        # Required top-level fields
        assert isinstance(data.get("version"), str)
        assert isinstance(data.get("agents"), list)

        # Network field structure
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

    @pytest.mark.asyncio
    async def test_agent_card_a2a_schema(self, hotel_app):
        """AgentCard conforms to A2A schema."""
        async with AsyncClient(
            transport=ASGITransport(app=hotel_app), base_url="http://test"
        ) as client:
            response = await client.get("/.well-known/agent.json")

        data = response.json()

        # Required A2A fields
        assert isinstance(data.get("name"), str)
        assert isinstance(data.get("url"), str)
        assert isinstance(data.get("protocolVersions"), list)
        assert isinstance(data.get("capabilities"), dict)
        assert isinstance(data.get("skills"), list)

        # URL should be valid
        assert data["url"].startswith("http://") or data["url"].startswith("https://")

    @pytest.mark.asyncio
    async def test_jsonrpc_response_schema(
        self, hotel_app, sample_a2a_send_message_request
    ):
        """JSON-RPC responses conform to 2.0 spec."""
        async with AsyncClient(
            transport=ASGITransport(app=hotel_app), base_url="http://test"
        ) as client:
            response = await client.post("/", json=sample_a2a_send_message_request)

        data = response.json()

        # JSON-RPC 2.0 required fields
        assert data["jsonrpc"] == "2.0"
        assert "id" in data

        # Must have either result or error
        assert ("result" in data) != ("error" in data)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
