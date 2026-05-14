import asyncio
import logging
from telethon import TelegramClient, events
from telethon.errors import FloodWaitError
from db import Database

log = logging.getLogger("tglogger")


def _media_type(event) -> str | None:
    if not event.message or not event.message.media:
        return None
    return type(event.message.media).__name__.replace("MessageMedia", "").lower() or "unknown"


async def _sender_info(event) -> tuple[int | None, str]:
    try:
        sender = await event.get_sender()
        if sender:
            parts = list(filter(None, [
                getattr(sender, "first_name", None),
                getattr(sender, "last_name", None),
            ]))
            name = " ".join(parts) or getattr(sender, "username", None) or "Unknown"
            return sender.id, name
    except Exception:
        pass
    return None, "Unknown"


async def _chat_display_name(event) -> str:
    try:
        chat = await event.get_chat()
        return getattr(chat, "title", None) or getattr(chat, "first_name", None) or "Unknown"
    except Exception:
        return "Unknown"


async def _safe_forward(client: TelegramClient, event, target: int) -> bool:
    try:
        await event.forward_to(target)
        return True
    except FloodWaitError as e:
        log.warning("FloodWait — sleeping %ds", e.seconds)
        await asyncio.sleep(e.seconds)
        try:
            await event.forward_to(target)
            return True
        except Exception as exc:
            log.error("Forward retry failed: %s", exc)
            return False
    except Exception as exc:
        log.error("Forward failed for msg %d: %s", event.id, exc)
        return False


def register_handlers(
    client: TelegramClient,
    db: Database,
    target_group: int,
    bot: TelegramClient | None = None,
    owner_id: int | None = None,
):

    @client.on(events.NewMessage)
    async def on_new_message(event):
        if event.out or await db.is_paused():
            return

        is_private = event.is_private
        is_watched_group = not is_private and await db.is_watched_chat(event.chat_id)

        if not is_private and not is_watched_group:
            return

        sender_id, sender_name = await _sender_info(event)
        chat_name = None if is_private else await _chat_display_name(event)
        text = event.text or ""
        media_type = _media_type(event)

        await db.save_message(
            message_id=event.id,
            sender_id=sender_id,
            sender_name=sender_name,
            chat_id=event.chat_id,
            chat_name=chat_name,
            text=text,
            media_type=media_type,
            date=event.date,
        )

        # For group messages, send a header label before the forwarded message
        if is_watched_group:
            try:
                await client.send_message(
                    target_group,
                    f"📌 **{chat_name}** — {sender_name}",
                )
            except Exception:
                pass

        # For watched users (VIP), add a star label before forwarding
        elif is_private and sender_id and await db.is_watched_user(sender_id):
            try:
                await client.send_message(target_group, f"⭐ **VIP** — {sender_name}")
            except Exception:
                pass

        forwarded = await _safe_forward(client, event, target_group)
        preview = (text[:60] + "…") if len(text) > 60 else text or f"[{media_type or 'media'}]"
        src = chat_name or "DM"
        log.info("NEW   id=%-10d  from=%-20s  src=%-15s  fwd=%s  %s",
                 event.id, sender_name, src, forwarded, preview)

    async def _push(text: str):
        """Send an alert via the bot DM (push notification) if configured."""
        if bot and owner_id:
            try:
                await bot.send_message(owner_id, text)
            except Exception as exc:
                log.error("Bot push failed: %s", exc)

    @client.on(events.MessageDeleted)
    async def on_message_deleted(event):
        if await db.is_paused():
            return
        # chat_id is available for channel/group deletions; None for private chats
        chat_id = getattr(event, "chat_id", None)
        for msg_id in event.deleted_ids:
            row = await db.get_message(msg_id, chat_id)
            if not row:
                continue
            await db.mark_deleted(msg_id)
            notice = (
                f"🗑 **Deleted message**\n"
                f"• From: {row['sender_name']} (`{row['sender_id']}`)\n"
                f"• Chat: {row['chat_name'] or 'DM'}\n"
                f"• Sent: {row['date']}\n"
                f"• Text: {row['text'] or '[media]'}"
            )
            try:
                await client.send_message(target_group, notice)
            except Exception as exc:
                log.error("Delete notice failed: %s", exc)
            await _push(notice)
        log.info("DELETED  ids=%s", event.deleted_ids)

    @client.on(events.MessageEdited)
    async def on_message_edited(event):
        if event.out or await db.is_paused():
            return

        is_private = event.is_private
        is_watched_group = not is_private and await db.is_watched_chat(event.chat_id)
        if not is_private and not is_watched_group:
            return

        new_text = event.text or ""
        row = await db.get_message(event.id, event.chat_id)
        await db.save_edit(event.id, event.chat_id, new_text)

        if row:
            notice = (
                f"✏️ **Edited message**\n"
                f"• From: {row['sender_name']}\n"
                f"• Chat: {row['chat_name'] or 'DM'}\n"
                f"• Before: {row['text'] or '[media]'}\n"
                f"• After: {new_text or '[media]'}"
            )
            try:
                await client.send_message(target_group, notice)
            except Exception as exc:
                log.error("Edit notice failed: %s", exc)
            await _push(notice)
        log.info("EDITED  id=%d", event.id)
