import discord
from discord.ext import commands, tasks
import json
import os
from keep_alive import keep_alive
import time
from itertools import cycle
from collections import Counter
import matplotlib.pyplot as plt
import datetime

# Assicurati che questi privileged intents siano abilitati anche nel Developer Portal
intents = discord.Intents.default()
intents.voice_states = True
intents.presences = True
intents.members = True

bot = commands.Bot(command_prefix='!', intents=intents)
DATA_FILE = 'user_activity.json'
GAMES_FILE = 'games_activity.json'
DAILY_STATS_FILE = 'daily_stats.json'
WEEKLY_STATS_FILE = 'weekly_stats.json'

BADGES = {
    "casual_gamer": "🐢",
    "night_owl": "🌙",
    "most_active": "🔥"
}

def load_data(filename):
    if os.path.exists(filename):
        with open(filename, 'r', encoding='utf-8') as f:
            return json.load(f)
    return {}

def save_data(data, filename):
    with open(filename, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=4)

def load_user_data():
    return load_data(DATA_FILE)

def save_user_data(data):
    save_data(data, DATA_FILE)

def load_games_data():
    return load_data(GAMES_FILE)

def save_games_data(data):
    save_data(data, GAMES_FILE)

def load_daily_stats():
    return load_data(DAILY_STATS_FILE)

def save_daily_stats(data):
    save_data(data, DAILY_STATS_FILE)

def load_weekly_stats():
    return load_data(WEEKLY_STATS_FILE)

def save_weekly_stats(data):
    save_data(data, WEEKLY_STATS_FILE)

user_messages = {}
game_start_counts = Counter()

@bot.event
async def on_ready():
    print(f"Bot connesso come {bot.user}")
    print("Comandi disponibili:", bot.commands)
    send_hourly_update.start()
    send_weekly_ranking.start()
    cleanup_inactive_users.start()
    change_status.start()
    calculate_daily_gamer.start()
    send_weekly_games_chart.start() # Avvia la nuova task per il grafico settimanale
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
            data = load_user_data()
            data[str(member.id)] = {
                "username": member.display_name,
                "voice_channel": voice_channel.name,
                "game": activity,
                "start_time": time.time()
            }
            save_user_data(data)
            games_data = load_games_data()
            game_name = activity.lower()
            games_data[game_name] = games_data.get(game_name, 0) + 1
            save_games_data(games_data)

            game_start_counts[game_name] += 1
            if game_start_counts[game_name] >= 4:
                await text_channel.send(f"@everyone 📢 Sembra che ci siano un po' di giocatori di **{activity}** in questo momento!")
                game_start_counts[game_name] = 0 # Reset the counter

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
        data = load_user_data()
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
    if current_time.tm_wday == 6 and current_time.tm_hour == 11:
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

            weekly_user_activity = load_weekly_stats().get("user_activity", {})
            casual_gamer = None
            max_unique_games = 0
            night_owl = None
            max_night_games = 0
            most_active_user = None
            max_playtime = 0

            user_unique_games = {}
            user_night_games = {}
            user_total_playtime = {}

            now = time.time()
            one_week_ago = now - (7 * 24 * 3600)

            for user_id, activities in weekly_user_activity.items():
                unique_games = set()
                night_games_count = 0
                total_playtime = 0
                for activity_data in activities:
                    if activity_data.get("game"):
                        unique_games.add(activity_data["game"].lower())
                        start_time = activity_data.get("start_time", 0)
                        end_time = activity_data.get("end_time", now) # Assuming ended now if not recorded
                        if start_time >= one_week_ago:
                            hour = time.localtime(start_time).tm_hour
                            if 0 <= hour < 6:
                                night_games_count += 1
                            total_playtime += (end_time - start_time)

                user_unique_games[user_id] = len(unique_games)
                user_night_games[user_id] = night_games_count
                user_total_playtime[user_id] = total_playtime

            for user_id, count in user_unique_games.items():
                if count > max_unique_games:
                    max_unique_games = count
                    casual_gamer = user_id

            for user_id, count in user_night_games.items():
                if count > max_night_games:
                    max_night_games = count
                    night_owl = user_id

            for user_id, playtime in user_total_playtime.items():
                if playtime > max_playtime:
                    max_playtime = playtime
                    most_active_user = user_id

            badges_str = ""
            if casual_gamer:
                member = bot.get_user(int(casual_gamer))
                if member:
                    badges_str += f"\n{BADGES['casual_gamer']} **Casual Gamer della settimana**: {member.mention} (ha giocato {max_unique_games} giochi diversi)"
            if night_owl:
                member = bot.get_user(int(night_owl))
                if member:
                    badges_str += f"\n{BADGES['night_owl']} **Notturno**: {member.mention} (ha avviato {max_night_games} giochi di notte)"
            if most_active_user:
                member = bot.get_user(int(most_active_user))
                if member:
                    badges_str += f"\n{BADGES['most_active']} **Più attivo della settimana**: {member.mention} (ha giocato per {format_time(max_playtime)})"

            if badges_str:
                embed = discord.Embed() # Inizializza l'embed qui
                embed.add_field(name="🏆 Special Awards", value=badges_str, inline=False)
                await channel.send(embed=embed)
            else:
                await channel.send(embed=embed) # Invia anche se non ci sono premi speciali
            save_games_data({}) # Reset weekly game stats
            save_weekly_stats({"user_activity": {}}) # Reset weekly user activity

