import json
import asyncio
import logging
from aiogram import Router, F, Bot
from aiogram.types import Message, CallbackQuery
from aiogram.filters import Command

import database as db
from keyboards import (
    courier_main_keyboard,
    delivery_time_keyboard,
    complete_order_keyboard,
)

router = Router()
logger = logging.getLogger(__name__)

# Aktiv taymerlar {order_id: task}
active_timers = {}
# Tushlik ovozlari
break_votes_set = set()
break_task = None

# ===== COURIER PANEL =====
@router.message(Command("courier"))
async def courier_panel(message: Message):
    if not await db.is_courier(message.from_user.id):
        await message.answer("❌ Sizda kuryer huquqi yo'q.")
        return
    await message.answer(
        "🚴 <b>Kuryer paneli</b>\n\nZakazlar kelib tushganda bu yerda ko'rinadi.",
        reply_markup=courier_main_keyboard(),
        parse_mode="HTML"
    )

# ===== ACCEPT ORDER =====
@router.callback_query(F.data.startswith("accept_"))
async def accept_order(call: CallbackQuery):
    order_id = int(call.data.replace("accept_", ""))
    order = await db.get_order(order_id)
    if not order:
        await call.answer("Zakaz topilmadi.", show_alert=True)
        return
    if order['status'] != 'pending':
        await call.answer("Bu zakaz allaqachon qayta ishlangan.", show_alert=True)
        return

    await call.message.edit_reply_markup(reply_markup=delivery_time_keyboard(order_id))
    await call.answer("⏱ Yetkazish vaqtini tanlang")

# ===== SET DELIVERY TIME =====
@router.callback_query(F.data.startswith("time_"))
async def set_delivery_time(call: CallbackQuery, bot: Bot):
    parts = call.data.split("_")
    order_id = int(parts[1])
    minutes = int(parts[2])

    order = await db.get_order(order_id)
    if not order or order['status'] != 'pending':
        await call.answer("Zakaz allaqachon qayta ishlangan.", show_alert=True)
        return

    is_ok = await db.is_admin(call.from_user.id) or await db.is_courier(call.from_user.id)
    if not is_ok:
        await call.answer("Ruxsat yo'q.", show_alert=True)
        return

    await db.accept_order(order_id, call.from_user.id, minutes)

    items_data = json.loads(order['items'])
    items_text = "\n".join([
        f"• {it['name']} x{it['count']} — {it['price'] * it['count']:,} so'm"
        for it in items_data
    ])

    await call.message.edit_text(
        f"✅ <b>Zakaz #{order_id} qabul qilindi!</b>\n\n"
        f"👤 Mijoz: {order['user_name']}\n"
        f"📞 Tel: {order['phone']}\n"
        f"📍 Manzil: {order['location']}\n\n"
        f"🛒 Zakaz:\n{items_text}\n\n"
        f"💰 Jami: {order['total_price']:,} so'm\n"
        f"⏱ Taxminiy vaqt: {minutes} daqiqa",
        parse_mode="HTML",
        reply_markup=complete_order_keyboard(order_id)
    )

    # Mijozga xabar
    try:
        await bot.send_message(
            order['user_id'],
            f"🚴 <b>Zakazingiz #{order_id} qabul qilindi!</b>\n\n"
            f"⏱ Taxminan <b>{minutes} daqiqa</b> ichida yetkaziladi.\n\n"
            "📦 «Sizning zakazlaringiz» bo'limida jarayon ko'rishingiz mumkin.",
            parse_mode="HTML"
        )
    except Exception as e:
        logger.error(f"Mijozga xabar ketmadi: {e}")

    # Taymerni boshlash
    if order_id in active_timers:
        active_timers[order_id].cancel()

    task = asyncio.create_task(
        delivery_timer(bot, order_id, order['user_id'], call.from_user.id, minutes)
    )
    active_timers[order_id] = task
    await call.answer(f"✅ Qabul qilindi! {minutes} daqiqa taymer boshlandi.")

# ===== DELIVERY TIMER =====
async def delivery_timer(bot: Bot, order_id: int, user_id: int, courier_id: int, minutes: int):
    await asyncio.sleep(minutes * 60)

    order = await db.get_order(order_id)
    if not order or order['status'] != 'accepted':
        return

    # Vaqt o'tib ketdi - har daqiqada ogohlantirish
    late_minutes = 0
    while True:
        late_minutes += 1
        await asyncio.sleep(60)
        order = await db.get_order(order_id)
        if not order or order['status'] != 'accepted':
            break
        try:
            await bot.send_message(
                courier_id,
                f"⚠️ Zakaz #{order_id}: yetkazish vaqti <b>{late_minutes} daqiqa</b> o'tib ketdi!",
                parse_mode="HTML"
            )
        except Exception as e:
            logger.error(f"Kuryerga ogoh xabar ketmadi: {e}")
        if late_minutes >= 10:
            break

