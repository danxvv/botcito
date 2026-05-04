"""Command modules for the Discord bot."""

from commands.music import setup as setup_music
from commands.stats import setup as setup_stats
from commands.recording import setup as setup_recording


def setup_commands(client):
    """Register all command modules with the bot client."""
    setup_music(client)
    setup_stats(client)
    setup_recording(client)
