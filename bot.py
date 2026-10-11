#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Троицкий храм · Дмитров — бот-центр управления (v4)

Возможности:
  /schedule — ввод расписания на неделю (мастер: день/время/служба), превью,
              публикация одним нажатием: сайт + Telegram + VK + MAX.
  /notes    — список записок за неделю (новые помечены), отметить прочитанной/обработанной/удалить.
  /gallery  — подсказка по управлению галереей (через сайт).
  Автоуведомления: новые записки с сайта приходят в чат админам.

Запуск на хостинге/сервере:  python3 bot.py
(крон/системный сервис — см. DEPLOY.md)
"""

import asyncio
import html
import json
import logging
import re
import sqlite3
from datetime import datetime, timedelta

import httpx
from aiogram import Bot, Dispatcher, F
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import (
    CallbackQuery, ForceReply, InlineKeyboardButton, InlineKeyboardMarkup,
    KeyboardButton, Message, ReplyKeyboardMarkup, ReplyKeyboardRemove,
)
from aiogram.client.default import DefaultBotProperties
from aiogram.client.session.aiohttp import AiohttpSession

import config as cfg

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("troit-bot")

# Подключение: реверс-прокси (API_BASE_URL) или SOCKS (PROXY_URL) — для доступа к Telegram из РФ
session = None
if getattr(cfg, "PROXY_URL", ""):
    session = AiohttpSession(proxy=cfg.PROXY_URL, base=getattr(cfg, "API_BASE_URL", "") or None)
    log.info("Используется прокси: %s", cfg.PROXY_URL)
elif getattr(cfg, "API_BASE_URL", ""):
    # мост задаётся через base сессии (иначе aiogram игнорирует base_url у Bot)
    session = AiohttpSession(base=cfg.API_BASE_URL)
    log.info("Используется мост: %s", cfg.API_BASE_URL)

bot = Bot(cfg.BOT_TOKEN, session=session, default=DefaultBotProperties(parse_mode="HTML"))
dp = Dispatcher(storage=MemoryStorage())

DB_PATH = cfg.DB_PATH

# ---------------- локальное хранилище (записки-кэш, журнал публикаций) ---------------

def db() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    with db() as c:
        c.executescript("""
        CREATE TABLE IF NOT EXISTS publish_log(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            ts TEXT NOT NULL,
            target TEXT NOT NULL,
            ok INTEGER NOT NULL,
            detail TEXT
        );
        """)

async def log_publish(target: str, ok: bool, detail: str = ""):
    with db() as c:
        c.execute("INSERT INTO publish_log(ts,target,ok,detail) VALUES (?,?,?,?)",
                  (datetime.now().isoformat(timespec="seconds"), target, int(ok), detail))

async def get_schedule_from_site() -> list:
    async with httpx.AsyncClient(timeout=15) as cl:
        r = await cl.get(f"{cfg.SITE_URL}/api.php")
        r.raise_for_status()
        return r.json() if isinstance(r.json(), list) else []

# ---------------- проверка админа ---------------

def admin_only(func):
    async def wrapper(event, *args, **kwargs):
        # aiogram 3.7+ передаёт dispatcher как keyword — убираем, чтобы не падало
        kwargs.pop("dispatcher", None)
        uid = event.from_user.id if event.from_user else 0
        if uid not in cfg.ADMIN_IDS:
            await event.answer("⛔ Доступ только для администраторов.")
            return
        return await func(event, *args, **kwargs)
    return wrapper

# ---------------- FSM: ввод расписания ---------------

class Sched(StatesGroup):
    day = State()
    time = State()
    service = State()
    confirm = State()

def sched_kb():
    return ReplyKeyboardMarkup(
        keyboard=[[KeyboardButton(text="✅ Завершить ввод"), KeyboardButton(text="❌ Отмена")]],
        resize_keyboard=True)

def fmt_schedule(items: list) -> str:
    lines = [html.escape(i.get("day_name") or "") for i in items]
    out = [cfg.SCHEDULE_HEADER]
    for i in items:
        t = i.get("service_time") or ""
        out.append(f"📅 <b>{html.escape(i.get('day_name',''))}</b>{' — ' + html.escape(t) if t else ''}")
        out.append(f"   ✝ {html.escape(i.get('service_name',''))}")
    return "\n".join(out)

def sched_admin_kb():
    return InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(text="🚀 Опубликовать сейчас", callback_data="pub:now"),
        InlineKeyboardButton(text="🔁 Отложить на 1 час", callback_data="pub:delay3600"),
    ], [
        InlineKeyboardButton(text="🗑 Очистить черновик", callback_data="pub:clear"),
    ]])

DRAFT: list = []  # черновик расписания (в памяти; после публикации очищается)

@dp.message(Command("start"))
@admin_only
async def cmd_start(m: Message):
    await m.answer(
        "⛪ <b>Бот Троицкого храма</b>\n\n"
        "/schedule — ввести расписание на неделю и опубликовать\n"
        "/notes — записки за неделю\n"
        "/gallery — управление галереей (через сайт)\n"
        "/log — журнал публикаций",
        reply_markup=ReplyKeyboardRemove())

@dp.message(Command("schedule"))
@admin_only
async def cmd_schedule(m: Message, state: FSMContext):
    await state.clear()
    DRAFT.clear()
    await m.answer("Введите <b>день</b> (например: «15 марта, Сб» или «2026-03-15»):",
                   reply_markup=sched_kb())
    await state.set_state(Sched.day)

@dp.message(Sched.day, F.text)
@admin_only
async def sched_day(m: Message, state: FSMContext):
    t = m.text.strip()
    if t == "❌ Отмена":
        await state.clear(); DRAFT.clear()
        return await m.answer("Отменено.", reply_markup=ReplyKeyboardRemove())
    if t == "✅ Завершить ввод":
        if not DRAFT:
            return await m.answer("Черновик пуст. Добавьте хотя бы одну службу.")
        await state.set_state(Sched.confirm)
        return await m.answer(
            "<b>Превью расписания:</b>\n\n" + fmt_schedule(DRAFT) +
            "\n\nПубликуем на: сайт, Telegram, VK, MAX?",
            reply_markup=sched_admin_kb())
    DRAFT.append({"day_name": t, "service_time": "", "service_name": ""})
    await m.answer("Время службы (например 09:00, можно пропустить — напишите «-»):")
    await state.set_state(Sched.time)

@dp.message(Sched.time, F.text)
@admin_only
async def sched_time(m: Message, state: FSMContext):
    t = m.text.strip()
    if t == "❌ Отмена":
        await state.clear(); DRAFT.clear()
        return await m.answer("Отменено.", reply_markup=ReplyKeyboardRemove())
    DRAFT[-1]["service_time"] = "" if t in ("-", "") else t
    await m.answer("Название службы (например «Литургия», «Всенощное бдение»):")
    await state.set_state(Sched.service)

@dp.message(Sched.service, F.text)
@admin_only
async def sched_service(m: Message, state: FSMContext):
    t = m.text.strip()
    if t == "❌ Отмена":
        await state.clear(); DRAFT.clear()
        return await m.answer("Отменено.", reply_markup=ReplyKeyboardRemove())
    DRAFT[-1]["service_name"] = t
    await m.answer(f"Добавлено: {DRAFT[-1]['day_name']} {DRAFT[-1]['service_time']} {t}\n\n"
                   "Введите следующий <b>день</b> или нажмите «✅ Завершить ввод».",
                   reply_markup=sched_kb())
    await state.set_state(Sched.day)

@dp.callback_query(Sched.confirm, F.data.startswith("pub:"))
@admin_only
async def pub_confirm(c: CallbackQuery, state: FSMContext):
    action = c.data.split(":")[1]
    if action == "clear":
        DRAFT.clear(); await state.clear()
        await c.message.edit_text("Черновик очищен.")
        return await c.answer()
    if not DRAFT:
        return await c.answer("Черновик пуст", show_alert=True)

    if action == "delay3600":
        # отложенная публикация
        asyncio.get_event_loop().call_later(3600, lambda: asyncio.ensure_future(publish_all(c.message)))
        await c.message.edit_text("⏳ Публикация отложена на 1 час.")
        await state.clear()
        return await c.answer()

    await c.message.edit_text("⏳ Публикую...")
    report = await publish_all(c.message)
    await c.message.edit_text(report)
    await state.clear()
    await c.answer()

# ---------------- кросспостинг ---------------

async def pub_site(items: list):
    """Очистить старые и вставить новые записи расписания на сайт."""
    async with httpx.AsyncClient(timeout=20, headers={"X-Bot-Key": cfg.BOT_API_KEY}) as cl:
        # удалить все существующие
        existing = (await cl.get(f"{cfg.SITE_URL}/api.php")).json()
        for row in existing:
            await cl.delete(f"{cfg.SITE_URL}/api.php?id={row['id']}")
        for it in items:
            r = await cl.post(f"{cfg.SITE_URL}/api.php",
                              json={"day": it["day_name"], "time": it.get("service_time",""), "service": it.get("service_name","")})
            if r.status_code not in (200, 201):
                return False, f"site: {r.status_code}"
    return True, ""

async def pub_telegram(text: str):
    await bot.send_message(cfg.CHANNEL_ID, text, disable_web_page_preview=True)
    return True, ""

async def pub_vk(text: str):
    if not cfg.VK_TOKEN:
        return False, "VK_TOKEN не задан"
    async with httpx.AsyncClient(timeout=15) as cl:
        r = await cl.get("https://api.vk.com/method/wall.post", params={
            "owner_id": cfg.VK_OWNER_ID, "message": text, "access_token": cfg.VK_TOKEN, "v": "5.199"})
        data = r.json()
        if "error" in data:
            return False, data["error"].get("error_msg", "vk error")
    return True, ""

async def pub_max(text: str):
    if not cfg.MAX_TOKEN:
        return False, "MAX_TOKEN не задан"
    async with httpx.AsyncClient(timeout=15) as cl:
        r = await cl.post("https://botapi.max.ru/messages?access_token=" + cfg.MAX_TOKEN,
                          json={"text": text, "chat_id": cfg.MAX_CHAT_ID})
        if r.status_code >= 300:
            return False, f"max: {r.status_code}"
    return True, ""

async def publish_all(status_msg: Message) -> str:
    text = fmt_schedule(DRAFT)
    results = []

    ok, det = await safe(pub_site, list(DRAFT))
    results.append(("Сайт", ok, det)); await log_publish("site", ok, det)

    ok, det = await safe(pub_telegram, text)
    results.append(("Telegram", ok, det)); await log_publish("telegram", ok, det)

    ok, det = await safe(pub_vk, text)
    results.append(("VK", ok, det)); await log_publish("vk", ok, det)

    ok, det = await safe(pub_max, text)
    results.append(("MAX", ok, det)); await log_publish("max", ok, det)

    DRAFT.clear()
    lines = ["📋 <b>Результат публикации:</b>"]
    for name, ok, det in results:
        lines.append(f"{'✅' if ok else '❌'} {name}{(' — ' + det) if (det and not ok) else ''}")
    return "\n".join(lines)

async def safe(fn, *args):
    try:
        r = await fn(*args)
        if isinstance(r, tuple): return r
        return True, ""
    except Exception as e:
        log.exception("publish failed")
        return False, str(e)

# ---------------- записки ---------------

@dp.message(Command("notes"))
@admin_only
async def cmd_notes(m: Message):
    async with httpx.AsyncClient(timeout=15, headers={"X-Bot-Key": cfg.BOT_API_KEY}) as cl:
        r = await cl.get(f"{cfg.SITE_URL}/notes_api.php", params={"days": 7})
        if r.status_code != 200:
            return await m.answer("❌ Не удалось получить записки с сайта.")
        notes = r.json()

    if not notes:
        return await m.answer("Записок за неделю нет 🕊")

    type_lbl = {"health": "О здравии", "repose": "О упокоении"}
    status_lbl = {"new": "🆕", "read": "👁", "done": "✅"}
    for n in notes[:20]:  # Telegram: не более ~20 сообщений подряд
        kb = InlineKeyboardMarkup(inline_keyboard=[[
            InlineKeyboardButton(text="👁 Прочитано", callback_data=f"note:read:{n['id']}"),
            InlineKeyboardButton(text="✅ Обработано", callback_data=f"note:done:{n['id']}"),
            InlineKeyboardButton(text="🗑 Удалить", callback_data=f"note:del:{n['id']}"),
        ]])
        created = (n.get("created_at") or "")[:16]
        await m.answer(
            f"{status_lbl.get(n['status'],'')} <b>{type_lbl.get(n['note_type'],'')}</b> · {created}\n"
            f"✝ <b>Имена:</b>\n{html.escape(n.get('names') or '')}\n"
            + (f"\n💬 {html.escape(n['comment'])}" if n.get("comment") else "")
            + (f"\n📞 {html.escape(n['contact'])}" if n.get("contact") else ""),
            reply_markup=kb)

@dp.callback_query(F.data.startswith("note:"))
@admin_only
async def note_action(c: CallbackQuery):
    _, action, nid = c.data.split(":")
    async with httpx.AsyncClient(timeout=15, headers={"X-Bot-Key": cfg.BOT_API_KEY}) as cl:
        if action == "del":
            r = await cl.delete(f"{cfg.SITE_URL}/notes_api.php?id={nid}")
        else:
            r = await cl.post(f"{cfg.SITE_URL}/notes_api.php?action=status",
                              json={"id": int(nid), "status": action})
        ok = r.status_code == 200 and r.json().get("ok")
    await c.answer("Готово" if ok else "Ошибка", show_alert=not ok)
    if ok:
        try:
            await c.message.edit_reply_markup(reply_markup=None)
        except Exception:
            pass

# ---------------- уведомления о новых записках ---------------

async def poll_new_notes():
    """Каждые 60 сек проверяет новые записки и уведомляет админов."""
    seen = set()
    with db() as c:
        c.execute("CREATE TABLE IF NOT EXISTS seen_notes(id INTEGER PRIMARY KEY)")
        seen = {r[0] for r in c.execute("SELECT id FROM seen_notes").fetchall()}
    while True:
        try:
            async with httpx.AsyncClient(timeout=15, headers={"X-Bot-Key": cfg.BOT_API_KEY}) as cl:
                r = await cl.get(f"{cfg.SITE_URL}/notes_api.php", params={"days": 2, "status": "new"})
                if r.status_code == 200:
                    for n in r.json():
                        if n["id"] in seen:
                            continue
                        seen.add(n["id"])
                        with db() as c:
                            c.execute("INSERT OR IGNORE INTO seen_notes(id) VALUES (?)", (n["id"],))
                        type_lbl = {"health": "О здравии", "repose": "О упокоении"}
                        for admin in cfg.ADMIN_IDS:
                            try:
                                await bot.send_message(admin,
                                    f"🕊 <b>Новая записка</b> ({type_lbl.get(n['note_type'],'')})\n"
                                    f"✝ {html.escape((n.get('names') or '')[:500])}\n\n"
                                    f"/notes — все записки")
                            except Exception:
                                pass
        except Exception:
            log.exception("notes poll failed")
        await asyncio.sleep(60)

# ---------------- журнал ---------------

@dp.message(Command("log"))
@admin_only
async def cmd_log(m: Message):
    with db() as c:
        rows = c.execute("SELECT ts,target,ok,detail FROM publish_log ORDER BY id DESC LIMIT 20").fetchall()
    if not rows:
        return await m.answer("Журнал пуст.")
    lines = ["🗂 <b>Последние публикации:</b>"]
    for r in rows:
        lines.append(f"{'✅' if r['ok'] else '❌'} {r['ts']} · {r['target']}{(' · ' + r['detail']) if r['detail'] else ''}")
    await m.answer("\n".join(lines))

@dp.message(Command("gallery"))
@admin_only
async def cmd_gallery(m: Message):
    await m.answer("🖼 Галерея управляется через сайт:\n"
                   f"{cfg.SITE_URL}/#gallery → «#admin» → панель «Добавить фото».")

# ---------------- main ---------------

async def main():
    init_db()
    asyncio.ensure_future(poll_new_notes())
    log.info("Бот запущен")
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
