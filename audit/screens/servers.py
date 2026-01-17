"""Servers overview screen."""

from textual.app import ComposeResult
from textual.screen import Screen
from textual.widgets import DataTable, Header, Footer, Static
from textual.containers import Container
from textual import work

from ..database import get_guild_command_count, get_guild_song_count


class ServersScreen(Screen):
    """Screen showing all servers the bot is in."""

    BINDINGS = [
        ("enter", "view_details", "View Details"),
        ("r", "refresh", "Refresh"),
    ]

    def compose(self) -> ComposeResult:
        yield Header()
        yield Container(
            Static("Servers Overview", id="title", classes="screen-title"),
            Static("Loading...", id="stats"),
            DataTable(id="servers-table", cursor_type="row", zebra_stripes=True),
            id="main-container",
        )
        yield Footer()

    def on_mount(self) -> None:
        """Set up table and load data."""
        table = self.query_one("#servers-table", DataTable)
        table.add_column("Server ID", key="id", width=20)
        table.add_column("Name", key="name", width=30)
        table.add_column("Members", key="members", width=10)
        table.add_column("Commands (24h)", key="commands", width=15)
        table.add_column("Songs (24h)", key="songs", width=12)
        self.load_servers()

    @work()
    async def load_servers(self) -> None:
        """Load server data in background."""
        table = self.query_one("#servers-table", DataTable)
        stats = self.query_one("#stats", Static)
        table.clear()

        # Get guilds from the Discord client stored in app
        guilds = self.app.guilds

        if not guilds:
            stats.update("No servers found. Bot may not be connected.")
            return

        for guild in guilds:
            cmd_count = get_guild_command_count(guild["id"])
            song_count = get_guild_song_count(guild["id"])

            table.add_row(
                str(guild["id"]),
                guild["name"][:28] + ".." if len(guild["name"]) > 28 else guild["name"],
                str(guild["member_count"]),
                str(cmd_count),
                str(song_count),
                key=str(guild["id"]),
            )

        stats.update(f"Total: {len(guilds)} servers")

    def action_view_details(self) -> None:
        """Navigate to server details."""
        table = self.query_one("#servers-table", DataTable)
        if table.cursor_row is not None and table.row_count > 0:
            row_key, _ = table.coordinate_to_cell_key(table.cursor_coordinate)
            guild_id = int(row_key.value)
            self.app.push_screen("users", {"guild_id": guild_id})

    def action_refresh(self) -> None:
        """Refresh the data."""
        self.load_servers()
