# -*- coding: utf-8 -*-
"""Test WebSocket real-time price streaming functionality."""

import asyncio
import json
import logging
from unittest.mock import AsyncMock, MagicMock, Mock, patch
from enum import Enum

import pytest
from fastapi.testclient import TestClient
from fastapi import WebSocket

logger = logging.getLogger(__name__)


class WebSocketState(Enum):
    """Mock WebSocket state enum."""
    CONNECTED = "connected"
    DISCONNECTED = "disconnected"


class MockWebSocketState:
    """Mock WebSocket client_state."""
    def __init__(self, state_name):
        self.name = state_name


class TestWebSocketRealtime:
    """Test WebSocket real-time price streaming."""

    def test_safe_send_json_with_connected_websocket(self):
        """Test _safe_send_json with a connected WebSocket."""
        from api.v1.endpoints.portfolio import _safe_send_json

        async def run_test():
            # Create a mock WebSocket
            mock_ws = Mock(spec=WebSocket)
            mock_ws.client_state = MockWebSocketState("connected")
            mock_ws.send_json = AsyncMock()

            # Test successful send
            result = await _safe_send_json(mock_ws, {"type": "test"})
            assert result is True
            mock_ws.send_json.assert_called_once_with({"type": "test"})

        asyncio.run(run_test())

    def test_safe_send_json_with_disconnected_websocket(self):
        """Test _safe_send_json with a disconnected WebSocket."""
        from api.v1.endpoints.portfolio import _safe_send_json

        async def run_test():
            # Create a mock WebSocket that's disconnected
            mock_ws = Mock(spec=WebSocket)
            mock_ws.client_state = MockWebSocketState("disconnected")
            mock_ws.send_json = AsyncMock()

            # Test send to disconnected socket
            result = await _safe_send_json(mock_ws, {"type": "test"})
            assert result is False
            mock_ws.send_json.assert_not_called()

        asyncio.run(run_test())

    def test_safe_send_json_with_send_exception(self):
        """Test _safe_send_json when send_json raises an exception."""
        from api.v1.endpoints.portfolio import _safe_send_json

        async def run_test():
            # Create a mock WebSocket that raises exception
            mock_ws = Mock(spec=WebSocket)
            mock_ws.client_state = MockWebSocketState("connected")
            mock_ws.send_json = AsyncMock(side_effect=Exception("Connection closed"))

            # Test send with exception
            result = await _safe_send_json(mock_ws, {"type": "test"})
            assert result is False

        asyncio.run(run_test())


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
