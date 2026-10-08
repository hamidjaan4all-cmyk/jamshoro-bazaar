# -*- coding: utf-8 -*-
"""Jamshoro Bazaar — local delivery MVP. Flask + SQLite. Bilingual EN/UR."""
import os
import random
import re
import secrets
import sqlite3
from datetime import date, datetime, timedelta
from functools import wraps

from flask import (Flask, render_template, request, redirect, url_for,
                   session, make_response, jsonify, abort)
from werkzeug.security import check_password_hash

from translations import tr, lang_from_request, STRINGS
from db import get_db, init_db, migrate, AREAS

app = Flask(__name__)
app.secret_key = os.environ.get("JB_SECRET", "jamshoro-bazaar-dev-secret")
app.config["SESSION_COOKIE_HTTPONLY"] = True

DELIVERY_FEE = 100
FREE_DELIVERY_OVER = 1000
STATUSES = ["placed", "confirmed", "preparing", "onway", "delivered", "cancelled"]
PHONE_RE = re.compile(r"^03\d{9}$")

OTP_EXPIRY_MIN = 5       # OTP codes expire after 5 minutes
OTP_MAX_ATTEMPTS = 5     # wrong-code attempts before the code is voided
RESEND_COOLDOWN_SEC = 60  # seconds before a new code can be requested

AREA_MAP = {k: (en, ur) for k, en, ur in AREAS}


def send_otp(phone, code):
    """Send the OTP code to the customer's phone via WhatsApp.

    DEMO MODE: no WhatsApp provider is connected in the MVP, so this function
    only logs the code and returns it — the caller displays it on screen.
    TO GO LIVE (WhatsApp Business Cloud API): fill in the body below —
    set WHATSAPP_TOKEN, WHATSAPP_PHONE_NUMBER_ID and WHATSAPP_TEMPLATE
    (an approved `authentication` template with a {{1}} code placeholder),
    then uncomment the requests.post block. Keep the same signature
    ``send_otp(phone, code)`` and everything else (generation, expiry,
    attempt limits, resend cooldown) keeps working unchanged.
    """
    app.logger.info("DEMO OTP for %s: %s", phone, code)
    # --- WhatsApp Business Cloud API (fill in at launch) ---
    # import requests
    # WHATSAPP_TOKEN = os.environ["WA_TOKEN"]
    # WHATSAPP_PHONE_NUMBER_ID = os.environ["WA_PHONE_NUMBER_ID"]
    # WHATSAPP_TEMPLATE = "jb_otp"  # approved authentication template
    # wa_phone = "92" + phone[1:]  # 03XXXXXXXXX -> 923XXXXXXXXX
    # requests.post(
    #     "https://graph.facebook.com/v21.0/%s/messages" % WHATSAPP_PHONE_NUMBER_ID,
    #     headers={"Authorization": "Bearer " + WHATSAPP_TOKEN},
    #     json={
    #         "messaging_product": "whatsapp",
    #         "to": wa_phone,
    #         "type": "template",
    #         "template": {
    #             "name": WHATSAPP_TEMPLATE,
    #             "language": {"code": "en"},
    #             "components": [{
    #                 "type": "body",
    #                 "parameters": [{"type": "text", "text": code}],
    #             }],
    #         },
    #     },
    #     timeout=15,
    # ).raise_for_status()
    return code


def _latest_otp(db, phone):
    return db.execute(
        "SELECT * FROM otp_codes WHERE phone=? AND used=0 ORDER BY id DESC LIMIT 1",
        (phone,)).fetchone()


def _otp_valid(row):
    return row and datetime.now() < datetime.fromisoformat(row["expires_at"])


# ---------- helpers ----------
def lang():
    return lang_from_request(request.args, request.cookies)


def T(key):
    return tr(key, lang())


