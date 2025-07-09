import os
import asyncio
from dotenv import load_dotenv
import discord
from discord.commands import option
from discord.ext import commands
import yt_dlp

load_dotenv()
TOKEN = os.getenv("DISCORD_TOKEN")

intents = discord.Intents.default()
bot = commands.Bot(command_prefix="!", intents=intents)

# Music state per guild
class MusicState:
    def __init__(self):
        self.queue = asyncio.Queue()
        self.current = None
        self.play_next_song = asyncio.Event()
        self.now_playing = None

    async def audio_player_task(self, voice_client):
        while True:
            self.play_next_song.clear()
            self.current = await self.queue.get()
            source, title = self.current
            self.now_playing = title
            ffmpeg_opts = {
                "before_options": "-reconnect 1 -reconnect_streamed 1 -reconnect_delay_max 5",
                "options": "-vn"
            }
            voice_client.play(
                discord.FFmpegPCMAudio(source, before_options=ffmpeg_opts["before_options"], options=ffmpeg_opts["options"]),
                after=lambda e: bot.loop.call_soon_threadsafe(self.play_next_song.set)
            )
            await self.play_next_song.wait()

music_states = {}

def get_music_state(guild):
    if guild.id not in music_states:
        music_states[guild.id] = MusicState()
    return music_states[guild.id]

def get_audio_source(query):
    ydl_opts = {
        "format": "bestaudio",
        "noplaylist": True,
        "quiet": True,
        "default_search": "ytsearch",
        "extract_flat": False,
    }
    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        info = ydl.extract_info(query, download=False)
        if "entries" in info:
            info = info["entries"][0]
        return info["url"], info.get("title", "Unknown Title")

@bot.event
async def on_ready():
    print(f"Bot connected as {bot.user}")

@bot.slash_command(description="Bot joins your current voice channel")
async def join(ctx: discord.ApplicationContext):
    if ctx.author.voice:
        channel = ctx.author.voice.channel
        if ctx.voice_client:
            await ctx.voice_client.move_to(channel)
        else:
            await channel.connect()
        await ctx.respond(f"Joined {channel.mention}!")
    else:
        await ctx.respond("You must be in a voice channel!", ephemeral=True)

@bot.slash_command(description="Play music from a YouTube URL or search term (adds to queue)")
@option("query", description="YouTube URL or search keywords")
async def play(ctx: discord.ApplicationContext, query: str):
    await ctx.defer()
    if not ctx.author.voice:
        await ctx.respond("You must be in a voice channel!", ephemeral=True)
        return

    voice_client = ctx.voice_client
    if not voice_client:
        channel = ctx.author.voice.channel
        voice_client = await channel.connect()
    elif voice_client.channel != ctx.author.voice.channel:
        await voice_client.move_to(ctx.author.voice.channel)

    state = get_music_state(ctx.guild)
    try:
        audio_url, title = get_audio_source(query)
    except Exception as e:
        await ctx.respond(f"Failed to get audio: {e}")
        return

    await state.queue.put((audio_url, title))
    await ctx.respond(f"Queued: **{title}**")

    if not hasattr(voice_client, "audio_player_task") or getattr(voice_client, "audio_player_task", None) is None or voice_client.audio_player_task.done():
        async def player_task():
            await state.audio_player_task(voice_client)
        voice_client.audio_player_task = bot.loop.create_task(player_task())

@bot.slash_command(description="Show the current queue")
async def queue(ctx: discord.ApplicationContext):
    state = get_music_state(ctx.guild)
    if state.queue.empty():
        await ctx.respond("The queue is empty.")
        return
    queue_list = list(state.queue._queue)
    desc = ""
    for i, (_, title) in enumerate(queue_list, 1):
        desc += f"{i}. {title}\n"
    await ctx.respond(f"**Current Queue:**\n{desc}")

@bot.slash_command(description="Skip the current song")
async def skip(ctx: discord.ApplicationContext):
    voice_client = ctx.voice_client
    if not voice_client or not voice_client.is_playing():
        await ctx.respond("Nothing is playing.", ephemeral=True)
        return
    voice_client.stop()
    await ctx.respond("Skipped current song.")

@bot.slash_command(description="Pause music")
async def pause(ctx: discord.ApplicationContext):
    voice_client = ctx.voice_client
    if not voice_client or not voice_client.is_playing():
        await ctx.respond("Nothing is playing.", ephemeral=True)
        return
    voice_client.pause()
    await ctx.respond("Paused playback.")

@bot.slash_command(description="Resume music")
async def resume(ctx: discord.ApplicationContext):
    voice_client = ctx.voice_client
    if not voice_client or not voice_client.is_paused():
        await ctx.respond("Nothing is paused.", ephemeral=True)
        return
    voice_client.resume()
    await ctx.respond("Resumed playback.")

@bot.slash_command(description="Stop and leave the voice channel; also clears the queue")
async def stop(ctx: discord.ApplicationContext):
    voice_client = ctx.voice_client
    state = get_music_state(ctx.guild)
    state.queue = asyncio.Queue()  # clear queue
    if voice_client:
        await voice_client.disconnect()
        await ctx.respond("Stopped and left the voice channel. Queue cleared.")
    else:
        await ctx.respond("I'm not connected to a voice channel.", ephemeral=True)

@bot.slash_command(description="Clear the queue")
async def clear(ctx: discord.ApplicationContext):
    state = get_music_state(ctx.guild)
    state.queue = asyncio.Queue()
    await ctx.respond("Queue cleared.")

@bot.slash_command(description="Show the currently playing song")
async def nowplaying(ctx: discord.ApplicationContext):
    state = get_music_state(ctx.guild)
    if state.now_playing:
        await ctx.respond(f"**Now Playing:** {state.now_playing}")
    else:
        await ctx.respond("Nothing is playing right now.")

bot.run(TOKEN)