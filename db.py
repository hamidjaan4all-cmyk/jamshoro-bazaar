# -*- coding: utf-8 -*-
"""SQLite database: schema + seed data for Jamshoro Bazaar."""
import sqlite3
import os
from werkzeug.security import generate_password_hash

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(BASE_DIR, "jamshoro_bazaar.db")

SCHEMA = """
CREATE TABLE IF NOT EXISTS categories (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    key TEXT UNIQUE NOT NULL,
    name_en TEXT NOT NULL,
    name_ur TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS shops (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name_en TEXT NOT NULL,
    name_ur TEXT NOT NULL,
    category_id INTEGER NOT NULL REFERENCES categories(id),
    area_key TEXT NOT NULL,
    is_open INTEGER NOT NULL DEFAULT 1
);
CREATE TABLE IF NOT EXISTS items (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    shop_id INTEGER NOT NULL REFERENCES shops(id) ON DELETE CASCADE,
    name_en TEXT NOT NULL,
    name_ur TEXT NOT NULL,
    price REAL NOT NULL,
    unit_en TEXT NOT NULL DEFAULT 'pc',
    unit_ur TEXT NOT NULL DEFAULT 'عدد',
    in_stock INTEGER NOT NULL DEFAULT 1
);
CREATE TABLE IF NOT EXISTS riders (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    username TEXT UNIQUE NOT NULL,
    password_hash TEXT NOT NULL,
    phone TEXT DEFAULT '',
    active INTEGER NOT NULL DEFAULT 1
);
CREATE TABLE IF NOT EXISTS admins (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    username TEXT UNIQUE NOT NULL,
    password_hash TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS orders (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    order_code TEXT UNIQUE NOT NULL,
    customer_name TEXT NOT NULL,
    phone TEXT NOT NULL,
    area_key TEXT NOT NULL,
    address_detail TEXT NOT NULL,
    subtotal REAL NOT NULL,
    delivery_fee REAL NOT NULL,
    total REAL NOT NULL,
    status TEXT NOT NULL DEFAULT 'placed',
    rider_id INTEGER REFERENCES riders(id),
    user_id INTEGER REFERENCES users(id),
    created_at TEXT NOT NULL DEFAULT (datetime('now', 'localtime'))
);
CREATE TABLE IF NOT EXISTS order_items (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    order_id INTEGER NOT NULL REFERENCES orders(id) ON DELETE CASCADE,
    item_name_en TEXT NOT NULL,
    item_name_ur TEXT NOT NULL,
    price REAL NOT NULL,
    qty INTEGER NOT NULL,
    line_total REAL NOT NULL
);
CREATE TABLE IF NOT EXISTS users (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    phone TEXT UNIQUE NOT NULL,
    name TEXT NOT NULL,
    created_at TEXT NOT NULL DEFAULT (datetime('now', 'localtime'))
);
CREATE TABLE IF NOT EXISTS otp_codes (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    phone TEXT NOT NULL,
    code TEXT NOT NULL,
    expires_at TEXT NOT NULL,
    attempts INTEGER NOT NULL DEFAULT 0,
    used INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL DEFAULT (datetime('now', 'localtime'))
);
CREATE TABLE IF NOT EXISTS custom_orders (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    order_code TEXT UNIQUE NOT NULL,
    customer_name TEXT NOT NULL,
    phone TEXT NOT NULL,
    area_key TEXT NOT NULL,
    address_detail TEXT NOT NULL,
    items_text TEXT NOT NULL,
    shop_hint TEXT,
    delivery_fee REAL NOT NULL,
    items_total REAL,
    status TEXT NOT NULL DEFAULT 'placed',
    rider_id INTEGER REFERENCES riders(id),
    user_id INTEGER REFERENCES users(id),
    admin_note TEXT,
    created_at TEXT NOT NULL DEFAULT (datetime('now', 'localtime'))
);
"""

AREAS = [
    ("area_mehran_uni", "Mehran University", "مہران یونیورسٹی"),
    ("area_sindh_uni", "Sindh University", "سندھ یونیورسٹی"),
    ("area_lumhs", "LUMHS", "لمس"),
    ("area_saeedabad", "Saeedabad", "سعیدآباد"),
    ("area_mehran_soc", "Mehran Society", "مہران سوسائٹی"),
    ("area_sindh_soc", "Sindh Society", "سندھ سوسائٹی"),
    ("area_colonies", "University Colonies", "یونیورسٹی کالونیز"),
    ("area_hostels", "Hostels", "ہاسٹلز"),
]

