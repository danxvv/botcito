"""Command modules for the Discord bot."""

from commands.music import setup as setup_music
from commands.stats import setup as setup_stats
from commands.recording import setup as setup_recording
from commands.voice import setup as setup_voice
from commands.guide import setup as setup_guide
from commands.discover import setup as setup_discover


def setup_commands(client):
    """Register all command modules with the bot client."""
    setup_music(client)
    setup_stats(client)
    setup_recording(client)
    setup_voice(client)
    setup_guide(client)
    setup_discover(client)