@app.context_processor
def inject_common():
    l = lang()
    return {
        "lang": l,
        "rtl": l == "ur",
        "T": lambda k: tr(k, l),
        "area_name": lambda k: AREA_MAP.get(k, (k, k))[1 if l == "ur" else 0],
        "st_name": lambda s: tr("st_" + s, l),
        "cart_count": sum(session.get("cart", {}).values()),
        "user_name": session.get("user_name"),
        "user_phone": session.get("user_phone"),
    }


def set_lang_cookie(resp):
    l = request.args.get("lang")
    if l in ("en", "ur"):
        resp.set_cookie("jb_lang", l, max_age=60 * 60 * 24 * 365)
    return resp


@app.after_request
def after(resp):
    return set_lang_cookie(resp)


def get_cart():
    return session.get("cart", {})


def save_cart(cart):
    session["cart"] = {str(k): int(v) for k, v in cart.items() if int(v) > 0}
    session.modified = True


def cart_detail():
    """Return (lines, subtotal, fee, total) for current cart."""
    cart = get_cart()
    lines, subtotal = [], 0
    if cart:
        db = get_db()
        for iid, qty in cart.items():
            row = db.execute(
                "SELECT i.*, s.name_en AS shop_en, s.name_ur AS shop_ur FROM items i "
                "JOIN shops s ON s.id=i.shop_id WHERE i.id=?", (iid,)).fetchone()
            if row and row["in_stock"]:
                lt = row["price"] * qty
                subtotal += lt
                lines.append({"item": row, "qty": qty, "line_total": lt})
        db.close()
    fee = 0 if subtotal >= FREE_DELIVERY_OVER or subtotal == 0 else DELIVERY_FEE
    return lines, subtotal, fee, subtotal + fee


def new_order_code(db):
    for _ in range(20):
        code = "JB-%06d" % random.randint(100000, 999999)
        if not db.execute("SELECT 1 FROM orders WHERE order_code=?", (code,)).fetchone():
            return code
    raise RuntimeError("order code collision")


def admin_required(f):
    @wraps(f)
    def wrapper(*a, **kw):
        if not session.get("admin"):
            return redirect(url_for("admin_login"))
        return f(*a, **kw)
    return wrapper


def rider_required(f):
    @wraps(f)
    def wrapper(*a, **kw):
        if not session.get("rider_id"):
            return redirect(url_for("rider_login"))
        return f(*a, **kw)
    return wrapper


def customer_login_required(f):
    @wraps(f)
    def wrapper(*a, **kw):
        if not session.get("user_id"):
            return redirect(url_for("register", next=request.path))
        return f(*a, **kw)
    return wrapper


def _safe_next():
    nxt = request.args.get("next") or request.form.get("next") or "/"
    return nxt if nxt.startswith("/") else "/"


# ---------- customer ----------
@app.route("/")
def home():
    db = get_db()
    q = request.args.get("q", "").strip()
    cat = request.args.get("cat", "")
    cats = db.execute("SELECT * FROM categories ORDER BY id").fetchall()
    sql = ("SELECT s.*, c.key AS cat_key FROM shops s JOIN categories c ON c.id=s.category_id WHERE 1=1")
    params = []
    if cat:
        sql += " AND c.key=?"; params.append(cat)
    if q:
        sql += " AND (s.name_en LIKE ? OR s.name_ur LIKE ? OR s.id IN (SELECT shop_id FROM items WHERE name_en LIKE ? OR name_ur LIKE ?))"
        params += ["%" + q + "%"] * 4
    sql += " ORDER BY s.is_open DESC, s.name_en"
    shops = db.execute(sql, params).fetchall()
    db.close()
    return render_template("home.html", categories=cats, shops=shops, q=q, cat=cat)


@app.route("/shop/<int:shop_id>")
def shop(shop_id):
    db = get_db()
    s = db.execute("SELECT s.*, c.key AS cat_key FROM shops s JOIN categories c ON c.id=s.category_id WHERE s.id=?",
                   (shop_id,)).fetchone()
    if not s:
        db.close(); abort(404)
    items = db.execute("SELECT * FROM items WHERE shop_id=? AND in_stock=1 ORDER BY name_en", (shop_id,)).fetchall()
    db.close()
    return render_template("shop.html", shop=s, items=items)