@tasks.loop(minutes=15)
async def cleanup_inactive_users():
    data = load_user_data()
    guild = discord.utils.get(bot.guilds)
    if not guild:
        return
    text_channel = discord.utils.get(guild.text_channels, name="attività-giocatori")
    if not text_channel:
        return
    updated_data = {}
    for user_id, details in data.items():
        member = guild.get_member(int(user_id))
        if member and member.voice and member.activity and member.activity.type == discord.ActivityType.playing:
            updated_data[user_id] = details
        elif int(user_id) in user_messages:
            try:
                msg = await text_channel.fetch_message(user_messages[int(user_id)])
                await msg.delete()
            except discord.NotFound:
                pass
            del user_messages[int(user_id)]
    save_user_data(updated_data)

@bot.tree.command(name="pulisci")
async def pulisci(interaction: discord.Interaction):
    await cleanup_inactive_users()
    await interaction.response.send_message("✅ Pulizia eseguita con successo!", ephemeral=True)

@bot.tree.command(name="statistiche")
async def statistiche(interaction: discord.Interaction):
    games_data = load_games_data()
    total_games_started = sum(games_data.values())
    most_played_game = max(games_data, key=games_data.get) if games_data else "Nessun gioco giocato oggi"
    top_3_games = sorted(games_data.items(), key=lambda item: item[1], reverse=True)[:3]
    top_3_str = "\n".join([f"**{game[0].title()}**: {game[1]} partite" for game in top_3_games]) if top_3_games else "Nessun dato"

    user_data = load_user_data()
    user_playtime = {}
    now = time.time()
    for user_id, details in user_data.items():
        if details.get("start_time"):
            user_playtime[user_id] = user_playtime.get(user_id, 0) + (now - details["start_time"])

    most_active_user = None
    max_playtime = 0
    for user_id, playtime in user_playtime.items():
        if playtime > max_playtime:
            max_playtime = playtime
            most_active_user = user_id

    most_active_user_mention = f"<@{most_active_user}>" if most_active_user else "Nessuno"
    playtime_str = format_time(max_playtime) if most_active_user else "N/A"

    embed = discord.Embed(
        title="📊 Statistiche in Tempo Reale",
        color=discord.Color.orange(),
        timestamp=discord.utils.utcnow()
    )
    embed.add_field(name="🎮 Gioco più giocato oggi:", value=most_played_game.title(), inline=False)
    embed.add_field(name="🕹️ Numero totale di giochi avviati:", value=total_games_started, inline=False)
    embed.add_field(name="🥇 Utente con più tempo in gioco:", value=f"{most_active_user_mention} ({playtime_str})", inline=False)
    embed.add_field(name="🏆 Top 3 giochi della settimana:", value=top_3_str, inline=False)
    await interaction.response.send_message(embed=embed)

@bot.tree.command(name="grafico_giochi_settimanali")
async def grafico_giochi_settimanali(interaction: discord.Interaction):
    await interaction.response.defer() # Per evitare il timeout se la generazione del grafico richiede tempo
    await send_weekly_games_chart_logic(interaction.channel) # Riutilizza la logica del grafico
    await interaction.followup.send("Grafico settimanale dei giochi generato e inviato nel canale.", ephemeral=True)

