import asyncio
import time
import traceback
import discord
from discord.ext import commands
import yt_dlp

from config import Config
from db.mongo import get_track
from presets.tracks import get_preset, describe_preset, match_trigger, match_oneshot, get_mood

_YTDL_BASE: dict = {
    'format': 'bestaudio[ext=webm]/bestaudio[ext=m4a]/bestaudio/best',
    'quiet': True,
    'no_warnings': True,
    'default_search': 'auto',
    'source_address': '0.0.0.0',
}
if Config.YTDLP_COOKIES:
    _YTDL_BASE['cookiefile'] = Config.YTDLP_COOKIES

# Each entry is a list of YouTube player clients tried in order.
# If one chain raises an error the next is attempted.
_CLIENT_CHAINS = [
    ['tv_embedded', 'ios'],
    ['mweb', 'android_testsuite'],
    ['web_creator', 'mediaconnect'],
]

FFMPEG_OPTIONS = {
    'before_options': '-reconnect 1 -reconnect_streamed 1 -reconnect_delay_max 5',
    'options': '-vn',
}

active_sessions: dict[int, dict] = {}

DELETE_AFTER = 5
TRIGGER_COOLDOWN = 30  # seconds between automatic track switches per guild

_last_trigger: dict[int, float] = {}


async def _reply(ctx: commands.Context, content: str):
    reply = await ctx.send(content)
    await asyncio.sleep(DELETE_AFTER)
    try:
        await ctx.message.delete()
        await reply.delete()
    except discord.NotFound:
        pass


def _extract_stream_url(url: str) -> dict:
    last_exc: Exception | None = None
    for clients in _CLIENT_CHAINS:
        opts = {
            **_YTDL_BASE,
            'extractor_args': {'youtube': {'player_client': clients}},
        }
        try:
            with yt_dlp.YoutubeDL(opts) as ydl:
                info = ydl.extract_info(url, download=False)
                if 'entries' in info:
                    info = info['entries'][0]
                return {
                    'stream_url': info['url'],
                    'title':      info.get('title', 'Unknown'),
                }
        except Exception as exc:
            last_exc = exc
            continue
    raise last_exc


