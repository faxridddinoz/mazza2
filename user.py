import json
import logging
from datetime import datetime, timedelta
from aiogram import Router, F, Bot
from aiogram.types import Message, CallbackQuery
from aiogram.filters import CommandStart, Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup

import database as db
from keyboards import (
    user_main_keyboard, start_inline_keyboard, category_keyboard,
    items_keyboard, item_detail_keyboard, location_keyboard,
    cancel_keyboard, order_action_keyboard
)

router = Router()
logger = logging.getLogger(__name__)

class OrderFSM(StatesGroup):
    waiting_name = State()
    waiting_phone = State()
    waiting_location = State()

user_carts = {}      
user_category = {}   

# ===== START =====
@router.message(CommandStart())
@router.message(F.text == "🚀 Boshlash")
async def cmd_start(message: Message, state: FSMContext):
    await state.clear()
    bot_info = await message.bot.get_me()
    text = (
        f"👋 Assalomu alaykum, <b>{message.from_user.first_name}</b>!\n\n"
        f"🤖 Men <b>{bot_info.first_name}</b> — ovqat yetkazib berish botiman.\n\n"
        "Quyidagilardan birini tanlang:"
    )
    await message.answer(text, reply_markup=user_main_keyboard(), parse_mode="HTML")
    await message.answer("📌 Menyu ko'rish yoki yordam olish:", reply_markup=start_inline_keyboard())

