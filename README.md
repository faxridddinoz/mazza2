import logging
from aiogram import Router, F, Bot
from aiogram.types import Message, CallbackQuery
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup

import database as db
from keyboards import (
    admin_main_keyboard, admin_menu_keyboard, admin_delete_menu_keyboard,
    confirm_delete_keyboard, admin_cancel_keyboard, category_select_keyboard,
    order_action_keyboard, promo_cancel_keyboard
)

router = Router()
logger = logging.getLogger(__name__)

# ===== STATES =====
class AddMenuFSM(StatesGroup):
    name = State()
    photo = State()
    price = State()
    delivery_time = State()
    category = State()

class AddAdminFSM(StatesGroup):
    waiting = State()

class AddCourierFSM(StatesGroup):
    waiting = State()

class AddChannelFSM(StatesGroup):
    waiting = State()

class PromoFSM(StatesGroup):
    media = State()
    caption = State()

class CancelOrderFSM(StatesGroup):
    waiting = State()

# ===== ADMIN PANEL =====
@router.message(Command("admin"))
async def admin_panel(message: Message):
    if not await db.is_admin(message.from_user.id):
        await message.answer("❌ Sizda admin huquqi yo'q.")
        return
    await message.answer("🛠 <b>Admin panel</b>", reply_markup=admin_main_keyboard(), parse_mode="HTML")

# ===== MENU MANAGEMENT =====
@router.message(F.text == "🍽 Menyu")
async def admin_menu_btn(message: Message):
    if not await db.is_admin(message.from_user.id):
        return
    await message.answer("🍽 Menyu boshqaruvi:", reply_markup=admin_menu_keyboard())

@router.callback_query(F.data == "menu_add")
async def menu_add_start(call: CallbackQuery, state: FSMContext):
    if not await db.is_admin(call.from_user.id):
        await call.answer("Ruxsat yo'q.", show_alert=True)
        return
    await state.set_state(AddMenuFSM.name)
    await call.message.answer("📝 Taom nomini kiriting:", reply_markup=admin_cancel_keyboard())
    await call.answer()

@router.message(AddMenuFSM.name)
async def menu_add_name(message: Message, state: FSMContext):
    if message.text == "❌ Bekor qilish":
        await state.clear()
        await message.answer("❌ Bekor qilindi.", reply_markup=admin_main_keyboard())
        return
    await state.update_data(name=message.text)
    await state.set_state(AddMenuFSM.photo)
    await message.answer("🖼 Taom rasmini yuboring (o'tkazib yuborish uchun 'skip' yozing):")

@router.message(AddMenuFSM.photo)
async def menu_add_photo(message: Message, state: FSMContext):
    if message.text == "❌ Bekor qilish":
        await state.clear()
        await message.answer("❌ Bekor qilindi.", reply_markup=admin_main_keyboard())
        return
    photo_id = None
    if message.photo:
        photo_id = message.photo[-1].file_id
    elif message.text and message.text.lower() == "skip":
        photo_id = None
    else:
        await message.answer("⚠️ Rasm yuboring yoki 'skip' yozing.")
        return
    await state.update_data(photo_id=photo_id)
    await state.set_state(AddMenuFSM.price)
    await message.answer("💰 Narxini kiriting (so'mda, faqat raqam):")

@router.message(AddMenuFSM.price)
async def menu_add_price(message: Message, state: FSMContext):
    if message.text == "❌ Bekor qilish":
        await state.clear()
        await message.answer("❌ Bekor qilindi.", reply_markup=admin_main_keyboard())
        return
    if not message.text.isdigit():
        await message.answer("⚠️ Faqat raqam kiriting!")
        return
    await state.update_data(price=int(message.text))
    await state.set_state(AddMenuFSM.delivery_time)
    await message.answer("⏱ Yetib borish vaqtini kiriting (daqiqada, faqat raqam):")

@router.message(AddMenuFSM.delivery_time)
async def menu_add_time(message: Message, state: FSMContext):
    if message.text == "❌ Bekor qilish":
        await state.clear()
        await message.answer("❌ Bekor qilindi.", reply_markup=admin_main_keyboard())
        return
    if not message.text.isdigit():
        await message.answer("⚠️ Faqat raqam kiriting!")
        return
    await state.update_data(delivery_time=int(message.text))
    await state.set_state(AddMenuFSM.category)
    await message.answer("📂 Kategoriyani tanlang:", reply_markup=category_select_keyboard())