CATEGORIES = [
    ("cat_grocery", "Grocery", "کریانہ"),
    ("cat_medicine", "Medicine", "ادویات"),
    ("cat_vegetables", "Vegetables", "سبزیاں"),
    ("cat_fruits", "Fruits", "پھل"),
    ("cat_snacks", "Snacks", "اسنیکس"),
    ("cat_restaurant", "Restaurants", "ریسٹورنٹ"),
]

# (shop_en, shop_ur, category_key, area_key, [(item_en, item_ur, price, unit_en, unit_ur), ...])
SHOPS = [
    ("Campus Grocery Store", "کیمپس کریانہ اسٹور", "cat_grocery", "area_mehran_uni", [
        ("Basmati Rice 5kg", "باسمتی چاول 5 کلو", 1450, "bag", "تھیلا"),
        ("Wheat Flour 10kg", "گندم کا آٹا 10 کلو", 1180, "bag", "تھیلا"),
        ("Cooking Oil 5L", "کوکنگ آئل 5 لیٹر", 2650, "bottle", "بوتل"),
        ("Sugar 5kg", "چینی 5 کلو", 690, "bag", "تھیلا"),
        ("Red Lentils (Masoor) 1kg", "مسور کی دال 1 کلو", 320, "kg", "کلو"),
        ("Chickpeas (Chana) 1kg", "کالے چنے 1 کلو", 380, "kg", "کلو"),
        ("Tea 950g", "چائے 950 گرام", 1950, "pack", "پیک"),
        ("Milk Powder 1kg", "خشک دودھ 1 کلو", 2100, "pack", "پیک"),
        ("Eggs (dozen)", "انڈے (درجن)", 380, "dozen", "درجن"),
        ("Bread (large)", "ڈبل روٹی (بڑی)", 180, "pc", "عدد"),
    ]),
    ("Al-Shifa Medical Store", "الشفا میڈیکل اسٹور", "cat_medicine", "area_lumhs", [
        ("Paracetamol 500mg (20 tabs)", "پیراسیٹامول 500mg (20 گولیاں)", 60, "strip", "پتّا"),
        ("ORS Sachets (6 pcs)", "او آر ایس (6 عدد)", 150, "pack", "پیک"),
        ("Bandage Roll", "پٹی", 80, "pc", "عدد"),
        ("Antiseptic Liquid 250ml", "اینٹی سیپٹک 250ml", 220, "bottle", "بوتل"),
        ("Cough Syrup", "کھانسی کا شربت", 180, "bottle", "بوتل"),
        ("Multivitamins (30 tabs)", "ملٹی وٹامن (30 گولیاں)", 450, "bottle", "بوتل"),
        ("Face Mask (pack of 10)", "ماسک (10 عدد)", 120, "pack", "پیک"),
        ("Digital Thermometer", "تھرمامیٹر", 350, "pc", "عدد"),
    ]),
    ("Fresh Sabzi & Fruit", "تازہ سبزی و پھل", "cat_vegetables", "area_saeedabad", [
        ("Tomato 1kg", "ٹماٹر 1 کلو", 160, "kg", "کلو"),
        ("Onion 1kg", "پیاز 1 کلو", 120, "kg", "کلو"),
        ("Potato 1kg", "آلو 1 کلو", 100, "kg", "کلو"),
        ("Spinach (bunch)", "پالک (گٹھی)", 60, "bunch", "گٹھی"),
        ("Cauliflower 1kg", "پھول گوبھی 1 کلو", 140, "kg", "کلو"),
        ("Banana (dozen)", "کیلا (درجن)", 180, "dozen", "درجن"),
        ("Apple 1kg", "سیب 1 کلو", 320, "kg", "کلو"),
        ("Orange 1kg", "کینو 1 کلو", 220, "kg", "کلو"),
        ("Guava 1kg", "امرود 1 کلو", 180, "kg", "کلو"),
    ]),
    ("Lazeez Samosa & Pakora House", "لذیذ سموسہ و پکوڑا ہاؤس", "cat_snacks", "area_sindh_uni", [
        ("Samosa (2 pcs)", "سموسہ (2 عدد)", 80, "plate", "پلیٹ"),
        ("Aloo Pakora 250g", "آلو پکوڑے 250 گرام", 150, "plate", "پلیٹ"),
        ("Chicken Samosa (2 pcs)", "چکن سموسہ (2 عدد)", 140, "plate", "پلیٹ"),
        ("Dahi Bhalla (plate)", "دہی بھلے (پلیٹ)", 150, "plate", "پلیٹ"),
        ("French Fries", "فرنچ فرائز", 180, "plate", "پلیٹ"),
        ("Bun Kebab", "بن کباب", 120, "pc", "عدد"),
        ("Cold Drink 500ml", "کولڈ ڈرنک 500ml", 120, "bottle", "بوتل"),
        ("Mineral Water 1.5L", "منرل واٹر 1.5 لیٹر", 130, "bottle", "بوتل"),
    ]),
    ("Mehran Mini Mart", "مہران منی مارٹ", "cat_grocery", "area_mehran_soc", [
        ("Biscuits (family pack)", "بسکٹ (فیملی پیک)", 250, "pack", "پیک"),
        ("Chips (4 pcs)", "چپس (4 عدد)", 200, "pack", "پیک"),
        ("Noodles (4 pack)", "نوڈلز (4 عدد)", 320, "pack", "پیک"),
        ("Juice 1L", "جوس 1 لیٹر", 280, "pack", "پیک"),
        ("Soap (3 pcs)", "صابن (3 عدد)", 270, "pack", "پیک"),
        ("Detergent 1kg", "سرف 1 کلو", 480, "pack", "پیک"),
        ("Toothpaste", "ٹوتھ پیسٹ", 320, "pc", "عدد"),
        ("Shampoo 400ml", "شیمپو 400ml", 650, "bottle", "بوتل"),
        ("Tea Cups (6 pcs)", "چائے کے کپ (6 عدد)", 450, "set", "سیٹ"),
        ("Notebook", "کاپی", 150, "pc", "عدد"),
    ]),
    ("Student Biryani House", "اسٹوڈنٹ بریانی ہاؤس", "cat_restaurant", "area_sindh_uni", [
        ("Chicken Biryani", "چکن بریانی", 180, "plate", "پلیٹ"),
        ("Beef Biryani", "بیف بریانی", 220, "plate", "پلیٹ"),
        ("Vegetable Biryani", "سبزی بریانی", 130, "plate", "پلیٹ"),
        ("Chicken Pulao", "چکن پلاؤ", 200, "plate", "پلیٹ"),
        ("Shami Kebab (2 pcs)", "شامی کباب (2 عدد)", 100, "pc", "عدد"),
        ("Raita", "رائتہ", 40, "bowl", "پیالی"),
        ("Salad", "سلاد", 50, "plate", "پلیٹ"),
        ("Zarda", "زردہ", 100, "bowl", "پیالی"),
        ("Cold Drink 345ml", "کولڈ ڈرنک 345ml", 90, "bottle", "بوتل"),
        ("Mineral Water 500ml", "منرل واٹر 500ml", 80, "bottle", "بوتل"),
    ]),
    ("Al-Madina Fast Food", "المدینہ فاسٹ فوڈ", "cat_restaurant", "area_mehran_uni", [
        ("Zinger Burger", "زنگر برگر", 320, "pc", "عدد"),
        ("Chicken Shawarma", "چکن شاورما", 220, "pc", "عدد"),
        ("Chicken Shawarma Platter", "چکن شاورما پلیٹر", 380, "plate", "پلیٹ"),
        ("French Fries", "فرنچ فرائز", 180, "plate", "پلیٹ"),
        ("Loaded Fries", "لوڈڈ فرائز", 350, "plate", "پلیٹ"),
        ("Chicken Pizza Slice", "چکن پیزا سلائس", 250, "slice", "سلائس"),
        ("Chicken Wings (6 pcs)", "چکن ونگز (6 عدد)", 400, "plate", "پلیٹ"),
        ("Garlic Mayo Dip", "گارلک میو ڈپ", 60, "cup", "کپ"),
        ("Mint Margarita", "منٹ مارگریٹا", 150, "glass", "گلاس"),
        ("Cold Drink 500ml", "کولڈ ڈرنک 500ml", 120, "bottle", "بوتل"),
    ]),
    ("Desi Dastarkhwan", "دیسی دسترخوان", "cat_restaurant", "area_hostels", [
        ("Chicken Karahi (half)", "چکن کڑاہی (آدھی)", 650, "plate", "پلیٹ"),
        ("Daal Fry", "دال فرائی", 220, "plate", "پلیٹ"),
        ("Mix Sabzi", "مکس سبزی", 200, "plate", "پلیٹ"),
        ("White Rice (plate)", "سفید چاول (پلیٹ)", 150, "plate", "پلیٹ"),
        ("Roti (2 pcs)", "روٹی (2 عدد)", 40, "pc", "عدد"),
        ("Naan", "نان", 50, "pc", "عدد"),
        ("Sweet Lassi", "میٹھی لسی", 120, "glass", "گلاس"),
        ("Salty Lassi", "نمکین لسی", 120, "glass", "گلاس"),
        ("Gulab Jamun (4 pcs)", "گلاب جامن (4 عدد)", 150, "plate", "پلیٹ"),
        ("Kheer", "کھیر", 120, "bowl", "پیالی"),
    ]),
]