class Music(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @commands.command(name='play')
    async def play(self, ctx: commands.Context):
        if not ctx.author.voice:
            asyncio.create_task(_reply(ctx, 'You need to be in a voice channel first.'))
            return

        voice_channel = ctx.author.voice.channel

        url = await get_track(ctx.channel.id)
        if url:
            label = f'the assigned track for **#{ctx.channel.name}**'
        else:
            url = get_preset(ctx.channel.name)
            vibe = describe_preset(ctx.channel.name)
            label = f'**{vibe}** preset for **#{ctx.channel.name}**'

        asyncio.create_task(_reply(ctx, f'Joining **{voice_channel.name}** · Loading {label}...'))

        if ctx.voice_client:
            await ctx.voice_client.move_to(voice_channel)
            vc = ctx.voice_client
        else:
            vc = await voice_channel.connect()

        if vc.is_playing():
            vc.stop()

        active_sessions[ctx.guild.id] = {
            'stopped':         False,
            'url':             url,
            'ambient_url':     url,
            'oneshot':         False,
            'interrupted':     False,
            'title':           None,
            'text_channel_id': ctx.channel.id,
            'vc':              vc,
            'volume':          0.4,
        }

        await self._start_playback(ctx.guild.id)

    async def _start_playback(self, guild_id: int):
        session = active_sessions.get(guild_id)
        if not session or session['stopped']:
            return

        vc: discord.VoiceClient = session['vc']
        url: str = session['url']

        try:
            loop = asyncio.get_event_loop()
            data = await loop.run_in_executor(None, _extract_stream_url, url)
            session['title'] = data['title']

            raw_source = discord.FFmpegPCMAudio(data['stream_url'], **FFMPEG_OPTIONS)
            source = discord.PCMVolumeTransformer(raw_source, volume=session['volume'])

            def after_play(error):
                if error:
                    print(f'[AmbientBot] Playback error: {error}')
                s = active_sessions.get(guild_id)
                if not s or s['stopped']:
                    return
                if s.get('interrupted'):
                    # Stopped externally — play whatever url is now set (oneshot or mood)
                    s['interrupted'] = False
                elif s.get('oneshot'):
                    # Oneshot finished naturally — restore ambient
                    s['oneshot'] = False
                    s['url'] = s['ambient_url']
                asyncio.run_coroutine_threadsafe(
                    self._start_playback(guild_id), self.bot.loop
                )

            vc.play(source, after=after_play)

        except Exception as exc:
            full_error = traceback.format_exc()
            print(f'[AmbientBot] Stream extraction error:\n{full_error}')
            text_channel = self.bot.get_channel(session.get('text_channel_id'))
            if text_channel:
                short = str(exc) or type(exc).__name__
                await text_channel.send(f'Could not load audio: `{short}`')

    @commands.command(name='leave')
    async def leave(self, ctx: commands.Context):
        session = active_sessions.pop(ctx.guild.id, None)
        if session:
            session['stopped'] = True
        _last_trigger.pop(ctx.guild.id, None)

        if ctx.voice_client:
            ctx.voice_client.stop()
            await ctx.voice_client.disconnect()
            asyncio.create_task(_reply(ctx, 'Left the voice channel. The ambience fades...'))
        else:
            asyncio.create_task(_reply(ctx, "I'm not in a voice channel."))

    @commands.command(name='volume')
    async def volume(self, ctx: commands.Context, vol: int):
        if not 0 <= vol <= 100:
            asyncio.create_task(_reply(ctx, 'Volume must be between 0 and 100.'))
            return
        session = active_sessions.get(ctx.guild.id)
        if not session:
            asyncio.create_task(_reply(ctx, 'Nothing is playing right now.'))
            return
        session['volume'] = vol / 100
        if ctx.voice_client and ctx.voice_client.source:
            ctx.voice_client.source.volume = vol / 100
        asyncio.create_task(_reply(ctx, f'Volume set to **{vol}%**.'))

    async def _play_mood(self, ctx: commands.Context, mood_name: str, label: str):
        if not ctx.author.voice:
            asyncio.create_task(_reply(ctx, 'You need to be in a voice channel first.'))
            return
        session = active_sessions.get(ctx.guild.id)
        if not session:
            asyncio.create_task(_reply(ctx, 'Start music first with `--play`.'))
            return
        url = get_mood(mood_name)
        if not url:
            asyncio.create_task(_reply(ctx, f'No track configured for `{mood_name}` in presets.json.'))
            return
        session['url'] = url
        session['ambient_url'] = url
        session['oneshot'] = False
        session['interrupted'] = True
        session['vc'].stop()
        asyncio.create_task(_reply(ctx, label))

    @commands.command(name='battle')
    async def battle(self, ctx: commands.Context):
        await self._play_mood(ctx, 'battle', '⚔️ Battle music!')

    @commands.command(name='switch')
    async def switch(self, ctx: commands.Context):
        session = active_sessions.get(ctx.guild.id)
        if not session:
            asyncio.create_task(_reply(ctx, 'Nothing is playing. Use `--play` first.'))
            return

        url = await get_track(ctx.channel.id)
        if url:
            label = f'the assigned track for **#{ctx.channel.name}**'
        else:
            url = get_preset(ctx.channel.name)
            vibe = describe_preset(ctx.channel.name)
            label = f'**{vibe}** preset for **#{ctx.channel.name}**'

        session['text_channel_id'] = ctx.channel.id
        session['url'] = url
        session['ambient_url'] = url
        session['oneshot'] = False
        session['interrupted'] = True
        _last_trigger.pop(ctx.guild.id, None)
        session['vc'].stop()

        asyncio.create_task(_reply(ctx, f'Switched to **#{ctx.channel.name}** · Loading {label}...'))

    @commands.command(name='nowplaying')
    async def nowplaying(self, ctx: commands.Context):
        session = active_sessions.get(ctx.guild.id)
        if not session:
            asyncio.create_task(_reply(ctx, 'Nothing is playing right now.'))
            return
        title = session.get('title') or session['url']
        asyncio.create_task(_reply(ctx, f'Now playing: **{title}**\n{session["url"]}'))

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        if message.author.bot or message.content.startswith('--'):
            return
        if not message.guild:
            return

        session = active_sessions.get(message.guild.id)
        if not session or session.get('text_channel_id') != message.channel.id:
            return

        content = message.content

        now = time.monotonic()
        if now - _last_trigger.get(message.guild.id, 0) < TRIGGER_COOLDOWN:
            return
        _last_trigger[message.guild.id] = now

        oneshot_url = match_oneshot(content)
        if oneshot_url:
            session['oneshot'] = True
            session['interrupted'] = True
            session['url'] = oneshot_url
            session['vc'].stop()
            return

        triggered_url = match_trigger(content)
        if triggered_url and triggered_url != session.get('ambient_url'):
            session['oneshot'] = False
            session['interrupted'] = True
            session['url'] = triggered_url
            session['ambient_url'] = triggered_url
            session['vc'].stop()

    @commands.Cog.listener()
    async def on_voice_state_update(
        self,
        member: discord.Member,
        before: discord.VoiceState,
        after: discord.VoiceState,
    ):
        if member.bot:
            return
        vc = member.guild.voice_client
        if not vc:
            return
        non_bot_members = [m for m in vc.channel.members if not m.bot]
        if len(non_bot_members) == 0:
            session = active_sessions.pop(member.guild.id, None)
            if session:
                session['stopped'] = True
            _last_trigger.pop(member.guild.id, None)
            vc.stop()
            await vc.disconnect()


async def setup(bot: commands.Bot):
    await bot.add_cog(Music(bot))
