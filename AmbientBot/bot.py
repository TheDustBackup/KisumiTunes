import asyncio
import discord
from discord.ext import commands

from config import Config
from db.mongo import init_db

discord.opus.load_opus('/opt/homebrew/lib/libopus.dylib')

intents = discord.Intents.default()
intents.message_content = True
intents.voice_states = True

bot = commands.Bot(command_prefix='--', intents=intents, help_command=None)

COGS = [
    'cogs.music',
    'cogs.admin',
]


@bot.event
async def on_ready():
    app_id = bot.user.id
    invite = (
        f'https://discord.com/oauth2/authorize?client_id={app_id}'
        '&permissions=3156992&scope=bot'
    )
    print(f'[AmbientBot] Logged in as {bot.user} (ID: {app_id})')
    print(f'[AmbientBot] Invite link: {invite}')
    await bot.change_presence(
        activity=discord.Activity(
            type=discord.ActivityType.listening,
            name='--play | ambient music',
        )
    )


@bot.command(name='help')
async def help_cmd(ctx: commands.Context):
    embed = discord.Embed(
        title='AmbientBot Commands',
        color=discord.Color.dark_purple(),
        description='Prefix: `--`',
    )
    embed.add_field(
        name='Music',
        value=(
            '`--play` · Join your voice channel and start ambient music\n'
            '`--leave` · Stop music and leave\n'
            '`--volume <0-100>` · Adjust volume\n'
            '`--nowplaying` · Show current track'
        ),
        inline=False,
    )
    embed.add_field(
        name='Admin (Manage Channels required)',
        value=(
            '`--settrack <url>` · Assign a YouTube/SoundCloud URL to this channel\n'
            '`--cleartrack` · Remove assigned track (revert to keyword preset)\n'
            '`--trackinfo` · Show current track assignment for this channel'
        ),
        inline=False,
    )
    embed.set_footer(text='Music loops until you use --leave or leave the voice channel.')
    await ctx.send(embed=embed)


@bot.event
async def on_command_error(ctx: commands.Context, error: commands.CommandError):
    if isinstance(error, commands.CommandNotFound):
        return
    if isinstance(error, commands.MissingRequiredArgument):
        await ctx.send(f'Missing argument: `{error.param.name}`. Use `--help` for usage.')
        return
    raise error


async def main():
    async with bot:
        await init_db()
        for cog in COGS:
            await bot.load_extension(cog)
        await bot.start(Config.DISCORD_TOKEN)


if __name__ == '__main__':
    asyncio.run(main())