RIDERS = [
    ("Ahmed Raza", "ahmed", "rider123", "03001234501"),
    ("Bilal Sheikh", "bilal", "rider123", "03001234502"),
]


def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def init_db(seed=True):
    fresh = not os.path.exists(DB_PATH)
    conn = get_db()
    conn.executescript(SCHEMA)
    if seed and fresh:
        for key, en, ur in CATEGORIES:
            conn.execute("INSERT INTO categories (key, name_en, name_ur) VALUES (?,?,?)", (key, en, ur))
        cat_ids = {r["key"]: r["id"] for r in conn.execute("SELECT id, key FROM categories")}
        for s_en, s_ur, ckey, akey, items in SHOPS:
            cur = conn.execute(
                "INSERT INTO shops (name_en, name_ur, category_id, area_key, is_open) VALUES (?,?,?,?,1)",
                (s_en, s_ur, cat_ids[ckey], akey))
            sid = cur.lastrowid
            for i_en, i_ur, price, u_en, u_ur in items:
                conn.execute(
                    "INSERT INTO items (shop_id, name_en, name_ur, price, unit_en, unit_ur, in_stock) VALUES (?,?,?,?,?,?,1)",
                    (sid, i_en, i_ur, price, u_en, u_ur))
        for name, username, pw, phone in RIDERS:
            conn.execute(
                "INSERT INTO riders (name, username, password_hash, phone, active) VALUES (?,?,?,?,1)",
                (name, username, generate_password_hash(pw), phone))
        conn.execute(
            "INSERT OR IGNORE INTO admins (username, password_hash) VALUES (?,?)",
            ("admin", generate_password_hash(os.environ.get("JB_ADMIN_PASSWORD", "admin123"))))
        conn.commit()
    conn.close()
    return DB_PATH