@app.route("/cart/add/<int:item_id>", methods=["POST"])
def cart_add(item_id):
    db = get_db()
    ok = db.execute("SELECT 1 FROM items WHERE id=? AND in_stock=1", (item_id,)).fetchone()
    db.close()
    if not ok:
        abort(404)
    cart = get_cart()
    cart[str(item_id)] = cart.get(str(item_id), 0) + 1
    save_cart(cart)
    nxt = request.form.get("next") or url_for("cart")
    return redirect(nxt)


@app.route("/cart")
def cart():
    lines, subtotal, fee, total = cart_detail()
    return render_template("cart.html", lines=lines, subtotal=subtotal, fee=fee, total=total)


@app.route("/cart/update", methods=["POST"])
def cart_update():
    cart = get_cart()
    iid = request.form.get("item_id")
    qty = int(request.form.get("qty", 0))
    if iid:
        if qty > 0:
            cart[iid] = min(qty, 99)
        else:
            cart.pop(iid, None)
    save_cart(cart)
    return redirect(url_for("cart"))


@app.route("/checkout")
@customer_login_required
def checkout():
    lines, subtotal, fee, total = cart_detail()
    if not lines:
        return redirect(url_for("cart"))
    return render_template("checkout.html", lines=lines, subtotal=subtotal, fee=fee,
                           total=total, areas=AREAS)


@app.route("/checkout", methods=["POST"])
@customer_login_required
def checkout_post():
    lines, subtotal, fee, total = cart_detail()
    l = lang()
    if not lines:
        return redirect(url_for("cart"))
    name = request.form.get("name", "").strip() or session.get("user_name", "")
    phone = re.sub(r"[\s-]", "", request.form.get("phone", "").strip()) or session.get("user_phone", "")
    area = request.form.get("area", "")
    addr = request.form.get("address", "").strip()
    err = None
    if not name:
        err = tr("name_required", l)
    elif not PHONE_RE.match(phone):
        err = tr("invalid_phone", l)
    elif area not in AREA_MAP:
        err = tr("area_required", l)
    elif not addr:
        err = tr("address_required", l)
    if err:
        return render_template("checkout.html", lines=lines, subtotal=subtotal, fee=fee,
                               total=total, areas=AREAS, error=err,
                               form=request.form), 400
    db = get_db()
    code = new_order_code(db)
    cur = db.execute(
        "INSERT INTO orders (order_code, customer_name, phone, area_key, address_detail,"
        " subtotal, delivery_fee, total, status, user_id) VALUES (?,?,?,?,?,?,?,?, 'placed', ?)",
        (code, name, phone, area, addr, subtotal, fee, total, session.get("user_id")))
    oid = cur.lastrowid
    for ln in lines:
        it = ln["item"]
        db.execute(
            "INSERT INTO order_items (order_id, item_name_en, item_name_ur, price, qty, line_total)"
            " VALUES (?,?,?,?,?,?)",
            (oid, it["name_en"], it["name_ur"], it["price"], ln["qty"], ln["line_total"]))
    db.commit(); db.close()
    session.pop("cart", None)
    return redirect(url_for("order_confirm", code=code))


@app.route("/order/<code>")
def order_confirm(code):
    db = get_db()
    o = db.execute("SELECT * FROM orders WHERE order_code=?", (code,)).fetchone()
    db.close()
    if not o:
        abort(404)
    return render_template("confirm.html", order=o)


