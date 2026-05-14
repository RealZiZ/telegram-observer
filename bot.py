import logging
from datetime import datetime
from telethon import TelegramClient, events
from telethon import utils as tg_utils
from db import Database

log = logging.getLogger("tglogger")

HELP_TEXT = """**Telegram Observer — Control Bot**

**Chats (groups/channels to monitor):**
`/addchat @username` or `/addchat -100...` — start monitoring
`/removechat <id>` — stop monitoring
`/listchats` — show all monitored chats

**Watched users (VIP list — highlighted in DM logs):**
`/adduser @username` or `/adduser <id>` — add to watchlist
`/removeuser <id>` — remove from watchlist
`/listusers` — show watchlist

**Stats & search:**
`/status` — uptime and summary
`/stats` — message breakdown by sender
`/recent [n]` — last N messages (default 5, max 20)
`/search <text>` — search message history

**Control:**
`/pause` — pause all logging
`/resume` — resume logging
`/export` — download the messages.db file
`/help` — show this message"""


def register_bot_handlers(
    bot: TelegramClient,
    userbot: TelegramClient,
    db: Database,
    owner_id: int,
    start_time: datetime,
):
    def is_owner(event) -> bool:
        return event.sender_id == owner_id

    @bot.on(events.NewMessage(pattern=r"^/(?:start|help)$"))
    async def cmd_help(event):
        if not is_owner(event):
            return
        await event.respond(HELP_TEXT)

    # ── Status & stats ────────────────────────────────────────────────────────
    @bot.on(events.NewMessage(pattern=r"^/status$"))
    async def cmd_status(event):
        if not is_owner(event):
            return
        paused = await db.is_paused()
        uptime = datetime.now() - start_time
        h, rem = divmod(int(uptime.total_seconds()), 3600)
        m, s = divmod(rem, 60)
        st = await db.stats()
        chats = await db.get_watched_chats()
        users = await db.get_watched_users()
        await event.respond(
            f"**Logger Status**\n\n"
            f"• State: {'⏸ Paused' if paused else '✅ Running'}\n"
            f"• Uptime: {h}h {m}m {s}s\n"
            f"• Total messages logged: {st['total']}\n"
            f"• Deleted captured: {st['deleted']}\n"
            f"• Edits captured: {st['edited']}\n"
            f"• Monitored groups/channels: {len(chats)}\n"
            f"• Watched users (VIP): {len(users)}"
        )

    @bot.on(events.NewMessage(pattern=r"^/stats$"))
    async def cmd_stats(event):
        if not is_owner(event):
            return
        st = await db.stats()
        lines = [
            "**Message Statistics**\n",
            f"• Total: {st['total']}",
            f"• Deleted: {st['deleted']}",
            f"• Edited: {st['edited']}",
            "\n**Top senders:**",
        ]
        for row in st["top_senders"]:
            lines.append(f"  └ {row['sender_name']}: {row['n']} msgs")
        await event.respond("\n".join(lines))

    # ── Chat management ───────────────────────────────────────────────────────
    @bot.on(events.NewMessage(pattern=r"^/addchat (.+)$"))
    async def cmd_addchat(event):
        if not is_owner(event):
            return
        arg = event.pattern_match.group(1).strip()
        try:
            arg = int(arg)  # numeric IDs must be int, not string
        except ValueError:
            pass
        try:
            entity = await userbot.get_entity(arg)
            chat_id = tg_utils.get_peer_id(entity)
            chat_name = getattr(entity, "title", None) or getattr(entity, "first_name", str(chat_id))
            chat_type = "channel" if getattr(entity, "broadcast", False) else "group"
            await db.add_watched_chat(chat_id, chat_name, chat_type)
            await event.respond(f"✅ Now monitoring **{chat_name}**\n`{chat_id}`")
        except Exception as exc:
            await event.respond(f"❌ {exc}\n\nTip: make sure your account is a member of that chat.")

    @bot.on(events.NewMessage(pattern=r"^/removechat (-?\d+)$"))
    async def cmd_removechat(event):
        if not is_owner(event):
            return
        chat_id = int(event.pattern_match.group(1))
        if await db.remove_watched_chat(chat_id):
            await event.respond(f"✅ Stopped monitoring `{chat_id}`.")
        else:
            await event.respond(f"❌ ID `{chat_id}` not in the list. Use /listchats to check.")

    @bot.on(events.NewMessage(pattern=r"^/listchats$"))
    async def cmd_listchats(event):
        if not is_owner(event):
            return
        chats = await db.get_watched_chats()
        if not chats:
            await event.respond("No chats monitored yet.\nUse `/addchat @username` to add one.")
            return
        lines = ["**Monitored chats:**"]
        for c in chats:
            lines.append(f"• **{c['chat_name']}** — `{c['chat_id']}` ({c['chat_type']})")
        await event.respond("\n".join(lines))

    # ── User watchlist ────────────────────────────────────────────────────────
    @bot.on(events.NewMessage(pattern=r"^/adduser (.+)$"))
    async def cmd_adduser(event):
        if not is_owner(event):
            return
        arg = event.pattern_match.group(1).strip()
        try:
            arg = int(arg)  # numeric IDs must be int, not string
        except ValueError:
            pass
        try:
            entity = await userbot.get_entity(arg)
            user_id = entity.id
            parts = list(filter(None, [
                getattr(entity, "first_name", None),
                getattr(entity, "last_name", None),
            ]))
            display_name = " ".join(parts) or getattr(entity, "username", str(user_id))
            username = getattr(entity, "username", None)
            await db.add_watched_user(user_id, username, display_name)
            uname_str = f"@{username}" if username else "no username"
            await event.respond(f"✅ Added **{display_name}** ({uname_str}) `{user_id}` to VIP watchlist.")
        except Exception as exc:
            await event.respond(f"❌ {exc}")

    @bot.on(events.NewMessage(pattern=r"^/removeuser (\d+)$"))
    async def cmd_removeuser(event):
        if not is_owner(event):
            return
        user_id = int(event.pattern_match.group(1))
        if await db.remove_watched_user(user_id):
            await event.respond(f"✅ Removed user `{user_id}` from watchlist.")
        else:
            await event.respond(f"❌ User `{user_id}` not in watchlist. Use /listusers.")

    @bot.on(events.NewMessage(pattern=r"^/listusers$"))
    async def cmd_listusers(event):
        if not is_owner(event):
            return
        users = await db.get_watched_users()
        if not users:
            await event.respond("Watchlist empty.\nUse `/adduser @username` to add someone.")
            return
        lines = ["**Watched users (VIP):**"]
        for u in users:
            uname = f"@{u['username']}" if u["username"] else "—"
            lines.append(f"• **{u['display_name']}** {uname} `{u['user_id']}`")
        await event.respond("\n".join(lines))

    # ── Search & recent ───────────────────────────────────────────────────────
    @bot.on(events.NewMessage(pattern=r"^/recent ?(\d*)$"))
    async def cmd_recent(event):
        if not is_owner(event):
            return
        raw = event.pattern_match.group(1)
        n = min(int(raw) if raw else 5, 20)
        msgs = await db.get_recent_messages(n)
        if not msgs:
            await event.respond("No messages logged yet.")
            return
        lines = [f"**Last {len(msgs)} messages:**"]
        for m in msgs:
            chat = m["chat_name"] or "DM"
            preview = (m["text"] or f"[{m['media_type'] or 'media'}]")[:80]
            lines.append(f"\n`{str(m['date'])[:16]}` **{m['sender_name']}** in {chat}\n└ {preview}")
        response = "\n".join(lines)
        if len(response) > 4000:
            response = response[:3990] + "\n…(truncated)"
        await event.respond(response)

    @bot.on(events.NewMessage(pattern=r"^/search (.+)$"))
    async def cmd_search(event):
        if not is_owner(event):
            return
        query = event.pattern_match.group(1).strip()
        results = await db.search_messages(query, limit=15)
        if not results:
            await event.respond(f"No results for `{query}`")
            return
        lines = [f"**Results for** `{query}` ({len(results)} found):"]
        for m in results:
            chat = m["chat_name"] or "DM"
            preview = (m["text"] or "")[:100]
            lines.append(f"\n`{str(m['date'])[:16]}` **{m['sender_name']}** in {chat}\n└ {preview}")
        response = "\n".join(lines)
        if len(response) > 4000:
            response = response[:3990] + "\n…(truncated)"
        await event.respond(response)

    # ── Control ───────────────────────────────────────────────────────────────
    @bot.on(events.NewMessage(pattern=r"^/pause$"))
    async def cmd_pause(event):
        if not is_owner(event):
            return
        await db.set_paused(True)
        await event.respond("⏸ Logging paused. Send /resume to restart.")

    @bot.on(events.NewMessage(pattern=r"^/resume$"))
    async def cmd_resume(event):
        if not is_owner(event):
            return
        await db.set_paused(False)
        await event.respond("▶️ Logging resumed.")

    @bot.on(events.NewMessage(pattern=r"^/export$"))
    async def cmd_export(event):
        if not is_owner(event):
            return
        try:
            await bot.send_file(event.chat_id, db.path, caption="📦 messages.db")
        except Exception as exc:
            await event.respond(f"❌ Export failed: {exc}")
