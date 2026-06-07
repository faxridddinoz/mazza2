import os
import json
import logging
import asyncio
from datetime import datetime, timedelta
import aiosqlite

from aiogram import Bot, Dispatcher, Router, F
from aiogram.types import (
    Message, CallbackQuery, ReplyKeyboardMarkup, KeyboardButton,
    InlineKeyboardMarkup, InlineKeyboardButton
)
from aiogram.filters import CommandStart, Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.utils.keyboard import ReplyKeyboardBuilder, InlineKeyboardBuilder

# ==================== НАСТРОЙКИ (КОНФИГ) ====================
TOKEN = "8749714916:AAFY3Vf_1NoFOSR5EhutHBNsq_Z0p-XH-GI"          # Вставьте сюда токен вашего бота
SUPER_ADMIN_ID = 8684039353           # Вставьте сюда ваш Telegram ID
DB_FILE = "delivery_bot.db"

router = Router()
logger = logging.getLogger(__name__)

# ==================== СОСТОЯНИЯ FSM ====================
class OrderFSM(StatesGroup):
    waiting_name = State()
    waiting_phone = State()
    waiting_location = State()

class AdminFSM(StatesGroup):
    waiting_courier_id = State()
    waiting_courier_username = State()
    waiting_courier_fullname = State()
    
    waiting_food_name = State()
    waiting_food_price = State()
    waiting_food_time = State()
    waiting_food_category = State()
    
    waiting_broadcast = State()

# Оперативная память для корзин пользователей
user_carts = {}      # {user_id: {item_id: count}}
user_category = {}   # {user_id: current_category}

# Переменные для таймеров курьеров
active_timers = {}
break_votes_set = set()
break_task = None

