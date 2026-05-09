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
MESSAGE_COUNTS_PATH = BASE_DIR / "message_counts.json"

DISCORD_TOKEN = os.getenv("DISCORD_TOKEN")
DISCORD_GUILD_NAME = os.getenv("DISCORD_GUILD_NAME", "asetianism")
DISCORD_CHANNEL_NAME = os.getenv("DISCORD_CHANNEL_NAME", "asetianism")
PORTUGAL_TZ = ZoneInfo("Europe/Lisbon")
POST_TIME = time(hour=3, minute=33, tzinfo=PORTUGAL_TZ)
STARTUP_MESSAGE = "An Asetianist by nature is a Loner."
RECENT_HISTORY_LIMIT = 7

startup_message_sent = False

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
        # Fallback for small datasets: at least avoid posting the same item two days in a row.
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

    tweet_url = f"https://x.com/{selected['username']}/status/{selected['id']}"

    embed = discord.Embed(
        title="Axiom of the Day",
        url=tweet_url,
        description=selected["text"],
        color=0x3498DB,
    )
    embed.add_field(name="Source", value=f"[Open on X]({tweet_url})", inline=False)
    embed.set_thumbnail(url="https://www.asetka.org/gfx/WordsinSilence_large.jpg")

    await channel.send(embed=embed)
    print(f"Posted utterance ID {selected['id']} at {POST_TIME.strftime('%H:%M %Z')}.")

    recent_posts.append(selected["id"])
    recent_posts = recent_posts[-RECENT_HISTORY_LIMIT:]
    save_recent_posts(RECENT_POSTS_PATH, recent_posts)
    return True


@send_daily_utterance.before_loop
async def before_send_daily_utterance() -> None:
    await bot.wait_until_ready()


try:
    with MESSAGE_COUNTS_PATH.open("r", encoding="utf-8") as file:
        message_counts = json.load(file)
except (FileNotFoundError, json.JSONDecodeError):
    message_counts = {}


@bot.command(name="ranking")
async def ranking(ctx: commands.Context) -> None:
    sorted_counts = sorted(message_counts.items(), key=lambda item: item[1], reverse=True)
    output = "Top Contributors\n\n"

    for index, (user_id, count) in enumerate(sorted_counts[:10], start=1):
        user = await bot.fetch_user(int(user_id))
        output += f"{index}. **{user.name}** - {count} messages\n"

    embed = discord.Embed(description=output, color=0x00FF00)
    await ctx.send(embed=embed)


@bot.command(name="postnow")
async def postnow(ctx: commands.Context) -> None:
    success = await post_one_utterance(ctx.channel)
    if not success:
        await ctx.send("Could not publish an utterance. Check logs for details.")


@bot.event
async def on_ready() -> None:
    global startup_message_sent

    print(f"Bot is online as {bot.user}.")

    if not send_daily_utterance.is_running():
        send_daily_utterance.start()

    if not startup_message_sent:
        channel = get_target_channel()
        if channel is not None:
            await channel.send(STARTUP_MESSAGE)
            startup_message_sent = True
            print("Startup message sent.")


if not DISCORD_TOKEN:
    raise RuntimeError("DISCORD_TOKEN is not set. Add it as an environment variable.")

bot.run(DISCORD_TOKEN)