@router.callback_query(F.data.startswith("newcat_"))
async def menu_add_category(call: CallbackQuery, state: FSMContext):
    # Faqat AddMenuFSM.category holatida ishlaydi
    current_state = await state.get_state()
    if current_state != AddMenuFSM.category:
        await call.answer("Bu tugma hozir ishlamaydi.", show_alert=True)
        return

    if not await db.is_admin(call.from_user.id):
        await call.answer("Ruxsat yo'q.", show_alert=True)
        return

    category = call.data.replace("newcat_", "")
    data = await state.get_data()

    # Majburiy maydonlarni tekshirish
    if not data.get('name') or data.get('price') is None or data.get('delivery_time') is None:
        await call.answer("Ma'lumotlar to'liq emas. Qaytadan boshlang.", show_alert=True)
        await state.clear()
        return

    await db.add_menu_item(
        name=data['name'],
        photo_id=data.get('photo_id'),
        price=data['price'],
        delivery_time=data['delivery_time'],
        category=category
    )
    await state.clear()
    await call.message.answer(
        f"✅ <b>{data['name']}</b> menyuga qo'shildi!\n"
        f"📂 Tur: {category}\n"
        f"💰 Narx: {data['price']:,} so'm\n"
        f"⏱ Vaqt: {data['delivery_time']} daqiqa",
        reply_markup=admin_main_keyboard(),
        parse_mode="HTML"
    )
    await call.answer("✅ Qo'shildi!")

# ===== VIEW MENU =====
@router.callback_query(F.data == "menu_view")
async def menu_view(call: CallbackQuery):
    if not await db.is_admin(call.from_user.id):
        await call.answer("Ruxsat yo'q.", show_alert=True)
        return
    items = await db.get_menu_items()
    if not items:
        await call.answer("Menyu bo'sh!", show_alert=True)
        return

    # Kategoriya bo'yicha guruhlash
    categories = {}
    for item in items:
        categories.setdefault(item['category'], []).append(item)

    # 4096 char limit uchun bo'lib yuborish
    text = "📋 <b>Menyu ro'yxati:</b>\n\n"
    messages = []
    for cat, cat_items in categories.items():
        chunk = f"<b>📂 {cat.upper()}</b>\n"
        for item in cat_items:
            chunk += f"  • {item['name']} — {item['price']:,} so'm ({item['delivery_time']} min)\n"
        chunk += "\n"
        if len(text) + len(chunk) > 4000:
            messages.append(text)
            text = chunk
        else:
            text += chunk

    if text.strip():
        messages.append(text)

    for msg in messages:
        await call.message.answer(msg, parse_mode="HTML")
    await call.answer()

# ===== DELETE MENU =====
@router.callback_query(F.data == "menu_delete")
async def menu_delete_list(call: CallbackQuery):
    if not await db.is_admin(call.from_user.id):
        await call.answer("Ruxsat yo'q.", show_alert=True)
        return
    items = await db.get_all_menu_items_admin()
    if not items:
        await call.answer("Menyu bo'sh!", show_alert=True)
        return
    await call.message.edit_text(
        "🗑 O'chirish uchun taomni tanlang:",
        reply_markup=admin_delete_menu_keyboard(items)
    )

@router.callback_query(F.data.startswith("del_item_"))
async def delete_item_confirm(call: CallbackQuery):
    item_id = int(call.data.replace("del_item_", ""))
    item = await db.get_menu_item(item_id)
    if not item:
        await call.answer("Topilmadi.", show_alert=True)
        return
    kb, word = confirm_delete_keyboard(item_id, item['category'])
    await call.message.edit_text(
        f"⚠️ Siz bu <b>{word}</b> o'chirmoqchimisiz?\n\n"
        f"<b>{item['name']}</b> — {item['price']:,} so'm",
        reply_markup=kb,
        parse_mode="HTML"
    )

@router.callback_query(F.data.startswith("confirm_del_"))
async def confirm_delete(call: CallbackQuery):
    item_id = int(call.data.replace("confirm_del_", ""))
    item = await db.get_menu_item(item_id)
    if not item:
        await call.answer("Topilmadi.", show_alert=True)
        return
    await db.delete_menu_item(item_id)
    await call.message.edit_text(
        f"✅ <b>{item['name']}</b> menyudan o'chirildi.",
        parse_mode="HTML"
    )
    await call.answer("O'chirildi!")