async def send_weekly_games_chart_logic(channel):
    settimana_corrente = datetime.date.today().isocalendar()[1]
    anno_corrente = datetime.date.today().year

    games_data_settimanali = Counter()
    weekly_stats = load_weekly_stats().get("user_activity", {})

    for user_id, activity_history in weekly_stats.items():
        for activity in activity_history:
            if activity.get("game") and activity.get("start_time"):
                start_time = datetime.datetime.fromtimestamp(activity["start_time"])
                if start_time.isocalendar()[1] == settimana_corrente and start_time.year == anno_corrente:
                    games_data_settimanali[activity["game"].lower()] += 1

    if not games_data_settimanali:
        await channel.send("📊 Nessun dato di gioco disponibile per questa settimana per generare il grafico.")
        return

    giochi = list(games_data_settimanali.keys())
    conteggi = list(games_data_settimanali.values())

    plt.figure(figsize=(10, 6))
    plt.bar(giochi, conteggi, color='skyblue')
    plt.xlabel("Gioco")
    plt.ylabel("Numero di Sessioni")
    plt.title(f"Giochi Più Giocati - Settimana {settimana_corrente}, {anno_corrente}")
    plt.xticks(rotation=45, ha='right')
    plt.tight_layout()

    nome_file_grafico = f"giochi_settimana_{settimana_corrente}_{anno_corrente}.png"
    plt.savefig(nome_file_grafico)
    plt.close()

    with open(nome_file_grafico, 'rb') as grafico:
        await channel.send(file=discord.File(grafico, filename=nome_file_grafico))

    os.remove(nome_file_grafico) # Pulizia del file temporaneo

@tasks.loop(time=discord.ext.tasks.time(hour=11, minute=0, day_of_week=6)) # Esegue alle 11:00 ogni domenica (giorno 6 è domenica)
async def send_weekly_games_chart():
    channel = discord.utils.get(bot.get_all_channels(), name="attività-giocatori")
    if channel:
        await send_weekly_games_chart_logic(channel)

@bot.event
async def on_message(message):
    if message.author == bot.user:
        return
    await bot.process_commands(message)

status = cycle(['fare il bot','tetris','fare il bot','PAC-MAN','calcetto'])

@tasks.loop(seconds=10)
async def change_status():
    await bot.change_presence(activity=discord.Game(next(status)))

@tasks.loop(time=discord.ext.tasks.time(23, 0)) # Runs at 23:00 daily
async def calculate_daily_gamer():
    channel = discord.utils.get(bot.get_all_channels(), name="attività-giocatori")
    if not channel:
        return

    user_data = load_user_data()
    daily_playtime = {}
    now = time.time()
    one_day_ago = now - (24 * 3600)
    daily_activity = {}

    for user_id, details in user_data.items():
        if details.get("start_time"):
            if details["start_time"] >= one_day_ago:
                daily_playtime[user_id] = daily_playtime.get(user_id, 0) + (now - details["start_time"])
            else:
                # Check for ongoing sessions from previous days
                if details.get("game") and details.get("voice_channel"):
                    daily_playtime[user_id] = daily_playtime.get(user_id, 0) + (now - details["start_time"])

        # Also track activity for weekly stats
        if details.get("game") and details.get("start_time"):
            if user_id not in daily_activity:
                daily_activity[user_id] = []
            daily_activity[user_id].append({
                "game": details["game"],
                "start_time": details["start_time"],
                "end_time": now # Assume ended now for daily tracking
            })

    gamer_of_the_day = None
    max_daily_playtime = 0
    for user_id, playtime in daily_playtime.items():
        if playtime > max_daily_playtime:
            max_daily_playtime = playtime
            gamer_of_the_day = user_id

    if gamer_of_the_day:
        member = bot.get_user(int(gamer_of_the_day))
        if member and channel:
            playtime_str = format_time(max_daily_playtime)
            await channel.send(f"🏆 **Gamer del giorno!** {member.mention} ha giocato per **{playtime_str}** nelle ultime 24 ore!")

    # Update weekly stats
    weekly_data = load_weekly_stats()
    weekly_user_activity = weekly_data.get("user_activity", {})
    for user_id, activities in daily_activity.items():
        if user_id not in weekly_user_activity:
            weekly_user_activity[user_id] = []
        weekly_user_activity[user_id].extend(activities)
    weekly_data["user_activity"] = weekly_user_activity
    save_weekly_stats(weekly_data)
    save_daily_stats({}) # Reset daily stats

keep_alive()
bot.run(os.environ['DISCORD_TOKEN'])
