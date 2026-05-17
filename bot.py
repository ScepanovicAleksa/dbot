import csv
import json
import os
import random
from datetime import time
from pathlib import Path
from zoneinfo import ZoneInfo

import discord
from discord.ext import commands, tasks
from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent
load_dotenv(BASE_DIR / ".env")

UTTERANCES_CSV_PATH = BASE_DIR / "utterances.csv"
RECENT_POSTS_PATH = BASE_DIR / "recent_posts.json"

DISCORD_TOKEN = os.getenv("DISCORD_TOKEN")
DISCORD_GUILD_NAME = os.getenv("DISCORD_GUILD_NAME", "asetianism")
DISCORD_CHANNEL_NAME = os.getenv("DISCORD_CHANNEL_NAME", "asetianism")
PORTUGAL_TZ = ZoneInfo("Europe/Lisbon")
POST_TIME = time(hour=3, minute=33, tzinfo=PORTUGAL_TZ)
STARTUP_MESSAGE = "An Asetianist by nature is a Loner."
RECENT_HISTORY_LIMIT = 7

intents = discord.Intents.default()
intents.message_content = True
bot = commands.Bot(command_prefix="!", intents=intents)


def load_utterances_from_csv(file_path: Path) -> list[dict]:
    if not file_path.exists():
        print(f"CSV file not found: {file_path}")
        return []

    utterances_data = []
    with file_path.open("r", encoding="utf-8-sig", newline="") as csv_file:
        reader = csv.DictReader(csv_file)

        required_columns = {"id", "username", "text"}
        if not required_columns.issubset(set(reader.fieldnames or [])):
            print("CSV is missing one or more required columns: id, username, text")
            return []

        for row in reader:
            post_id = (row.get("id") or "").strip()
            username = (row.get("username") or "").strip()
            text = (row.get("text") or "").strip()

            if not post_id or not username or not text:
                continue

            utterances_data.append(
                {
                    "id": post_id,
                    "username": username,
                    "text": text,
                    "created_at": (row.get("created_at") or "").strip(),
                }
            )

    print(f"Loaded {len(utterances_data)} utterances from CSV.")
    return utterances_data


def load_recent_posts(file_path: Path) -> list[str]:
    if not file_path.exists():
        return []

    try:
        with file_path.open("r", encoding="utf-8") as file:
            data = json.load(file)
        if isinstance(data, list):
            return [str(item) for item in data]
    except (json.JSONDecodeError, OSError) as error:
        print(f"Could not read recent posts file: {error}")

    return []


def save_recent_posts(file_path: Path, recent_posts: list[str]) -> None:
    try:
        with file_path.open("w", encoding="utf-8") as file:
            json.dump(recent_posts[-RECENT_HISTORY_LIMIT:], file, ensure_ascii=False, indent=2)
    except OSError as error:
        print(f"Could not save recent posts file: {error}")


def pick_random_utterance(utterances_data: list[dict], recent_post_ids: list[str]) -> dict | None:
    if not utterances_data:
        return None

    candidates = [item for item in utterances_data if item["id"] not in recent_post_ids]

    if not candidates:
        last_post_id = recent_post_ids[-1] if recent_post_ids else None
        candidates = [item for item in utterances_data if item["id"] != last_post_id]

    if not candidates:
        return None

    return random.choice(candidates)


def get_target_channel() -> discord.TextChannel | None:
    guild = discord.utils.get(bot.guilds, name=DISCORD_GUILD_NAME)
    if guild is None:
        print(f"Guild not found: {DISCORD_GUILD_NAME}")
        return None

    channel = discord.utils.get(guild.text_channels, name=DISCORD_CHANNEL_NAME)
    if channel is None:
        print(f"Channel not found: {DISCORD_CHANNEL_NAME}")
        return None

    return channel


def format_utterance_embed(selected: dict) -> discord.Embed:
    tweet_url = f"https://x.com/{selected['username']}/status/{selected['id']}"
    embed = discord.Embed(
        title="Utterance of the Day",
        url=tweet_url,
        description=selected["text"],
        color=0x3498DB,
    )
    embed.set_thumbnail(url="https://www.asetka.org/gfx/WordsinSilence_large.jpg")
    return embed


