
import os
import asyncio
import shlex

from dotenv import load_dotenv
import discord
from discord.ext import commands
import yt_dlp

# --------------------------------------------------
# CONFIGURATION
# --------------------------------------------------

load_dotenv()

TOKEN = os.getenv("DISCORD_TOKEN")

if not TOKEN:
    raise RuntimeError("DISCORD_TOKEN is missing from environment variables.")

intents = discord.Intents.default()
bot = commands.Bot(command_prefix="!", intents=intents)

YDL_OPTIONS = {
    "format": "bestaudio/best",
    "noplaylist": True,
    "quiet": True,
    "no_warnings": True,
    "default_search": "ytsearch",
    "extract_flat": False,
    "remote_components": ["ejs:github"],
}

FFMPEG_BEFORE_OPTIONS = (
    "-reconnect 1 "
    "-reconnect_streamed 1 "
    "-reconnect_delay_max 5"
)


# --------------------------------------------------
# YOUTUBE EXTRACTION
# --------------------------------------------------

def get_audio_source(query):
    """
    Extracts the audio URL, title and HTTP headers
    required by YouTube for playback.
    """

    with yt_dlp.YoutubeDL(YDL_OPTIONS) as ydl:
        info = ydl.extract_info(query, download=False)

        if "entries" in info:
            entries = info["entries"]

            if not entries:
                raise Exception("No search results found.")

            info = entries[0]

        if not info or not info.get("url"):
            raise Exception("Could not extract audio URL.")

        return (
            info["url"],
            info.get("title", "Unknown Title"),
            info.get("http_headers", {})
        )


# --------------------------------------------------
# MUSIC STATE
# --------------------------------------------------

class MusicState:

    def __init__(self):
        self.queue = asyncio.Queue()
        self.current = None
        self.now_playing = None
        self.play_next_song = asyncio.Event()
        self.player_task = None

    async def audio_player_task(self, voice_client):

        while True:

            self.play_next_song.clear()

            try:
                self.current = await self.queue.get()

            except asyncio.CancelledError:
                break

            if not voice_client or not voice_client.is_connected():
                self.current = None
                self.now_playing = None
                break

            source, title, headers = self.current
            self.now_playing = title

            header_string = "".join(
                f"{key}: {value}\r\n"
                for key, value in headers.items()
            )

            before_options = FFMPEG_BEFORE_OPTIONS

            if header_string:
                before_options += (
                    " -headers "
                    + shlex.quote(header_string)
                )

            try:

                audio_source = discord.FFmpegPCMAudio(
                    source,
                    before_options=before_options,
                    options="-vn"
                )

                loop = asyncio.get_running_loop()

                def after_playing(error):

                    if error:
                        print(f"Playback error: {error}")

                    try:
                        loop.call_soon_threadsafe(
                            self.play_next_song.set
                        )
                    except RuntimeError:
                        pass

                voice_client.play(
                    audio_source,
                    after=after_playing
                )

                await self.play_next_song.wait()

            except asyncio.CancelledError:
                break

            except Exception as error:
                print(f"Audio player error: {error}")

            self.current = None
            self.now_playing = None

        self.current = None
        self.now_playing = None


# One music state per Discord server
music_states = {}


def get_music_state(guild_id):

    if guild_id not in music_states:
        music_states[guild_id] = MusicState()

    return music_states[guild_id]


# --------------------------------------------------
# BOT EVENTS
# --------------------------------------------------

@bot.event
async def on_ready():

    print(f"Bot connected as {bot.user}")
    print("Music bot is ready!")


# --------------------------------------------------
# JOIN COMMAND
# --------------------------------------------------

@bot.slash_command(
    name="join",
    description="Join your voice channel."
)
async def join(ctx):

    await ctx.defer()

    if not ctx.author.voice:
        await ctx.followup.send(
            "You need to be in a voice channel first.",
            ephemeral=True
        )
        return

    channel = ctx.author.voice.channel

    try:

        if ctx.voice_client:

            await ctx.voice_client.move_to(channel)

        else:

            await channel.connect()

        await ctx.followup.send(
            f"Joined **{channel.name}**."
        )

    except Exception as error:

        print(f"Join error: {error}")

        await ctx.followup.send(
            f"Could not join the voice channel: {error}",
            ephemeral=True
        )


# --------------------------------------------------
# PLAY COMMAND
# --------------------------------------------------