# ===== REJECT ORDER =====
@router.callback_query(F.data.startswith("reject_"))
async def reject_order(call: CallbackQuery, bot: Bot):
    order_id = int(call.data.replace("reject_", ""))
    order = await db.get_order(order_id)
    if not order:
        await call.answer("Zakaz topilmadi.", show_alert=True)
        return
    if order['status'] != 'pending':
        await call.answer("Bu zakaz allaqachon qayta ishlangan.", show_alert=True)
        return

    await db.reject_order(order_id)
    await call.message.edit_text(
        f"❌ <b>Zakaz #{order_id} rad etildi.</b>",
        parse_mode="HTML"
    )
    try:
        await bot.send_message(
            order['user_id'],
            f"😔 #{order_id} zakazingiz rad etildi.\n"
            "Iltimos, qayta urinib ko'ring yoki biz bilan bog'laning."
        )
    except Exception as e:
        logger.error(f"Rad xabari ketmadi: {e}")
    await call.answer("Rad etildi.")

# ===== COMPLETE ORDER =====
@router.callback_query(F.data.startswith("complete_"))
async def complete_order(call: CallbackQuery, bot: Bot):
    order_id = int(call.data.replace("complete_", ""))
    order = await db.get_order(order_id)
    if not order:
        await call.answer("Zakaz topilmadi.", show_alert=True)
        return

    await db.complete_order(order_id)

    # Taymerni to'xtatish
    if order_id in active_timers:
        active_timers[order_id].cancel()
        del active_timers[order_id]

    await call.message.edit_text(
        f"✅ <b>Zakaz #{order_id} muvaffaqiyatli yetkazildi!</b>",
        parse_mode="HTML"
    )
    try:
        await bot.send_message(
            order['user_id'],
            f"🎉 <b>Zakazingiz #{order_id} yetkazildi!</b>\n\nRahmat! Yana buyurtma bering 😊",
            parse_mode="HTML"
        )
    except Exception as e:
        logger.error(f"Yetkazildi xabari ketmadi: {e}")
    await call.answer("✅ Yetkazildi deb belgilandi!")

# ===== LUNCH / BREAK =====
@router.message(F.text == "🍽 Tushlik / Dam olish")
async def lunch_break(message: Message, bot: Bot):
    global break_task

    if not await db.is_courier(message.from_user.id):
        return

    couriers = await db.get_couriers()
    if not couriers:
        return

    uid = message.from_user.id

    if uid in break_votes_set:
        await message.answer(
            f"✅ Siz allaqachon ovoz bergansiz. "
            f"({len(break_votes_set)}/{len(couriers)}) Boshqa kuryrlar ham bosishini kuting."
        )
        return

    break_votes_set.add(uid)
    voted = len(break_votes_set)
    total = len(couriers)

    await message.answer(
        f"✅ Ovozingiz qabul qilindi! ({voted}/{total})\n"
        "Barcha kuryrlar ovoz bersa, tushlik boshlanadi."
    )

    # Barcha kuryerlar ovoz berdimi?
    all_ids = {c['user_id'] for c in couriers}
    if break_votes_set >= all_ids:
        break_votes_set.clear()
        for c in couriers:
            try:
                await bot.send_message(
                    c['user_id'],
                    "🍽 <b>Tushlik vaqti boshlandi!</b>\n"
                    "⏱ 1 soat dam olasiz.\n\n"
                    "Bu vaqtda zakazlar qabul qilinmaydi.",
                    parse_mode="HTML"
                )
            except Exception as e:
                logger.error(f"Tushlik xabari ketmadi: {e}")

        if break_task:
            break_task.cancel()
        break_task = asyncio.create_task(
            break_timer(bot, [c['user_id'] for c in couriers])
        )

async def break_timer(bot: Bot, courier_ids: list):
    # Har daqiqada tekshir, 30/15/5/1 daqiqada ogohlantir
    for elapsed in range(1, 61):
        await asyncio.sleep(60)
        remaining = 60 - elapsed
        if remaining in [30, 15, 5, 1]:
            for uid in courier_ids:
                try:
                    await bot.send_message(
                        uid,
                        f"⏰ Tushlikka <b>{remaining} daqiqa</b> qoldi!",
                        parse_mode="HTML"
                    )
                except Exception as e:
                    logger.error(f"Tushlik ogoh xabari ketmadi: {e}")

    # Tushlik tugadi
    for uid in courier_ids:
        try:
            await bot.send_message(
                uid,
                "✅ <b>Tushlik vaqti tugadi!</b>\nIsh boshlanmoqda...",
                parse_mode="HTML"
            )
        except Exception as e:
            logger.error(f"Tushlik tugadi xabari ketmadi: {e}")
