import asyncio
import json
from pathlib import Path
import discord
from discord.ext import commands

from db.mongo import set_track, clear_track, get_track
from cogs.music import _reply, DELETE_AFTER

_PRESETS_FILE = Path(__file__).parent.parent / 'presets.json'


def _load_presets() -> dict:
    with open(_PRESETS_FILE, 'r', encoding='utf-8') as f:
        return json.load(f)


def _save_presets(data: dict):
    with open(_PRESETS_FILE, 'w', encoding='utf-8') as f:
        json.dump(data, f, indent=2, ensure_ascii=False)


class Admin(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    # --settrack <url>
    @commands.command(name='settrack')
    @commands.has_permissions(manage_channels=True)
    async def settrack(self, ctx: commands.Context, url: str):
        await set_track(ctx.channel.id, url, ctx.guild.id)
        asyncio.create_task(_reply(ctx,
            f'Track assigned to **#{ctx.channel.name}**.\n'
            f'Use `--play` to start it.\n{url}'
        ))

    # --cleartrack
    @commands.command(name='cleartrack')
    @commands.has_permissions(manage_channels=True)
    async def cleartrack(self, ctx: commands.Context):
        existing = await get_track(ctx.channel.id)
        if not existing:
            asyncio.create_task(_reply(ctx, f'**#{ctx.channel.name}** has no assigned track.'))
            return
        await clear_track(ctx.channel.id)
        asyncio.create_task(_reply(ctx,
            f'Track removed from **#{ctx.channel.name}**. '
            'Next `--play` will use the keyword preset.'
        ))

    # --trackinfo
    @commands.command(name='trackinfo')
    async def trackinfo(self, ctx: commands.Context):
        url = await get_track(ctx.channel.id)
        if url:
            asyncio.create_task(_reply(ctx, f'Assigned track for **#{ctx.channel.name}**:\n{url}'))
        else:
            from presets.tracks import get_preset, describe_preset
            preset_url = get_preset(ctx.channel.name)
            vibe = describe_preset(ctx.channel.name)
            asyncio.create_task(_reply(ctx,
                f'No assigned track for **#{ctx.channel.name}**.\n'
                f'Would use **{vibe}** preset:\n{preset_url}'
            ))

    # --setpreset <section> <keyword> <url>
    # section: preset | trigger | oneshot | mood
    # example: --setpreset preset aldea https://youtube.com/...
    # example: --setpreset trigger lluvia https://youtube.com/...
    @commands.command(name='setpreset')
    @commands.has_permissions(manage_channels=True)
    async def setpreset(self, ctx: commands.Context, section: str, keyword: str, url: str):
        section_map = {
            'preset':  None,
            'trigger': '_triggers',
            'oneshot': '_oneshots',
            'mood':    '_moods',
        }
        if section not in section_map:
            await ctx.send(
                'Invalid section. Use: `preset`, `trigger`, `oneshot`, or `mood`.\n'
                'Example: `--setpreset trigger lluvia https://...`'
            )
            return

        data = _load_presets()
        key = section_map[section]

        if key is None:
            data[keyword] = url
        else:
            if key not in data:
                data[key] = {}
            data[key][keyword] = url

        _save_presets(data)
        location = f'`{key}.{keyword}`' if key else f'`{keyword}`'
        asyncio.create_task(_reply(ctx, f'Preset saved: {location} → {url}'))

    # --removepreset <section> <keyword>
    @commands.command(name='removepreset')
    @commands.has_permissions(manage_channels=True)
    async def removepreset(self, ctx: commands.Context, section: str, keyword: str):
        section_map = {
            'preset':  None,
            'trigger': '_triggers',
            'oneshot': '_oneshots',
            'mood':    '_moods',
        }
        if section not in section_map:
            asyncio.create_task(_reply(ctx, 'Invalid section. Use: `preset`, `trigger`, `oneshot`, or `mood`.'))
            return

        data = _load_presets()
        key = section_map[section]

        if key is None:
            if keyword not in data:
                asyncio.create_task(_reply(ctx, f'Keyword `{keyword}` not found in presets.'))
                return
            del data[keyword]
        else:
            if key not in data or keyword not in data[key]:
                asyncio.create_task(_reply(ctx, f'Keyword `{keyword}` not found in `{key}`.'))
                return
            del data[key][keyword]

        _save_presets(data)
        asyncio.create_task(_reply(ctx, f'Removed `{keyword}` from `{key or "presets"}`.'))


    @settrack.error
    @cleartrack.error
    @setpreset.error
    @removepreset.error
    async def permission_error(self, ctx: commands.Context, error):
        if isinstance(error, commands.MissingPermissions):
            asyncio.create_task(_reply(ctx, 'You need **Manage Channels** permission to use that command.'))
        elif isinstance(error, commands.MissingRequiredArgument):
            asyncio.create_task(_reply(ctx, f'Missing argument: `{error.param.name}`.'))


async def setup(bot: commands.Bot):
    await bot.add_cog(Admin(bot))
