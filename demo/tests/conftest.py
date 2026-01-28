"""
Shared pytest fixtures for demo tests.
"""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch
import sys
from pathlib import Path

# Add demo directory to path
demo_dir = Path(__file__).parent.parent
sys.path.insert(0, str(demo_dir))


@pytest.fixture
def mock_openai_response():
    """Mock OpenAI chat completion response."""
    mock_response = MagicMock()
    mock_response.choices = [MagicMock()]
    mock_response.choices[0].message.content = "This is a test response from the AI."
    return mock_response


@pytest.fixture
def mock_openai_client(mock_openai_response):
    """Mock AsyncOpenAI client."""
    mock_client = AsyncMock()
    mock_client.chat.completions.create = AsyncMock(return_value=mock_openai_response)
    return mock_client


@pytest.fixture
def sample_a2a_send_message_request():
    """Sample A2A SendMessage JSON-RPC request."""
    return {
        "jsonrpc": "2.0",
        "method": "SendMessage",
        "params": {
            "message": {
                "role": "user",
                "parts": [{"type": "text", "text": "What time is checkout?"}],
                "messageId": "test-msg-123"
            }
        },
        "id": "test-request-1"
    }


@pytest.fixture
def sample_a2a_get_task_request():
    """Sample A2A GetTask JSON-RPC request."""
    return {
        "jsonrpc": "2.0",
        "method": "GetTask",
        "params": {"taskId": "test-task-123"},
        "id": "test-request-2"
    }


@pytest.fixture
def sample_a2a_cancel_task_request():
    """Sample A2A CancelTask JSON-RPC request."""
    return {
        "jsonrpc": "2.0",
        "method": "CancelTask",
        "params": {"taskId": "test-task-123"},
        "id": "test-request-3"
    }
