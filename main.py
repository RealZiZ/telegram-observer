"""
Telegram Observer
━━━━━━━━━━━━━━━━
• Userbot: logs all DMs + messages from watched groups/channels
• Control bot: manage via Telegram commands

Run:
    pip install telethon aiosqlite python-dotenv
    python main.py
"""

import asyncio
import logging
import os
import sys
from datetime import datetime
from logging.handlers import RotatingFileHandler

from dotenv import load_dotenv
from telethon import TelegramClient
from telethon.errors import SessionPasswordNeededError
from telethon.tl.functions.bots import SetBotCommandsRequest
from telethon.tl.types import BotCommand, BotCommandScopeDefault

from db import Database
from userbot import register_handlers
from bot import register_bot_handlers

load_dotenv()

API_ID       = int(os.getenv("API_ID", 0))
API_HASH     = os.getenv("API_HASH", "")
TARGET_GROUP = int(os.getenv("TARGET_GROUP", 0))
SESSION_NAME = os.getenv("SESSION_NAME", "session")
DB_PATH      = os.getenv("DB_PATH", "messages.db")
LOG_FILE     = os.getenv("LOG_FILE", "logger.log")
BOT_TOKEN    = os.getenv("BOT_TOKEN", "")
OWNER_ID     = int(os.getenv("OWNER_ID", 0))

missing = [k for k, v in {
    "API_ID": API_ID, "API_HASH": API_HASH, "TARGET_GROUP": TARGET_GROUP,
    "BOT_TOKEN": BOT_TOKEN, "OWNER_ID": OWNER_ID,
}.items() if not v]
if missing:
    sys.exit(f"ERROR: missing from .env: {', '.join(missing)}")


def _build_logger() -> logging.Logger:
    fmt = logging.Formatter(
        "%(asctime)s  %(levelname)-8s  %(message)s", datefmt="%Y-%m-%d %H:%M:%S"
    )
    logger = logging.getLogger("tglogger")
    logger.setLevel(logging.INFO)
    fh = RotatingFileHandler(LOG_FILE, maxBytes=5 * 1024 * 1024, backupCount=3, encoding="utf-8")
    fh.setFormatter(fmt)
    sh = logging.StreamHandler(sys.stdout)
    sh.setFormatter(fmt)
    logger.addHandler(fh)
    logger.addHandler(sh)
    return logger


log = _build_logger()


async def main():
    db = Database(DB_PATH)
    await db.connect()

    start_time = datetime.now()
    userbot = TelegramClient(SESSION_NAME, API_ID, API_HASH)
    bot = TelegramClient("bot_session", API_ID, API_HASH)

    register_handlers(userbot, db, TARGET_GROUP, bot=bot, owner_id=OWNER_ID)
    register_bot_handlers(bot, userbot, db, OWNER_ID, start_time)

    try:
        await userbot.start()
        await bot.start(bot_token=BOT_TOKEN)

        await bot(SetBotCommandsRequest(
            scope=BotCommandScopeDefault(),
            lang_code="",
            commands=[
                BotCommand("status",     "Uptime and summary"),
                BotCommand("stats",      "Message breakdown by sender"),
                BotCommand("recent",     "Last N messages (e.g. /recent 10)"),
                BotCommand("search",     "Search logs (e.g. /search hello)"),
                BotCommand("listchats",  "Show monitored groups/channels"),
                BotCommand("addchat",    "Monitor a chat (e.g. /addchat @group)"),
                BotCommand("removechat", "Stop monitoring a chat"),
                BotCommand("listusers",  "Show VIP watchlist"),
                BotCommand("adduser",    "Add to VIP watchlist"),
                BotCommand("removeuser", "Remove from VIP watchlist"),
                BotCommand("pause",      "Pause all logging"),
                BotCommand("resume",     "Resume logging"),
                BotCommand("export",     "Download the messages.db file"),
                BotCommand("help",       "Show all commands"),
            ],
        ))

        me = await userbot.get_me()
        bot_me = await bot.get_me()
        log.info("━" * 55)
        log.info("  Account  : %s (id=%s)", me.first_name, me.id)
        log.info("  Bot      : @%s", bot_me.username)
        log.info("  Target   : %s", TARGET_GROUP)
        log.info("  Owner ID : %s", OWNER_ID)
        log.info("━" * 55)

        await asyncio.gather(
            userbot.run_until_disconnected(),
            bot.run_until_disconnected(),
        )
    except SessionPasswordNeededError:
        log.critical("2FA: run once interactively to create the session file, then restart.")
        sys.exit(1)
    except (KeyboardInterrupt, asyncio.CancelledError):
        log.info("Shutdown requested.")
    except Exception as exc:
        log.error("Fatal error: %s", exc, exc_info=True)
    finally:
        try:
            await userbot.disconnect()
            await bot.disconnect()
        except Exception:
            pass
        await db.close()
        log.info("Shutdown complete.")


if __name__ == "__main__":
    asyncio.run(main())
