import discord
from discord.ext import commands, tasks
import json
import os
from keep_alive import keep_alive
import time
from itertools import cycle

intents = discord.Intents.default()
intents.voice_states = True
intents.presences = True
intents.members = True

bot = commands.Bot(command_prefix='!', intents=intents)
DATA_FILE = 'user_activity.json'
GAMES_FILE = 'games_activity.json'

def load_data():
    if os.path.exists(DATA_FILE):
        with open(DATA_FILE, 'r', encoding='utf-8') as f:
            return json.load(f)
    return {}

def save_data(data):
    with open(DATA_FILE, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=4)

def load_games_data():
    if os.path.exists(GAMES_FILE):
        with open(GAMES_FILE, 'r', encoding='utf-8') as f:
            return json.load(f)
    return {}

def save_games_data(data):
    with open(GAMES_FILE, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=4)

user_messages = {}

@bot.event
async def on_ready():
    print(f"Bot connesso come {bot.user}")
    print("Comandi disponibili:", bot.commands)
    send_hourly_update.start()
    send_weekly_ranking.start()
    cleanup_inactive_users.start()
    change_status.start()
    print("Your bot is ready")

@bot.event
async def on_presence_update(before, after):
    if after.activity and after.activity.type == discord.ActivityType.playing:
        await check_and_update(after)

@bot.event
async def on_voice_state_update(member, before, after):
    if after.channel:
        await check_and_update(member)

async def check_and_update(member):
    voice_channel = member.voice.channel if member.voice else None
    activity = member.activity.name if member.activity and member.activity.type == discord.ActivityType.playing else None
    if voice_channel and activity:
        embed = discord.Embed(title="🎮 Attività in corso",
                              description=f"{member.mention} sta giocando",
                              color=discord.Color.green(),
                              timestamp=discord.utils.utcnow())
        embed.set_author(name=member.display_name,
                         icon_url=member.avatar.url if member.avatar else member.default_avatar.url)
        embed.add_field(name="🎧 Canale Vocale", value=voice_channel.name, inline=True)
        embed.add_field(name="🕹️ Gioco", value=activity, inline=True)
        embed.set_footer(text=f"ID Utente: {member.id}")
        text_channel = discord.utils.get(member.guild.text_channels, name="attività-giocatori")
        if text_channel:
            if member.id in user_messages:
                try:
                    msg = await text_channel.fetch_message(user_messages[member.id])
                    await msg.edit(embed=embed)
                except discord.NotFound:
                    msg = await text_channel.send(embed=embed)
                    user_messages[member.id] = msg.id
            else:
                msg = await text_channel.send(embed=embed)
                user_messages[member.id] = msg.id
            data = load_data()
            data[str(member.id)] = {
                "username": member.display_name,
                "voice_channel": voice_channel.name,
                "game": activity,
                "start_time": time.time()
            }
            save_data(data)
            games_data = load_games_data()
            game_name = activity.lower()
            games_data[game_name] = games_data.get(game_name, 0) + 1
            save_games_data(games_data)

def format_time(seconds):
    hours = seconds // 3600
    minutes = (seconds % 3600) // 60
    seconds = seconds % 60
    return f"{hours}h {minutes}m {seconds}s" if hours > 0 else f"{minutes}m {seconds}s"

@tasks.loop(hours=1)
async def send_hourly_update():
    now = time.localtime()
    if 0 <= now.tm_hour < 10:
        return
    channel = discord.utils.get(bot.get_all_channels(), name="attività-giocatori")
    if channel:
        data = load_data()
        active_players = []
        for user_id, details in data.items():
            if details.get("game") and details.get("start_time"):
                elapsed_time = int(time.time() - details["start_time"])
                elapsed_time_str = format_time(elapsed_time)
                active_players.append(
                    f"{details['username']} sta giocando **{details['game']}** da **{elapsed_time_str}** in {details['voice_channel']}")
        if active_players:
            embed = discord.Embed(
                title="📊 Aggiornamento Attività Giocatori",
                description="Ecco chi sta giocando attualmente:",
                color=discord.Color.blue(),
                timestamp=discord.utils.utcnow())
            embed.add_field(name="Giocatori attivi:", value="\n".join(active_players), inline=False)
            await channel.send(embed=embed)
        else:
            await channel.send("📭 Nessun giocatore attivo al momento.")

@tasks.loop(hours=168)
async def send_weekly_ranking():
    current_time = time.localtime()
    if current_time.tm_wday == 6 and current_time.tm_hour == 10:
        channel = discord.utils.get(bot.get_all_channels(), name="attività-giocatori")
        if channel:
            games_data = load_games_data()
            if not games_data:
                await channel.send("📭 Nessun dato sui giochi della settimana.")
                return
            sorted_games = sorted(games_data.items(), key=lambda x: x[1], reverse=True)
            ranking = [f"**{game[0].title()}**: {game[1]} partite" for game in sorted_games]
            embed = discord.Embed(
                title="📅 Classifica Settimanale - Giochi Più Giocati",
                description="Ecco i giochi più giocati questa settimana:",
                color=discord.Color.purple(),
                timestamp=discord.utils.utcnow())
            embed.add_field(name="Top Giochi della Settimana", value="\n".join(ranking), inline=False)
            await channel.send(embed=embed)

@tasks.loop(minutes=15)
async def cleanup_inactive_users():
    data = load_data()
    guild = discord.utils.get(bot.guilds)
    text_channel = discord.utils.get(guild.text_channels, name="attività-giocatori")
    if not text_channel:
        return
    updated_data = data.copy()
    for user_id, details in data.items():
        member = guild.get_member(int(user_id))
        if not member or not member.voice or not member.activity or member.activity.type != discord.ActivityType.playing:
            if int(user_id) in user_messages:
                try:
                    msg = await text_channel.fetch_message(user_messages[int(user_id)])
                    await msg.delete()
                except discord.NotFound:
                    pass
                del user_messages[int(user_id)]
            if user_id in updated_data:
                del updated_data[user_id]
    save_data(updated_data)

@bot.command(name="pulisci")
@commands.has_permissions(administrator=True)
async def pulisci(ctx):
    await cleanup_inactive_users()
    await ctx.send("✅ Pulizia eseguita con successo!")

@bot.event
async def on_message(message):
    if message.author == bot.user:
        return
    await bot.process_commands(message)

status = cycle(['fare il bot','tetris','fare il bot','PAC-MAN','calcetto'])

@tasks.loop(seconds=10)
async def change_status():
    await bot.change_presence(activity=discord.Game(next(status)))

keep_alive()
bot.run(os.getenv("DISCORD_TOKEN"))