@app.route("/track")
def track():
    code = request.args.get("code", "").strip().upper()
    phone = re.sub(r"[\s-]", "", request.args.get("phone", "").strip())
    order, items, orders = None, [], []
    db = get_db()
    if code:
        order = db.execute(
            "SELECT o.*, r.name AS rider_name FROM orders o LEFT JOIN riders r ON r.id=o.rider_id"
            " WHERE o.order_code=?", (code,)).fetchone()
        if order:
            items = db.execute("SELECT * FROM order_items WHERE order_id=?", (order["id"],)).fetchall()
    elif phone and PHONE_RE.match(phone):
        orders = db.execute("SELECT * FROM orders WHERE phone=? ORDER BY id DESC LIMIT 10", (phone,)).fetchall()
    db.close()
    searched = bool(code or phone)
    not_found = searched and not order and not orders
    return render_template("track.html", order=order, items=items, orders=orders,
                           not_found=not_found, code=request.args.get("code", ""))


# ---------- customer registration (mobile OTP) ----------
@app.route("/register")
def register():
    if session.get("user_id"):
        return redirect(_safe_next())
    return render_template("register.html", next=_safe_next())


@app.route("/register", methods=["POST"])
def register_post():
    l = lang()
    phone = re.sub(r"[\s-]", "", request.form.get("phone", "").strip())
    nxt = _safe_next()
    if not PHONE_RE.match(phone):
        return render_template("register.html", error=tr("invalid_phone", l), next=nxt), 400
    db = get_db()
    last = db.execute("SELECT created_at FROM otp_codes WHERE phone=? ORDER BY id DESC LIMIT 1",
                      (phone,)).fetchone()
    if last:
        age = (datetime.now() - datetime.fromisoformat(last["created_at"])).total_seconds()
        if age < RESEND_COOLDOWN_SEC:
            db.close()
            return render_template("register.html", error=tr("resend_wait", l), next=nxt), 429
    # void any previous unused codes for this phone
    db.execute("UPDATE otp_codes SET used=1 WHERE phone=? AND used=0", (phone,))
    code = "%06d" % secrets.randbelow(1000000)
    expires = (datetime.now() + timedelta(minutes=OTP_EXPIRY_MIN)).isoformat(timespec="seconds")
    db.execute("INSERT INTO otp_codes (phone, code, expires_at) VALUES (?,?,?)",
               (phone, code, expires))
    db.commit(); db.close()
    send_otp(phone, code)  # demo mode: code shown on the verify page
    session["pending_phone"] = phone
    return redirect(url_for("register_verify", next=nxt))


@app.route("/register/verify")
def register_verify():
    phone = session.get("pending_phone")
    if not phone:
        return redirect(url_for("register", next=_safe_next()))
    db = get_db()
    row = _latest_otp(db, phone)
    is_new = not db.execute("SELECT 1 FROM users WHERE phone=?", (phone,)).fetchone()
    db.close()
    demo_code = row["code"] if row and _otp_valid(row) else None
    return render_template("verify.html", phone=phone, is_new=is_new,
                           demo_code=demo_code, next=_safe_next())