# ==================== ФУНКЦИИ БАЗЫ ДАННЫХ ====================
async def init_db():
    async with aiosqlite.connect(DB_FILE) as db:
        await db.execute("""
            CREATE TABLE IF NOT EXISTS admins (
                id INTEGER PRIMARY KEY,
                user_id INTEGER UNIQUE NOT NULL,
                username TEXT,
                full_name TEXT,
                added_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        await db.execute("""
            CREATE TABLE IF NOT EXISTS couriers (
                id INTEGER PRIMARY KEY,
                user_id INTEGER UNIQUE NOT NULL,
                username TEXT,
                full_name TEXT,
                is_on_break INTEGER DEFAULT 0,
                break_started_at TIMESTAMP,
                added_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        await db.execute("""
            CREATE TABLE IF NOT EXISTS menu_items (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                photo_id TEXT,
                price INTEGER NOT NULL,
                delivery_time INTEGER NOT NULL,
                category TEXT NOT NULL,
                is_active INTEGER DEFAULT 1,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        await db.execute("""
            CREATE TABLE IF NOT EXISTS orders (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                user_name TEXT,
                phone TEXT NOT NULL,
                location TEXT NOT NULL,
                items TEXT NOT NULL,
                total_price INTEGER NOT NULL,
                status TEXT DEFAULT 'pending',
                courier_id INTEGER,
                delivery_minutes INTEGER,
                accepted_at TIMESTAMP,
                completed_at TIMESTAMP,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        await db.execute("""
            INSERT OR IGNORE INTO admins (user_id, full_name) VALUES (?, ?)
        """, (SUPER_ADMIN_ID, "Super Admin"))
        await db.commit()

async def get_admins():
    async with aiosqlite.connect(DB_FILE) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute("SELECT * FROM admins") as cursor:
            return await cursor.fetchall()

async def is_admin(user_id: int) -> bool:
    async with aiosqlite.connect(DB_FILE) as db:
        async with db.execute("SELECT id FROM admins WHERE user_id=?", (user_id,)) as cursor:
            return await cursor.fetchone() is not None

async def add_admin(user_id: int, username: str, full_name: str):
    async with aiosqlite.connect(DB_FILE) as db:
        await db.execute(
            "INSERT OR IGNORE INTO admins (user_id, username, full_name) VALUES (?,?,?)",
            (user_id, username, full_name)
        )
        await db.commit()

async def get_couriers():
    async with aiosqlite.connect(DB_FILE) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute("SELECT * FROM couriers") as cursor:
            return await cursor.fetchall()

async def is_courier(user_id: int) -> bool:
    async with aiosqlite.connect(DB_FILE) as db:
        async with db.execute("SELECT id FROM couriers WHERE user_id=?", (user_id,)) as cursor:
            return await cursor.fetchone() is not None

async def add_courier(user_id: int, username: str, full_name: str):
    async with aiosqlite.connect(DB_FILE) as db:
        await db.execute(
            "INSERT OR IGNORE INTO couriers (user_id, username, full_name) VALUES (?,?,?)",
            (user_id, username, full_name)
        )
        await db.commit()

async def add_menu_item(name, photo_id, price, delivery_time, category):
    async with aiosqlite.connect(DB_FILE) as db:
        await db.execute(
            "INSERT INTO menu_items (name, photo_id, price, delivery_time, category) VALUES (?,?,?,?,?)",
            (name, photo_id, price, delivery_time, category)
        )
        await db.commit()

async def get_menu_items(category=None):
    async with aiosqlite.connect(DB_FILE) as db:
        db.row_factory = aiosqlite.Row
        if category:
            async with db.execute(
                "SELECT * FROM menu_items WHERE category=? AND is_active=1 ORDER BY id", (category,)
            ) as cursor:
                return await cursor.fetchall()
        else:
            async with db.execute(
                "SELECT * FROM menu_items WHERE is_active=1 ORDER BY category, id"
            ) as cursor:
                return await cursor.fetchall()

async def get_menu_item(item_id: int):
    async with aiosqlite.connect(DB_FILE) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute("SELECT * FROM menu_items WHERE id=?", (item_id,)) as cursor:
            return await cursor.fetchone()

async def get_categories():
    async with aiosqlite.connect(DB_FILE) as db:
        async with db.execute(
            "SELECT DISTINCT category FROM menu_items WHERE is_active=1"
        ) as cursor:
            rows = await cursor.fetchall()
            return [r[0] for r in rows]

async def create_order(user_id, user_name, phone, location, items, total_price):
    async with aiosqlite.connect(DB_FILE) as db:
        cursor = await db.execute(
            """INSERT INTO orders (user_id, user_name, phone, location, items, total_price)
               VALUES (?,?,?,?,?,?)""",
            (user_id, user_name, phone, location, items, total_price)
        )
        await db.commit()
        return cursor.lastrowid

async def get_order(order_id: int):
    async with aiosqlite.connect(DB_FILE) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute("SELECT * FROM orders WHERE id=?", (order_id,)) as cursor:
            return await cursor.fetchone()

async def get_user_last_order(user_id: int):
    async with aiosqlite.connect(DB_FILE) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            "SELECT * FROM orders WHERE user_id=? ORDER BY created_at DESC LIMIT 1", (user_id,)
        ) as cursor:
            return await cursor.fetchone()

async def accept_order(order_id: int, courier_id: int, delivery_minutes: int):
    async with aiosqlite.connect(DB_FILE) as db:
        await db.execute(
            """UPDATE orders SET status='accepted', courier_id=?, delivery_minutes=?,
               accepted_at=CURRENT_TIMESTAMP WHERE id=?""",
            (courier_id, delivery_minutes, order_id)
        )
        await db.commit()

async def reject_order(order_id: int):
    async with aiosqlite.connect(DB_FILE) as db:
        await db.execute("UPDATE orders SET status='rejected' WHERE id=?", (order_id,))
        await db.commit()

async def complete_order(order_id: int):
    async with aiosqlite.connect(DB_FILE) as db:
        await db.execute(
            "UPDATE orders SET status='completed', completed_at=CURRENT_TIMESTAMP WHERE id=?",
            (order_id,)
        )
        await db.commit()

async def get_all_user_ids():
    async with aiosqlite.connect(DB_FILE) as db:
        async with db.execute("SELECT DISTINCT user_id FROM orders") as cursor:
            rows = await cursor.fetchall()
            return [r[0] for r in rows]

async def get_stats():
    async with aiosqlite.connect(DB_FILE) as db:
        async with db.execute("SELECT COUNT(*), SUM(total_price) FROM orders WHERE status='completed'") as c:
            comp_count, comp_sum = await c.fetchone()
        async with db.execute("SELECT COUNT(*) FROM orders WHERE status='pending'") as p:
            pend_count = (await p.fetchone())[0]
        async with db.execute("SELECT COUNT(*) FROM orders WHERE status='rejected'") as r:
            rej_count = (await r.fetchone())[0]
        return {
            "completed_count": comp_count or 0,
            "completed_sum": comp_sum or 0,
            "pending_count": pend_count or 0,
            "rejected_count": rej_count or 0
        }

# ==================== КЛАВИАТУРЫ (KEYBOARDS) ====================
def user_main_keyboard():
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="🍽 Menyu"), KeyboardButton(text="📦 Sizning zakazlaringiz")],
            [KeyboardButton(text="🚀 Boshlash")]
        ],
        resize_keyboard=True
    )

