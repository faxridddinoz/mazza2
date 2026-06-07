# 🍕 Ovqat Yetkazib Berish Boti

## O'rnatish

### 1. Python o'rnatish
Python 3.10 yoki undan yuqori versiya kerak.

### 2. Kutubxonalarni o'rnatish
```bash
pip install -r requirements.txt
```

### 3. config.py ni sozlash
# `config.py` faylini oching va quyidagilarni to'ldiring:

BOT_TOKEN = "YOUR_BOT_TOKEN_HERE"   # @BotFather dan olingan token
SUPER_ADMIN_ID = 123456789          # Sizning Telegram ID ingiz


**Telegram ID ni qanday bilish:**
- @userinfobot ga `/start` yuboring

**Bot token olish:**
- @BotFather ga `/newbot` yuboring

### 4. Botni ishga tushirish
```bash
python bot.py
```

---

## Foydalanuvchi uchun buyruqlar
##| Buyruq | Vazifasi |
##|--------|----------|
| `/start` yoki `🚀 Boshlash` | Botni ishga tushirish |
| `📦 Sizning zakazlaringiz` | Oxirgi zakaz va taymer |
| `/menu` | Menyuni ko'rish |
| `/help` | Yordam |
| `/myorders` | Oxirgi zakaz |

---

## Admin uchun
**Admin panelga kirish:** `/admin`

| Tugma | Vazifasi |
|-------|----------|
| `🍽 Menyu` | Menyu boshqaruvi (qo'shish/ko'rish/o'chirish) |
| `👤 Admin qo'shish` | Yangi admin qo'shish (Telegram ID orqali) |
| `🚴 Dastavchi qo'shish` | Yangi kuryer qo'shish (Telegram ID orqali) |
| `📢 Reklama kanali qo'shish` | Kanal qo'shish |
| `📣 Reklama yuborish` | Barcha foydalanuvchilarga xabar |
| `🚫 Zakaz bekor qilish` | Zakazni admin bekor qiladi |

### Menyu kategoriyalari
- Taom, Shirinlik, Ichimlik, Salat, Grill, Pizza, Burger, Sho'rva, Non, Set

---

## Kuryer uchun
**Kuryer panelga kirish:** `/courier`

| Tugma | Vazifasi |
|-------|----------|
| Zakaz kelib tushganda | Qabul qilish / Rad etish tugmalari chiqadi |
| Qabul qilish | Yetkazish vaqtini tanlaydi va taymer boshlanadi |
| ✅ Zakaz yetkazildi | Zakazni tugallangan deb belgilaydi |
| `🍽 Tushlik / Dam olish` | Barcha kuryerlar bosganida 1 soatlik tanaffus |

---

## Tuzilma
```
food_bot/
├── bot.py           # Asosiy fayl
├── config.py        # Token va sozlamalar
├── database.py      # SQLite ma'lumotlar bazasi
├── keyboards.py     # Barcha tugmalar
├── requirements.txt
├── handlers/
│   ├── user.py      # Foydalanuvchi handlerlari
│   ├── admin.py     # Admin handlerlari
│   └── courier.py   # Kuryer handlerlari
└── food_bot.db      # Avtomatik yaratiladi
```
