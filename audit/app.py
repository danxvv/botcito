"""Main Textual application for Discord bot audit."""

import asyncio
from pathlib import Path

import discord
from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.widgets import Header, Footer, Static, LoadingIndicator
from textual.containers import Container

from .screens.servers import ServersScreen
from .screens.users import UsersScreen
from .screens.music import MusicScreen
from .database import init_db, get_total_stats


class AuditApp(App):
    """Discord Bot Audit TUI Application."""

    CSS_PATH = Path(__file__).parent / "styles.tcss"
    TITLE = "Discord Bot Audit"

    BINDINGS = [
        Binding("1", "show_servers", "Servers", show=True),
        Binding("2", "show_commands", "Commands", show=True),
        Binding("3", "show_music", "Music", show=True),
        Binding("r", "refresh", "Refresh", show=True),
        Binding("q", "quit", "Quit", show=True),
    ]

    MODES = {
        "servers": "servers",
        "users": "users",
        "music": "music",
    }

    def __init__(self, discord_token: str):
        super().__init__()
        self.discord_token = discord_token
        self.guilds: list[dict] = []
        self._connected = False

    def compose(self) -> ComposeResult:
        yield Header()
        yield Container(
            Static("Connecting to Discord...", id="status"),
            LoadingIndicator(id="loading"),
            id="loading-container",
        )
        yield Footer()

    async def on_mount(self) -> None:
        """Initialize database and connect to Discord."""
        init_db()
        self.run_worker(self.connect_discord())

    async def connect_discord(self) -> None:
        """Connect to Discord and fetch guild list."""
        status = self.query_one("#status", Static)
        status.update("Connecting to Discord API...")

        try:
            # Create a minimal Discord client just to fetch guild info
            intents = discord.Intents.default()
            client = discord.Client(intents=intents)

            @client.event
            async def on_ready():
                self.guilds = [
                    {
                        "id": g.id,
                        "name": g.name,
                        "member_count": g.member_count or 0,
                    }
                    for g in client.guilds
                ]
                await client.close()

            # Run the client with a timeout
            try:
                await asyncio.wait_for(
                    client.start(self.discord_token),
                    timeout=30.0,
                )
            except asyncio.TimeoutError:
                status.update("Connection timed out. Showing cached data...")
            except discord.LoginFailure:
                status.update("Invalid Discord token. Check your .env file.")
                return

        except Exception as e:
            status.update(f"Error: {e}")
            return

        self._connected = True
        # Remove loading screen and show servers
        loading = self.query_one("#loading-container", Container)
        loading.remove()

        # Show summary stats
        stats = get_total_stats()
        self.sub_title = (
            f"{len(self.guilds)} servers | "
            f"{stats['total_commands']} commands | "
            f"{stats['total_songs']} songs logged"
        )

        # Install and switch to servers mode
        self.install_screen(ServersScreen(), name="servers")
        self.install_screen(UsersScreen(), name="users")
        self.install_screen(MusicScreen(), name="music")
        self.switch_mode("servers")

    def action_show_servers(self) -> None:
        """Show servers screen."""
        if self._connected:
            self.switch_mode("servers")

    def action_show_commands(self) -> None:
        """Show commands screen."""
        if self._connected:
            self.switch_mode("users")

    def action_show_music(self) -> None:
        """Show music screen."""
        if self._connected:
            self.switch_mode("music")

    def action_refresh(self) -> None:
        """Refresh current screen data."""
        if hasattr(self.screen, "action_refresh"):
            self.screen.action_refresh()

    def push_screen(self, screen_name: str, params: dict | None = None) -> None:
        """Push a screen with optional parameters."""
        if params and screen_name == "users":
            # Create a new instance with the guild_id
            self.install_screen(
                UsersScreen(guild_id=params.get("guild_id")),
                name=f"users_{params.get('guild_id')}",
            )
            super().push_screen(f"users_{params.get('guild_id')}")
        else:
            super().push_screen(screen_name)
