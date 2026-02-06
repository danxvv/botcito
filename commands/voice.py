"""Voice/TTS slash commands (/talk, /stoptalk, /speak)."""

import discord
from discord import app_commands

from audit.logger import log_command
from commands.helpers import ensure_voice, get_tts_error_message
from music_player import player_manager


def setup(client):
    """Register voice/TTS commands on the client."""

    @client.tree.command(name="talk", description="Start voice conversation mode - bot listens and responds")
    @log_command
    async def talk(interaction: discord.Interaction):
        """Start voice conversation mode."""
        if not await ensure_voice(interaction):
            return

        guild_id = interaction.guild_id

        try:
            voice_conv = client.get_voice_conversation()
        except ValueError as e:
            await interaction.response.send_message(
                f"Configuration error: {e}", ephemeral=True
            )
            return

        # Check if already in talk mode
        if voice_conv.is_active(guild_id):
            await interaction.response.send_message(
                "Already in voice conversation mode! Use `/stoptalk` to stop.",
                ephemeral=True,
            )
            return

        # Connect to voice channel if not already connected
        channel = interaction.user.voice.channel
        voice_client = await player_manager.connect(guild_id, channel)

        # Start voice conversation
        try:
            await voice_conv.start(guild_id, voice_client)
            tts_status = "" if voice_conv.tts_available else "\n*Note: TTS not configured - responses will be logged to console only.*"
            await interaction.response.send_message(
                "Voice conversation started! I'm now listening. "
                "Speak naturally and I'll respond after you pause.\n"
                f"Use `/stoptalk` to end the conversation.{tts_status}"
            )
        except ValueError as e:
            await interaction.response.send_message(
                f"Failed to start voice conversation: {e}", ephemeral=True
            )

    @client.tree.command(name="stoptalk", description="Stop voice conversation mode")
    @log_command
    async def stoptalk(interaction: discord.Interaction):
        """Stop voice conversation mode."""
        guild_id = interaction.guild_id

        try:
            voice_conv = client.get_voice_conversation()
        except ValueError as e:
            await interaction.response.send_message(
                f"Configuration error: {e}", ephemeral=True
            )
            return

        if not voice_conv.is_active(guild_id):
            await interaction.response.send_message(
                "Not in voice conversation mode. Use `/talk` to start.",
                ephemeral=True,
            )
            return

        voice_conv.stop(guild_id)
        await interaction.response.send_message("Voice conversation ended.")

    @client.tree.command(name="speak", description="Make the bot speak text aloud")
    @app_commands.describe(text="The text for the bot to speak", language="Language for TTS")
    @app_commands.choices(language=[
        app_commands.Choice(name="Spanish", value="es"),
        app_commands.Choice(name="English", value="en"),
        app_commands.Choice(name="French", value="fr"),
        app_commands.Choice(name="German", value="de"),
        app_commands.Choice(name="Italian", value="it"),
        app_commands.Choice(name="Portuguese", value="pt"),
        app_commands.Choice(name="Polish", value="pl"),
        app_commands.Choice(name="Turkish", value="tr"),
        app_commands.Choice(name="Russian", value="ru"),
        app_commands.Choice(name="Dutch", value="nl"),
        app_commands.Choice(name="Czech", value="cs"),
        app_commands.Choice(name="Arabic", value="ar"),
        app_commands.Choice(name="Chinese", value="zh"),
        app_commands.Choice(name="Japanese", value="ja"),
        app_commands.Choice(name="Hungarian", value="hu"),
        app_commands.Choice(name="Korean", value="ko"),
    ])
    @log_command
    async def speak(
        interaction: discord.Interaction,
        text: str,
        language: app_commands.Choice[str] | None = None,
    ):
        """Make the bot speak text using TTS."""
        if not await ensure_voice(interaction):
            return

        guild_id = interaction.guild_id
        await interaction.response.defer()

        try:
            voice_conv = client.get_voice_conversation()
        except ValueError as e:
            await interaction.followup.send(f"Configuration error: {e}")
            return

        # Connect to voice channel if not already connected
        channel = interaction.user.voice.channel
        await player_manager.connect(guild_id, channel)

        # Get language value if provided
        lang = language.value if language else None

        # Speak the text
        try:
            success = await voice_conv.speak_text(guild_id, text, language=lang)
            if success:
                lang_display = f" ({language.name})" if language else ""
                truncated = f"{text[:100]}..." if len(text) > 100 else text
                await interaction.followup.send(f"Speaking{lang_display}: *{truncated}*")
            else:
                await interaction.followup.send("Failed to speak. Bot may not be in a voice channel.")
        except Exception as e:
            await interaction.followup.send(get_tts_error_message(e))