# ===== ADD ADMIN =====
@router.message(F.text == "👤 Admin qo'shish")
async def add_admin_start(message: Message, state: FSMContext):
    if not await db.is_admin(message.from_user.id):
        return
    await state.set_state(AddAdminFSM.waiting)
    await message.answer(
        "👤 Yangi admin qo'shish uchun uning Telegram ID sini kiriting\n"
        "(@userinfobot ga /start yuboring — ID sini oladi):",
        reply_markup=admin_cancel_keyboard()
    )

@router.message(AddAdminFSM.waiting)
async def add_admin_process(message: Message, state: FSMContext, bot: Bot):
    if message.text == "❌ Bekor qilish":
        await state.clear()
        await message.answer("❌ Bekor qilindi.", reply_markup=admin_main_keyboard())
        return
    if not message.text.lstrip('-').isdigit():
        await message.answer("⚠️ Faqat raqam (Telegram ID) kiriting!")
        return
    new_id = int(message.text)
    try:
        user_info = await bot.get_chat(new_id)
        full_name = user_info.full_name
        username = user_info.username or ""
    except Exception:
        full_name = "Noma'lum"
        username = ""
    await db.add_admin(new_id, username, full_name)
    await state.clear()
    await message.answer(
        f"✅ <b>{full_name}</b> (ID: {new_id}) admin sifatida qo'shildi!",
        reply_markup=admin_main_keyboard(),
        parse_mode="HTML"
    )

# ===== ADD COURIER =====
@router.message(F.text == "🚴 Dastavchi qo'shish")
async def add_courier_start(message: Message, state: FSMContext):
    if not await db.is_admin(message.from_user.id):
        return
    await state.set_state(AddCourierFSM.waiting)
    await message.answer(
        "🚴 Yangi dastavchi qo'shish uchun uning Telegram ID sini kiriting:",
        reply_markup=admin_cancel_keyboard()
    )

@router.message(AddCourierFSM.waiting)
async def add_courier_process(message: Message, state: FSMContext, bot: Bot):
    if message.text == "❌ Bekor qilish":
        await state.clear()
        await message.answer("❌ Bekor qilindi.", reply_markup=admin_main_keyboard())
        return
    if not message.text.lstrip('-').isdigit():
        await message.answer("⚠️ Faqat raqam (Telegram ID) kiriting!")
        return
    cid = int(message.text)
    try:
        user_info = await bot.get_chat(cid)
        full_name = user_info.full_name
        username = user_info.username or ""
    except Exception:
        full_name = "Noma'lum"
        username = ""
    await db.add_courier(cid, username, full_name)
    await state.clear()
    await message.answer(
        f"✅ <b>{full_name}</b> (ID: {cid}) dastavchi sifatida qo'shildi!\n"
        "Endi u /courier buyrug'i orqali paneliga kira oladi.",
        reply_markup=admin_main_keyboard(),
        parse_mode="HTML"
    )

# ===== PROMO CHANNEL =====
@router.message(F.text == "📢 Reklama kanali qo'shish")
async def add_channel_start(message: Message, state: FSMContext):
    if not await db.is_admin(message.from_user.id):
        return
    await state.set_state(AddChannelFSM.waiting)
    await message.answer(
        "📢 Kanal ID sini kiriting.\n\n"
        "Masalan: @mening_kanalim yoki -1001234567890\n\n"
        "⚠️ Botni kanalga admin qilib qo'shing!",
        reply_markup=admin_cancel_keyboard()
    )

@router.message(AddChannelFSM.waiting)
async def add_channel_process(message: Message, state: FSMContext, bot: Bot):
    if message.text == "❌ Bekor qilish":
        await state.clear()
        await message.answer("❌ Bekor qilindi.", reply_markup=admin_main_keyboard())
        return
    channel_id = message.text.strip()
    try:
        chat = await bot.get_chat(channel_id)
        await db.add_promo_channel(str(chat.id), chat.title)
        await state.clear()
        await message.answer(
            f"✅ Kanal <b>{chat.title}</b> qo'shildi!",
            reply_markup=admin_main_keyboard(),
            parse_mode="HTML"
        )
    except Exception as e:
        await message.answer(
            f"❌ Xatolik: {e}\n"
            "Kanal ID ni tekshiring va botni kanalga admin qilib qo'shing."
        )