@bot.slash_command(
    name="play",
    description="Play a song from YouTube."
)
async def play(
    ctx,
    query: discord.Option(
        str,
        description="Song name or YouTube URL"
    )
):

    await ctx.defer()

    if not ctx.author.voice:
        await ctx.followup.send(
            "Join a voice channel before playing music.",
            ephemeral=True
        )
        return

    channel = ctx.author.voice.channel

    try:

        voice_client = ctx.voice_client

        if voice_client:

            if voice_client.channel != channel:
                await voice_client.move_to(channel)

        else:

            voice_client = await channel.connect()

    except Exception as error:

        print(f"Voice connection error: {error}")

        await ctx.followup.send(
            f"Could not connect to your voice channel: {error}",
            ephemeral=True
        )
        return

    try:

        audio_url, title, headers = await asyncio.to_thread(
            get_audio_source,
            query
        )

    except Exception as error:

        print(f"YouTube extraction error: {error}")

        await ctx.followup.send(
            f"Could not find or load that song: {error}",
            ephemeral=True
        )
        return

    state = get_music_state(ctx.guild.id)

    await state.queue.put(
        (audio_url, title, headers)
    )

    if state.player_task is None or state.player_task.done():

        state.player_task = asyncio.create_task(
            state.audio_player_task(voice_client)
        )

    await ctx.followup.send(
        f"Added **{title}** to the queue."
    )


# --------------------------------------------------
# QUEUE COMMAND
# --------------------------------------------------

@bot.slash_command(
    name="queue",
    description="Show the music queue."
)
async def queue(ctx):

    state = get_music_state(ctx.guild.id)

    upcoming = list(state.queue._queue)

    if not state.now_playing and not upcoming:

        await ctx.respond("The queue is empty.")
        return

    message = ""

    if state.now_playing:

        message += (
            f"**Now playing:** {state.now_playing}\n\n"
        )

    if upcoming:

        message += "**Up next:**\n"

        for index, song in enumerate(upcoming, start=1):

            _, title, _ = song

            message += f"`{index}.` {title}\n"

    else:

        message += "No more songs in the queue."

    await ctx.respond(message[:1900])


# --------------------------------------------------
# SKIP COMMAND
# --------------------------------------------------

@bot.slash_command(
    name="skip",
    description="Skip the current song."
)
async def skip(ctx):

    voice_client = ctx.voice_client

    if not voice_client or not voice_client.is_playing():

        await ctx.respond(
            "Nothing is currently playing.",
            ephemeral=True
        )
        return

    voice_client.stop()

    await ctx.respond("Skipped the current song.")


# --------------------------------------------------
# PAUSE COMMAND
# --------------------------------------------------

@bot.slash_command(
    name="pause",
    description="Pause the current song."
)
async def pause(ctx):

    voice_client = ctx.voice_client

    if voice_client and voice_client.is_playing():

        voice_client.pause()

        await ctx.respond("Music paused.")

    else:

        await ctx.respond(
            "Nothing is currently playing.",
            ephemeral=True
        )


# --------------------------------------------------
# RESUME COMMAND
# --------------------------------------------------

@bot.slash_command(
    name="resume",
    description="Resume the paused song."
)
async def resume(ctx):

    voice_client = ctx.voice_client

    if voice_client and voice_client.is_paused():

        voice_client.resume()

        await ctx.respond("Music resumed.")

    else:

        await ctx.respond(
            "Music is not paused.",
            ephemeral=True
        )


# --------------------------------------------------
# STOP COMMAND
# --------------------------------------------------

@bot.slash_command(
    name="stop",
    description="Stop music and disconnect."
)
async def stop(ctx):

    voice_client = ctx.voice_client

    state = get_music_state(ctx.guild.id)

    # Empty the queue
    while not state.queue.empty():

        try:
            state.queue.get_nowait()
            state.queue.task_done()
        except asyncio.QueueEmpty:
            break

    # Stop current playback
    if voice_client and voice_client.is_playing():

        voice_client.stop()

    # Cancel the player task
    if state.player_task and not state.player_task.done():

        state.player_task.cancel()

        try:
            await state.player_task
        except asyncio.CancelledError:
            pass

    state.player_task = None
    state.current = None
    state.now_playing = None

    # Disconnect
    if voice_client:

        await voice_client.disconnect()

    await ctx.respond("Music stopped and queue cleared.")


# --------------------------------------------------
# CLEAR COMMAND
# --------------------------------------------------

@bot.slash_command(
    name="clear",
    description="Clear the upcoming music queue."
)
async def clear(ctx):

    state = get_music_state(ctx.guild.id)

    while not state.queue.empty():

        try:
            state.queue.get_nowait()
            state.queue.task_done()
        except asyncio.QueueEmpty:
            break

    await ctx.respond("The queue has been cleared.")


# --------------------------------------------------
# NOW PLAYING COMMAND
# --------------------------------------------------

@bot.slash_command(
    name="nowplaying",
    description="Show the currently playing song."
)
async def nowplaying(ctx):

    state = get_music_state(ctx.guild.id)

    if state.now_playing:

        await ctx.respond(
            f"**Now playing:** {state.now_playing}"
        )

    else:

        await ctx.respond(
            "Nothing is currently playing.",
            ephemeral=True
        )


# --------------------------------------------------
# RUN BOT
# --------------------------------------------------

bot.run(TOKEN)
