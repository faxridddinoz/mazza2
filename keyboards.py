import aiosqlite
from config import DB_FILE

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
            CREATE TABLE IF NOT EXISTS promo_channels (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                channel_id TEXT UNIQUE NOT NULL,
                channel_name TEXT,
                added_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        # Super admin qo'shish
        from config import SUPER_ADMIN_ID
        await db.execute("""
            INSERT OR IGNORE INTO admins (user_id, full_name) VALUES (?, ?)
        """, (SUPER_ADMIN_ID, "Super Admin"))
        await db.commit()

# ===== ADMIN =====
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

# ===== COURIER =====
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

async def set_courier_break(user_id: int, on_break: bool):
    async with aiosqlite.connect(DB_FILE) as db:
        if on_break:
            await db.execute(
                "UPDATE couriers SET is_on_break=1, break_started_at=CURRENT_TIMESTAMP WHERE user_id=?",
                (user_id,)
            )
        else:
            await db.execute(
                "UPDATE couriers SET is_on_break=0, break_started_at=NULL WHERE user_id=?",
                (user_id,)
            )
        await db.commit()

async def get_courier_break_status(user_id: int):
    async with aiosqlite.connect(DB_FILE) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute("SELECT is_on_break, break_started_at FROM couriers WHERE user_id=?", (user_id,)) as cursor:
            return await cursor.fetchone()

# ===== MENU =====
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

async def get_all_menu_items_admin():
    async with aiosqlite.connect(DB_FILE) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute("SELECT * FROM menu_items WHERE is_active=1 ORDER BY category, id") as cursor:
            return await cursor.fetchall()

async def get_menu_item(item_id: int):
    async with aiosqlite.connect(DB_FILE) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute("SELECT * FROM menu_items WHERE id=?", (item_id,)) as cursor:
            return await cursor.fetchone()

async def delete_menu_item(item_id: int):
    async with aiosqlite.connect(DB_FILE) as db:
        await db.execute("UPDATE menu_items SET is_active=0 WHERE id=?", (item_id,))
        await db.commit()

async def get_categories():
    async with aiosqlite.connect(DB_FILE) as db:
        async with db.execute(
            "SELECT DISTINCT category FROM menu_items WHERE is_active=1"
        ) as cursor:
            rows = await cursor.fetchall()
            return [r[0] for r in rows]

# ===== ORDERS =====
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

async def get_pending_orders():
    async with aiosqlite.connect(DB_FILE) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute("SELECT * FROM orders WHERE status='pending' ORDER BY created_at") as cursor:
            return await cursor.fetchall()

# ===== PROMO CHANNELS =====
async def add_promo_channel(channel_id: str, channel_name: str):
    async with aiosqlite.connect(DB_FILE) as db:
        await db.execute(
            "INSERT OR IGNORE INTO promo_channels (channel_id, channel_name) VALUES (?,?)",
            (channel_id, channel_name)
        )
        await db.commit()

async def get_promo_channels():
    async with aiosqlite.connect(DB_FILE) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute("SELECT * FROM promo_channels") as cursor:
            return await cursor.fetchall()

# ===== ALL USERS =====
async def get_all_user_ids():
    async with aiosqlite.connect(DB_FILE) as db:
        async with db.execute("SELECT DISTINCT user_id FROM orders") as cursor:
            rows = await cursor.fetchall()
            return [r[0] for r in rows]