@app.route("/register/verify", methods=["POST"])
def register_verify_post():
    l = lang()
    phone = session.get("pending_phone")
    nxt = _safe_next()
    if not phone:
        return redirect(url_for("register", next=nxt))
    entered = re.sub(r"\D", "", request.form.get("code", ""))
    name = request.form.get("name", "").strip()
    db = get_db()
    row = _latest_otp(db, phone)
    err = None
    if not row or not _otp_valid(row):
        err = tr("otp_expired", l)
    elif row["attempts"] >= OTP_MAX_ATTEMPTS:
        db.execute("UPDATE otp_codes SET used=1 WHERE id=?", (row["id"],))
        db.commit()
        err = tr("too_many_attempts", l)
    elif entered != row["code"]:
        db.execute("UPDATE otp_codes SET attempts=attempts+1 WHERE id=?", (row["id"],))
        db.commit()
        left = OTP_MAX_ATTEMPTS - row["attempts"] - 1
        is_new = not db.execute("SELECT 1 FROM users WHERE phone=?", (phone,)).fetchone()
        db.close()
        return render_template("verify.html", phone=phone, is_new=is_new,
                               demo_code=row["code"], next=nxt,
                               error="%s (%d)" % (tr("wrong_otp", l), max(left, 0))), 400
    if err:
        db.close()
        return render_template("verify.html", phone=phone, is_new=True,
                               demo_code=None, next=nxt, error=err), 400
    db.execute("UPDATE otp_codes SET used=1 WHERE id=?", (row["id"],))
    user = db.execute("SELECT * FROM users WHERE phone=?", (phone,)).fetchone()
    if not user:
        if not name:
            db.close()
            return render_template("verify.html", phone=phone, is_new=True,
                                   demo_code=None, next=nxt,
                                   error=tr("name_required", l)), 400
        cur = db.execute("INSERT INTO users (phone, name) VALUES (?,?)", (phone, name))
        user_id, user_name = cur.lastrowid, name
    else:
        user_id, user_name = user["id"], user["name"]
    db.commit(); db.close()
    session.pop("pending_phone", None)
    session["user_id"] = user_id
    session["user_name"] = user_name
    session["user_phone"] = phone
    return redirect(nxt)


@app.route("/register/resend", methods=["POST"])
def register_resend():
    phone = session.get("pending_phone")
    nxt = _safe_next()
    if not phone:
        return redirect(url_for("register", next=nxt))
    db = get_db()
    last = db.execute("SELECT created_at FROM otp_codes WHERE phone=? ORDER BY id DESC LIMIT 1",
                      (phone,)).fetchone()
    if last and (datetime.now() - datetime.fromisoformat(last["created_at"])).total_seconds() < RESEND_COOLDOWN_SEC:
        db.close()
        return redirect(url_for("register_verify", next=nxt))
    db.execute("UPDATE otp_codes SET used=1 WHERE phone=? AND used=0", (phone,))
    code = "%06d" % secrets.randbelow(1000000)
    expires = (datetime.now() + timedelta(minutes=OTP_EXPIRY_MIN)).isoformat(timespec="seconds")
    db.execute("INSERT INTO otp_codes (phone, code, expires_at) VALUES (?,?,?)",
               (phone, code, expires))
    db.commit(); db.close()
    send_otp(phone, code)
    return redirect(url_for("register_verify", next=nxt))


@app.route("/logout")
def customer_logout():
    for k in ("user_id", "user_name", "user_phone", "pending_phone"):
        session.pop(k, None)
    return redirect(url_for("home"))


# ---------- admin ----------
@app.route("/admin/login", methods=["GET", "POST"])
def admin_login():
    if request.method == "POST":
        db = get_db()
        a = db.execute("SELECT * FROM admins WHERE username=?", (request.form.get("username", ""),)).fetchone()
        db.close()
        if a and check_password_hash(a["password_hash"], request.form.get("password", "")):
            session["admin"] = True
            return redirect(url_for("admin_dash"))
        return render_template("admin/login.html", error=T("invalid_login"))
    return render_template("admin/login.html")


@app.route("/admin/logout")
def admin_logout():
    session.pop("admin", None)
    return redirect(url_for("admin_login"))


@app.route("/admin")
@admin_required
def admin_dash():
    db = get_db()
    today = date.today().isoformat()
    n_orders = db.execute("SELECT COUNT(*) c FROM orders WHERE date(created_at)=?", (today,)).fetchone()["c"]
    rev = db.execute("SELECT COALESCE(SUM(total),0) s FROM orders WHERE date(created_at)=? AND status!='cancelled'",
                     (today,)).fetchone()["s"]
    by_status = {r["status"]: r["c"] for r in
                 db.execute("SELECT status, COUNT(*) c FROM orders WHERE date(created_at)=? GROUP BY status", (today,))}
    recent = db.execute("SELECT * FROM orders ORDER BY id DESC LIMIT 8").fetchall()
    db.close()
    return render_template("admin/dashboard.html", n_orders=n_orders, revenue=rev,
                           by_status=by_status, recent=recent, statuses=STATUSES)


