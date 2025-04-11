import os
import discord
from discord.ext import commands, tasks
import random
import datetime
import pytz
from collections import defaultdict
from threading import Thread
from flask import Flask, request

# Assicurati che questi privileged intents siano abilitati nel Developer Portal
intents = discord.Intents.default()
intents.voice_states = True
intents.presences = True
intents.members = True
intents.message_content = True

bot = commands.Bot(command_prefix='!', intents=intents)

# Nomi dei canali
TESTUALE_RIASSUNTO = "attività-giocatore"
TESTUALE_STATISTICHE = "statistiche-giocatori"

# Lista di colori casuali per i giocatori
EMBED_COLORS = [
    discord.Color.red(),
    discord.Color.green(),
    discord.Color.blue(),
    discord.Color.purple(),
    discord.Color.orange(),
    discord.Color.yellow(),
    discord.Color.teal(),
    discord.Color.magenta()
]

player_colors = {}  # Dizionario per assegnare un colore unico a ciascun giocatore
weekly_stats = defaultdict(list)  # Traccia l'attività settimanale dei giocatori

BADGES = {
    "casual_gamer": "🎮",
    "night_owl": "🦉",
    "most_active": "🏆"
}

async def get_active_players(guild):
    active_players = []
    for member in guild.members:
        if member.voice and member.voice.channel and member.activity and member.activity.type == discord.ActivityType.playing:
            active_players.append(member)
            if member.id not in player_colors:
                player_colors[member.id] = random.choice(EMBED_COLORS)
    return active_players

async def send_summary(guild):
    now = datetime.datetime.now(pytz.timezone('Europe/Rome'))
    if 10 <= now.hour < 24:  # Invia messaggi tra le 10:00 e le 23:59
        channel = discord.utils.get(guild.text_channels, name=TESTUALE_RIASSUNTO)
        if channel:
            active_players = await get_active_players(guild)
            if active_players:
                embed = discord.Embed(
                    title=f"🎮 Giocatori Attivi",
                    color=discord.Color.blurple()
                )
                if guild.icon:
                    embed.set_thumbnail(url=guild.icon.url)
                for member in active_players:
                    color = player_colors.get(member.id, discord.Color.default())
                    embed.add_field(
                        name=member.display_name,
                        value=f"Sta giocando a: {member.activity.name}",
                        inline=True
                    )
                    embed.color = color
                    await channel.send(embed=embed)

# Task separata per inviare il messaggio di inattività ogni ora
@tasks.loop(minutes=60)
async def send_inactivity_message():
    now = datetime.datetime.now(pytz.timezone('Europe/Rome'))
    if 10 <= now.hour < 24:
        for guild in bot.guilds:
            channel = discord.utils.get(guild.text_channels, name=TESTUALE_RIASSUNTO)
            if channel and not await get_active_players(guild):
                await channel.send(f"😴 Nessun giocatore attivo in nessun canale vocale.")

async def clear_channel(channel):
    try:
        await channel.purge(limit=None)
        print(f"Canale '{channel.name}' pulito.")
    except discord.errors.Forbidden:
        print(f"Non ho i permessi per pulire il canale '{channel.name}'.")
    except discord.errors.NotFound:
        print(f"Il canale '{channel.name}' non è stato trovato.")

@tasks.loop(hours=24)
async def daily_channel_cleanup():
    now = datetime.datetime.now(pytz.timezone('Europe/Rome'))
    if now.hour == 5 and now.minute == 0:
        for guild in bot.guilds:
            channel_to_clear = discord.utils.get(guild.text_channels, name=TESTUALE_RIASSUNTO)
            if channel_to_clear:
                await clear_channel(channel_to_clear)

async def update_weekly_stats(member, game, start_time):
    weekly_stats[member.id].append({"game": game, "start_time": start_time.timestamp()})

@bot.event
async def on_presence_update(before, after):
    if after.activity and after.activity.type == discord.ActivityType.playing and after.member.voice and after.member.voice.channel:
        now = datetime.datetime.now(pytz.timezone('Europe/Rome'))
        await update_weekly_stats(after.member, after.activity.name, now)
    elif before.activity and before.activity.type == discord.ActivityType.playing and not after.activity:
        pass

