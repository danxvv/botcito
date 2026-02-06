"""LLM/guide slash commands (/model, /guide) and TTS voice helpers."""

import asyncio
import os
import time

import discord
from discord import app_commands

from audit.logger import log_command
from commands.helpers import ensure_voice, get_tts_error_message, get_tts_footer_status
from music_player import player_manager


def _truncate_for_tts(text: str, max_chars: int = 2000) -> str:
    """Truncate text for TTS at a sentence boundary."""
    if len(text) <= max_chars:
        return text

    truncate_at = max_chars
    for punct in [". ", "! ", "? ", "\n"]:
        last_pos = text[:max_chars].rfind(punct)
        if last_pos > max_chars // 2:
            truncate_at = last_pos + 1
            break
    return text[:truncate_at].strip()


async def _rewrite_for_voice(text: str, api_key: str) -> str:
    """
    Rewrite text into a natural conversational style for voice output.

    Uses MiniMax M2-her via OpenRouter to transform structured/markdown
    text into something that sounds natural when spoken aloud.

    Args:
        text: The raw guide response text (already truncated)
        api_key: OpenRouter API key

    Returns:
        Rewritten text optimised for TTS, or the original text on failure
    """
    import httpx

    prompt = (
        "Reescribe el siguiente texto para que suene natural al ser hablado en voz alta "
        "por un motor de s\u00edntesis de voz (TTS). "
        "Hazlo conversacional, c\u00e1lido y f\u00e1cil de seguir al o\u00eddo.\n\n"
        "Reglas de formato para TTS:\n"
        "- Usa oraciones cortas y claras, de m\u00e1ximo 200 caracteres cada una.\n"
        "- Usa puntuaci\u00f3n clara: puntos, comas, signos de exclamaci\u00f3n e interrogaci\u00f3n "
        "para guiar el tono y las pausas naturales.\n"
        "- Usa comas para crear pausas de respiraci\u00f3n entre ideas.\n"
        "- Escribe todos los n\u00fameros con letras (por ejemplo, 'quinientos' en vez de '500').\n"
        "- Escribe las abreviaturas completas (por ejemplo, 'por ejemplo' en vez de 'ej.', "
        "'puntos de vida' en vez de 'HP').\n"
        "- Elimina cualquier markdown, vi\u00f1etas, listas numeradas, URLs, bloques de c\u00f3digo "
        "o formato especial.\n"
        "- No uses par\u00e9ntesis, corchetes ni caracteres especiales.\n"
        "- Transmite la emoci\u00f3n y el tono con las palabras mismas, ya que el TTS adapta "
        "su entonaci\u00f3n seg\u00fan el significado del texto.\n"
        "- Conserva toda la informaci\u00f3n importante pero pres\u00e9ntala como si fueras "
        "un amigo experto explic\u00e1ndolo en una llamada de voz.\n"
        "- S\u00e9 conciso, apunta a un resumen hablado, no una transcripci\u00f3n del original.\n"
        "- NO agregues ning\u00fan pre\u00e1mbulo como '\u00a1Claro!' o 'Aqu\u00ed tienes'.\n"
        "- Solo escribe la versi\u00f3n hablada reescrita.\n\n"
        f"Texto original:\n{text}"
    )

    try:
        async with httpx.AsyncClient(timeout=30.0) as http:
            resp = await http.post(
                "https://openrouter.ai/api/v1/chat/completions",
                headers={
                    "Authorization": f"Bearer {api_key}",
                    "Content-Type": "application/json",
                },
                json={
                    "model": "minimax/minimax-m2-her",
                    "messages": [
                        {
                            "role": "system",
                            "content": (
                                "Eres una asistente de voz amigable que reescribe "
                                "texto para ser hablado en voz alta por un motor "
                                "de s\u00edntesis de voz Qwen3-TTS. "
                                "Tu salida se env\u00eda directamente al TTS, as\u00ed que "
                                "escribe exactamente lo que se debe decir. "
                                "Usa oraciones cortas con puntuaci\u00f3n clara para "
                                "guiar la prosodia. Usa comas para pausas naturales. "
                                "Escribe n\u00fameros con letras y abreviaturas completas. "
                                "Sin markdown, sin caracteres especiales, sin "
                                "acotaciones ni direcciones de escena. "
                                "Responde siempre en espa\u00f1ol."
                            ),
                        },
                        {"role": "user", "content": prompt},
                    ],
                    "max_tokens": 1024,
                },
            )
            resp.raise_for_status()
            data = resp.json()
            rewritten = data["choices"][0]["message"]["content"].strip()
            return rewritten if rewritten else text
    except Exception:
        # On any failure, fall back to the original text
        return text