@app.route("/admin/orders")
@admin_required
def admin_orders():
    st = request.args.get("status", "")
    db = get_db()
    sql = ("SELECT o.*, r.name AS rider_name FROM orders o LEFT JOIN riders r ON r.id=o.rider_id")
    params = []
    if st in STATUSES:
        sql += " WHERE o.status=?"; params.append(st)
    sql += " ORDER BY o.id DESC"
    orders = db.execute(sql, params).fetchall()
    riders = db.execute("SELECT * FROM riders WHERE active=1 ORDER BY name").fetchall()
    db.close()
    return render_template("admin/orders.html", orders=orders, riders=riders,
                           statuses=STATUSES, fstatus=st)


@app.route("/admin/orders/<int:oid>")
@admin_required
def admin_order_detail(oid):
    db = get_db()
    o = db.execute("SELECT o.*, r.name AS rider_name FROM orders o LEFT JOIN riders r ON r.id=o.rider_id WHERE o.id=?",
                   (oid,)).fetchone()
    if not o:
        db.close(); abort(404)
    items = db.execute("SELECT * FROM order_items WHERE order_id=?", (oid,)).fetchall()
    riders = db.execute("SELECT * FROM riders WHERE active=1 ORDER BY name").fetchall()
    db.close()
    return render_template("admin/order_detail.html", order=o, items=items,
                           riders=riders, statuses=STATUSES)


@app.route("/admin/orders/<int:oid>/status", methods=["POST"])
@admin_required
def admin_order_status(oid):
    st = request.form.get("status", "")
    if st in STATUSES:
        db = get_db()
        db.execute("UPDATE orders SET status=? WHERE id=?", (st, oid))
        db.commit(); db.close()
    return redirect(url_for("admin_order_detail", oid=oid))


@app.route("/admin/orders/<int:oid>/assign", methods=["POST"])
@admin_required
def admin_order_assign(oid):
    rid = request.form.get("rider_id") or None
    db = get_db()
    if rid:
        ok = db.execute("SELECT 1 FROM riders WHERE id=? AND active=1", (rid,)).fetchone()
        rid = rid if ok else None
    db.execute("UPDATE orders SET rider_id=? WHERE id=?", (rid, oid))
    db.commit(); db.close()
    return redirect(url_for("admin_order_detail", oid=oid))


def _crud_list(tpl, table, order_by="id"):
    db = get_db()
    rows = db.execute("SELECT * FROM %s ORDER BY %s" % (table, order_by)).fetchall()
    db.close()
    return render_template(tpl, rows=rows)


@app.route("/admin/shops")
@admin_required
def admin_shops():
    db = get_db()
    rows = db.execute("SELECT s.*, c.key AS cat_key FROM shops s JOIN categories c ON c.id=s.category_id ORDER BY s.id").fetchall()
    cats = db.execute("SELECT * FROM categories ORDER BY id").fetchall()
    db.close()
    return render_template("admin/shops.html", rows=rows, categories=cats, areas=AREAS)


@app.route("/admin/shops/add", methods=["POST"])
@admin_required
def admin_shop_add():
    db = get_db()
    db.execute("INSERT INTO shops (name_en, name_ur, category_id, area_key, is_open) VALUES (?,?,?,?,?)",
               (request.form["name_en"], request.form["name_ur"], request.form["category_id"],
                request.form["area_key"], 1 if request.form.get("is_open") else 0))
    db.commit(); db.close()
    return redirect(url_for("admin_shops"))


