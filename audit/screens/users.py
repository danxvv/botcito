"""Users and commands screen."""

from textual.app import ComposeResult
from textual.screen import Screen
from textual.widgets import DataTable, Header, Footer, Static, TabbedContent, TabPane
from textual.containers import Container
from textual import work

from ..database import (
    get_command_stats_by_guild,
    get_command_stats_by_user,
    get_recent_commands,
    get_user_song_count,
)


class UsersScreen(Screen):
    """Screen showing command usage by users."""

    BINDINGS = [
        ("escape", "go_back", "Back"),
        ("r", "refresh", "Refresh"),
    ]

    def __init__(self, guild_id: int | None = None, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.guild_id = guild_id

    def compose(self) -> ComposeResult:
        title = f"Command Usage - Guild: {self.guild_id}" if self.guild_id else "Command Usage - All Servers"
        yield Header()
        with Container(id="main-container"):
            yield Static(title, id="title", classes="screen-title")
            with TabbedContent():
                with TabPane("By Command", id="tab-commands"):
                    yield DataTable(id="commands-table", cursor_type="row", zebra_stripes=True)
                with TabPane("By User", id="tab-users"):
                    yield DataTable(id="users-table", cursor_type="row", zebra_stripes=True)
                with TabPane("Recent", id="tab-recent"):
                    yield DataTable(id="recent-table", cursor_type="row", zebra_stripes=True)
        yield Footer()

    def on_mount(self) -> None:
        """Set up tables."""
        # Commands table
        cmd_table = self.query_one("#commands-table", DataTable)
        cmd_table.add_column("Command", width=15)
        cmd_table.add_column("Total Uses", width=12)
        cmd_table.add_column("Success Rate", width=12)
        cmd_table.add_column("Last Used", width=20)

        # Users table
        user_table = self.query_one("#users-table", DataTable)
        user_table.add_column("User", width=25)
        user_table.add_column("Commands", width=12)
        user_table.add_column("Songs", width=10)
        user_table.add_column("Last Active", width=20)

        # Recent table
        recent_table = self.query_one("#recent-table", DataTable)
        recent_table.add_column("Time", width=18)
        recent_table.add_column("Server", width=18)
        recent_table.add_column("User", width=18)
        recent_table.add_column("Command", width=12)
        recent_table.add_column("Status", width=8)

        self.load_data()

    @work()
    async def load_data(self) -> None:
        """Load command statistics."""
        # Load commands by command name
        cmd_table = self.query_one("#commands-table", DataTable)
        cmd_table.clear()
        cmd_stats = get_command_stats_by_guild(self.guild_id)
        for stat in cmd_stats:
            success_rate = (stat["success_count"] / stat["count"] * 100) if stat["count"] > 0 else 0
            last_used = stat["last_used"][:16] if stat["last_used"] else "Never"
            cmd_table.add_row(
                stat["command_name"],
                str(stat["count"]),
                f"{success_rate:.0f}%",
                last_used,
            )

        # Load by user
        user_table = self.query_one("#users-table", DataTable)
        user_table.clear()
        user_stats = get_command_stats_by_user(self.guild_id)
        for stat in user_stats:
            song_count = get_user_song_count(stat["user_id"], self.guild_id)
            last_active = stat["last_active"][:16] if stat["last_active"] else "Never"
            user_name = stat["user_name"] or str(stat["user_id"])
            if len(user_name) > 23:
                user_name = user_name[:20] + "..."
            user_table.add_row(
                user_name,
                str(stat["command_count"]),
                str(song_count),
                last_active,
            )

        # Load recent
        recent_table = self.query_one("#recent-table", DataTable)
        recent_table.clear()
        recent = get_recent_commands(self.guild_id, limit=50)
        for log in recent:
            timestamp = log["timestamp"][:16] if log["timestamp"] else ""
            guild_name = log["guild_name"] or "Unknown"
            if len(guild_name) > 16:
                guild_name = guild_name[:13] + "..."
            user_name = log["user_name"] or "Unknown"
            if len(user_name) > 16:
                user_name = user_name[:13] + "..."
            status = "OK" if log["success"] else "FAIL"
            recent_table.add_row(
                timestamp,
                guild_name,
                user_name,
                log["command_name"],
                status,
            )

    def action_go_back(self) -> None:
        """Return to previous screen or servers mode if at base."""
        if len(self.app.screen_stack) > 1:
            self.app.pop_screen()
        else:
            # At base of mode stack, switch to servers mode
            self.app.switch_mode("servers")

    def action_refresh(self) -> None:
        """Refresh the data."""
        self.load_data()
