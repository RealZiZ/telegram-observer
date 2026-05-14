# Telegram Observer

A self-hosted Telegram logger that silently records every private message sent to you, tracks edits and deletions, and lets you monitor specific groups and channels — all controlled through a dedicated Telegram bot.

## Features

- **DM logging** — every incoming private message is saved and forwarded to your inbox group
- **Group/channel monitoring** — add any group you're in; its messages get logged too
- **Edit tracking** — captures the original text before and after every edit
- **Deletion alerts** — when someone deletes a message you already logged, you get a push notification via the bot with the original content
- **VIP watchlist** — mark specific users; their messages get a ⭐ label in your feed
- **Full-text search** — search your entire message history from the bot
- **Pause/resume** — toggle logging on and off without stopping the service
- **DB export** — the bot sends you the SQLite database file on demand
- **24/7 systemd service** — runs on any Linux machine, auto-restarts on crash

## Architecture

```
main.py        — entry point, runs both clients
userbot.py     — Telethon userbot (your account) — listens and logs
bot.py         — Telegram control bot — handles commands
db.py          — async SQLite database layer
```

Two Telethon clients run side by side in the same asyncio event loop:
- **Userbot** — logged in as your Telegram account, sees all your messages
- **Control bot** — a separate bot you message to manage the logger

## Requirements

- Python 3.10+
- A Telegram account with API credentials from [my.telegram.org](https://my.telegram.org)
- A Telegram bot token from [@BotFather](https://t.me/BotFather)
- A private group/channel to use as your message inbox

## Setup

**1. Clone and install dependencies**

```bash
git clone https://github.com/yourname/telegram-observer
cd telegram-observer
pip install telethon aiosqlite python-dotenv
```

**2. Configure**

```bash
cp .env.example .env
```

Fill in `.env`:

| Variable | Description |
|----------|-------------|
| `API_ID` | From [my.telegram.org](https://my.telegram.org) |
| `API_HASH` | From [my.telegram.org](https://my.telegram.org) |
| `TARGET_GROUP` | ID of your inbox group (e.g. `-1001234567890`) |
| `BOT_TOKEN` | From [@BotFather](https://t.me/BotFather) |
| `OWNER_ID` | Your Telegram user ID — get it from [@userinfobot](https://t.me/userinfobot) |

**3. Authenticate your account (first run only)**

```bash
python main.py
```

Telethon will prompt for your phone number and the verification code. After that, the session is saved and you won't be prompted again.

**4. Run as a 24/7 service (Linux)**

```ini
# /etc/systemd/system/tglogger.service
[Unit]
Description=Telegram Observer
After=network-online.target
Wants=network-online.target

[Service]
User=youruser
WorkingDirectory=/path/to/telegram-observer
ExecStart=/usr/bin/python3 main.py
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
```

```bash
sudo systemctl enable --now tglogger
```

## Bot Commands

### Monitoring
| Command | Description |
|---------|-------------|
| `/addchat @username` | Start logging a group or channel |
| `/addchat -1001234567890` | Add by numeric ID (for private groups) |
| `/removechat <id>` | Stop monitoring a chat |
| `/listchats` | Show all monitored chats |

### VIP Watchlist
| Command | Description |
|---------|-------------|
| `/adduser @username` | Add a user to the VIP list (⭐ label on their messages) |
| `/removeuser <id>` | Remove a user from the VIP list |
| `/listusers` | Show the VIP list |

### Stats & Search
| Command | Description |
|---------|-------------|
| `/status` | Uptime, message counts, current state |
| `/stats` | Message breakdown by sender |
| `/recent 10` | Last N logged messages |
| `/search <text>` | Full-text search across all logged messages |

### Control
| Command | Description |
|---------|-------------|
| `/pause` | Pause all logging |
| `/resume` | Resume logging |
| `/export` | Receive the SQLite database file |
| `/help` | Show all commands |

## How to get a private group's ID

Forward any message from that group to [@userinfobot](https://t.me/userinfobot) — it will show the chat ID. Use that with `/addchat`.

## Database

Messages are stored in an SQLite database (`messages.db`) with three tables:

- `messages` — every logged message with sender, chat, text, media type, timestamps
- `message_edits` — full edit history (before/after for every edit)
- `watched_chats` — groups and channels being monitored
- `watched_users` — VIP watchlist

## Notes

- Only **you** can use the control bot — it checks your Telegram user ID against `OWNER_ID` and ignores everyone else
- The session file (`session.session`) is equivalent to your Telegram login — keep it private and never commit it
- Telegram does not always include the chat ID in deletion events for private chats, so deletion detection works best for monitored groups
