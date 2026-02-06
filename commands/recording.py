"""Recording commands: record, stoprecord."""

import discord
from audit.logger import log_command
from music_player import player_manager

from commands.helpers import ensure_voice


def setup(client):
    @client.tree.command(name="record", description="Start recording voice channel audio")
    @log_command
    async def record(interaction: discord.Interaction):
        """Start recording audio from the voice channel."""
        if not await ensure_voice(interaction):
            return

        guild_id = interaction.guild_id

        # Check if already recording
        if player_manager.is_recording(guild_id):
            await interaction.response.send_message(
                "Already recording! Use `/stoprecord` to stop.", ephemeral=True
            )
            return

        # Connect to voice channel if not already connected
        channel = interaction.user.voice.channel
        await player_manager.connect(guild_id, channel)

        # Start recording
        session = await player_manager.start_recording(guild_id, interaction.user.id)

        if session:
            await interaction.response.send_message(
                f"Recording started. Use `/stoprecord` to save the recording.\n"
                f"Session ID: `{session.session_id}`"
            )
        else:
            await interaction.response.send_message(
                "Failed to start recording. Make sure the bot is in a voice channel.",
                ephemeral=True,
            )

    @client.tree.command(name="stoprecord", description="Stop recording and save audio files")
    @log_command
    async def stoprecord(interaction: discord.Interaction):
        """Stop recording and save audio files."""
        guild_id = interaction.guild_id

        if not player_manager.is_recording(guild_id):
            await interaction.response.send_message(
                "Not currently recording. Use `/record` to start.", ephemeral=True
            )
            return

        await interaction.response.defer()

        # Stop recording and save files
        stats = await player_manager.stop_recording(guild_id)

        if not stats:
            await interaction.followup.send("Failed to stop recording.")
            return

        if stats["user_count"] == 0:
            await interaction.followup.send(
                "Recording stopped. No audio was captured.\n"
                f"Session ID: `{stats['session_id']}`"
            )
            return

        # Build response message
        lines = [
            f"Recording saved!",
            f"Session ID: `{stats['session_id']}`",
            f"Duration: {stats['total_seconds']:.1f}s",
            f"Users recorded: {stats['user_count']}",
            f"Output: `{stats['output_dir']}`",
            "",
            "**Files:**",
        ]

        for user_id, user_info in stats["users"].items():
            filepath = stats["saved_files"].get(user_id, "N/A")
            lines.append(f"- {user_info['name']}: {user_info['seconds']:.1f}s")

        await interaction.followup.send("\n".join(lines))