@tasks.loop(hours=24 * 7)
async def send_weekly_stats():
    now = datetime.datetime.now(pytz.timezone('Europe/Rome'))
    if now.weekday() == 0 and now.hour == 10 and now.minute == 0:
        for guild in bot.guilds:
            stats_channel = discord.utils.get(guild.text_channels, name=TESTUALE_STATISTICHE)
            if stats_channel:
                await stats_channel.send("📊 **Statistiche di gioco settimanali:**")
                if weekly_stats:
                    game_counts = defaultdict(int)
                    player_activity_seconds = defaultdict(int)
                    now_ts = now.timestamp()
                    week_start_ts = (now - datetime.timedelta(days=now.weekday())).replace(hour=0, minute=0, second=0, microsecond=0).timestamp()

                    for user_id, activities in weekly_stats.items():
                        total_playtime = 0
                        for activity in activities:
                            if activity.get("start_time") >= week_start_ts and activity.get("start_time") <= now_ts and activity.get("game"):
                                game_counts[activity["game"].lower()] += 1
                                total_playtime += 60 * 5

                        player_activity_seconds[user_id] = total_playtime

                    if game_counts:
                        sorted_games = sorted(game_counts.items(), key=lambda item: item[1], reverse=True)
                        await stats_channel.send("**Giochi più giocati:**")
                        for game, count in sorted_games[:5]:
                            await stats_channel.send(f"- {game}: {count} volte")
                    else:
                        await stats_channel.send("Nessun dato di gioco registrato per questa settimana.")

                    if player_activity_seconds:
                        sorted_players = sorted(player_activity_seconds.items(), key=lambda item: item[1], reverse=True)
                        await stats_channel.send("\n**Premi settimanali:**")
                        badges = {}
                        if sorted_players:
                            most_active_player_id = sorted_players[0][0]
                            badges[most_active_player_id] = BADGES["most_active"]

                            for user_id, playtime in sorted_players[:3]:
                                member = guild.get_member(user_id)
                                if member:
                                    badge_str = badges.get(user_id, "")
                                    await stats_channel.send(f"- {member.display_name}: {datetime.timedelta(seconds=playtime)} {badge_str}")
                    else:
                        await stats_channel.send("Nessuna attività dei giocatori registrata per questa settimana.")

                weekly_stats.clear()

app = Flask(__name__)

@app.route('/')
def health_check():
    return "Bot è attivo!"

def run_flask():
    app.run(host='0.0.0.0', port=int(os.environ.get('PORT', 8080)))

def keep_alive():
    server = Thread(target=run_flask)
    server.daemon = True
    server.start()

@bot.event
async def on_ready():
    print(f"Bot connesso come {bot.user}")
    keep_alive()
    send_periodic_summary.start()
    daily_channel_cleanup.start()
    send_weekly_stats.start()
    send_inactivity_message.start()

@tasks.loop(seconds=60)
async def send_periodic_summary():
    now = datetime.datetime.now(pytz.timezone('Europe/Rome'))
    if 10 <= now.hour < 24:
        for guild in bot.guilds:
            await send_summary(guild)

@bot.event
async def on_voice_state_update(member, before, after):
    now = datetime.datetime.now(pytz.timezone('Europe/Rome'))
    if 10 <= now.hour < 24:
        for guild in bot.guilds:
            await send_summary(guild)

@bot.event
async def on_presence_update(before, after):
    if after.activity and after.activity.type == discord.ActivityType.playing and after.member.voice and after.member.voice.channel:
        now = datetime.datetime.now(pytz.timezone('Europe/Rome'))
        await update_weekly_stats(after.member, after.activity.name, now)
    elif before.activity and before.activity.type == discord.ActivityType.playing and not after.activity:
        pass

@bot.command(name="riassunto")
async def manual_summary(ctx):
    await send_summary(ctx.guild)

@bot.command(name="pulisci")
@commands.has_permissions(manage_messages=True)
async def pulisci(ctx, amount: int):
    await ctx.channel.purge(limit=amount + 1)
    await ctx.send(f"🧹 Puliti {amount} messaggi.", delete_after=5)

@pulisci.error
async def pulisci_error(ctx, error):
    if isinstance(error, commands.MissingPermissions):
        await ctx.send("⚠️ Non hai i permessi per usare questo comando.")

# Ottieni il token Discord dalla variabile d'ambiente
TOKEN = os.environ.get('DISCORD_TOKEN')
if TOKEN:
    bot.run(TOKEN)
else:
    print("Errore: La variabile d'ambiente DISCORD_TOKEN non è impostata.")