def migrate():
    """Upgrade an existing database: new tables, orders.user_id, restaurant
    category and restaurant shops. Safe to run multiple times (idempotent)."""
    conn = get_db()
    conn.executescript("""
CREATE TABLE IF NOT EXISTS users (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    phone TEXT UNIQUE NOT NULL,
    name TEXT NOT NULL,
    created_at TEXT NOT NULL DEFAULT (datetime('now', 'localtime'))
);
CREATE TABLE IF NOT EXISTS otp_codes (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    phone TEXT NOT NULL,
    code TEXT NOT NULL,
    expires_at TEXT NOT NULL,
    attempts INTEGER NOT NULL DEFAULT 0,
    used INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL DEFAULT (datetime('now', 'localtime'))
);
CREATE TABLE IF NOT EXISTS custom_orders (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    order_code TEXT UNIQUE NOT NULL,
    customer_name TEXT NOT NULL,
    phone TEXT NOT NULL,
    area_key TEXT NOT NULL,
    address_detail TEXT NOT NULL,
    items_text TEXT NOT NULL,
    shop_hint TEXT,
    delivery_fee REAL NOT NULL,
    items_total REAL,
    status TEXT NOT NULL DEFAULT 'placed',
    rider_id INTEGER REFERENCES riders(id),
    user_id INTEGER REFERENCES users(id),
    admin_note TEXT,
    created_at TEXT NOT NULL DEFAULT (datetime('now', 'localtime'))
);
""")
    cols = [r["name"] for r in conn.execute("PRAGMA table_info(orders)")]
    if "user_id" not in cols:
        conn.execute("ALTER TABLE orders ADD COLUMN user_id INTEGER REFERENCES users(id)")
    if not conn.execute("SELECT 1 FROM categories WHERE key='cat_restaurant'").fetchone():
        conn.execute("INSERT INTO categories (key, name_en, name_ur) VALUES (?,?,?)",
                     ("cat_restaurant", "Restaurants", "ریسٹورنٹ"))
    cat_ids = {r["key"]: r["id"] for r in conn.execute("SELECT id, key FROM categories")}
    for s_en, s_ur, ckey, akey, items in SHOPS:
        if ckey != "cat_restaurant":
            continue
        if conn.execute("SELECT 1 FROM shops WHERE name_en=?", (s_en,)).fetchone():
            continue
        cur = conn.execute(
            "INSERT INTO shops (name_en, name_ur, category_id, area_key, is_open) VALUES (?,?,?,?,1)",
            (s_en, s_ur, cat_ids[ckey], akey))
        sid = cur.lastrowid
        for i_en, i_ur, price, u_en, u_ur in items:
            conn.execute(
                "INSERT INTO items (shop_id, name_en, name_ur, price, unit_en, unit_ur, in_stock)"
                " VALUES (?,?,?,?,?,?,1)",
                (sid, i_en, i_ur, price, u_en, u_ur))
    conn.commit()
    conn.close()
    return DB_PATH


if __name__ == "__main__":
    print("DB at:", init_db())
