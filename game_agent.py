"""
Game help agent using Agno with Exa MCP for web search.

This module provides backward compatibility by re-exporting from the
game_agent package. For new code, import directly from the package:

    from game_agent import GameAgent

The module also exports AGENT_INSTRUCTIONS for backward compatibility.
"""

from game_agent import AGENT_INSTRUCTIONS, GameAgent

__all__ = ["GameAgent", "AGENT_INSTRUCTIONS"]