# ===== PROMO SEND =====
@router.message(F.text == "📣 Reklama yuborish")
async def promo_send_start(message: Message, state: FSMContext):
    if not await db.is_admin(message.from_user.id):
        return
    await state.set_state(PromoFSM.media)
    await message.answer(
        "📣 Reklama yuborish\n\n"
        "1️⃣ Avval rasm yoki video yuboring\n"
        "(faqat matn bo'lsa 'skip' yozing):",
        reply_markup=promo_cancel_keyboard()
    )

@router.message(PromoFSM.media)
async def promo_get_media(message: Message, state: FSMContext):
    if message.text == "❌ Bekor qilish":
        await state.clear()
        await message.answer("❌ Bekor qilindi.", reply_markup=admin_main_keyboard())
        return
    media_type = None
    media_id = None
    if message.photo:
        media_type = "photo"
        media_id = message.photo[-1].file_id
    elif message.video:
        media_type = "video"
        media_id = message.video.file_id
    elif message.text and message.text.lower() == "skip":
        media_type = "none"
    else:
        await message.answer("⚠️ Rasm, video yuboring yoki 'skip' yozing.")
        return
    await state.update_data(media_type=media_type, media_id=media_id)
    await state.set_state(PromoFSM.caption)
    await message.answer("2️⃣ Endi reklama matnini kiriting:")

@router.message(PromoFSM.caption)
async def promo_send(message: Message, state: FSMContext, bot: Bot):
    if message.text == "❌ Bekor qilish":
        await state.clear()
        await message.answer("❌ Bekor qilindi.", reply_markup=admin_main_keyboard())
        return
    data = await state.get_data()
    caption = message.text
    media_type = data.get('media_type')
    media_id = data.get('media_id')

    user_ids = await db.get_all_user_ids()
    channels = await db.get_promo_channels()
    targets = list(user_ids) + [ch['channel_id'] for ch in channels]

    sent = 0
    failed = 0
    for target in targets:
        try:
            if media_type == "photo":
                await bot.send_photo(target, media_id, caption=caption)
            elif media_type == "video":
                await bot.send_video(target, media_id, caption=caption)
            else:
                await bot.send_message(target, caption)
            sent += 1
        except Exception as e:
            logger.error(f"Reklama {target} ga ketmadi: {e}")
            failed += 1

    await state.clear()
    await message.answer(
        f"✅ Reklama yuborildi!\n\n"
        f"📬 Yuborildi: {sent}\n❌ Xatolik: {failed}",
        reply_markup=admin_main_keyboard()
    )

# ===== CANCEL ORDER (ADMIN) =====
@router.message(F.text == "🚫 Zakaz bekor qilish (Admin)")
async def cancel_order_admin_start(message: Message, state: FSMContext):
    if not await db.is_admin(message.from_user.id):
        return
    orders = await db.get_pending_orders()
    if not orders:
        await message.answer("📭 Kutilayotgan zakazlar yo'q.")
        return
    text = "🚫 Qaysi zakazni bekor qilmoqchisiz? ID kiriting:\n\n"
    for order_row in orders:
        text += f"#{order_row['id']} — {order_row['user_name']} | {order_row['phone']}\n"
    await state.set_state(CancelOrderFSM.waiting)
    await message.answer(text, reply_markup=admin_cancel_keyboard())

@router.message(CancelOrderFSM.waiting)
async def cancel_order_admin_process(message: Message, state: FSMContext, bot: Bot):
    if message.text == "❌ Bekor qilish":
        await state.clear()
        await message.answer("❌ Bekor qilindi.", reply_markup=admin_main_keyboard())
        return
    if not message.text.isdigit():
        await message.answer("⚠️ Zakaz ID sini kiriting (faqat raqam):")
        return
    order_id = int(message.text)
    order_row = await db.get_order(order_id)
    if not order_row:
        await message.answer("❌ Zakaz topilmadi.")
        return
    await db.reject_order(order_id)
    await state.clear()
    await message.answer(f"✅ Zakaz #{order_id} bekor qilindi.", reply_markup=admin_main_keyboard())
    try:
        await bot.send_message(
            order_row['user_id'],
            f"❌ Afsuski, #{order_id} zakazingiz admin tomonidan bekor qilindi.\n"
            "Muammo bo'lsa admin bilan bog'laning."
        )
    except Exception as e:
        logger.error(f"Bekor xabari mijozga ketmadi: {e}")
