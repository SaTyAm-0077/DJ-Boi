
import os
import asyncio
from dotenv import load_dotenv

import discord
from discord.commands import option
from discord.ext import commands
import yt_dlp

load_dotenv()
TOKEN = os.getenv("DISCORD_TOKEN")

if not TOKEN:
    raise RuntimeError("DISCORD_TOKEN environment variable is missing.")

intents = discord.Intents.default()
bot = commands.Bot(command_prefix="!", intents=intents)


# YouTube extraction configuration
YDL_OPTIONS = {
    "format": "bestaudio/best",
    "noplaylist": True,
    "quiet": True,
    "no_warnings": False,
    "default_search": "ytsearch",
    "extract_flat": False,
    "remote_components": ["ejs:github"],
}


# Music state per server
class MusicState:
    def __init__(self):
        self.queue = asyncio.Queue()
        self.current = None
        self.now_playing = None
        self.play_next_song = asyncio.Event()
        self.player_task = None

    async def audio_player_task(self, voice_client):
        try:
            while voice_client.is_connected():
                self.play_next_song.clear()

                self.current = await self.queue.get()
                source, title = self.current
                self.now_playing = title

                ffmpeg = discord.FFmpegPCMAudio(
                    source,
                    before_options=(
                        "-reconnect 1 "
                        "-reconnect_streamed 1 "
                        "-reconnect_delay_max 5"
                    ),
                    options="-vn"
                )

                def after_playing(error):
                    if error:
                        print(f"Audio playback error: {error}")

                    bot.loop.call_soon_threadsafe(
                        self.play_next_song.set
                    )

                voice_client.play(
                    ffmpeg,
                    after=after_playing
                )

                await self.play_next_song.wait()

                self.current = None
                self.now_playing = None

        except asyncio.CancelledError:
            raise

        except Exception as error:
            print(f"Player task error: {error}")

        finally:
            self.current = None
            self.now_playing = None


music_states = {}


def get_music_state(guild):
    if guild.id not in music_states:
        music_states[guild.id] = MusicState()

    return music_states[guild.id]


# Run yt-dlp outside the asyncio event loop
def get_audio_source(query):
    with yt_dlp.YoutubeDL(YDL_OPTIONS) as ydl:
        info = ydl.extract_info(query, download=False)

        if not info:
            raise Exception("No results found.")

        if "entries" in info:
            entries = info.get("entries") or []

            if not entries:
                raise Exception("No songs found.")

            info = entries[0]

        audio_url = info.get("url")
        title = info.get("title", "Unknown Title")

        if not audio_url:
            raise Exception("Could not extract audio URL.")

        return audio_url, title


@bot.event
async def on_ready():
    print(f"Bot connected as {bot.user}")
    print("Music bot is ready!")


# JOIN
@bot.slash_command(
    description="Join your current voice channel"
)
async def join(ctx: discord.ApplicationContext):

    await ctx.defer()

    if not ctx.author.voice:
        await ctx.followup.send(
            "You must be in a voice channel!"
        )
        return

    channel = ctx.author.voice.channel

    try:
        if ctx.voice_client:
            await ctx.voice_client.move_to(channel)
        else:
            await channel.connect()

        await ctx.followup.send(
            f"Joined {channel.mention}!"
        )

    except Exception as error:
        print(f"Join error: {error}")

        await ctx.followup.send(
            f"Could not join voice channel: {error}"
        )


# PLAY
@bot.slash_command(
    description="Play music from YouTube or search keywords"
)
@option(
    "query",
    description="YouTube URL or song name"
)
async def play(
    ctx: discord.ApplicationContext,
    query: str
):

    await ctx.defer()

    if not ctx.author.voice:
        await ctx.followup.send(
            "You must be in a voice channel!"
        )
        return

    try:
        voice_client = ctx.voice_client

        if not voice_client:
            channel = ctx.author.voice.channel
            voice_client = await channel.connect()

        elif voice_client.channel != ctx.author.voice.channel:
            await voice_client.move_to(
                ctx.author.voice.channel
            )

        # Extract song information without blocking Discord
        audio_url, title = await asyncio.to_thread(
            get_audio_source,
            query
        )

        state = get_music_state(ctx.guild)

        await state.queue.put((audio_url, title))

        await ctx.followup.send(
            f"Queued: **{title}**"
        )

        # Start only one player task per server
        if (
            state.player_task is None
            or state.player_task.done()
        ):
            state.player_task = asyncio.create_task(
                state.audio_player_task(voice_client)
            )

    except Exception as error:
        print(f"Play error: {error}")

        await ctx.followup.send(
            f"Playback error: {error}"
        )


# QUEUE
@bot.slash_command(
    description="Show the current music queue"
)
async def queue(ctx: discord.ApplicationContext):

    state = get_music_state(ctx.guild)

    songs = list(state.queue._queue)

    if not songs:
        await ctx.respond("The queue is empty.")
        return

    description = "\n".join(
        f"{i}. {title}"
        for i, (_, title) in enumerate(songs, 1)
    )

    await ctx.respond(
        f"**Current Queue:**\n{description}"
    )


# SKIP
@bot.slash_command(
    description="Skip the current song"
)
async def skip(ctx: discord.ApplicationContext):

    voice_client = ctx.voice_client

    if not voice_client or not voice_client.is_playing():
        await ctx.respond(
            "Nothing is playing.",
            ephemeral=True
        )
        return

    voice_client.stop()

    await ctx.respond("Skipped current song.")


# PAUSE
@bot.slash_command(
    description="Pause music"
)
async def pause(ctx: discord.ApplicationContext):

    voice_client = ctx.voice_client

    if not voice_client or not voice_client.is_playing():
        await ctx.respond(
            "Nothing is playing.",
            ephemeral=True
        )
        return

    voice_client.pause()

    await ctx.respond("Paused playback.")


# RESUME
@bot.slash_command(
    description="Resume music"
)
async def resume(ctx: discord.ApplicationContext):

    voice_client = ctx.voice_client

    if not voice_client or not voice_client.is_paused():
        await ctx.respond(
            "Nothing is paused.",
            ephemeral=True
        )
        return

    voice_client.resume()

    await ctx.respond("Resumed playback.")


# STOP
@bot.slash_command(
    description="Stop music and leave the voice channel"
)
async def stop(ctx: discord.ApplicationContext):

    state = get_music_state(ctx.guild)
    voice_client = ctx.voice_client

    # Clear queue without replacing its object
    while not state.queue.empty():
        try:
            state.queue.get_nowait()
        except asyncio.QueueEmpty:
            break

    if state.player_task and not state.player_task.done():
        state.player_task.cancel()

    if voice_client:
        await voice_client.disconnect()

        await ctx.respond(
            "Stopped and left the voice channel. Queue cleared."
        )
    else:
        await ctx.respond(
            "I'm not connected to a voice channel.",
            ephemeral=True
        )


# CLEAR QUEUE
@bot.slash_command(
    description="Clear the music queue"
)
async def clear(ctx: discord.ApplicationContext):

    state = get_music_state(ctx.guild)

    while not state.queue.empty():
        try:
            state.queue.get_nowait()
        except asyncio.QueueEmpty:
            break

    await ctx.respond("Queue cleared.")


# NOW PLAYING
@bot.slash_command(
    description="Show the currently playing song"
)
async def nowplaying(ctx: discord.ApplicationContext):

    state = get_music_state(ctx.guild)

    if state.now_playing:
        await ctx.respond(
            f"**Now Playing:** {state.now_playing}"
        )
    else:
        await ctx.respond(
            "Nothing is playing right now."
        )


bot.run(TOKEN)
