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
DISCORD_GUILD_ID = os.getenv("DISCORD_GUILD_ID")
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
    if not DISCORD_GUILD_ID:
        print("DISCORD_GUILD_ID is missing from .env file.")
        return None

    guild = bot.get_guild(int(DISCORD_GUILD_ID))
    if guild is None:
        print(f"Guild with ID {DISCORD_GUILD_ID} not found.")
        return None

    channel = discord.utils.get(guild.text_channels, name=DISCORD_CHANNEL_NAME)
    
    if channel is None:
        print(f"Primary channel '{DISCORD_CHANNEL_NAME}' not found. Trying fallback channel 'public'...")
        channel = discord.utils.get(guild.text_channels, name="public")

    if channel is None:
        print("Neither primary channel nor fallback channel 'public' was found.")
        return None

    return channel


def format_utterance_embed(selected: dict, title: str = "Utterance of the Day") -> discord.Embed:
    tweet_url = f"https://x.com/{selected['username']}/status/{selected['id']}"
    embed = discord.Embed(
        title=title,
        url=tweet_url,
        description=selected["text"],
        color=0x3498DB,
    )
    embed.set_thumbnail(url="https://www.asetka.org/gfx/WordsinSilence_large.jpg")
    return embed


# klasa za interaktivne dugmice (paginaciju) unutar discorda
class SearchPaginationView(discord.ui.View):
    def __init__(self, results: list[dict], query: str):
        super().__init__(timeout=60.0) # dugmici su aktivni 60 sekundi
        self.results = results
        self.query = query
        self.current_index = 0

    def update_buttons(self) -> None:
        # gasimo dugme 'back' ako smo na prvoj stranici
        self.children[0].disabled = self.current_index == 0
        # gasimo dugme 'next' ako smo na poslednjoj stranici
        self.children[1].disabled = self.current_index == len(self.results) - 1

    def create_embed(self) -> discord.Embed:
        item = self.results[self.current_index]
        title_text = f"Search Result {self.current_index + 1} of {len(self.results)} for '{self.query}'"
        return format_utterance_embed(item, title=title_text)

    @discord.ui.button(label="◀ Back", style=discord.ButtonStyle.secondary, disabled=True)
    async def back_button(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        if self.current_index > 0:
            self.current_index -= 1
            self.update_buttons()
            await interaction.response.edit_message(embed=self.create_embed(), view=self)

    @discord.ui.button(label="Next ▶", style=discord.ButtonStyle.primary)
    async def next_button(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        if self.current_index < len(self.results) - 1:
            self.current_index += 1
            self.update_buttons()
            await interaction.response.edit_message(embed=self.create_embed(), view=self)

    async def on_timeout(self) -> None:
        # kada istekne vrijeme, gasimo dugmice da niko ne moze da klikne
        for child in self.children:
            child.disabled = True
        try:
            if hasattr(self, "message"):
                await self.message.edit(view=self)
        except Exception:
            pass


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


@bot.command(name="search")
@commands.cooldown(1, 10, commands.BucketType.user)
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

    # ako ima samo jedan rezultat, saljemo obican embed bez dugmica
    if len(results) == 1:
        embed = format_utterance_embed(results[0], title=f"Found 1 exact match for '{query}'")
        await ctx.send(embed=embed)
        return

    # ako ima vise rezultata, pokrecemo paginaciju sa dugmicima
    view = SearchPaginationView(results, query)
    view.update_buttons()
    
    embed = view.create_embed()
    view.message = await ctx.send(embed=embed, view=view)


@bot.event
async def on_command_error(ctx: commands.Context, error: Exception) -> None:
    if isinstance(error, commands.CommandOnCooldown):
        seconds = round(error.retry_after)
        await ctx.send(f"Hold on. You are using this command too fast. Try again in {seconds}s.", delete_after=5)
        return
    
    print(f"An error occurred: {error}")


@bot.event
async def on_guild_join(guild: discord.Guild) -> None:
    print(f"Bot successfully added to server: {guild.name}")
    
    if DISCORD_GUILD_ID and guild.id == int(DISCORD_GUILD_ID):
        channel = discord.utils.get(guild.text_channels, name=DISCORD_CHANNEL_NAME)
        if channel is None:
            channel = discord.utils.get(guild.text_channels, name="public")
            
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