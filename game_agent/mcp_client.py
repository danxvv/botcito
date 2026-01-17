"""MCP tools connection management using async context manager pattern."""

import asyncio
import logging
from types import TracebackType

from agno.tools.mcp import MCPTools

logger = logging.getLogger(__name__)

from .config import (
    EXA_MCP_BASE_URL,
    EXA_MCP_TOOLS,
    EXA_MCP_TRANSPORT,
    MCP_CONNECT_TIMEOUT_SECONDS,
)


def build_exa_mcp_url(api_key: str) -> str:
    """
    Build the Exa MCP URL with API key and enabled tools.

    Args:
        api_key: The Exa API key

    Returns:
        Fully constructed MCP URL with query parameters
    """
    tools_param = ",".join(EXA_MCP_TOOLS)
    return f"{EXA_MCP_BASE_URL}?exaApiKey={api_key}&tools={tools_param}"


class MCPConnection:
    """
    Async context manager for MCP tools connection.

    Handles connection lifecycle with proper timeout and cleanup.

    Usage:
        async with MCPConnection(api_key) as mcp_tools:
            # Use mcp_tools here
            pass
    """

    def __init__(self, exa_api_key: str) -> None:
        """
        Initialize the MCP connection manager.

        Args:
            exa_api_key: The Exa API key for authentication
        """
        self._exa_api_key = exa_api_key
        self._mcp_tools: MCPTools | None = None

    def __repr__(self) -> str:
        """Return string representation with masked API key."""
        return "MCPConnection(exa_api_key='***')"

    async def __aenter__(self) -> MCPTools:
        """Connect to MCP and return the tools instance."""
        url = build_exa_mcp_url(self._exa_api_key)

        self._mcp_tools = MCPTools(
            transport=EXA_MCP_TRANSPORT,
            url=url,
        )

        await asyncio.wait_for(
            self._mcp_tools.connect(),
            timeout=MCP_CONNECT_TIMEOUT_SECONDS,
        )

        return self._mcp_tools

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: TracebackType | None,
    ) -> None:
        """Close the MCP connection."""
        if self._mcp_tools is not None:
            try:
                await self._mcp_tools.close()
            except Exception as e:
                # Log but don't mask the original exception
                logger.warning("Error closing MCP connection: %s", e)
            finally:
                self._mcp_tools = None
