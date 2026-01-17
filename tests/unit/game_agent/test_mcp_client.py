"""Unit tests for game_agent/mcp_client.py - MCP connection management.

Note: These tests are skipped if agno has Python version compatibility issues.
"""

import asyncio
import sys
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

# Try to import agno to check compatibility
try:
    from agno.tools.mcp import MCPTools
    AGNO_COMPATIBLE = True
except (TypeError, AssertionError, ImportError):
    AGNO_COMPATIBLE = False


pytestmark = pytest.mark.skipif(
    not AGNO_COMPATIBLE,
    reason="agno library has Python version compatibility issues"
)


# Only import if agno is compatible
if AGNO_COMPATIBLE:
    from game_agent.mcp_client import MCPConnection, build_exa_mcp_url
else:
    # Define dummy classes to prevent NameError during collection
    MCPConnection = None
    build_exa_mcp_url = None


class TestBuildExaMcpUrl:
    """Tests for build_exa_mcp_url function."""

    def test_includes_api_key(self):
        """Test URL includes API key as query parameter."""
        url = build_exa_mcp_url("test-api-key-123")

        assert "exaApiKey=test-api-key-123" in url

    def test_includes_tools_param(self):
        """Test URL includes tools parameter."""
        url = build_exa_mcp_url("key")

        assert "tools=" in url

    def test_url_format(self):
        """Test URL has correct base and query structure."""
        url = build_exa_mcp_url("key")

        assert url.startswith("https://")
        assert "?" in url
        assert "&" in url  # Multiple params


class TestMCPConnectionInit:
    """Tests for MCPConnection initialization."""

    def test_init_stores_api_key(self):
        """Test init stores API key."""
        conn = MCPConnection("test-key")

        assert conn._exa_api_key == "test-key"
        assert conn._mcp_tools is None

    def test_repr_masks_api_key(self):
        """Test repr doesn't expose API key."""
        conn = MCPConnection("super-secret-key-12345")

        repr_str = repr(conn)

        assert "super-secret-key" not in repr_str
        assert "***" in repr_str


class TestMCPConnectionContextManager:
    """Tests for MCPConnection async context manager."""

    @pytest.mark.asyncio
    async def test_aenter_returns_mcp_tools(self):
        """Test __aenter__ returns MCPTools instance."""
        mock_tools = MagicMock()
        mock_tools.connect = AsyncMock()

        with patch("game_agent.mcp_client.MCPTools", return_value=mock_tools):
            conn = MCPConnection("test-key")

            async with conn as tools:
                assert tools is mock_tools
                mock_tools.connect.assert_called_once()

    @pytest.mark.asyncio
    async def test_aenter_creates_mcp_tools_with_correct_params(self):
        """Test MCPTools created with correct URL and transport."""
        mock_tools = MagicMock()
        mock_tools.connect = AsyncMock()

        with patch("game_agent.mcp_client.MCPTools", return_value=mock_tools) as mock_mcp_class:
            conn = MCPConnection("my-api-key")

            async with conn:
                # Check MCPTools was called with correct params
                call_kwargs = mock_mcp_class.call_args[1]
                assert "url" in call_kwargs
                assert "my-api-key" in call_kwargs["url"]
                assert "transport" in call_kwargs

    @pytest.mark.asyncio
    async def test_aexit_closes_connection(self):
        """Test __aexit__ closes the MCP connection."""
        mock_tools = MagicMock()
        mock_tools.connect = AsyncMock()
        mock_tools.close = AsyncMock()

        with patch("game_agent.mcp_client.MCPTools", return_value=mock_tools):
            conn = MCPConnection("test-key")

            async with conn:
                pass

            mock_tools.close.assert_called_once()

    @pytest.mark.asyncio
    async def test_aexit_clears_mcp_tools_reference(self):
        """Test __aexit__ sets _mcp_tools to None."""
        mock_tools = MagicMock()
        mock_tools.connect = AsyncMock()
        mock_tools.close = AsyncMock()

        with patch("game_agent.mcp_client.MCPTools", return_value=mock_tools):
            conn = MCPConnection("test-key")

            async with conn:
                assert conn._mcp_tools is not None

            assert conn._mcp_tools is None

    @pytest.mark.asyncio
    async def test_aexit_handles_close_error(self):
        """Test __aexit__ handles errors during close gracefully."""
        mock_tools = MagicMock()
        mock_tools.connect = AsyncMock()
        mock_tools.close = AsyncMock(side_effect=Exception("Close failed"))

        with patch("game_agent.mcp_client.MCPTools", return_value=mock_tools):
            conn = MCPConnection("test-key")

            # Should not raise - error is logged but swallowed
            async with conn:
                pass

            # _mcp_tools should still be cleared
            assert conn._mcp_tools is None

    @pytest.mark.asyncio
    async def test_aexit_preserves_exception(self):
        """Test __aexit__ doesn't mask exceptions from within context."""
        mock_tools = MagicMock()
        mock_tools.connect = AsyncMock()
        mock_tools.close = AsyncMock()

        with patch("game_agent.mcp_client.MCPTools", return_value=mock_tools):
            conn = MCPConnection("test-key")

            with pytest.raises(ValueError, match="test error"):
                async with conn:
                    raise ValueError("test error")
