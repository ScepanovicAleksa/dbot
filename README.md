# Discord Daily Utterance Bot

Bot reads posts from `utterances.csv`, picks one random item, and posts it to Discord every day at **03:33 AM Portugal time** (`Europe/Lisbon`).

## What It Uses From `utterances.csv`
The bot expects these columns to exist:
- `id`
- `username`
- `text`

It also reads `created_at` if available, but that is optional.

Your CSV already has the required structure (header includes `id`, `username`, and `text`).

## Current Behavior
- Startup message on boot (once per process):
  - `An Asetianist by nature is a Loner.`
- Daily post time:
  - `03:33` in `Europe/Lisbon`
- Random selection with memory of the last 7 posted IDs:
  - never repeats yesterday's post
  - avoids repeats within last 7 posts whenever possible
- Includes clickable X link for the selected post:
  - format: `https://x.com/{username}/status/{id}`
- Manual test command:
  - `!postnow` to publish immediately in the current channel

## Setup (Local)
1. Install Python 3.10+.
2. Create venv and install deps:

```bash
python -m venv .venv
source .venv/bin/activate   # Linux/macOS
# or on Windows PowerShell: .venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

3. Configure env vars:

```bash
cp .env.example .env
```

Set real values in `.env`:
- `DISCORD_TOKEN`
- `DISCORD_GUILD_NAME`
- `DISCORD_CHANNEL_NAME`

4. Run bot:

```bash
python bot.py
```

## Connect Bot to Discord
1. Open Discord Developer Portal.
2. Create/select application -> Bot.
3. Copy bot token and put it in `DISCORD_TOKEN`.
4. Enable **Message Content Intent** (needed for `!postnow` and `!ranking`).
5. OAuth2 -> URL Generator:
   - Scopes: `bot`
   - Bot permissions: `Send Messages`, `Embed Links`, `Read Message History`, `View Channels`
6. Use generated URL to invite bot to your server.
7. Set env names exactly to your real server/channel names:
   - `DISCORD_GUILD_NAME`
   - `DISCORD_CHANNEL_NAME`

## Test Checklist
1. Start bot and confirm startup message appears.
2. In target channel run `!postnow`.
3. Confirm embed appears with `Open on X` link and that link opens correct tweet.
4. Check `recent_posts.json` is created and updated.
5. Repeat `!postnow` several times and verify no repeat inside last 7 IDs.

## Deploy on Oracle Cloud VM (Recommended: Ubuntu)

### 1. Prepare VM
```bash
sudo apt update && sudo apt upgrade -y
sudo apt install -y python3 python3-venv python3-pip git
```

### 2. Upload/clone project
```bash
git clone <your-repo-url>
cd dbot
```

### 3. Install bot
```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

### 4. Configure environment
Create `.env` in project root:
```bash
DISCORD_TOKEN=YOUR_TOKEN
DISCORD_GUILD_NAME=asetianism
DISCORD_CHANNEL_NAME=asetianism
```

### 5. Run as systemd service
Create `/etc/systemd/system/dbot.service`:

```ini
[Unit]
Description=Discord Daily Utterance Bot
After=network.target

[Service]
Type=simple
User=ubuntu
WorkingDirectory=/home/ubuntu/dbot
EnvironmentFile=/home/ubuntu/dbot/.env
ExecStart=/home/ubuntu/dbot/.venv/bin/python /home/ubuntu/dbot/bot.py
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
```

Enable and start:
```bash
sudo systemctl daemon-reload
sudo systemctl enable dbot
sudo systemctl start dbot
sudo systemctl status dbot
```

View logs:
```bash
journalctl -u dbot -f
```

## Do You Need Docker?
No, not required.

For this bot, `systemd + venv` is usually simplest and stable enough.
Use Docker only if you already standardize deployments with containers.

## Optional Docker (if you want)
Minimal `Dockerfile`:

```Dockerfile
FROM python:3.12-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY . .
CMD ["python", "bot.py"]
```

Run:
```bash
docker build -t dbot .
docker run -d --name dbot --restart unless-stopped --env-file .env dbot
```
