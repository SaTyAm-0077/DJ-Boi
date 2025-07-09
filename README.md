# DJ Boi Discord Music Bot

DJ Boi is a powerful and simple Discord music bot built with [py-cord](https://github.com/Pycord-Development/pycord) and [yt-dlp](https://github.com/yt-dlp/yt-dlp). It supports YouTube search/streaming, queue management, skipping, pause/resume, and more — all with modern Discord slash commands.

## Features

- Slash commands for all actions
- Join/leave voice channels
- Play music from YouTube links or search terms
- Song queue with display and clear options
- Skip, pause, and resume playback
- Shows currently playing track
- Per-server queue management

## Add DJ Boi to Your Server (Hosted Bot)

Want to use the bot without self-hosting?  
You can add the official, 24/7 online DJ Boi bot to your server:

**[👉 Click here to invite DJ Boi to your Discord server!](https://discord.com/oauth2/authorize?client_id=1392166254021836882&permissions=3147776&scope=bot%20applications.commands)**

## Setup

### 1. Install requirements

Make sure you’re running Python 3.7+
(Also note that Python 13+ is **NOT** supported due to audioop not included in Python 13 and above.)

Then run this command in Command Prompt / Terminal
```bash
pip install -r requirements.txt
```

You also need [ffmpeg](https://ffmpeg.org/) installed and available in your system PATH.

### 2. Create a Discord Bot

- Go to the [Discord Developer Portal](https://discord.com/developers/applications)
- Create a new application and add a bot user
- Copy the bot token

### 3. Set up your `.env`

Create a `.env` file in the project root:

```
DISCORD_TOKEN=YOUR_BOT_TOKEN_HERE
```

### 4. Run the bot

```bash
python main.py
```

## Usage

Invite the bot to your server with the correct permissions (View Channels, Connect, Speak, and Use Slash Commands).

### Slash Commands

- `/join` — Join your current voice channel
- `/play <query or url>` — Play a YouTube song or search and queue it
- `/queue` — Show the current queue
- `/skip` — Skip the current song
- `/pause` — Pause playback
- `/resume` — Resume playback
- `/stop` — Stop and leave the channel (clears the queue)
- `/clear` — Clear the queue
- `/nowplaying` — Show the currently playing song

## Notes

- Volume control is not live—users adjust playback volume through their Discord client.
- Only one queue per server/guild is supported.

## Contributing

Pull requests and suggestions are welcome! Please open an issue first for any major changes.

## License

MIT