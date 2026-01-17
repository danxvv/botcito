"""Integration tests for game agent flow."""

import os
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

# Try to import agno to check compatibility
try:
    from agno.db.sqlite import SqliteDb
    AGNO_COMPATIBLE = True
except (TypeError, AssertionError, ImportError):
    AGNO_COMPATIBLE = False


pytestmark = pytest.mark.skipif(
    not AGNO_COMPATIBLE,
    reason="agno library has Python version compatibility issues"
)


class TestGameAgentFlow:
    """Integration tests for complete game agent flow."""

    @pytest.fixture
    def mock_environment(self):
        """Mock environment with valid API keys."""
        return {
            "EXA_API_KEY": "test-exa-api-key",
            "OPENROUTER_API_KEY": "test-openrouter-api-key",
        }

    @pytest.mark.asyncio
    async def test_complete_ask_flow(self, mock_environment):
        """Test complete flow from question to response."""
        with patch.dict(os.environ, mock_environment, clear=True):
            with patch("game_agent.agent.SqliteDb") as mock_db:
                with patch("game_agent.agent.MCPConnection") as mock_mcp_conn:
                    with patch("game_agent.agent.create_game_agent") as mock_create_agent:
                        # Setup mock response chunks
                        mock_event1 = MagicMock()
                        mock_event1.content = "Here is the strategy: "
                        mock_event2 = MagicMock()
                        mock_event2.content = "Attack the weak point."

                        async def mock_arun(*args, **kwargs):
                            yield mock_event1
                            yield mock_event2

                        mock_agent = MagicMock()
                        mock_agent.arun = mock_arun
                        mock_create_agent.return_value = mock_agent

                        mock_mcp_conn.return_value.__aenter__ = AsyncMock(return_value=MagicMock())
                        mock_mcp_conn.return_value.__aexit__ = AsyncMock(return_value=None)

                        from game_agent.agent import GameAgent

                        agent = GameAgent()

                        # Collect response chunks
                        chunks = []
                        async for chunk in agent.ask(111, 222, "How to beat boss?"):
                            chunks.append(chunk)

                        assert len(chunks) == 2
                        assert "".join(chunks) == "Here is the strategy: Attack the weak point."

    @pytest.mark.asyncio
    async def test_ask_simple_returns_complete_response(self, mock_environment):
        """Test ask_simple returns complete response as string."""
        with patch.dict(os.environ, mock_environment, clear=True):
            with patch("game_agent.agent.SqliteDb"):
                with patch("game_agent.agent.MCPConnection") as mock_mcp_conn:
                    with patch("game_agent.agent.create_game_agent") as mock_create_agent:
                        mock_event = MagicMock()
                        mock_event.content = "Complete answer here."

                        async def mock_arun(*args, **kwargs):
                            yield mock_event

                        mock_agent = MagicMock()
                        mock_agent.arun = mock_arun
                        mock_create_agent.return_value = mock_agent

                        mock_mcp_conn.return_value.__aenter__ = AsyncMock(return_value=MagicMock())
                        mock_mcp_conn.return_value.__aexit__ = AsyncMock(return_value=None)

                        from game_agent.agent import GameAgent

                        agent = GameAgent()
                        result = await agent.ask_simple(111, 222, "Question?")

                        assert result == "Complete answer here."

    @pytest.mark.asyncio
    async def test_different_users_get_different_sessions(self, mock_environment):
        """Test different users get isolated sessions."""
        with patch.dict(os.environ, mock_environment, clear=True):
            with patch("game_agent.agent.SqliteDb"):
                with patch("game_agent.agent.MCPConnection") as mock_mcp_conn:
                    with patch("game_agent.agent.create_game_agent") as mock_create_agent:
                        with patch("game_agent.agent.create_session_context") as mock_session:
                            mock_event = MagicMock()
                            mock_event.content = "Response"

                            async def mock_arun(*args, **kwargs):
                                yield mock_event

                            mock_agent = MagicMock()
                            mock_agent.arun = mock_arun
                            mock_create_agent.return_value = mock_agent

                            mock_mcp_conn.return_value.__aenter__ = AsyncMock(return_value=MagicMock())
                            mock_mcp_conn.return_value.__aexit__ = AsyncMock(return_value=None)

                            mock_session.return_value = MagicMock(
                                user_id_str="user1",
                                session_id="guild_user1",
                            )

                            from game_agent.agent import GameAgent

                            agent = GameAgent()

                            # User 1 asks
                            async for _ in agent.ask(111, 100, "Q1"):
                                pass

                            # User 2 asks
                            mock_session.return_value = MagicMock(
                                user_id_str="user2",
                                session_id="guild_user2",
                            )
                            async for _ in agent.ask(111, 200, "Q2"):
                                pass

                            # Verify different sessions were created
                            calls = mock_session.call_args_list
                            assert len(calls) == 2
                            assert calls[0][0] == (111, 100)
                            assert calls[1][0] == (111, 200)


class TestEnvironmentValidation:
    """Integration tests for environment validation."""

    def test_missing_keys_raises_error(self):
        """Test missing API keys raises proper error."""
        with patch.dict(os.environ, {}, clear=True):
            with pytest.raises(Exception) as exc_info:
                from game_agent.agent import GameAgent

                GameAgent()

            assert "EXA_API_KEY" in str(exc_info.value) or "OPENROUTER_API_KEY" in str(exc_info.value)

    def test_partial_keys_raises_error(self):
        """Test partial API keys raises error with missing key name."""
        with patch.dict(os.environ, {"EXA_API_KEY": "test"}, clear=True):
            with pytest.raises(Exception) as exc_info:
                from game_agent.agent import GameAgent

                GameAgent()

            assert "OPENROUTER_API_KEY" in str(exc_info.value)