@app.route("/admin/shops/<int:sid>/edit", methods=["POST"])
@admin_required
def admin_shop_edit(sid):
    db = get_db()
    db.execute("UPDATE shops SET name_en=?, name_ur=?, category_id=?, area_key=?, is_open=? WHERE id=?",
               (request.form["name_en"], request.form["name_ur"], request.form["category_id"],
                request.form["area_key"], 1 if request.form.get("is_open") else 0, sid))
    db.commit(); db.close()
    return redirect(url_for("admin_shops"))


@app.route("/admin/shops/<int:sid>/delete", methods=["POST"])
@admin_required
def admin_shop_delete(sid):
    db = get_db()
    db.execute("DELETE FROM shops WHERE id=?", (sid,))
    db.commit(); db.close()
    return redirect(url_for("admin_shops"))


@app.route("/admin/shops/<int:sid>/items")
@admin_required
def admin_items(sid):
    db = get_db()
    shop = db.execute("SELECT * FROM shops WHERE id=?", (sid,)).fetchone()
    if not shop:
        db.close(); abort(404)
    rows = db.execute("SELECT * FROM items WHERE shop_id=? ORDER BY id", (sid,)).fetchall()
    db.close()
    return render_template("admin/items.html", shop=shop, rows=rows)


@app.route("/admin/shops/<int:sid>/items/add", methods=["POST"])
@admin_required
def admin_item_add(sid):
    db = get_db()
    db.execute("INSERT INTO items (shop_id, name_en, name_ur, price, unit_en, unit_ur, in_stock) VALUES (?,?,?,?,?,?,?)",
               (sid, request.form["name_en"], request.form["name_ur"], float(request.form["price"]),
                request.form.get("unit_en", "pc"), request.form.get("unit_ur", "عدد"),
                1 if request.form.get("in_stock") else 0))
    db.commit(); db.close()
    return redirect(url_for("admin_items", sid=sid))


@app.route("/admin/items/<int:iid>/edit", methods=["POST"])
@admin_required
def admin_item_edit(iid):
    db = get_db()
    row = db.execute("SELECT shop_id FROM items WHERE id=?", (iid,)).fetchone()
    db.execute("UPDATE items SET name_en=?, name_ur=?, price=?, unit_en=?, unit_ur=?, in_stock=? WHERE id=?",
               (request.form["name_en"], request.form["name_ur"], float(request.form["price"]),
                request.form.get("unit_en", "pc"), request.form.get("unit_ur", "عدد"),
                1 if request.form.get("in_stock") else 0, iid))
    db.commit(); db.close()
    return redirect(url_for("admin_items", sid=row["shop_id"]))


@app.route("/admin/items/<int:iid>/delete", methods=["POST"])
@admin_required
def admin_item_delete(iid):
    db = get_db()
    row = db.execute("SELECT shop_id FROM items WHERE id=?", (iid,)).fetchone()
    db.execute("DELETE FROM items WHERE id=?", (iid,))
    db.commit(); db.close()
    return redirect(url_for("admin_items", sid=row["shop_id"]))


@app.route("/admin/categories")
@admin_required
def admin_categories():
    return _crud_list("admin/categories.html", "categories")


@app.route("/admin/categories/add", methods=["POST"])
@admin_required
def admin_category_add():
    db = get_db()
    db.execute("INSERT OR IGNORE INTO categories (key, name_en, name_ur) VALUES (?,?,?)",
               (request.form["key"], request.form["name_en"], request.form["name_ur"]))
    db.commit(); db.close()
    return redirect(url_for("admin_categories"))


@app.route("/admin/categories/<int:cid>/delete", methods=["POST"])
@admin_required
def admin_category_delete(cid):
    db = get_db()
    db.execute("DELETE FROM categories WHERE id=?", (cid,))
    db.commit(); db.close()
    return redirect(url_for("admin_categories"))


@app.route("/admin/riders")
@admin_required
def admin_riders():
    return _crud_list("admin/riders.html", "riders", "name")


