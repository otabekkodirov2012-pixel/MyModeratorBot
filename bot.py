import sqlite3

conn = sqlite3.connect('users.db')
cursor = conn.cursor()
cursor.execute('CREATE TABLE IF NOT EXISTS users (id INTEGER PRIMARY KEY)')
conn.commit() import os
import time
import logging
from collections import defaultdict, deque
from datetime import datetime, timedelta, timezone

from telegram import Update, ChatPermissions
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    ContextTypes,
    filters,
)

# Токен берётся из секретной переменной окружения
TOKEN = os.getenv("BOT_TOKEN")

logging.basicConfig(level=logging.INFO)
spam_history = defaultdict(deque)

if not TOKEN:
    raise RuntimeError("Не задан BOT_TOKEN!")


async def is_admin(update: Update, context: ContextTypes.DEFAULT_TYPE) -> bool:
    if not update.effective_user or not update.effective_chat:
        return False

    try:
        member = await context.bot.get_chat_member(
            update.effective_chat.id,
            update.effective_user.id,
        )
        return member.status in ("administrator", "creator")
    except Exception:
        return False


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE): 
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    cursor.execute('INSERT OR IGNORE INTO users (id) VALUES (?)', (update.effective_user.id,))
    conn.commit()
    cursor.execute('SELECT COUNT(*) FROM users')
    count = cursor.fetchone()[0]
    
    text = (f"Привет! Я бот-модератор. "
            f"Мой создатель Отабек (@TemaBruno) 🐶\n\n"
            f"/del — удалить сообщение (ответом на него)\n"
            f"/ban — заблокировать пользователя\n"
            f"/mute 10 — мут на 10 минут\n"
            f"/unmute — снять мут\n\n"
            f"Защита от частого спама включена.\n\n"
            f"Всего пользователей: {count}")
            
    await update.effective_message.reply_text(text)


async def delete_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    message = update.effective_message
    if not await is_admin(update, context):
        await message.reply_text("Эта команда доступна только администраторам.")
        return

    target = message.reply_to_message
    if not target:
        await message.reply_text("Ответь командой /del на сообщение.")
        return

    try:
        await target.delete()
        await message.delete()
    except Exception:
        await message.reply_text("Не получилось удалить. Проверь права бота.")


async def ban_user(update: Update, context: ContextTypes.DEFAULT_TYPE):
    message = update.effective_message
    if not await is_admin(update, context):
        await message.reply_text("Эта команда доступна только администраторам.")
        return

    target = message.reply_to_message
    if not target or not target.from_user:
        await message.reply_text("Ответь командой /ban на сообщение пользователя.")
        return

    if target.from_user.id == context.bot.id:
        await message.reply_text("Я не могу заблокировать самого себя.")
        return

    try:
        await context.bot.ban_chat_member(
            chat_id=update.effective_chat.id,
            user_id=target.from_user.id,
        )
        await message.reply_text("Пользователь заблокирован.")
    except Exception:
        await message.reply_text("Не удалось заблокировать. Проверь права бота.")


async def mute_user(update: Update, context: ContextTypes.DEFAULT_TYPE):
    message = update.effective_message
    if not await is_admin(update, context):
        await message.reply_text("Эта команда доступна только администраторам.")
        return

    target = message.reply_to_message
    if not target or not target.from_user:
        await message.reply_text("Ответь на сообщение командой /mute 10.")
        return

    try:
        minutes = int(context.args[0]) if context.args else 10
    except ValueError:
        await message.reply_text("Укажи число минут, например: /mute 10")
        return

    if not 1 <= minutes <= 10080:
        await message.reply_text("Укажи срок от 1 минуты до 7 дней.")
        return

    try:
        until = datetime.now(timezone.utc) + timedelta(minutes=minutes)
        await context.bot.restrict_chat_member(
            chat_id=update.effective_chat.id,
            user_id=target.from_user.id,
            permissions=ChatPermissions(can_send_messages=False),
            until_date=until,
        )
        await message.reply_text(f"Мут выдан на {minutes} мин.")
    except Exception:
        await message.reply_text("Не удалось выдать мут. Проверь права бота.")


async def unmute_user(update: Update, context: ContextTypes.DEFAULT_TYPE):
    message = update.effective_message
    if not await is_admin(update, context):
        await message.reply_text("Эта команда доступна только администраторам.")
        return

    target = message.reply_to_message
    if not target or not target.from_user:
        await message.reply_text("Ответь на сообщение пользователя командой /unmute.")
        return

    try:
        await context.bot.restrict_chat_member(
            chat_id=update.effective_chat.id,
            user_id=target.from_user.id,
            permissions=ChatPermissions(
                can_send_messages=True,
                can_send_audios=True,
                can_send_documents=True,
                can_send_photos=True,
                can_send_videos=True,
                can_send_video_notes=True,
                can_send_voice_notes=True,
                can_send_polls=True,
                can_send_other_messages=True,
                can_add_web_page_previews=True,
            ),
        )
        await message.reply_text("Мут снят.")
    except Exception:
        await message.reply_text("Не удалось снять мут. Проверь права бота.")


async def anti_spam(update: Update, context: ContextTypes.DEFAULT_TYPE):
    message = update.effective_message
    chat = update.effective_chat
    user = update.effective_user

    if not message or not chat or not user or chat.type == "private":
        return

    if message.text and message.text.startswith("/"):
        return

    if user.is_bot or await is_admin(update, context):
        return

    now = time.monotonic()
    key = (chat.id, user.id)
    history = spam_history[key]

    # Учитываем сообщения за последние 8 секунд
    while history and now - history[0] > 8:
        history.popleft()

    history.append(now)

    # 5 сообщений за 8 секунд — удаляем последнее и выдаём мут на минуту
    if len(history) >= 5:
        history.clear()
        try:
            await message.delete()
            await context.bot.restrict_chat_member(
                chat_id=chat.id,
                user_id=user.id,
                permissions=ChatPermissions(can_send_messages=False),
                until_date=datetime.now(timezone.utc) + timedelta(seconds=60),
            )
            await context.bot.send_message(
                chat_id=chat.id,
                text=f"🔇 {user.first_name} получил мут на 1 минуту за частый спам.",
            )
        except Exception:
            logging.exception("Не удалось применить антиспам")


app = Application.builder().token(TOKEN).build()

app.add_handler(CommandHandler("start", start))
app.add_handler(CommandHandler("del", delete_message))
app.add_handler(CommandHandler("ban", ban_user))
app.add_handler(CommandHandler("mute", mute_user))
app.add_handler(CommandHandler("unmute", unmute_user))
app.add_handler(MessageHandler(filters.ALL, anti_spam))

print("MyModeratorBot запущен!")
app.run_polling()