# ===== MY ORDERS =====
@router.message(F.text == "📦 Sizning zakazlaringiz")
async def my_orders(message: Message):
    order = await db.get_user_last_order(message.from_user.id)
    if not order:
        await message.answer("📭 Siz hali hech qanday zakaz bermagansiz.")
        return

    items_data = json.loads(order['items'])
    items_text = "\n".join([f"• {it['name']} x{it['count']} — {it['price'] * it['count']:,} so'm" for it in items_data])
    status_map = {
        'pending': '⏳ Kutilmoqda',
        'accepted': '🚴 Yetkazilmoqda',
        'completed': '✅ Yetkazildi',
        'rejected': '❌ Rad etildi'
    }
    status = status_map.get(order['status'], order['status'])

    text = (
        f"📦 <b>Oxirgi zakazingiz #{order['id']}</b>\n\n"
        f"{items_text}\n\n"
        f"💰 Jami: <b>{order['total_price']:,} so'm</b>\n"
        f"📌 Holat: {status}\n"
    )

    if order['status'] == 'accepted' and order['accepted_at'] and order['delivery_minutes']:
        accepted_at = datetime.fromisoformat(order['accepted_at'])
        deadline = accepted_at + timedelta(minutes=order['delivery_minutes'])
        now = datetime.utcnow()
        diff = deadline - now

        if diff.total_seconds() > 0:
            mins = int(diff.total_seconds() // 60)
            secs = int(diff.total_seconds() % 60)
            text += f"⏱ Yetib kelishiga: <b>{mins} daqiqa {secs} soniya</b> qoldi"
        else:
            late = now - deadline
            mins = int(late.total_seconds() // 60)
            secs = int(late.total_seconds() % 60)
            text += f"⚠️ Vaqt {mins} daqiqa {secs} soniya <b>o'tib ketdi</b>!"

    elif order['status'] == 'completed' and order['completed_at']:
        text += f"🕐 Yetkazildi: {order['completed_at'][:16]}"

    await message.answer(text, parse_mode="HTML")

# ===== MENU =====
@router.callback_query(F.data == "open_menu")
async def open_menu(call: CallbackQuery):
    await call.answer()
    categories = await db.get_categories()
    if not categories:
        await call.message.edit_text("😔 Menyu hozircha bo'sh. Keyinroq kiring.")
        return
    await call.message.edit_text(
        "🍽 <b>Menyudan kategoriya tanlang:</b>",
        reply_markup=category_keyboard(categories),
        parse_mode="HTML"
    )

@router.callback_query(F.data.startswith("cat_"))
async def select_category(call: CallbackQuery):
    await call.answer()
    category = call.data.replace("cat_", "")
    user_carts.setdefault(call.from_user.id, {})
    user_category[call.from_user.id] = category

    if category == "all":
        items = await db.get_menu_items()
    else:
        items = await db.get_menu_items(category)

    if not items:
        await call.answer("Bu kategoriyada mahsulot yo'q.", show_alert=True)
        return

    cart = user_carts.get(call.from_user.id, {})
    cat_title = "Barcha taomlar" if category == "all" else category.capitalize()
    await call.message.edit_text(
        f"🍽 <b>{cat_title}</b>\n\nTaom tanlang:",
        reply_markup=items_keyboard(items, cart),
        parse_mode="HTML"
    )

@router.callback_query(F.data.startswith("item_"))
async def select_item(call: CallbackQuery):
    await call.answer()
    item_id = int(call.data.replace("item_", ""))
    item = await db.get_menu_item(item_id)
    if not item:
        await call.answer("Mahsulot topilmadi.", show_alert=True)
        return

    cart = user_carts.setdefault(call.from_user.id, {})
    count = cart.get(item_id, 0)

    text = (
        f"🍽 <b>{item['name']}</b>\n\n"
        f"💰 Narxi: <b>{item['price']:,} so'm</b>\n"
        f"⏱ Yetib borish: <b>{item['delivery_time']} daqiqa</b>\n"
        f"📂 Tur: {item['category']}\n\n"
        f"Savatda: <b>{count} ta</b>"
    )

    if item['photo_id']:
        try:
            await call.message.answer_photo(
                photo=item['photo_id'],
                caption=text,
                reply_markup=item_detail_keyboard(item_id, count),
                parse_mode="HTML"
            )
            await call.message.delete()
            return
        except:
            pass

    await call.message.edit_text(text, reply_markup=item_detail_keyboard(item_id, count), parse_mode="HTML")

@router.callback_query(F.data.startswith("plus_"))
async def add_to_cart(call: CallbackQuery):
    item_id = int(call.data.replace("plus_", ""))
    cart = user_carts.setdefault(call.from_user.id, {})
    cart[item_id] = cart.get(item_id, 0) + 1

    item = await db.get_menu_item(item_id)
    count = cart[item_id]
    await call.message.edit_reply_markup(reply_markup=item_detail_keyboard(item_id, count))
    await call.answer(f"✅ {item['name']} qo'shildi ({count} ta)")

@router.callback_query(F.data.startswith("minus_"))
async def remove_from_cart(call: CallbackQuery):
    item_id = int(call.data.replace("minus_", ""))
    cart = user_carts.setdefault(call.from_user.id, {})
    if cart.get(item_id, 0) > 0:
        cart[item_id] -= 1
        if cart[item_id] == 0:
            del cart[item_id]

    item = await db.get_menu_item(item_id)
    count = cart.get(item_id, 0)
    await call.message.edit_reply_markup(reply_markup=item_detail_keyboard(item_id, count))
    await call.answer(f"➖ {item['name']} kamaytirildi ({count} ta)")

@router.callback_query(F.data == "back_to_items")
async def back_to_items(call: CallbackQuery):
    await call.answer()
    category = user_category.get(call.from_user.id, "all")
    if category == "all":
        items = await db.get_menu_items()
    else:
        items = await db.get_menu_items(category)

    cart = user_carts.get(call.from_user.id, {})
    cat_title = "Barcha taomlar" if category == "all" else category.capitalize()

    chat_id = call.message.chat.id
    try:
        await call.message.delete()
    except:
        pass
    
    # Xavfsiz xabar jo'natish (delete qilingandan so'ng call.message uzilishi mumkin)
    await call.bot.send_message(
        chat_id=chat_id,
        text=f"🍽 <b>{cat_title}</b>\n\nTaom tanlang:",
        reply_markup=items_keyboard(items, cart),
        parse_mode="HTML"
    )

@router.callback_query(F.data == "noop")
async def noop(call: CallbackQuery):
    await call.answer()

# ===== CHECKOUT =====
@router.callback_query(F.data == "checkout")
async def checkout(call: CallbackQuery, state: FSMContext):
    await call.answer()
    cart = user_carts.get(call.from_user.id, {})
    if not cart:
        await call.answer("Savat bo'sh!", show_alert=True)
        return

    await state.set_state(OrderFSM.waiting_name)
    await call.message.answer(
        "📝 Zakaz berish uchun ma'lumot kiritamiz.\n\n"
        "1️⃣ Ism va familiyangizni kiriting:",
        reply_markup=cancel_keyboard()
    )

@router.message(OrderFSM.waiting_name)
async def get_name(message: Message, state: FSMContext):
    if message.text == "❌ Bekor qilish":
        await state.clear()
        await message.answer("❌ Zakaz bekor qilindi.", reply_markup=user_main_keyboard())
        return
    await state.update_data(name=message.text)
    await state.set_state(OrderFSM.waiting_phone)
    await message.answer("2️⃣ Telefon raqamingizni kiriting:\n(Masalan: +998901234567)")

@router.message(OrderFSM.waiting_phone)
async def get_phone(message: Message, state: FSMContext):
    if message.text == "❌ Bekor qilish":
        await state.clear()
        await message.answer("❌ Zakaz bekor qilindi.", reply_markup=user_main_keyboard())
        return
    await state.update_data(phone=message.text)
    await state.set_state(OrderFSM.waiting_location)
    await message.answer(
        "3️⃣ Manzilingizni yuboring (lokatsiya yoki matn):",
        reply_markup=location_keyboard()
    )

@router.message(OrderFSM.waiting_location)
async def get_location(message: Message, state: FSMContext, bot: Bot):
    if message.text == "❌ Bekor qilish":
        await state.clear()
        await message.answer("❌ Zakaz bekor qilindi.", reply_markup=user_main_keyboard())
        return

    data = await state.get_data()
    cart = user_carts.get(message.from_user.id, {})

    if message.location:
        location_text = f"📍 {message.location.latitude}, {message.location.longitude}"
        location_link = f"https://maps.google.com/?q={message.location.latitude},{message.location.longitude}"
    else:
        location_text = message.text
        location_link = None

    items_list = []
    total = 0
    for item_id, count in cart.items():
        item = await db.get_menu_item(item_id)
        if item:
            items_list.append({
                "id": item_id, "name": item['name'],
                "price": item['price'], "count": count
            })
            total += item['price'] * count

    items_json = json.dumps(items_list, ensure_ascii=False)
    order_id = await db.create_order(
        user_id=message.from_user.id,
        user_name=data['name'],
        phone=data['phone'],
        location=location_text,
        items=items_json,
        total_price=total
    )

    items_text = "\n".join([f"• {it['name']} x{it['count']} — {it['price']*it['count']:,} so'm" for it in items_list])

    await message.answer(
        f"✅ <b>Zakazingiz qabul qilindi! #{order_id}</b>\n\n"
        f"{items_text}\n\n"
        f"💰 Jami: <b>{total:,} so'm</b>\n"
        f"👤 Ism: {data['name']}\n"
        f"📞 Tel: {data['phone']}\n"
        f"📍 Manzil: {location_text}\n\n"
        "⏳ Kuryerimiz tez orada bog'lanadi!",
        reply_markup=user_main_keyboard(),
        parse_mode="HTML"
    )

    order_text = (
        f"🆕 <b>Yangi zakaz #{order_id}</b>\n\n"
        f"👤 Mijoz: {data['name']}\n"
        f"📞 Tel: {data['phone']}\n"
        f"📍 Manzil: {location_text}\n"
    )
    if location_link:
        order_text += f"🗺 <a href='{location_link}'>Xaritada ko'rish</a>\n"
    order_text += f"\n🛒 Zakaz:\n{items_text}\n\n💰 Jami: <b>{total:,} so'm</b>"

    admins = await db.get_admins()
    couriers = await db.get_couriers()

    notified = set()
    for admin in admins:
        try:
            await bot.send_message(admin['user_id'], order_text,
                                   reply_markup=order_action_keyboard(order_id), parse_mode="HTML")
            notified.add(admin['user_id'])
        except Exception as e:
            logger.error(f"Admin {admin['user_id']} ga xabar ketmadi: {e}")

    for courier in couriers:
        if courier['user_id'] not in notified and not courier['is_on_break']:
            try:
                await bot.send_message(courier['user_id'], order_text,
                                       reply_markup=order_action_keyboard(order_id), parse_mode="HTML")
            except Exception as e:
                logger.error(f"Courier {courier['user_id']} ga xabar ketmadi: {e}")

    user_carts.pop(message.from_user.id, None)
    await state.clear()

# ===== HELP =====
@router.callback_query(F.data == "open_help")
async def open_help(call: CallbackQuery):
    await call.answer()
    text = (
        "❓ <b>Yordam</b>\n\n"
        "Mavjud buyruqlar:\n\n"
        "🚀 /start — Botni qayta ishga tushirish\n"
        "🍽 /menu — Menyuni ko'rish\n"
        "📦 /myorders — Oxirgi zakazim\n"
        "❓ /help — Yordam\n\n"
        "📞 Muammo bo'lsa admin bilan bog'laning."
    )
    await call.message.edit_text(text, parse_mode="HTML", reply_markup=start_inline_keyboard())

@router.message(Command("help"))
async def help_cmd(message: Message):
    text = (
        "❓ <b>Yordam</b>\n\n"
        "Mavjud buyruqlar:\n\n"
        "🚀 /start — Botni qayta ishga tushirish\n"
        "🍽 /menu — Menyuni ko'rish\n"
        "📦 /myorders — Oxirgi zakazim\n"
        "❓ /help — Yordam\n\n"
        "📞 Muammo bo'lsa admin bilan bog'laning."
    )
    await message.answer(text, parse_mode="HTML")

@router.message(Command("menu"))
async def menu_cmd(message: Message):
    categories = await db.get_categories()
    if not categories:
        await message.answer("😔 Menyu hozircha bo'sh.")
        return
    await message.answer("🍽 Kategoriya tanlang:", reply_markup=category_keyboard(categories))

@router.message(Command("myorders"))
async def myorders_cmd(message: Message):
    await my_orders(message)

@router.callback_query(F.data == "close")
async def close_menu(call: CallbackQuery):
    await call.answer()
    await call.message.delete()