utterances = load_utterances_from_csv(UTTERANCES_CSV_PATH)
recent_posts = load_recent_posts(RECENT_POSTS_PATH)


@tasks.loop(time=POST_TIME)
async def send_daily_utterance() -> None:
    global recent_posts

    channel = get_target_channel()
    if channel is None:
        return

    await post_one_utterance(channel)


async def post_one_utterance(channel: discord.TextChannel) -> bool:
    global recent_posts

    if not utterances:
        print("No utterances loaded; skipping scheduled post.")
        return False

    selected = pick_random_utterance(utterances, recent_posts)
    if selected is None:
        print("No utterance available for posting.")
        return False

    embed = format_utterance_embed(selected)
    await channel.send(embed=embed)
    print(f"Posted utterance ID {selected['id']} at {POST_TIME.strftime('%H:%M %Z')}.")

    recent_posts.append(selected["id"])
    recent_posts = recent_posts[-RECENT_HISTORY_LIMIT:]
    save_recent_posts(RECENT_POSTS_PATH, recent_posts)
    return True


@send_daily_utterance.before_loop
async def before_send_daily_utterance() -> None:
    await bot.wait_until_ready()


@bot.command(name="postnow")
async def postnow(ctx: commands.Context) -> None:
    success = await post_one_utterance(ctx.channel)
    if not success:
        await ctx.send("Could not publish an utterance. Check logs for details.")


@bot.command(name="search")
async def search(ctx: commands.Context, *, query: str = "") -> None:
    if not query.strip():
        await ctx.send("Please provide a search term. Example: `!search loner`")
        return

    if not utterances:
        await ctx.send("The database is empty or the CSV file could not be loaded.")
        return

    search_query = query.lower().strip()
    results = [item for item in utterances if search_query in item["text"].lower()]

    if not results:
        await ctx.send(f"No results found for: `{query}`")
        return

    # ako postoji tacno jedan rezultat, saljemo puni embed format
    if len(results) == 1:
        embed = format_utterance_embed(results[0])
        await ctx.send(content="Found 1 exact match:", embed=embed)
        return

    # ako ima vise rezultata, pravimo finu, preglednu listu sa linkovima
    output = f"Found **{len(results)}** results for `{query}`:\n\n"
    
    for index, item in enumerate(results, start=1):
        tweet_url = f"https://x.com/{item['username']}/status/{item['id']}"
        # skracujemo tekst na 80 karaktera u ispisu liste cisto zbog preglednosti
        clean_text = item["text"].replace("\n", " ")
        short_text = clean_text if len(clean_text) <= 80 else f"{clean_text[:80]}..."
        
        output += f"{index}. [{short_text}]({tweet_url})\n"

    # ako je lista predugacka za obicnu tekstualnu poruku (discord limit je 4000)
    if len(output) > 4000:
        output = output[:3900] + "\n...and more results. Try refining your search query."

    embed = discord.Embed(
        title="Search Results",
        description=output,
        color=0x3498DB
    )
    embed.set_thumbnail(url="https://www.asetka.org/gfx/WordsinSilence_large.jpg")
    await ctx.send(embed=embed)


@bot.event
async def on_guild_join(guild: discord.Guild) -> None:
    print(f"Bot successfully added to server: {guild.name}")
    channel = discord.utils.get(guild.text_channels, name=DISCORD_CHANNEL_NAME)
    if channel is not None:
        await channel.send(STARTUP_MESSAGE)
        print("Initial greeting message sent to the server.")


@bot.event
async def on_ready() -> None:
    print(f"Bot is online as {bot.user}.")

    if not send_daily_utterance.is_running():
        send_daily_utterance.start()


if not DISCORD_TOKEN:
    raise RuntimeError("DISCORD_TOKEN is not set. Add it as an environment variable.")

bot.run(DISCORD_TOKEN)