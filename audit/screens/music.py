"""Music playback history screen."""

from textual.app import ComposeResult
from textual.screen import Screen
from textual.widgets import DataTable, Header, Footer, Static, Input
from textual.containers import Container, Horizontal
from textual import work

from ..database import get_music_history


def format_duration(seconds: int) -> str:
    """Format seconds as MM:SS or HH:MM:SS."""
    if seconds <= 0:
        return "Live"
    minutes, secs = divmod(seconds, 60)
    hours, minutes = divmod(minutes, 60)
    if hours:
        return f"{hours}:{minutes:02d}:{secs:02d}"
    return f"{minutes}:{secs:02d}"


class MusicScreen(Screen):
    """Screen showing music playback history."""

    BINDINGS = [
        ("escape", "go_back", "Back"),
        ("/", "focus_search", "Search"),
        ("r", "refresh", "Refresh"),
    ]

    def __init__(self, guild_id: int | None = None, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.guild_id = guild_id
        self.search_term = ""

    def compose(self) -> ComposeResult:
        yield Header()
        yield Container(
            Static("Music Playback History", id="title", classes="screen-title"),
            Horizontal(
                Input(placeholder="Search songs or users... (press /)", id="search"),
                Static("Total: 0 songs", id="stats"),
                id="toolbar",
            ),
            DataTable(id="music-table", cursor_type="row", zebra_stripes=True),
            id="main-container",
        )
        yield Footer()

    def on_mount(self) -> None:
        """Set up table columns."""
        table = self.query_one("#music-table", DataTable)
        table.add_column("Time", width=16)
        table.add_column("Server", width=16)
        table.add_column("User", width=16)
        table.add_column("Title", width=35)
        table.add_column("Duration", width=8)
        table.add_column("Action", width=6)
        self.load_music_history()

    @work()
    async def load_music_history(self) -> None:
        """Load music history data."""
        table = self.query_one("#music-table", DataTable)
        stats = self.query_one("#stats", Static)
        table.clear()

        history = get_music_history(
            guild_id=self.guild_id,
            search=self.search_term if self.search_term else None,
            limit=200,
        )

        for log in history:
            timestamp = log["timestamp"][:16] if log["timestamp"] else ""
            guild_name = log["guild_name"] or "Unknown"
            if len(guild_name) > 14:
                guild_name = guild_name[:11] + "..."
            user_name = log["user_name"] or "Unknown"
            if len(user_name) > 14:
                user_name = user_name[:11] + "..."
            title = log["title"] or "Unknown"
            if len(title) > 33:
                title = title[:30] + "..."
            duration = format_duration(log["duration"] or 0)

            table.add_row(
                timestamp,
                guild_name,
                user_name,
                title,
                duration,
                log["action"] or "?",
            )

        stats.update(f"Total: {len(history)} songs")

    def on_input_submitted(self, event: Input.Submitted) -> None:
        """Handle search input."""
        if event.input.id == "search":
            self.search_term = event.value
            self.load_music_history()

    def action_focus_search(self) -> None:
        """Focus the search input."""
        search = self.query_one("#search", Input)
        search.focus()

    def action_go_back(self) -> None:
        """Return to previous screen or servers mode if at base."""
        if len(self.app.screen_stack) > 1:
            self.app.pop_screen()
        else:
            # At base of mode stack, switch to servers mode
            self.app.switch_mode("servers")

    def action_refresh(self) -> None:
        """Refresh the data."""
        self.load_music_history()