def start_inline_keyboard():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🍽 Menyuni ochish", callback_data="open_menu")],
        [InlineKeyboardButton(text="❓ Yordam", callback_data="open_help")]
    ])

def category_keyboard(categories):
    builder = InlineKeyboardBuilder()
    for cat in categories:
        builder.button(text=str(cat).capitalize(), callback_data=f"cat_{cat}")
    builder.button(text="🌐 Barcha taomlar", callback_data="cat_all")
    builder.adjust(2)
    return builder.as_markup()

def items_keyboard(items, cart):
    builder = InlineKeyboardBuilder()
    for item in items:
        count = cart.get(item['id'], 0)
        text = f"{item['name']} ({count} ta)" if count > 0 else item['name']
        builder.button(text=text, callback_data=f"item_{item['id']}")
    builder.adjust(1)
    
    bottom_builder = InlineKeyboardBuilder()
    if cart:
        bottom_builder.button(text="🛒 Rasmiylashtirish (Checkout)", callback_data="checkout")
    bottom_builder.button(text="⬅️ Kategoriyalar", callback_data="open_menu")
    bottom_builder.adjust(1)
    builder.attach(bottom_builder)
    return builder.as_markup()

def item_detail_keyboard(item_id, count):
    builder = InlineKeyboardBuilder()
    builder.row(
        InlineKeyboardButton(text="➖", callback_data=f"minus_{item_id}"),
        InlineKeyboardButton(text=f"{count} ta", callback_data="noop"),
        InlineKeyboardButton(text="➕", callback_data=f"plus_{item_id}")
    )
    if count > 0:
        builder.row(InlineKeyboardButton(text="🛒 Rasmiylashtirish", callback_data="checkout"))
    builder.row(InlineKeyboardButton(text="⬅️ Ortga", callback_data="back_to_items"))
    return builder.as_markup()

def location_keyboard():
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="📍 Lokatsiya yuborish", request_location=True)],
            [KeyboardButton(text="❌ Bekor qilish")]
        ],
        resize_keyboard=True
    )

def cancel_keyboard():
    return ReplyKeyboardMarkup(
        keyboard=[[KeyboardButton(text="❌ Bekor qilish")]],
        resize_keyboard=True
    )

def courier_main_keyboard():
    return ReplyKeyboardMarkup(
        keyboard=[[KeyboardButton(text="🍽 Tushlik / Dam olish")]],
        resize_keyboard=True
    )

def admin_main_keyboard():
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="➕ Kuryer qo'shish"), KeyboardButton(text="➕ Taom qo'shish")],
            [KeyboardButton(text="📊 Statistika"), KeyboardButton(text="📢 Reklama")]
        ],
        resize_keyboard=True
    )

def order_action_keyboard(order_id):
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="✅ Qabul qilish", callback_data=f"accept_{order_id}"),
            InlineKeyboardButton(text="❌ Rad etish", callback_data=f"reject_{order_id}")
        ]
    ])

def delivery_time_keyboard(order_id):
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="15 min", callback_data=f"time_{order_id}_15"),
            InlineKeyboardButton(text="30 min", callback_data=f"time_{order_id}_30")
        ],
        [
            InlineKeyboardButton(text="45 min", callback_data=f"time_{order_id}_45"),
            InlineKeyboardButton(text="60 min", callback_data=f"time_{order_id}_60")
        ]
    ])

def complete_order_keyboard(order_id):
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="✅ Yetkazib berildi", callback_data=f"complete_{order_id}")]
    ])


# ==================== ОБРАБОТЧИКИ ПОЛЬЗОВАТЕЛЕЙ (USER) ====================
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

@router.message(F.text == "🍽 Menyu")
@router.message(Command("menu"))
async def menu_cmd(message: Message):
    categories = await get_categories()
    if not categories:
        await message.answer("😔 Menyu hozircha bo'sh.")
        return
    await message.answer("🍽 Kategoriya tanlang:", reply_markup=category_keyboard(categories))

@router.message(F.text == "📦 Sizning zakazlaringiz")
async def my_orders_handler(message: Message):
    order = await get_user_last_order(message.from_user.id)
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
        try:
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
        except:
            pass
    elif order['status'] == 'completed' and order['completed_at']:
        text += f"🕐 Yetkazildi: {order['completed_at'][:16]}"

await message.answer(text, parse_mode="HTML")
