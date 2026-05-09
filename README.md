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

## Deploy on DigitalOcean (Recommended)

For this bot, the simplest stable approach is:
- 1 small Droplet (`$4/mo` plan)
- run with `systemd`
- no Docker required

### Why DigitalOcean for this bot
- Predictable pricing with monthly cap per Droplet.
- Free always-on DDoS protection (network/transport layers).
- Free cloud firewalls.
- Easy VPS workflow.

### 1. Create Droplet
1. Create a Ubuntu 24.04 Droplet (`Basic`, smallest plan is enough).
2. Add your SSH key while creating.
3. Region: choose nearest to your audience.
4. Optional but recommended: rename Droplet to `dbot-prod`.

### 2. Basic security setup
1. In DigitalOcean Cloud Firewall:
   - allow inbound `22/tcp` only from your IP.
   - deny everything else inbound.
2. Outbound can stay open (bot needs outbound HTTPS to Discord/X links only for message content).
3. In Billing settings, enable **Billing Alert** (for example `$6` or `$8`).

Note: Billing Alert is an alert, not a hard spending cap.

### 3. SSH and install runtime
```bash
ssh root@<DROPLET_IP>
apt update && apt upgrade -y
apt install -y git python3 python3-venv python3-pip
```

### 4. Clone project and install dependencies
```bash
git clone <your-repo-url>
cd dbot
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

### 5. Configure environment
```bash
cp .env.example .env
nano .env
```

Set:
```env
DISCORD_TOKEN=YOUR_TOKEN
DISCORD_GUILD_NAME=asetianism
DISCORD_CHANNEL_NAME=asetianism
```

### 6. Run as systemd service
Create `/etc/systemd/system/dbot.service`:

```ini
[Unit]
Description=Discord Daily Utterance Bot
After=network.target

[Service]
Type=simple
User=root
WorkingDirectory=/root/dbot
EnvironmentFile=/root/dbot/.env
ExecStart=/root/dbot/.venv/bin/python /root/dbot/bot.py
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
```

Enable and start:
```bash
systemctl daemon-reload
systemctl enable dbot
systemctl start dbot
systemctl status dbot
```

View logs:
```bash
journalctl -u dbot -f
```

## Test Checklist (Discord)
1. Bot appears online in your server.
2. Startup message appears:
   - `An Asetianist by nature is a Loner.`
3. Run `!postnow` in target channel.
4. Confirm embed shows utterance text and working `Open on X` link.
5. Confirm `recent_posts.json` is created.
6. Run `!postnow` multiple times and verify no repeats in the last 7 posts.
7. Leave bot running and verify scheduled post at `03:33` `Europe/Lisbon`.

## Update Workflow
When you push new code:

```bash
cd /root/dbot
git pull
source .venv/bin/activate
pip install -r requirements.txt
systemctl restart dbot
journalctl -u dbot -n 50 --no-pager
```

## Docker?
Not needed for this project.

Use Docker only if you already standardize all deployments with containers.