@app.route("/admin/riders/add", methods=["POST"])
@admin_required
def admin_rider_add():
    from werkzeug.security import generate_password_hash
    db = get_db()
    try:
        db.execute("INSERT INTO riders (name, username, password_hash, phone, active) VALUES (?,?,?,?,1)",
                   (request.form["name"], request.form["username"],
                    generate_password_hash(request.form["password"]), request.form.get("phone", "")))
        db.commit()
    except sqlite3.IntegrityError:
        pass
    db.close()
    return redirect(url_for("admin_riders"))


@app.route("/admin/riders/<int:rid>/toggle", methods=["POST"])
@admin_required
def admin_rider_toggle(rid):
    db = get_db()
    db.execute("UPDATE riders SET active = 1 - active WHERE id=?", (rid,))
    db.commit(); db.close()
    return redirect(url_for("admin_riders"))


@app.route("/admin/riders/<int:rid>/delete", methods=["POST"])
@admin_required
def admin_rider_delete(rid):
    db = get_db()
    db.execute("DELETE FROM riders WHERE id=?", (rid,))
    db.commit(); db.close()
    return redirect(url_for("admin_riders"))


# ---------- rider ----------
@app.route("/rider/login", methods=["GET", "POST"])
def rider_login():
    if request.method == "POST":
        db = get_db()
        r = db.execute("SELECT * FROM riders WHERE username=? AND active=1",
                       (request.form.get("username", ""),)).fetchone()
        db.close()
        if r and check_password_hash(r["password_hash"], request.form.get("password", "")):
            session["rider_id"] = r["id"]
            return redirect(url_for("rider_home"))
        return render_template("rider/login.html", error=T("invalid_login"))
    return render_template("rider/login.html")


@app.route("/rider/logout")
def rider_logout():
    session.pop("rider_id", None)
    return redirect(url_for("rider_login"))


@app.route("/rider")
@rider_required
def rider_home():
    db = get_db()
    me = db.execute("SELECT * FROM riders WHERE id=?", (session["rider_id"],)).fetchone()
    orders = db.execute(
        "SELECT * FROM orders WHERE rider_id=? AND status IN ('confirmed','preparing','onway')"
        " ORDER BY id DESC", (session["rider_id"],)).fetchall()
    done = db.execute(
        "SELECT * FROM orders WHERE rider_id=? AND status='delivered' ORDER BY id DESC LIMIT 10",
        (session["rider_id"],)).fetchall()
    db.close()
    return render_template("rider/home.html", me=me, orders=orders, done=done)


@app.route("/rider/orders/<int:oid>")
@rider_required
def rider_order(oid):
    db = get_db()
    o = db.execute("SELECT * FROM orders WHERE id=? AND rider_id=?", (oid, session["rider_id"])).fetchone()
    if not o:
        db.close(); abort(404)
    items = db.execute("SELECT * FROM order_items WHERE order_id=?", (oid,)).fetchall()
    db.close()
    return render_template("rider/order.html", order=o, items=items)


@app.route("/rider/orders/<int:oid>/status", methods=["POST"])
@rider_required
def rider_order_status(oid):
    st = request.form.get("status", "")
    if st in ("onway", "delivered"):
        db = get_db()
        db.execute("UPDATE orders SET status=? WHERE id=? AND rider_id=?", (st, oid, session["rider_id"]))
        db.commit(); db.close()
    return redirect(url_for("rider_order", oid=oid))


# ---------- PWA ----------
@app.route("/manifest.json")
def manifest():
    return jsonify({
        "name": "Jamshoro Bazaar",
        "short_name": "JB Bazaar",
        "start_url": "/",
        "display": "standalone",
        "background_color": "#ffffff",
        "theme_color": "#1b7a3d",
        "icons": [{"src": "/static/icon.png", "sizes": "512x512", "type": "image/png"}],
    })


@app.route("/health")
def health():
    return "ok"


if __name__ == "__main__":
    init_db()
    migrate()
    app.run(host="127.0.0.1", port=int(os.environ.get("PORT", "5050")))