async def _speak_guide_response(
    client,
    interaction: discord.Interaction,
    voice_channel,
    full_response: str,
    embed: discord.Embed,
    message,
):
    """Speak the guide response via TTS."""
    guild_id = interaction.guild_id
    tts_text = _truncate_for_tts(full_response)

    try:
        await player_manager.connect(guild_id, voice_channel)
        voice_conv = client.get_voice_conversation()

        # Rewrite for natural voice delivery via MiniMax M2-her
        embed.set_footer(text="Powered by Agno + Exa | Preparing voice...")
        await message.edit(embed=embed)

        api_key = os.getenv("OPENROUTER_API_KEY", "")
        if api_key:
            tts_text = await _rewrite_for_voice(tts_text, api_key)
            print(tts_text)

        embed.set_footer(text="Powered by Agno + Exa | Speaking...")
        await message.edit(embed=embed)

        await voice_conv.speak_text(guild_id, tts_text)

        embed.set_footer(text="Powered by Agno + Exa | Spoken")
        await message.edit(embed=embed)
    except Exception as e:
        status = get_tts_footer_status(e)
        embed.set_footer(text=f"Powered by Agno + Exa | {status}")
        await message.edit(embed=embed)


def setup(client):
    """Register LLM/guide commands on the client."""

    @client.tree.command(name="model", description="Change the AI model for /guide command")
    @app_commands.describe(model="The LLM model to use")
    @app_commands.choices(model=[
        app_commands.Choice(name="OpenAI GPT-5.2", value="openai/gpt-5.2"),
        app_commands.Choice(name="xAI Grok 4.1 Fast", value="x-ai/grok-4.1-fast"),
        app_commands.Choice(name="Google Gemini 3 Pro", value="google/gemini-3-pro-preview"),
        app_commands.Choice(name="Anthropic Claude Sonnet 4.5", value="anthropic/claude-sonnet-4.5"),
        app_commands.Choice(name="Anthropic Claude Haiku 4.5", value="anthropic/claude-haiku-4.5"),
        app_commands.Choice(name="Google Gemini 3 Flash", value="google/gemini-3-flash-preview"),
        app_commands.Choice(name="MiniMax: MiniMax M2-her", value="minimax/minimax-m2-her"),
    ])
    @log_command
    async def model(interaction: discord.Interaction, model: app_commands.Choice[str]):
        """Change the LLM model used by the /guide command."""
        from settings import set_llm_model, get_llm_model

        if set_llm_model(model.value):
            await interaction.response.send_message(f"Model changed to **{model.name}**")
        else:
            current = get_llm_model()
            await interaction.response.send_message(
                f"Invalid model. Current model: **{current}**",
                ephemeral=True
            )

    @client.tree.command(name="guide", description="Get help with video games using AI")
    @app_commands.guild_only()
    @app_commands.describe(
        question="Your gaming question (tips, strategies, builds, etc.)",
        voice="Enable voice output (default: off)"
    )
    @log_command
    async def guide(interaction: discord.Interaction, question: str, voice: bool | None = None):
        """Answer gaming questions using AI with web search."""
        # Check if user is in voice channel
        user_in_voice = interaction.user.voice is not None
        voice_channel = interaction.user.voice.channel if user_in_voice else None

        # Handle explicit voice=True when not in voice channel
        if voice is True and not user_in_voice:
            await interaction.response.send_message(
                "You need to be in a voice channel to use voice output!",
                ephemeral=True,
            )
            return

        await interaction.response.defer()

        guild_id = interaction.guild_id
        user_id = interaction.user.id

        # Create initial embed
        embed = discord.Embed(
            title=question[:256],  # Discord title limit
            description="Searching for answers...",
            color=discord.Color.blue(),
        )
        embed.set_footer(text="Powered by GameGuide Team")

        message = await interaction.followup.send(embed=embed)

        try:
            agent = client.get_game_agent()
        except ValueError as e:
            embed.description = f"Configuration error: {e}"
            embed.color = discord.Color.red()
            await message.edit(embed=embed)
            return

        # Voice output only if explicitly enabled
        should_speak = voice is True

        try:
            response_chunks: list[str] = []
            last_update = time.monotonic()

            async for chunk in agent.ask(guild_id, user_id, question):
                response_chunks.append(chunk)

                # Update embed at most once per second to avoid rate limits
                if time.monotonic() - last_update >= 1.0:
                    embed.description = "".join(response_chunks)[:4000]  # Discord embed limit
                    embed.color = discord.Color.gold()
                    await message.edit(embed=embed)
                    last_update = time.monotonic()

            # Final update with complete response
            full_response = "".join(response_chunks)
            embed.description = full_response[:4000] if full_response else "No response generated."
            embed.color = discord.Color.green()
            await message.edit(embed=embed)

            # Speak response if voice output is enabled
            if should_speak and full_response.strip():
                await _speak_guide_response(client, interaction, voice_channel, full_response, embed, message)

        except (TimeoutError, asyncio.TimeoutError):
            embed.description = "Request timed out. Please try again."
            embed.color = discord.Color.red()
            await message.edit(embed=embed)
        except Exception as e:
            embed.description = f"Error: {str(e)[:500]}"
            embed.color = discord.Color.red()
            await message.edit(embed=embed)
