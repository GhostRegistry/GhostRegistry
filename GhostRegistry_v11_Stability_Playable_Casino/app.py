from flask import Flask, render_template, request, redirect, session, Response, jsonify
from supabase import create_client
import bcrypt
import os
import random
import string
import uuid
import base64
from datetime import datetime, date
from werkzeug.utils import secure_filename

app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", "ghostregistry_secret_key")
UPLOAD_FOLDER = os.path.join(app.static_folder, "uploads")
os.makedirs(UPLOAD_FOLDER, exist_ok=True)
ALLOWED_IMAGE_EXTENSIONS = {"png", "jpg", "jpeg", "gif", "webp"}

SUPABASE_URL = os.environ.get("SUPABASE_URL", "https://rzogtnozxurtfcbaygqi.supabase.co")
SUPABASE_KEY = os.environ.get("SUPABASE_KEY", "sb_publishable_QWWXCsEEI7dqpK31Q51jnw_9dYAQ2c3")

supabase = create_client(SUPABASE_URL, SUPABASE_KEY)

CREDIT_NAME = "Ghost Shards"
UNLOCK_COST = 100
MYSTERY_CRATE_COST = 500
ELITE_WHEEL_COST = 1000
PROFILE_EFFECT_COST = 750
RECORD_SCANNER_COST = 300
ELITE_WHEEL_REWARDS = [100, 250, 500, 1000, 2500, 5000]
PROFILE_EFFECTS = [
    "Neon Ghost",
    "Phantom Blue",
    "Shadow Pulse",
    "Gold Architect",
    "Wraith Aura"
]



def safe_select(table_name, default=None, order_by=None, desc=True, limit=None):
    try:
        q = supabase.table(table_name).select("*")
        if order_by:
            q = q.order(order_by, desc=desc)
        if limit:
            q = q.limit(limit)
        return q.execute().data or []
    except Exception as e:
        print(f"SAFE SELECT ERROR {table_name}:", e)
        return default if default is not None else []


def safe_insert(table_name, data):
    try:
        return supabase.table(table_name).insert(data).execute().data
    except Exception as e:
        print(f"SAFE INSERT ERROR {table_name}:", e)
        return None


def safe_update(table_name, data, column, value):
    try:
        return supabase.table(table_name).update(data).eq(column, value).execute().data
    except Exception as e:
        print(f"SAFE UPDATE ERROR {table_name}:", e)
        return None


def get_inventory(user_id):
    try:
        items = supabase.table("user_inventory").select("*").eq("user_id", user_id).execute().data or []
        # Older SQL versions may have used item_name only. Normalize so the shop still works.
        for item in items:
            if not item.get("item_key") and item.get("item_name"):
                item["item_key"] = str(item.get("item_name", "")).strip().lower().replace(" ", "_")
        return items
    except Exception as e:
        print("INVENTORY READ ERROR:", e)
        return []


def has_inventory(user_id, item_key):
    return any(i.get("item_key") == item_key for i in get_inventory(user_id))


def add_inventory_item(user_id, item_key, item_name, item_type="cosmetic", meta=None):
    # If the item already exists, stack quantity instead of creating infinite duplicates.
    try:
        existing = supabase.table("user_inventory").select("*").eq("user_id", user_id).eq("item_key", item_key).execute().data or []
        if existing:
            current_qty = existing[0].get("quantity") or 1
            return supabase.table("user_inventory").update({
                "quantity": current_qty + 1,
                "item_name": item_name,
                "item_type": item_type,
                "meta": meta or existing[0].get("meta") or {}
            }).eq("id", existing[0]["id"]).execute().data
    except Exception as e:
        print("INVENTORY STACK ERROR:", e)

    return safe_insert("user_inventory", {
        "user_id": user_id,
        "item_key": item_key,
        "item_name": item_name,
        "item_type": item_type,
        "quantity": 1,
        "meta": meta or {}
    })


def record_shop_purchase(user_id, item_key, item_name, cost, reward_text=""):
    safe_insert("shop_purchases", {
        "user_id": user_id,
        "item_key": item_key,
        "item_name": item_name,
        "cost": cost,
        "reward_text": reward_text
    })


def user_unlocked_count(user_id):
    try:
        return len(unlocked_record_ids(user_id))
    except Exception:
        return 0


def public_activity(limit=12):
    logs = safe_select("audit_logs", order_by="timestamp", desc=True, limit=limit)
    safe_actions = []
    for log in logs:
        action = (log.get("action") or "activity").replace("_", " ").title()
        safe_actions.append({
            "title": action,
            "by": log.get("performed_by", "system"),
            "time": log.get("timestamp", log.get("created_at", "")),
            "details": log.get("details", "")[:120]
        })
    return safe_actions


def ghost_news():
    announcements = [l for l in safe_select("audit_logs", order_by="timestamp", desc=True, limit=30) if l.get("action") == "global_announcement"]
    news = [{"title": a.get("target_record", "System Announcement"), "text": a.get("details", ""), "time": a.get("timestamp", "")} for a in announcements]
    if not news:
        news = [
            {"title": "GhostRegistry v2 Online", "text": "The upgraded GhostRegistry network is active with records, ranks, shop, guide, missions, and command consoles.", "time": "System"},
            {"title": "Unlock Protocol", "text": "Operatives can search first and last names before spending Ghost Shards to unlock full intelligence.", "time": "System"},
            {"title": "Command Access", "text": "Overseers and Architects have expanded command tools, including Ghost Shard management.", "time": "System"}
        ]
    return news

def get_rank(credits):
    credits = safe_int(credits, 0)
    if credits >= 10000:
        return "Wraith"
    if credits >= 5000:
        return "Spectre"
    if credits >= 2500:
        return "Phantom"
    if credits >= 1000:
        return "Hunter"
    if credits >= 500:
        return "Watcher"
    return "Recruit"


def role_guide(role):
    role = (role or "operative").strip().lower()
    common = [
        {"title": "Dashboard", "text": "Use the dashboard as your main menu. It shows your Ghost Shards, social code, records count, shop, wheel, arcade, chat, and account settings."},
        {"title": "Account Management", "text": "Open Account Management to change your username or password. You must enter your current password first."},
        {"title": "Daily Wheel", "text": "Spin once per day to earn free Ghost Shards."},
        {"title": "Arcade", "text": "Use Ghost Shards in the arcade games. These are fake in-site credits only, not real money."},
        {"title": "Chat", "text": "Use Public Chat Network to post messages or filter posts with a friend's social code."},
    ]
    operative = [
        {"title": "Records Database", "text": "Search by first or last name before unlocking. Names stay visible so you can choose whose information to unlock."},
        {"title": "Unlocking Records", "text": f"Click Unlock on a locked record. It costs {UNLOCK_COST} {CREDIT_NAME}. After unlocking, email, address, phone, age, role, and notes become visible forever."},
        {"title": "Ghost Shard Shop", "text": "Buy a random record unlock bundle when you want a surprise unlock."},
        {"title": "Ranks", "text": "Your cosmetic rank is based on Ghost Shards: Recruit, Watcher, Hunter, Phantom, Spectre, then Wraith."},
    ]
    overseer = [
        {"title": "Overseer Console", "text": "Open the Overseer Console to view records, view deleted records, view audit logs, reset operative passwords, and manage Ghost Shards."},
        {"title": "Giving Ghost Shards", "text": "Use a username plus social code to give Ghost Shards to operatives. You can also give Ghost Shards to yourself from the self-credit box."},
        {"title": "Password Resets", "text": "Select an operative account, enter a new password, then reset it. Overseers cannot reset architect or overseer accounts."},
        {"title": "Records", "text": "Overseers can create, edit, and delete active records from the Records Database, but cannot permanently delete deleted records."},
    ]
    architect = [
        {"title": "Architect Command Center", "text": "Architects have full system control: user creation, user updates, Ghost Shards, record recovery, permanent deletion, and audit management."},
        {"title": "User Management", "text": "Create operative, overseer, or architect accounts. Architects cannot modify other architect accounts unless it is their own account."},
        {"title": "Emergency Lockdown", "text": "Use Emergency Lockdown to force every user to log in again. This is useful after a password leak or major system change."},
        {"title": "Record Recovery", "text": "Restore deleted records or permanently delete them from the Architect Command Center."},
    ]
    if role == "architect":
        return common + operative + overseer + architect
    if role == "overseer":
        return common + operative + overseer
    return common + operative


def safe_int(value, default=0):
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def hash_password(password):
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


def check_password(password, password_hash):
    try:
        return bcrypt.checkpw(password.encode("utf-8"), password_hash.encode("utf-8"))
    except:
        return False


def current_user():
    return session.get("user")


def generate_social_code():
    while True:
        code = "GHOST-" + "".join(random.choices(string.ascii_uppercase + string.digits, k=4))
        existing = supabase.table("users").select("*").eq("social_code", code).execute().data
        if not existing:
            return code


def refresh_session_user():
    user = current_user()

    if not user:
        return None

    db_user = supabase.table("users").select("*").eq("id", user["id"]).execute().data

    if not db_user:
        session.clear()
        return None

    db_user = db_user[0]

    updates = {}

    if db_user.get("credits") is None:
        updates["credits"] = 0

    if not db_user.get("social_code"):
        updates["social_code"] = generate_social_code()

    if updates:
        supabase.table("users").update(updates).eq("id", db_user["id"]).execute()
        db_user = supabase.table("users").select("*").eq("id", user["id"]).execute().data[0]

    session["user"] = {
        "id": db_user["id"],
        "username": db_user["username"],
        "role": db_user["role"].strip().lower(),
        "session_version": db_user.get("session_version", 1),
        "credits": db_user.get("credits", 0),
        "social_code": db_user.get("social_code", ""),
        "rank": get_rank(db_user.get("credits", 0)),
        "account_locked": db_user.get("account_locked", False),
        "avatar_url": db_user.get("avatar_url", ""),
        "profile_effect": db_user.get("profile_effect", "")
    }

    return session["user"]



def get_system_setting(key, default=None):
    try:
        rows = supabase.table("system_settings").select("*").eq("setting_key", key).execute().data or []
        if rows:
            return rows[0].get("setting_value")
    except Exception as e:
        print("SYSTEM SETTING READ ERROR:", e)
    return default

def set_system_setting(key, value):
    try:
        rows = supabase.table("system_settings").select("*").eq("setting_key", key).execute().data or []
        if rows:
            supabase.table("system_settings").update({"setting_value": value}).eq("setting_key", key).execute()
        else:
            supabase.table("system_settings").insert({"setting_key": key, "setting_value": value}).execute()
        return True
    except Exception as e:
        print("SYSTEM SETTING WRITE ERROR:", e)
        return False

def force_logout_user(user_id):
    try:
        rows = supabase.table("users").select("*").eq("id", user_id).execute().data or []
        if rows:
            v = (rows[0].get("session_version", 1) or 1) + 1
            supabase.table("users").update({"session_version": v}).eq("id", user_id).execute()
            return True
    except Exception as e:
        print("FORCE LOGOUT ERROR:", e)
    return False

def notify_user(user_id, title, text):
    safe_insert("notifications", {"user_id": user_id, "title": title, "message": text, "is_read": False})



def user_avatar_map():
    rows = safe_select("users")
    return {u.get("id"): {
        "avatar_url": u.get("avatar_url") or u.get("profile_pic") or "",
        "rank": get_rank(u.get("credits", 0)),
        "role": u.get("role", "operative"),
        "username": u.get("username", "Unknown")
    } for u in rows}

def decorate_messages_with_profiles(messages, id_field="user_id"):
    profiles = user_avatar_map()
    out = []
    for m in messages or []:
        mm = dict(m)
        p = profiles.get(mm.get(id_field), {})
        mm["avatar_url"] = p.get("avatar_url", "")
        mm["sender_rank"] = p.get("rank", "Recruit")
        mm["sender_role"] = p.get("role", "operative")
        out.append(mm)
    return out

def grant_achievement(user_id, code, title, reward=0):
    try:
        existing = supabase.table("user_achievements").select("*").eq("user_id", user_id).eq("achievement_code", code).execute().data or []
        if existing:
            return False
        supabase.table("user_achievements").insert({"user_id": user_id, "achievement_code": code, "title": title, "reward": reward}).execute()
        if reward:
            add_credits(user_id, reward, "achievement_reward", title)
        notify_user(user_id, "Achievement unlocked", f"{title} (+{reward} {CREDIT_NAME})" if reward else title)
        return True
    except Exception as e:
        print("ACHIEVEMENT ERROR:", e)
        return False

def evaluate_achievements(user_id):
    user_rows = supabase.table("users").select("*").eq("id", user_id).execute().data or []
    if not user_rows:
        return
    u = user_rows[0]
    grant_achievement(user_id, "first_login", "First Login", 50)
    if safe_int(u.get("credits"),0) >= 1000:
        grant_achievement(user_id, "shard_1000", "Hunter Wallet", 100)
    if safe_int(u.get("credits"),0) >= 1000000:
        grant_achievement(user_id, "millionaire", "Ghost Shard Millionaire", 1000)
    if user_unlocked_count(user_id) >= 1:
        grant_achievement(user_id, "first_unlock", "First Record Unlock", 100)
    if len([p for p in safe_select("shop_purchases") if p.get("user_id") == user_id]) >= 1:
        grant_achievement(user_id, "first_purchase", "First Shop Purchase", 100)

def mission_cards(user_id):
    today = date.today().isoformat()
    logs = [l for l in safe_select("audit_logs", order_by="timestamp", desc=True, limit=200) if l.get("performed_by") == current_user().get("username")]
    def done(action): return any((l.get("action") == action and str(l.get("timestamp", l.get("created_at", ""))).startswith(today)) for l in logs)
    return [
        {"name":"Daily Login Signal","goal":"Log in today.","reward":"10 GS","done":True},
        {"name":"Spin The Wheel","goal":"Spin the Daily Wheel.","reward":"30 GS","done":done("daily_wheel_spin")},
        {"name":"Network Message","goal":"Post in public chat.","reward":"25 GS","done":done("chat_message")},
        {"name":"Record Hunter","goal":"Unlock a record.","reward":"50 GS","done":done("record_unlocked")},
        {"name":"Arcade Run","goal":"Play an arcade game.","reward":"25 GS","done":done("arcade_play")},
    ]

def validate_session():
    user = current_user()

    if not user:
        return False

    db_user = supabase.table("users").select("*").eq("id", user["id"]).execute().data

    if not db_user:
        session.clear()
        return False

    db_user = db_user[0]

    if get_system_setting("website_lockdown", "off") == "on" and (db_user.get("role", "").strip().lower() != "architect"):
        session.clear()
        return False

    if db_user.get("account_locked") and (db_user.get("role", "").strip().lower() != "architect"):
        session.clear()
        return False

    db_version = db_user.get("session_version", 1)
    session_version = user.get("session_version", 1)

    if db_version != session_version:
        session.clear()
        return False

    refresh_session_user()
    return True


def get_user(username):
    res = supabase.table("users").select("*").eq("username", username.strip()).execute()
    return res.data[0] if res.data else None


def log_action(action, target_record="", details=""):
    user = current_user()

    try:
        supabase.table("audit_logs").insert({
            "action": action,
            "target_record": target_record,
            "performed_by": user["username"] if user else "system",
            "details": details
        }).execute()
    except Exception as e:
        print("AUDIT LOG ERROR:", e)


def log_credit(username, user_id, amount, action, details=""):
    try:
        supabase.table("credit_logs").insert({
            "user_id": user_id,
            "username": username,
            "amount": amount,
            "action": action,
            "details": details
        }).execute()
    except Exception as e:
        print("CREDIT LOG ERROR:", e)


def add_credits(user_id, amount, action, details=""):
    target = supabase.table("users").select("*").eq("id", user_id).execute().data

    if not target:
        return False

    target = target[0]
    current = target.get("credits") or 0
    new_total = current + amount

    if new_total < 0:
        return False

    supabase.table("users").update({
        "credits": new_total
    }).eq("id", user_id).execute()

    log_credit(target["username"], user_id, amount, action, details)

    if current_user() and current_user()["id"] == user_id:
        refresh_session_user()

    return True



def safe_table_select(table, default=None):
    try:
        return supabase.table(table).select("*").execute().data
    except Exception as e:
        print(f"{table.upper()} SELECT ERROR:", e)
        return default if default is not None else []


def has_inventory_item(user_id, item_name):
    try:
        rows = supabase.table("user_inventory").select("*").eq("user_id", user_id).eq("item_name", item_name).execute().data
        return bool(rows)
    except Exception as e:
        print("INVENTORY CHECK ERROR:", e)
        return False


def add_inventory_item(user_id, item_name, quantity=1):
    try:
        rows = supabase.table("user_inventory").select("*").eq("user_id", user_id).eq("item_name", item_name).execute().data

        if rows:
            current_qty = rows[0].get("quantity") or 1
            supabase.table("user_inventory").update({
                "quantity": current_qty + quantity
            }).eq("id", rows[0]["id"]).execute()
        else:
            supabase.table("user_inventory").insert({
                "user_id": user_id,
                "item_name": item_name,
                "quantity": quantity
            }).execute()

        return True
    except Exception as e:
        print("INVENTORY ADD ERROR:", e)
        return False


def record_shop_purchase(user_id, item_name, cost):
    try:
        supabase.table("shop_purchases").insert({
            "user_id": user_id,
            "item_name": item_name,
            "cost": cost
        }).execute()
    except Exception as e:
        print("SHOP PURCHASE LOG ERROR:", e)


def current_inventory(user_id):
    try:
        return supabase.table("user_inventory").select("*").eq("user_id", user_id).execute().data
    except Exception as e:
        print("INVENTORY LOAD ERROR:", e)
        return []


def user_has_record_scanner(user_id):
    return has_inventory_item(user_id, "Record Scanner")


def apply_rank_from_credits(user_id):
    try:
        target = supabase.table("users").select("*").eq("id", user_id).execute().data
        if not target:
            return
        credits = target[0].get("credits") or 0
        if credits >= 10000:
            rank = "Wraith"
        elif credits >= 5000:
            rank = "Spectre"
        elif credits >= 2500:
            rank = "Phantom"
        elif credits >= 1000:
            rank = "Hunter"
        elif credits >= 500:
            rank = "Watcher"
        else:
            rank = "Recruit"
        supabase.table("users").update({"rank": rank}).eq("id", user_id).execute()
    except Exception as e:
        print("RANK UPDATE ERROR:", e)

def unlocked_record_ids(user_id):
    unlocks = supabase.table("record_unlocks").select("*").eq("user_id", user_id).execute().data
    return [u["record_id"] for u in unlocks]


def delete_records_by_ids(record_ids, username):
    deleted_count = 0

    for record_id in record_ids:
        found = supabase.table("records").select("*").eq("id", record_id).execute().data

        if found:
            r = found[0]

            deleted_data = {
                "original_record_id": str(r.get("id", "")),
                "first_name": r.get("first_name"),
                "last_name": r.get("last_name"),
                "email": r.get("email"),
                "address": r.get("address"),
                "phone": r.get("phone"),
                "age": r.get("age"),
                "role": r.get("role"),
                "notes": r.get("notes"),
                "created_by": r.get("created_by"),
                "deleted_by": username
            }

            supabase.table("deleted_records").insert(deleted_data).execute()
            supabase.table("records").delete().eq("id", record_id).execute()

            deleted_count += 1

    return deleted_count


@app.route("/", methods=["GET", "POST"])
@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        username = request.form.get("username", "").strip()
        password = request.form.get("password", "").strip()
        noodle_ok = request.form.get("noodle_terms") == "on"
        if not noodle_ok:
            return render_template("login.html", error="You must accept the Official Noodle Terms before entering.")

        user = get_user(username)

        if user and check_password(password, user["password_hash"].strip()):
            if user.get("account_locked") and user.get("role", "").strip().lower() != "architect":
                return render_template("login.html", error="This account is locked by Architect Lockdown.")

            updates = {}

            if user.get("credits") is None:
                updates["credits"] = 0

            if not user.get("social_code"):
                updates["social_code"] = generate_social_code()

            if updates:
                supabase.table("users").update(updates).eq("id", user["id"]).execute()
                user = get_user(username)

            session["user"] = {
                "id": user["id"],
                "username": user["username"],
                "role": user["role"].strip().lower(),
                "session_version": user.get("session_version", 1),
                "credits": user.get("credits", 0),
                "social_code": user.get("social_code", ""),
                "rank": get_rank(user.get("credits", 0)),
                "account_locked": user.get("account_locked", False)
            }

            log_action("login", username, "User logged in.")
            return redirect("/dashboard")

        return render_template("login.html", error="Invalid username or password")

    return render_template("login.html")


@app.route("/logout")
def logout():
    if current_user():
        log_action("logout", current_user()["username"], "User logged out.")

    session.clear()
    return redirect("/login")


@app.route("/dashboard")
def dashboard():
    if not validate_session():
        return redirect("/login")

    user = current_user()

    records = safe_select("records")
    deleted_records = safe_select("deleted_records")
    logs = safe_select("audit_logs")
    users = safe_select("users")

    stats = {
        "records": len(records),
        "deleted": len(deleted_records),
        "logs": len(logs),
        "users": len(users)
    }

    return render_template(
        "dashboard.html",
        user=user,
        stats=stats,
        credit_name=CREDIT_NAME,
        unlocked_count=user_unlocked_count(user["id"]),
        activity=public_activity(5),
        news=ghost_news()[:2],
        missions=mission_cards(user["id"]),
        inbox_count=len([m for m in safe_select("private_messages") if m.get("recipient_id") == user["id"] and not m.get("is_read")]),
        unread_notifications=len([n for n in safe_select("notifications") if n.get("user_id") == user["id"] and not n.get("is_read")])
    )


@app.route("/wheel", methods=["GET", "POST"])
def wheel():
    if not validate_session():
        return redirect("/login")

    user = current_user()
    message = ""
    reward = None

    today = str(date.today())
    db_user = supabase.table("users").select("*").eq("id", user["id"]).execute().data[0]

    can_spin = db_user.get("last_spin") != today

    if request.method == "POST":
        if not can_spin:
            message = "You have already spun the wheel today."
        else:
            if has_inventory(user["id"], "elite_wheel_boost") or has_inventory(user["id"], "elite_wheel_ticket"):
                reward = random.choice([100, 250, 500, 750, 1000, 1500, 2500, 5000])
            else:
                reward = random.choice([10, 25, 50, 75, 100, 125, 150, 200])

            supabase.table("users").update({
                "credits": (db_user.get("credits") or 0) + reward,
                "last_spin": today
            }).eq("id", user["id"]).execute()

            log_credit(user["username"], user["id"], reward, "daily_wheel", "Daily wheel reward.")
            log_action("daily_wheel_spin", user["username"], f"Won {reward} {CREDIT_NAME}.")

            refresh_session_user()
            can_spin = False
            message = f"You won {reward} {CREDIT_NAME}."

    return render_template(
        "wheel.html",
        user=current_user(),
        credit_name=CREDIT_NAME,
        can_spin=can_spin,
        reward=reward,
        message=message
    )


@app.route("/arcade", methods=["GET", "POST"])
def arcade():
    if not validate_session():
        return redirect("/login")

    user = current_user()
    message = ""

    def draw_card():
        ranks = [2,3,4,5,6,7,8,9,10,10,10,10,11]
        return random.choice(ranks)

    def hand_total(cards):
        total = sum(cards)
        aces = sum(1 for c in cards if c == 11)
        while total > 21 and aces:
            total -= 10
            aces -= 1
        return total

    def poker_result():
        ranks = list(range(2, 15))
        suits = ["♠", "♥", "♦", "♣"]
        deck = [(r, s) for r in ranks for s in suits]
        hand = random.sample(deck, 5)
        rs = sorted([r for r, _ in hand])
        ss = [s for _, s in hand]
        counts = sorted([rs.count(r) for r in set(rs)], reverse=True)
        flush = len(set(ss)) == 1
        straight = (max(rs) - min(rs) == 4 and len(set(rs)) == 5) or rs == [2,3,4,5,14]
        if straight and flush:
            return "Straight Flush", 12, hand
        if counts[0] == 4:
            return "Four of a Kind", 8, hand
        if counts == [3,2]:
            return "Full House", 6, hand
        if flush:
            return "Flush", 5, hand
        if straight:
            return "Straight", 4, hand
        if counts[0] == 3:
            return "Three of a Kind", 3, hand
        if counts == [2,2,1]:
            return "Two Pair", 2, hand
        if counts[0] == 2:
            return "Pair", 1, hand
        return "High Card", -1, hand

    def card_names(hand):
        names = {11:"J", 12:"Q", 13:"K", 14:"A"}
        return " ".join(f"{names.get(r, r)}{suit}" for r, suit in hand)

    if request.method == "POST":
        game = request.form.get("game")
        bet = safe_int(request.form.get("bet"), 0)
        choice = request.form.get("choice", "")

        db_user = supabase.table("users").select("*").eq("id", user["id"]).execute().data[0]
        balance = db_user.get("credits") or 0

        if bet <= 0:
            message = "Enter a valid bet."
        elif bet > balance:
            message = "You do not have enough Ghost Shards."
        else:
            win_amount = 0
            result_text = ""

            if game == "slots":
                symbols = ["👻", "💎", "🔷", "🕯️", "👑", "🌀"]
                reels = [random.choice(symbols) for _ in range(3)]
                unique = len(set(reels))
                if unique == 1:
                    win_amount = bet * 5
                    result_text = f"Neon Slots: {' '.join(reels)} — JACKPOT! You won {win_amount}."
                elif unique == 2:
                    win_amount = bet * 2
                    result_text = f"Neon Slots: {' '.join(reels)} — two matched. You won {win_amount}."
                else:
                    win_amount = -bet
                    result_text = f"Neon Slots: {' '.join(reels)} — no match. You lost {bet}."

            elif game == "blackjack":
                player = [draw_card(), draw_card()]
                dealer = [draw_card(), draw_card()]
                # simple auto-play: player draws under 16, dealer draws under 17
                while hand_total(player) < 16:
                    player.append(draw_card())
                while hand_total(dealer) < 17:
                    dealer.append(draw_card())
                pt, dt = hand_total(player), hand_total(dealer)
                if pt > 21:
                    win_amount = -bet
                    result_text = f"Blackjack: you busted with {pt}. Dealer had {dt}. You lost {bet}."
                elif dt > 21 or pt > dt:
                    win_amount = bet
                    result_text = f"Blackjack: you scored {pt}, dealer scored {dt}. You won {bet}."
                elif pt == dt:
                    win_amount = 0
                    result_text = f"Blackjack: push at {pt}. Your bet was returned."
                else:
                    win_amount = -bet
                    result_text = f"Blackjack: you scored {pt}, dealer scored {dt}. You lost {bet}."

            elif game == "poker":
                name, multiplier, hand = poker_result()
                if multiplier > 0:
                    win_amount = bet * multiplier
                    result_text = f"Ghost Poker: {card_names(hand)} — {name}. You won {win_amount}."
                else:
                    win_amount = -bet
                    result_text = f"Ghost Poker: {card_names(hand)} — {name}. You lost {bet}."

            elif game == "roulette":
                roll = random.randint(0, 36)
                if roll == 0:
                    color = "green"
                elif roll % 2 == 0:
                    color = "black"
                else:
                    color = "red"
                if choice == color:
                    win_amount = bet * (14 if color == "green" else 1)
                    result_text = f"Phantom Roulette landed {roll} ({color}). You won {win_amount}."
                else:
                    win_amount = -bet
                    result_text = f"Phantom Roulette landed {roll} ({color}). You lost {bet}."

            elif game == "baccarat":
                outcomes = ["player"] * 44 + ["banker"] * 45 + ["tie"] * 11
                outcome = random.choice(outcomes)
                if choice == outcome:
                    win_amount = bet * (8 if outcome == "tie" else 1)
                    result_text = f"Baccarat result: {outcome}. You won {win_amount}."
                else:
                    win_amount = -bet
                    result_text = f"Baccarat result: {outcome}. You lost {bet}."

            elif game == "jackpot_vault":
                outcome = random.choice(["1", "2", "3", "1", "2", "3", "ghost"])
                if choice == outcome:
                    win_amount = bet * (10 if outcome == "ghost" else 3)
                    result_text = f"Jackpot Vault opened {outcome}. You won {win_amount}."
                else:
                    win_amount = -bet
                    result_text = f"Jackpot Vault opened {outcome}. You lost {bet}."

            else:
                result_text = "Unknown arcade game."

            if result_text != "Unknown arcade game.":
                add_credits(user["id"], win_amount, "arcade", result_text)
                refresh_session_user()
                log_action("arcade_play", user["username"], result_text)
                try:
                    notify_user(user["id"], "Arcade result", result_text)
                except Exception:
                    pass
            message = result_text

    return render_template(
        "arcade.html",
        user=current_user(),
        credit_name=CREDIT_NAME,
        message=message
    )

@app.route("/chat", methods=["GET", "POST"])
def chat():
    if not validate_session():
        return redirect("/login")

    user = current_user()
    message = ""
    filter_code = request.args.get("social_code", "").strip()

    if request.method == "POST":
        chat_message = request.form.get("message", "").strip()

        if chat_message:
            supabase.table("chat_messages").insert({
                "user_id": user["id"],
                "username": user["username"],
                "social_code": user["social_code"],
                "message": chat_message
            }).execute()

            log_action("chat_message", user["username"], "User sent a chat message.")
            return redirect("/chat")

    if filter_code:
        messages = supabase.table("chat_messages").select("*").eq("social_code", filter_code).order("created_at", desc=True).execute().data
    else:
        messages = supabase.table("chat_messages").select("*").order("created_at", desc=True).limit(100).execute().data

    return render_template(
        "chat.html",
        user=user,
        messages=decorate_messages_with_profiles(messages),
        filter_code=filter_code,
        credit_name=CREDIT_NAME,
        message=message
    )


@app.route("/records", methods=["GET", "POST"])
def records():
    if not validate_session():
        return redirect("/login")

    user = current_user()
    message = ""

    if request.method == "POST":
        action = request.form.get("action")

        if action == "unlock_record":
            if user["role"] != "operative":
                return redirect("/records")

            record_id = request.form.get("record_id")
            already = supabase.table("record_unlocks").select("*").eq("user_id", user["id"]).eq("record_id", record_id).execute().data

            if already:
                message = "Record already unlocked."
            elif user.get("credits", 0) < UNLOCK_COST:
                message = f"You need {UNLOCK_COST} {CREDIT_NAME} to unlock this record."
            else:
                add_credits(user["id"], -UNLOCK_COST, "unlock_record", f"Unlocked record {record_id}.")
                supabase.table("record_unlocks").insert({
                    "user_id": user["id"],
                    "record_id": record_id
                }).execute()

                refresh_session_user()
                log_action("record_unlocked", record_id, f"Operative unlocked record for {UNLOCK_COST} {CREDIT_NAME}.")
                message = "Record unlocked forever."

        elif user["role"] in ["overseer", "architect"]:
            if action == "create_record":
                data = {
                    "first_name": request.form.get("first_name"),
                    "last_name": request.form.get("last_name"),
                    "email": request.form.get("email"),
                    "address": request.form.get("address"),
                    "phone": request.form.get("phone"),
                    "age": request.form.get("age") or None,
                    "role": request.form.get("role"),
                    "notes": request.form.get("notes"),
                    "created_by": user["username"]
                }

                supabase.table("records").insert(data).execute()
                log_action("record_created", f"{data['first_name']} {data['last_name']}", "Record created.")
                message = "Record created."

            elif action == "edit_record":
                record_id = request.form.get("record_id")

                if not record_id:
                    message = "Select a record first."
                else:
                    data = {
                        "first_name": request.form.get("first_name"),
                        "last_name": request.form.get("last_name"),
                        "email": request.form.get("email"),
                        "address": request.form.get("address"),
                        "phone": request.form.get("phone"),
                        "age": request.form.get("age") or None,
                        "role": request.form.get("role"),
                        "notes": request.form.get("notes"),
                        "updated_by": user["username"]
                    }

                    supabase.table("records").update(data).eq("id", record_id).execute()
                    log_action("record_edited", record_id, "Record edited.")
                    message = "Record updated."

            elif action == "delete_record":
                record_ids = request.form.getlist("record_ids")

                if not record_ids:
                    single_id = request.form.get("record_id")
                    if single_id:
                        record_ids = [single_id]

                if not record_ids:
                    message = "Select at least one record."
                else:
                    deleted_count = delete_records_by_ids(record_ids, user["username"])
                    log_action("records_deleted", str(deleted_count), "Multiple records deleted.")
                    message = f"{deleted_count} records deleted."

    records_data = supabase.table("records").select("*").execute().data
    unlocked = unlocked_record_ids(user["id"]) if user["role"] == "operative" else []

    return render_template(
        "records.html",
        records=records_data,
        unlocked=unlocked,
        unlock_cost=UNLOCK_COST,
        user=current_user(),
        message=message,
        credit_name=CREDIT_NAME,
        has_record_scanner=user_has_record_scanner(user["id"])
    )


@app.route("/shop", methods=["GET", "POST"])
def shop():
    if not validate_session():
        return redirect("/login")

    user = current_user()
    message = ""
    warning = ""

    try:
        inventory = current_inventory(user["id"])
    except Exception:
        inventory = []
        warning = "Shop inventory tables are missing. Add user_inventory and shop_purchases in Supabase."

    owned_items = [i.get("item_name") for i in inventory]
    records_data = supabase.table("records").select("*").execute().data
    unlocked = unlocked_record_ids(user["id"])
    locked_records = [r for r in records_data if r["id"] not in unlocked]

    if request.method == "POST":
        action = request.form.get("action")
        db_user = supabase.table("users").select("*").eq("id", user["id"]).execute().data[0]
        balance = db_user.get("credits") or 0

        if action == "random_unlock":
            if not locked_records:
                message = "No locked records left to unlock."
            elif balance < 250:
                message = "Not enough Ghost Shards."
            else:
                chosen = random.choice(locked_records)
                add_credits(user["id"], -250, "shop_random_unlock", f"Random unlocked record {chosen['id']}.")
                supabase.table("record_unlocks").insert({
                    "user_id": user["id"],
                    "record_id": chosen["id"]
                }).execute()
                record_shop_purchase(user["id"], "Random Record Unlock", 250)
                log_action("shop_random_unlock", chosen["id"], "Bought random record unlock.")
                refresh_session_user()
                message = f"Random record unlocked: {chosen.get('first_name', '')} {chosen.get('last_name', '')}"

        elif action == "mystery_crate":
            if balance < MYSTERY_CRATE_COST:
                message = "Not enough Ghost Shards."
            else:
                rewards = [
                    ("credits", 100),
                    ("credits", 250),
                    ("credits", 500),
                    ("item", "Neon Ghost Badge"),
                    ("item", "Phantom Chat Tag"),
                    ("item", "Wheel Boost Ticket")
                ]
                reward_type, reward_value = random.choice(rewards)
                add_credits(user["id"], -MYSTERY_CRATE_COST, "shop_mystery_crate", "Opened Mystery Crate.")
                if reward_type == "credits":
                    add_credits(user["id"], reward_value, "mystery_crate_reward", "Mystery Crate credit reward.")
                    message = f"Mystery Crate opened. You won {reward_value} Ghost Shards."
                else:
                    add_inventory_item(user["id"], reward_value, 1)
                    message = f"Mystery Crate opened. You won: {reward_value}."
                record_shop_purchase(user["id"], "Mystery Crate", MYSTERY_CRATE_COST)
                refresh_session_user()

        elif action == "elite_wheel_boost":
            if has_inventory_item(user["id"], "Elite Wheel Boost"):
                message = "Elite Wheel Boost is already active."
            elif balance < ELITE_WHEEL_COST:
                message = "Not enough Ghost Shards."
            else:
                add_credits(user["id"], -ELITE_WHEEL_COST, "shop_elite_wheel", "Bought Elite Wheel Boost.")
                add_inventory_item(user["id"], "Elite Wheel Boost", 1)
                try:
                    supabase.table("users").update({"elite_wheel": True}).eq("id", user["id"]).execute()
                except Exception as e:
                    print("ELITE WHEEL COLUMN ERROR:", e)
                record_shop_purchase(user["id"], "Elite Wheel Boost", ELITE_WHEEL_COST)
                refresh_session_user()
                message = "Elite Wheel Boost activated. Elite Wheel is now available."

        elif action == "profile_effect":
            effect = request.form.get("effect", "Neon Ghost")
            if effect not in PROFILE_EFFECTS:
                effect = "Neon Ghost"
            if balance < PROFILE_EFFECT_COST:
                message = "Not enough Ghost Shards."
            elif has_inventory_item(user["id"], f"Profile Effect: {effect}"):
                message = "You already own that profile effect. Equip it from Inventory."
            else:
                add_credits(user["id"], -PROFILE_EFFECT_COST, "shop_profile_effect", f"Bought profile effect {effect}.")
                add_inventory_item(user["id"], f"Profile Effect: {effect}", 1)
                record_shop_purchase(user["id"], f"Profile Effect: {effect}", PROFILE_EFFECT_COST)
                refresh_session_user()
                message = f"Profile effect purchased: {effect}. Equip it from Inventory."

        elif action == "record_scanner":
            if has_inventory_item(user["id"], "Record Scanner"):
                message = "Record Scanner is already active."
            elif balance < RECORD_SCANNER_COST:
                message = "Not enough Ghost Shards."
            else:
                add_credits(user["id"], -RECORD_SCANNER_COST, "shop_record_scanner", "Bought Record Scanner.")
                add_inventory_item(user["id"], "Record Scanner", 1)
                record_shop_purchase(user["id"], "Record Scanner", RECORD_SCANNER_COST)
                refresh_session_user()
                message = "Record Scanner activated. Locked records now reveal age and role."

        return redirect("/shop?message=" + message)

    if request.args.get("message"):
        message = request.args.get("message")

    inventory = current_inventory(user["id"])
    owned_items = [i.get("item_name") for i in inventory]

    return render_template(
        "shop.html",
        user=current_user(),
        credit_name=CREDIT_NAME,
        message=message,
        warning=warning,
        locked_count=len(locked_records),
        owned_items=owned_items,
        mystery_crate_cost=MYSTERY_CRATE_COST,
        elite_wheel_cost=ELITE_WHEEL_COST,
        profile_effect_cost=PROFILE_EFFECT_COST,
        record_scanner_cost=RECORD_SCANNER_COST,
        profile_effects=PROFILE_EFFECTS
    )


@app.route("/guide")
def guide():
    if not validate_session():
        return redirect("/login")

    user = current_user()
    return render_template(
        "guide.html",
        user=user,
        credit_name=CREDIT_NAME,
        guide_items=role_guide(user.get("role")),
        rank=get_rank(user.get("credits", 0))
    )


def allowed_image_file(filename):
    return "." in filename and filename.rsplit(".", 1)[1].lower() in ALLOWED_IMAGE_EXTENSIONS

def image_to_data_url(uploaded, ext, max_bytes=2_000_000):
    """Store small avatars directly in Supabase as a data URL so Render redeploys do not erase them."""
    uploaded.stream.seek(0)
    raw = uploaded.read(max_bytes + 1)
    uploaded.stream.seek(0)
    if len(raw) > max_bytes:
        return None
    mime = "image/jpeg" if ext in ["jpg", "jpeg"] else f"image/{ext}"
    encoded = base64.b64encode(raw).decode("ascii")
    return f"data:{mime};base64,{encoded}"


@app.route("/profile", methods=["GET", "POST"])
def profile():
    if not validate_session():
        return redirect("/login")

    user = current_user()
    message = ""
    warning = ""

    if request.method == "POST":
        action = request.form.get("action")

        if action == "upload_avatar":
            uploaded = request.files.get("avatar")
            if not uploaded or not uploaded.filename:
                warning = "Choose an image file first."
            elif not allowed_image_file(uploaded.filename):
                warning = "Only PNG, JPG, JPEG, GIF, or WEBP images are allowed."
            else:
                filename = secure_filename(uploaded.filename)
                ext = filename.rsplit(".", 1)[1].lower()
                avatar_url = image_to_data_url(uploaded, ext)
                if not avatar_url:
                    final_name = f"avatar_{user['id']}_{uuid.uuid4().hex[:10]}.{ext}"
                    final_path = os.path.join(UPLOAD_FOLDER, final_name)
                    uploaded.save(final_path)
                    avatar_url = f"/static/uploads/{final_name}"
                    warning = "Large image saved locally. For permanent Render avatars, use an image under 2MB or Supabase Storage later."
                updated = safe_update("users", {"avatar_url": avatar_url}, "id", user["id"])
                if updated is None:
                    warning = "Image received, but Supabase is missing the users.avatar_url column. Run supabase_upgrade.sql."
                else:
                    log_action("avatar_updated", user["username"], "Updated profile picture.")
                    refresh_session_user()
                    message = "Profile picture updated."

        elif action == "upload_banner":
            uploaded = request.files.get("banner")
            if not uploaded or not uploaded.filename:
                warning = "Choose a banner image first."
            elif not allowed_image_file(uploaded.filename):
                warning = "Only PNG, JPG, JPEG, GIF, or WEBP images are allowed."
            else:
                filename = secure_filename(uploaded.filename)
                ext = filename.rsplit(".", 1)[1].lower()
                final_name = f"banner_{user['id']}_{uuid.uuid4().hex[:10]}.{ext}"
                final_path = os.path.join(UPLOAD_FOLDER, final_name)
                uploaded.save(final_path)
                banner_url = f"/static/uploads/{final_name}"
                updated = safe_update("users", {"banner_url": banner_url}, "id", user["id"])
                if updated is None:
                    warning = "Image saved locally, but Supabase is missing the users.banner_url column."
                else:
                    log_action("banner_updated", user["username"], "Updated profile banner.")
                    refresh_session_user()
                    message = "Profile banner updated."

        elif action == "save_bio":
            bio = request.form.get("bio", "").strip()[:280]
            updated = safe_update("users", {"bio": bio}, "id", user["id"])
            if updated is None:
                warning = "Supabase is missing the users.bio column."
            else:
                log_action("profile_bio_updated", user["username"], "Updated profile bio.")
                refresh_session_user()
                message = "Profile bio saved."

        elif action == "remove_avatar":
            updated = safe_update("users", {"avatar_url": ""}, "id", user["id"])
            if updated is None:
                warning = "Supabase is missing the users.avatar_url column."
            else:
                refresh_session_user()
                message = "Profile picture removed."

    user = current_user()
    unlocks = user_unlocked_count(user["id"])
    rank = get_rank(user.get("credits", 0))
    return render_template("profile.html", user=user, credit_name=CREDIT_NAME, unlocks=unlocks, rank=rank, message=message, warning=warning)


@app.route("/leaderboard")
def leaderboard():
    if not validate_session():
        return redirect("/login")
    users = safe_select("users")
    users = sorted(users, key=lambda u: safe_int(u.get("credits"), 0), reverse=True)[:50]
    rows = []
    for i, u in enumerate(users, start=1):
        rows.append({"place": i, "username": u.get("username"), "role": u.get("role"), "credits": safe_int(u.get("credits"), 0), "rank": get_rank(u.get("credits", 0)), "social_code": u.get("social_code", "")})
    return render_template("leaderboard.html", user=current_user(), credit_name=CREDIT_NAME, rows=rows)


@app.route("/notifications", methods=["GET", "POST"])
def notifications():
    if not validate_session():
        return redirect("/login")
    user = current_user()
    if request.method == "POST":
        for n in safe_select("notifications"):
            if n.get("user_id") == user["id"]:
                safe_update("notifications", {"is_read": True}, "id", n.get("id"))
    items = [n for n in safe_select("notifications", order_by="created_at", desc=True, limit=80) if n.get("user_id") == user["id"]]
    credit_logs = [c for c in safe_select("credit_logs", order_by="created_at", desc=True, limit=50) if c.get("user_id") == user["id"] or c.get("username") == user["username"]]
    for c in credit_logs[:15]:
        amount = safe_int(c.get("amount"), 0)
        items.append({"title":"Ghost Shards update", "message":f"{amount:+} {CREDIT_NAME} — {c.get('action','')}. {c.get('details','')}", "created_at":c.get("created_at",""), "is_read":True})
    if not items:
        items = [{"title":"No notifications yet", "message":"Gifts, unlocks, shop buys, achievements, and system alerts will appear here.", "created_at":"System", "is_read":True}]
    return render_template("notifications.html", user=user, credit_name=CREDIT_NAME, items=items)

@app.route("/news", methods=["GET", "POST"])
def news():
    if not validate_session():
        return redirect("/login")
    user = current_user()
    message = ""
    if request.method == "POST" and user["role"] == "architect":
        title = request.form.get("title", "System Announcement").strip()
        body = request.form.get("body", "").strip()
        if body:
            log_action("global_announcement", title, body)
            message = "Announcement posted."
    return render_template("news.html", user=user, credit_name=CREDIT_NAME, news=ghost_news(), message=message)


@app.route("/missions", methods=["GET", "POST"])
def missions():
    if not validate_session():
        return redirect("/login")
    user = current_user()
    message = ""
    if request.method == "POST":
        reward = safe_int(request.form.get("reward"), 0)
        name = request.form.get("mission_name", "Mission")
        if reward > 0:
            add_credits(user["id"], reward, "mission_reward", name)
            notify_user(user["id"], "Mission completed", f"{name}: +{reward} {CREDIT_NAME}")
            refresh_session_user()
            message = f"Mission reward claimed: +{reward} {CREDIT_NAME}."
    return render_template("missions.html", user=current_user(), credit_name=CREDIT_NAME, missions=mission_cards(user["id"]), message=message)

@app.route("/cases", methods=["GET", "POST"])
def cases():
    if not validate_session():
        return redirect("/login")
    user = current_user()
    message = ""
    if request.method == "POST":
        title = request.form.get("title", "").strip()
        notes = request.form.get("notes", "").strip()
        record_ids = request.form.get("record_ids", "").strip()
        if title:
            safe_insert("case_files", {"user_id": user["id"], "title": title, "notes": notes, "record_ids": record_ids})
            notify_user(user["id"], "Case file created", title)
            message = "Case file saved."
    files = [c for c in safe_select("case_files", order_by="created_at", desc=True) if c.get("user_id") == user["id"]]
    records = safe_select("records")[:80]
    return render_template("cases.html", user=current_user(), credit_name=CREDIT_NAME, cases=files, records=records, message=message)

@app.route("/network")
def network():
    if not validate_session():
        return redirect("/login")
    records = safe_select("records")[:30]
    return render_template("network.html", user=current_user(), credit_name=CREDIT_NAME, records=records)


@app.route("/online")
def online():
    if not validate_session():
        return redirect("/login")
    logs = safe_select("audit_logs", order_by="timestamp", desc=True, limit=30)
    seen = []
    for l in logs:
        name = l.get("performed_by")
        if name and name not in seen and name != "system":
            seen.append(name)
    if current_user()["username"] not in seen:
        seen.insert(0, current_user()["username"])
    return render_template("online.html", user=current_user(), credit_name=CREDIT_NAME, seen=seen[:20])


@app.route("/events")
def events():
    if not validate_session():
        return redirect("/login")
    event_cards = [
        {"title": "Double Shards Weekend", "text": "Architects can announce double-shard events through Ghost News Network."},
        {"title": "Free Unlock Day", "text": "Use the announcement system to tell operatives when a temporary event is active."},
        {"title": "Mystery Crate Drop", "text": "Marketplace crates and bundle unlocks are available from the Ghost Shard Shop."},
    ]
    return render_template("events.html", user=current_user(), credit_name=CREDIT_NAME, events=event_cards)


@app.route("/friends", methods=["GET", "POST"])
def friends():
    if not validate_session():
        return redirect("/login")
    message = ""
    found = None
    if request.method == "POST":
        code = request.form.get("social_code", "").strip()
        matches = []
        try:
            matches = supabase.table("users").select("*").eq("social_code", code).execute().data or []
        except Exception:
            matches = []
        if matches:
            found = matches[0]
            message = f"Found {found.get('username')} — use their social code to filter chat or send public messages."
        else:
            message = "No user found with that social code."
    return render_template("friends.html", user=current_user(), credit_name=CREDIT_NAME, message=message, found=found)


@app.route("/analytics")
def analytics():
    if not validate_session():
        return redirect("/login")
    if current_user()["role"] not in ["overseer", "architect"]:
        return redirect("/dashboard")
    records = safe_select("records")
    users = safe_select("users")
    unlocks = safe_select("record_unlocks")
    logs = safe_select("audit_logs")
    top_roles = {}
    for r in records:
        top_roles[r.get("role") or "Unknown"] = top_roles.get(r.get("role") or "Unknown", 0) + 1
    return render_template("analytics.html", user=current_user(), credit_name=CREDIT_NAME, records=len(records), users=len(users), unlocks=len(unlocks), logs=len(logs), top_roles=top_roles)


@app.route("/system-check")
def system_check():
    if not validate_session():
        return redirect("/login")
    if current_user()["role"] != "architect":
        return redirect("/dashboard")

    required_tables = [
        "users", "records", "deleted_records", "audit_logs", "credit_logs",
        "record_unlocks", "user_inventory", "shop_purchases", "chat_messages"
    ]
    checks = []
    for table in required_tables:
        try:
            supabase.table(table).select("*").limit(1).execute()
            checks.append({"name": table, "status": "OK", "details": "Connected"})
        except Exception as e:
            checks.append({"name": table, "status": "Missing/Error", "details": str(e)[:160]})

    optional_user_columns = ["avatar_url", "banner_url", "bio", "profile_effect", "last_spin", "last_elite_spin", "session_version", "account_locked", "social_code", "credits"]
    column_checks = []
    sample_users = safe_select("users", limit=1)
    if sample_users:
        sample = sample_users[0]
        for col in optional_user_columns:
            column_checks.append({"name": f"users.{col}", "status": "OK" if col in sample else "Missing", "details": "Needed for newer upgrades"})
    else:
        for col in optional_user_columns:
            column_checks.append({"name": f"users.{col}", "status": "Unknown", "details": "No user row could be read"})

    env_checks = [
        {"name": "SECRET_KEY", "status": "OK" if os.environ.get("SECRET_KEY") else "Using fallback", "details": "Add this in Render for production"},
        {"name": "SUPABASE_URL", "status": "OK" if os.environ.get("SUPABASE_URL") else "Using fallback", "details": SUPABASE_URL},
        {"name": "SUPABASE_KEY", "status": "OK" if os.environ.get("SUPABASE_KEY") else "Using fallback", "details": "Set this in Render environment variables"},
    ]
    return render_template("system_check.html", user=current_user(), credit_name=CREDIT_NAME, checks=checks, column_checks=column_checks, env_checks=env_checks)


@app.route("/backup")
def backup():
    if not validate_session():
        return redirect("/login")
    if current_user()["role"] != "architect":
        return redirect("/dashboard")
    import json
    data = {
        "records": safe_select("records"),
        "deleted_records": safe_select("deleted_records"),
        "users_public": [{"username": u.get("username"), "role": u.get("role"), "credits": u.get("credits"), "social_code": u.get("social_code")} for u in safe_select("users")],
        "audit_logs": safe_select("audit_logs")
    }
    return Response(json.dumps(data, indent=2, default=str), mimetype="application/json", headers={"Content-Disposition": "attachment; filename=ghostregistry_backup.json"})


@app.route("/marketplace", methods=["GET", "POST"])
def marketplace():
    if not validate_session():
        return redirect("/login")
    user = current_user()
    message = ""
    if request.method == "POST":
        action = request.form.get("action")
        if action == "list":
            item = request.form.get("item_name", "").strip()
            price = safe_int(request.form.get("price"), 0)
            if item and price > 0:
                safe_insert("marketplace_listings", {"seller_id": user["id"], "seller_username": user["username"], "item_name": item, "price": price, "status": "open"})
                message = "Marketplace listing created."
        elif action == "buy":
            listing_id = request.form.get("listing_id")
            listings = [l for l in safe_select("marketplace_listings") if str(l.get("id")) == str(listing_id) and l.get("status") == "open"]
            if listings:
                l = listings[0]
                if user.get("credits",0) < safe_int(l.get("price"),0):
                    message = "Not enough Ghost Shards."
                else:
                    add_credits(user["id"], -safe_int(l.get("price"),0), "marketplace_buy", l.get("item_name"))
                    add_credits(l.get("seller_id"), safe_int(l.get("price"),0), "marketplace_sale", l.get("item_name"))
                    safe_update("marketplace_listings", {"status":"sold", "buyer_id":user["id"]}, "id", l.get("id"))
                    add_inventory_item(user["id"], str(l.get("item_name","")).lower().replace(" ","_"), l.get("item_name"), "marketplace")
                    notify_user(l.get("seller_id"), "Marketplace sale", f"{l.get('item_name')} sold for {l.get('price')} {CREDIT_NAME}")
                    refresh_session_user()
                    message = "Item purchased."
    listings = [l for l in safe_select("marketplace_listings", order_by="created_at", desc=True) if l.get("status") == "open"]
    return render_template("marketplace.html", user=current_user(), credit_name=CREDIT_NAME, listings=listings, message=message)




@app.route("/inventory", methods=["GET", "POST"])
def inventory():
    if not validate_session():
        return redirect("/login")

    user = current_user()
    message = ""

    if request.method == "POST":
        action = request.form.get("action")
        effect = request.form.get("effect", "").strip()

        if action == "equip_effect":
            item_name = f"Profile Effect: {effect}"
            if not effect:
                message = "Choose an effect first."
            elif not has_inventory_item(user["id"], item_name):
                message = "You do not own that profile effect."
            else:
                try:
                    supabase.table("users").update({"profile_effect": effect}).eq("id", user["id"]).execute()
                    log_action("profile_effect_equipped", user["username"], f"Equipped {effect}.")
                    refresh_session_user()
                    message = f"Equipped profile effect: {effect}."
                except Exception as e:
                    print("PROFILE EFFECT EQUIP ERROR:", e)
                    message = "Missing users.profile_effect column in Supabase."

        elif action == "unequip_effect":
            try:
                supabase.table("users").update({"profile_effect": ""}).eq("id", user["id"]).execute()
                refresh_session_user()
                message = "Profile effect unequipped."
            except Exception:
                message = "Missing users.profile_effect column in Supabase."

    items = current_inventory(user["id"])
    owned_effects = []
    for item in items:
        name = item.get("item_name", "")
        if name.startswith("Profile Effect: "):
            owned_effects.append(name.replace("Profile Effect: ", ""))

    return render_template(
        "inventory.html",
        user=current_user(),
        items=items,
        owned_effects=owned_effects,
        message=message,
        credit_name=CREDIT_NAME
    )



@app.route("/elite-wheel", methods=["GET", "POST"])
def elite_wheel():
    if not validate_session():
        return redirect("/login")

    user = current_user()
    message = ""
    reward = None

    if not has_inventory_item(user["id"], "Elite Wheel Boost"):
        return render_template(
            "elite_wheel.html",
            user=user,
            credit_name=CREDIT_NAME,
            has_elite=False,
            can_spin=False,
            reward=None,
            message="Buy Elite Wheel Boost in the shop to unlock this page."
        )

    today = str(date.today())
    db_user = supabase.table("users").select("*").eq("id", user["id"]).execute().data[0]
    can_spin = db_user.get("last_elite_spin") != today

    if request.method == "POST":
        if not can_spin:
            message = "You have already spun the Elite Wheel today."
        else:
            reward = random.choice(ELITE_WHEEL_REWARDS)
            supabase.table("users").update({
                "credits": (db_user.get("credits") or 0) + reward,
                "last_elite_spin": today
            }).eq("id", user["id"]).execute()
            log_credit(user["username"], user["id"], reward, "elite_wheel", "Elite Wheel reward.")
            log_action("elite_wheel_spin", user["username"], f"Won {reward} {CREDIT_NAME}.")
            refresh_session_user()
            can_spin = False
            message = f"Elite Wheel reward: {reward} {CREDIT_NAME}."

    return render_template(
        "elite_wheel.html",
        user=current_user(),
        credit_name=CREDIT_NAME,
        has_elite=True,
        can_spin=can_spin,
        reward=reward,
        message=message
    )

@app.route("/account", methods=["GET", "POST"])
def account():
    if not validate_session():
        return redirect("/login")

    user = current_user()
    message = ""

    if request.method == "POST":
        current_password = request.form.get("current_password", "").strip()
        new_username = request.form.get("new_username", "").strip()
        new_password = request.form.get("new_password", "").strip()

        db_user_data = supabase.table("users").select("*").eq("id", user["id"]).execute().data

        if not db_user_data:
            message = "Account not found."
        else:
            db_user = db_user_data[0]

            if not check_password(current_password, db_user["password_hash"]):
                message = "Original password incorrect."
            else:
                updates = {}

                if new_username:
                    updates["username"] = new_username

                if new_password:
                    updates["password_hash"] = hash_password(new_password)

                if updates:
                    updates["session_version"] = (db_user.get("session_version", 1) or 1) + 1
                    supabase.table("users").update(updates).eq("id", user["id"]).execute()
                    log_action("account_updated", user["username"], "User updated own account.")
                    session.clear()
                    return redirect("/login")
                else:
                    message = "Nothing changed."

    return render_template(
        "account.html",
        user=current_user(),
        message=message,
        credit_name=CREDIT_NAME
    )


@app.route("/overseer", methods=["GET", "POST"])
def overseer():
    if not validate_session():
        return redirect("/login")

    user = current_user()

    if user["role"] != "overseer":
        return redirect("/dashboard")

    message = ""

    if request.method == "POST":
        action = request.form.get("action")

        if action == "self_credits":
            amount = safe_int(request.form.get("self_credit_amount"), 0)

            if amount == 0:
                message = "Enter a valid amount."
            else:
                add_credits(user["id"], amount, "overseer_self_credit", f"Overseer {user['username']} gave themselves {amount} {CREDIT_NAME}.")
                refresh_session_user()
                log_action("self_credits_given", user["username"], f"Overseer gave themselves {amount} {CREDIT_NAME}.")
                message = f"Added {amount} {CREDIT_NAME} to your own account."


        elif action == "give_credits":
            username = request.form.get("credit_username", "").strip()
            social_code = request.form.get("credit_social_code", "").strip()
            amount = safe_int(request.form.get("credit_amount"), 0)

            target = supabase.table("users").select("*").eq("username", username).eq("social_code", social_code).execute().data

            if not target:
                message = "No account found with that username and social code."
            elif target[0]["role"] != "operative" and target[0]["id"] != user["id"]:
                message = "Overseers can only give Ghost Shards to operatives or themselves."
            elif amount == 0:
                message = "Enter a valid amount."
            else:
                add_credits(target[0]["id"], amount, "overseer_gift", f"Given by overseer {user['username']}.")
                refresh_session_user()
                log_action("credits_given", username, f"Overseer gave {amount} {CREDIT_NAME}.")
                message = f"Gave {amount} {CREDIT_NAME} to {username}."

        elif action == "reset_member_password":
            target_id = request.form.get("target_id")
            new_password = request.form.get("new_password", "").strip()

            if not target_id:
                message = "Select an operative first."
            elif not new_password:
                message = "Enter a new password."
            else:
                target_data = supabase.table("users").select("*").eq("id", target_id).execute().data

                if target_data and target_data[0]["role"] == "operative":
                    target = target_data[0]
                    supabase.table("users").update({
                        "password_hash": hash_password(new_password),
                        "session_version": (target.get("session_version", 1) or 1) + 1
                    }).eq("id", target_id).execute()

                    log_action("operative_password_reset", target["username"], "Overseer reset operative password.")
                    message = "Operative password reset."
                else:
                    message = "Overseers can only reset operative passwords."

    records_data = supabase.table("records").select("*").execute().data
    deleted_records = supabase.table("deleted_records").select("*").execute().data
    users_data = supabase.table("users").select("*").execute().data
    logs = supabase.table("audit_logs").select("*").execute().data

    stats = {
        "records": len(records_data),
        "deleted": len(deleted_records),
        "operatives": len([u for u in users_data if u.get("role") == "operative"]),
        "logs": len(logs)
    }

    return render_template(
        "overseer.html",
        user=current_user(),
        records=records_data,
        deleted_records=deleted_records,
        users=users_data,
        logs=logs,
        stats=stats,
        message=message,
        credit_name=CREDIT_NAME
    )


@app.route("/architect", methods=["GET", "POST"])
def architect():
    if not validate_session():
        return redirect("/login")

    user = current_user()

    if user["role"] != "architect":
        return redirect("/dashboard")

    message = ""

    if request.method == "POST":
        action = request.form.get("action")

        if action == "create_user":
            username = request.form.get("username", "").strip()
            password = request.form.get("password", "").strip()
            role = request.form.get("role", "").strip()

            if not username or not password or not role:
                message = "Username, password, and role are required."
            else:
                social_code = generate_social_code()

                supabase.table("users").insert({
                    "username": username,
                    "password_hash": hash_password(password),
                    "role": role,
                    "session_version": 1,
                    "credits": 0,
                    "social_code": social_code
                }).execute()

                log_action("user_created", username, f"Created {role} account.")
                message = "User created."

        elif action == "update_user":
            target_id = request.form.get("target_id")
            new_username = request.form.get("new_username", "").strip()
            new_password = request.form.get("new_password", "").strip()
            new_role = request.form.get("new_role", "").strip()

            if not target_id:
                message = "Select a user first."
            else:
                target_data = supabase.table("users").select("*").eq("id", target_id).execute().data

                if target_data:
                    target = target_data[0]

                    if target["role"] == "architect" and target["id"] != user["id"]:
                        message = "Architects cannot modify other Architect accounts."
                    else:
                        updates = {}

                        if new_username:
                            updates["username"] = new_username

                        if new_password:
                            updates["password_hash"] = hash_password(new_password)

                        if new_role:
                            updates["role"] = new_role

                        if updates:
                            updates["session_version"] = (target.get("session_version", 1) or 1) + 1
                            supabase.table("users").update(updates).eq("id", target_id).execute()
                            log_action("user_updated", target["username"], "Architect updated user.")
                            message = "User updated."
                        else:
                            message = "Nothing changed."

        elif action == "delete_user":
            target_id = request.form.get("target_id")

            if not target_id:
                message = "Select a user first."
            else:
                target_data = supabase.table("users").select("*").eq("id", target_id).execute().data

                if target_data:
                    target = target_data[0]

                    if target["role"] == "architect":
                        message = "Architect accounts cannot be deleted here."
                    else:
                        supabase.table("users").delete().eq("id", target_id).execute()
                        log_action("user_deleted", target["username"], "Architect deleted user.")
                        message = "User deleted."

        elif action == "self_credits":
            amount = safe_int(request.form.get("self_credit_amount"), 0)

            if amount == 0:
                message = "Enter a valid amount."
            else:
                add_credits(user["id"], amount, "architect_self_credit", f"Architect {user['username']} gave themselves {amount} {CREDIT_NAME}.")
                refresh_session_user()
                log_action("self_credits_given", user["username"], f"Architect gave themselves {amount} {CREDIT_NAME}.")
                message = f"Added {amount} {CREDIT_NAME} to your own account."

        elif action == "give_credits":
            username = request.form.get("credit_username", "").strip()
            social_code = request.form.get("credit_social_code", "").strip()
            amount = safe_int(request.form.get("credit_amount"), 0)

            target = supabase.table("users").select("*").eq("username", username).eq("social_code", social_code).execute().data

            if not target:
                message = "No account found with that username and social code."
            elif amount == 0:
                message = "Enter a valid amount."
            else:
                add_credits(target[0]["id"], amount, "architect_gift", f"Given by architect {user['username']}.")
                refresh_session_user()
                log_action("credits_given", username, f"Architect gave {amount} {CREDIT_NAME}.")
                message = f"Gave {amount} {CREDIT_NAME} to {username}."

        elif action == "restore_record":
            deleted_id = request.form.get("deleted_record_id")

            if not deleted_id:
                message = "Select a deleted record first."
            else:
                target = supabase.table("deleted_records").select("*").eq("id", deleted_id).execute().data

                if target:
                    r = target[0]

                    restored_data = {
                        "first_name": r.get("first_name"),
                        "last_name": r.get("last_name"),
                        "email": r.get("email"),
                        "address": r.get("address"),
                        "phone": r.get("phone"),
                        "age": r.get("age"),
                        "role": r.get("role"),
                        "notes": r.get("notes"),
                        "created_by": r.get("created_by"),
                        "updated_by": user["username"]
                    }

                    supabase.table("records").insert(restored_data).execute()
                    supabase.table("deleted_records").delete().eq("id", deleted_id).execute()

                    log_action("record_restored", f"{r.get('first_name', '')} {r.get('last_name', '')}", "Architect restored record.")
                    message = "Record restored."

        elif action == "permanent_delete_record":
            deleted_id = request.form.get("deleted_record_id")

            if not deleted_id:
                message = "Select a deleted record first."
            else:
                target = supabase.table("deleted_records").select("*").eq("id", deleted_id).execute().data

                if target:
                    r = target[0]
                    supabase.table("deleted_records").delete().eq("id", deleted_id).execute()
                    log_action("record_permanently_deleted", f"{r.get('first_name', '')} {r.get('last_name', '')}", "Architect permanently deleted record.")
                    message = "Record permanently deleted."


        elif action == "lock_non_architects":
            code = request.form.get("lock_code", "").strip()
            if not (code.isdigit() and len(code) == 4):
                message = "Enter a 4 digit lockdown code first."
            else:
                set_system_setting("website_lockdown", "on")
                set_system_setting("lockdown_code", code)
                all_users = supabase.table("users").select("*").execute().data
                locked_count = 0
                for account in all_users:
                    if account.get("role", "").strip().lower() in ["operative", "overseer"]:
                        safe_update("users", {
                            "account_locked": True,
                            "session_version": (account.get("session_version", 1) or 1) + 1
                        }, "id", account["id"])
                        notify_user(account["id"], "Website locked down", "Architect lockdown is active.")
                        locked_count += 1
                log_action("architect_lockdown", "operatives_overseers", f"Locked {locked_count} non-architect accounts with code protection.")
                message = f"Lockdown active. {locked_count} Overseer/Operative accounts were kicked out."

        elif action == "unlock_non_architects":
            code = request.form.get("unlock_code", "").strip()
            stored_code = get_system_setting("lockdown_code", "")
            if code != stored_code:
                message = "Wrong 4 digit unlock code."
            else:
                set_system_setting("website_lockdown", "off")
                all_users = supabase.table("users").select("*").execute().data
                unlocked_count = 0
                for account in all_users:
                    if account.get("role", "").strip().lower() in ["operative", "overseer"]:
                        safe_update("users", {
                            "account_locked": False,
                            "session_version": (account.get("session_version", 1) or 1) + 1
                        }, "id", account["id"])
                        unlocked_count += 1
                log_action("architect_unlockdown", "operatives_overseers", f"Unlocked {unlocked_count} non-architect accounts.")
                message = f"Lockdown removed. {unlocked_count} Overseer/Operative accounts can log in again."

        elif action == "emergency_lockdown":
            all_users = supabase.table("users").select("*").execute().data
            for account in all_users:
                supabase.table("users").update({
                    "session_version": (account.get("session_version", 1) or 1) + 1
                }).eq("id", account["id"]).execute()

            refresh_session_user()
            log_action("emergency_lockdown", "all_users", "Architect forced every account to log in again.")
            message = "Emergency session reset complete. Every account must log in again."

        elif action == "delete_audit_log":
            log_ids = request.form.getlist("audit_log_ids")

            if not log_ids:
                single_id = request.form.get("audit_log_id")
                if single_id:
                    log_ids = [single_id]

            if not log_ids:
                message = "Select at least one audit log."
            else:
                for log_id in log_ids:
                    supabase.table("audit_logs").delete().eq("id", log_id).execute()

                message = f"{len(log_ids)} audit logs deleted."

    users_data = supabase.table("users").select("*").execute().data
    records_data = supabase.table("records").select("*").execute().data
    deleted_records = supabase.table("deleted_records").select("*").execute().data
    logs = supabase.table("audit_logs").select("*").execute().data

    stats = {
        "users": len(users_data),
        "records": len(records_data),
        "deleted": len(deleted_records),
        "logs": len(logs)
    }

    return render_template(
        "architect.html",
        user=current_user(),
        users=users_data,
        records=records_data,
        deleted_records=deleted_records,
        logs=logs,
        stats=stats,
        message=message,
        credit_name=CREDIT_NAME
    )


@app.route("/session-status")
def session_status():
    ok = validate_session()
    return jsonify({"ok": bool(ok), "redirect": "/login" if not ok else ""})

@app.route("/achievements")
def achievements():
    if not validate_session():
        return redirect("/login")
    user = current_user()
    evaluate_achievements(user["id"])
    rows = [a for a in safe_select("user_achievements", order_by="created_at", desc=True) if a.get("user_id") == user["id"]]
    return render_template("achievements.html", user=current_user(), credit_name=CREDIT_NAME, achievements=rows)

@app.route("/messages", methods=["GET", "POST"])
def messages():
    if not validate_session():
        return redirect("/login")
    user = current_user()
    message = ""
    if request.method == "POST":
        recipient_code = request.form.get("recipient_code", "").strip()
        body = request.form.get("body", "").strip()
        matches = supabase.table("users").select("*").eq("social_code", recipient_code).execute().data or []
        if not matches:
            message = "No user found with that social code."
        elif body:
            r = matches[0]
            safe_insert("private_messages", {"sender_id": user["id"], "sender_username": user["username"], "recipient_id": r["id"], "recipient_username": r["username"], "body": body, "is_read": False})
            notify_user(r["id"], "New private message", f"From {user['username']}")
            message = "Private message sent."
    inbox = [m for m in safe_select("private_messages", order_by="created_at", desc=True) if m.get("recipient_id") == user["id"]]
    sent = [m for m in safe_select("private_messages", order_by="created_at", desc=True) if m.get("sender_id") == user["id"]]
    for m in inbox:
        if not m.get("is_read"):
            safe_update("private_messages", {"is_read": True}, "id", m.get("id"))
    inbox = decorate_messages_with_profiles(inbox, "sender_id")
    sent = decorate_messages_with_profiles(sent, "sender_id")
    return render_template("messages.html", user=current_user(), credit_name=CREDIT_NAME, inbox=inbox, sent=sent, message=message)

@app.route("/directory")
def directory():
    if not validate_session():
        return redirect("/login")
    users = safe_select("users")
    return render_template("directory.html", user=current_user(), credit_name=CREDIT_NAME, users=users)

@app.route("/security-dashboard")
def security_dashboard():
    if not validate_session():
        return redirect("/login")
    if current_user()["role"] != "architect":
        return redirect("/dashboard")
    users = safe_select("users")
    logs = safe_select("audit_logs", order_by="timestamp", desc=True, limit=80)
    stats = {
        "users": len(users),
        "locked": len([u for u in users if u.get("account_locked")]),
        "lockdown": get_system_setting("website_lockdown", "off"),
        "logs": len(logs),
        "records": len(safe_select("records")),
        "notifications": len(safe_select("notifications")),
    }
    return render_template("security_dashboard.html", user=current_user(), credit_name=CREDIT_NAME, stats=stats, logs=logs[:25])


# =============================
# FINAL ROADMAP / BIG UPDATE PAGES
# =============================
ROADMAP_SECTIONS = {
    "Command Center": ["Unified dashboard widgets", "Notifications", "Missions", "Messages", "Wheel timers", "Recent activity", "Customizable layout"],
    "Real-Time Systems": ["Live chat", "Live private messages", "Live notifications", "Live credits", "Instant kick-outs", "Online status", "Lockdown activation"],
    "Investigation Tools": ["Case files", "Record relationship graph", "Record timeline", "Relationship heatmap", "Evidence notes", "Shared investigations"],
    "Ghost Casino": ["Poker room with AI", "Blackjack dealer AI", "Roulette", "Baccarat", "Slots", "Video Poker", "VIP casino", "Tournaments", "Spectator mode", "Replay viewer"],
    "Fun Games": ["Flappy Ghost", "Ghost Snake", "Chess", "Minesweeper", "Space Invaders", "Breakout", "Typing challenge", "Reaction test", "Puzzle hub", "No Ghost Shard rewards"],
    "Profiles & Social": ["Avatar on every message", "Banners", "Bio", "Friends", "Following", "GhostNet feed", "Reactions", "Comments", "Profile HQ"],
    "Economy & Collectibles": ["Marketplace", "Auctions", "Trading", "Mystery crates", "Ghost pets", "Titles", "Seasonal cosmetics", "Economy analytics"],
    "Overseer Command": ["Moderation center", "Warnings", "Temporary mutes", "Reports", "Support tickets", "Bulk rewards", "User activity reviews", "Investigation dashboard"],
    "Architect Command": ["4-digit lockdown/unlockdown", "Event creator", "Broadcasts", "Security center", "Database backup", "Cosmetic creator", "Museum", "Testing realm", "Global monitor"],
    "Events & Endgame": ["Hall of Fame", "Daily login calendar", "Season pass", "Community challenges", "World events", "Lore mode", "Cinematic effects", "Ghost Radio"],
    "Noodle Department": ["Joke noodle terms", "Noodle facts", "Noodle achievement", "Noodle title", "Floating ramen aura", "Global noodle emergency"]
}

@app.route("/command-center")
def command_center():
    if not validate_session(): return redirect("/login")
    user = current_user()
    return render_template("command_center.html", user=user, credit_name=CREDIT_NAME, missions=mission_cards(user["id"]), activity=public_activity(8), news=ghost_news()[:3])

@app.route("/roadmap")
def roadmap():
    if not validate_session(): return redirect("/login")
    return render_template("roadmap.html", user=current_user(), credit_name=CREDIT_NAME, sections=ROADMAP_SECTIONS)

@app.route("/fun-games")
def fun_games():
    if not validate_session(): return redirect("/login")
    games = ["Flappy Ghost", "Ghost Snake", "Space Invaders", "Ghost Breakout", "Ghost Runner", "Aim Trainer", "Memory Match", "Hacker Typing", "Reaction Test", "Minesweeper", "Chess", "Connect 4", "Tic Tac Toe", "Solitaire", "Puzzle Hub"]
    return render_template("fun_games.html", user=current_user(), credit_name=CREDIT_NAME, games=games)

@app.route("/investigation-graph")
def investigation_graph():
    if not validate_session(): return redirect("/login")
    records = safe_select("records", limit=40)
    return render_template("investigation_graph.html", user=current_user(), credit_name=CREDIT_NAME, records=records)

@app.route("/headquarters")
def headquarters():
    if not validate_session(): return redirect("/login")
    return render_template("headquarters.html", user=current_user(), credit_name=CREDIT_NAME)

@app.route("/hall-of-fame")
def hall_of_fame():
    if not validate_session(): return redirect("/login")
    users = sorted(safe_select("users"), key=lambda u: (u.get("credits") or 0), reverse=True)[:10]
    return render_template("hall_of_fame.html", user=current_user(), credit_name=CREDIT_NAME, users=users)

@app.route("/daily-calendar")
def daily_calendar():
    if not validate_session(): return redirect("/login")
    days = [(i, 50 + i*25 if i < 30 else "Special Cosmetic Crate") for i in range(1,31)]
    return render_template("daily_calendar.html", user=current_user(), credit_name=CREDIT_NAME, days=days)

@app.route("/ghost-radio")
def ghost_radio():
    if not validate_session(): return redirect("/login")
    return render_template("ghost_radio.html", user=current_user(), credit_name=CREDIT_NAME)

@app.route("/ghostnet")
def ghostnet():
    if not validate_session(): return redirect("/login")
    return render_template("ghostnet.html", user=current_user(), credit_name=CREDIT_NAME, posts=public_activity(10))



# ============================================
# V6 COMPLETE ROADMAP EXPANSION ROUTES
# These pages make every master-roadmap system visible inside the site.
# Large systems are built as upgrade-ready hubs/placeholders unless already implemented.
# ============================================

def roadmap_status_cards():
    return [
        ("Core", "Login, roles, records, credits, compact menu", "Working"),
        ("Real-time", "Session polling, instant kick checks, future WebSocket layer", "Partial"),
        ("Casino", "Slots/Blackjack/Poker/Roulette/Baccarat hubs, deeper AI planned", "Partial"),
        ("Fun Games", "Flappy Ghost and game hub pages for no-credit games", "Partial"),
        ("Social", "Chat, messages, profile icons, GhostNet/Friends hubs", "Partial"),
        ("Admin", "Architect/Overseer command-center hubs and security pages", "Partial"),
        ("Investigation", "Case files, graph, timeline, heatmap hubs", "Partial"),
        ("Economy", "Shop, marketplace, crates, bank, analytics hubs", "Partial"),
        ("Cosmetics", "Profiles, pets, titles, banners, effects hubs", "Partial"),
        ("Noodle Department", "Joke terms, noodle easter eggs roadmap", "Working/Planned"),
    ]

@app.route("/master-roadmap")
def master_roadmap():
    if not validate_session():
        return redirect("/login")
    return render_template("master_roadmap.html", user=current_user(), cards=roadmap_status_cards())

@app.route("/casino")
def casino_lobby():
    if not validate_session():
        return redirect("/login")
    return render_template("casino_lobby.html", user=current_user(), credit_name=CREDIT_NAME)

@app.route("/casino/<game>")
def casino_game(game):
    if not validate_session():
        return redirect("/login")
    names = {
        "poker":"Texas Hold'em Poker Room", "blackjack":"Blackjack Hall", "roulette":"Roulette Floor",
        "baccarat":"Baccarat Lounge", "slots":"Neon Slots Room", "video-poker":"Video Poker",
        "jackpot":"Jackpot Vault", "tournaments":"Tournament Center", "vip":"VIP Casino Lounge"
    }
    playable = {"poker", "blackjack", "roulette", "baccarat", "slots", "video-poker", "jackpot"}
    if game in playable:
        return render_template("casino_game_standalone.html", user=current_user(), game=game, title=names.get(game, "Ghost Casino"), credit_name=CREDIT_NAME)
    return render_template("casino_game.html", user=current_user(), game=game, title=names.get(game, "Ghost Casino"), credit_name=CREDIT_NAME)

@app.route("/fun/<game>")
def fun_game(game):
    if not validate_session():
        return redirect("/login")
    titles = {
        "flappy":"Flappy Ghost", "snake":"Ghost Snake", "space":"Space Invaders", "breakout":"Ghost Breakout",
        "runner":"Ghost Runner", "aim":"Aim Trainer", "memory":"Memory Match", "typing":"Hacker Typing Challenge",
        "reaction":"Reaction Test", "minesweeper":"Minesweeper", "chess":"Chess", "connect4":"Connect 4",
        "tictactoe":"Tic Tac Toe", "solitaire":"Solitaire", "puzzles":"Puzzle Hub"
    }
    if game == "flappy":
        return render_template("flappy_ghost.html", user=current_user())
    return render_template("fun_game_detail.html", user=current_user(), title=titles.get(game, "Fun Game"), game=game)

@app.route("/admin/architect-command")
def architect_command_v6():
    if not validate_session():
        return redirect("/login")
    if current_user().get("role") != "architect":
        return redirect("/dashboard")
    return render_template("architect_command_v6.html", user=current_user())

@app.route("/admin/overseer-command")
def overseer_command_v6():
    if not validate_session():
        return redirect("/login")
    if current_user().get("role") not in ["overseer", "architect"]:
        return redirect("/dashboard")
    return render_template("overseer_command_v6.html", user=current_user())

@app.route("/systems/<section>")
def systems_section(section):
    if not validate_session():
        return redirect("/login")
    titles = {
        "realtime":"Real-Time Systems", "notifications":"Notification Center", "missions":"Missions & Achievements",
        "levels":"XP, Levels & Prestige", "hq":"Headquarters & Trophy Room", "ghostnet":"GhostNet Social Platform",
        "marketplace":"Marketplace, Trading & Auctions", "events":"Seasonal Events & Event Creator",
        "pets":"Ghost Pets, Titles & Cosmetics", "museum":"Architect Museum & Hall of Fame",
        "economy":"Economy Tracker & Bank", "records":"Record Timeline, Graph & Heatmap",
        "ai":"Ghost AI Assistant", "radio":"Ghost Radio", "noodles":"Noodle Department",
        "mobile":"Mobile, Dashboard, Quality of Life",
        "battlepass":"Season Pass & Login Calendar",
        "community":"Community Challenges & Voting",
        "mystery":"Mystery Crates & Rare Drops",
        "lore":"Lore, Story Mode & Secrets",
        "cinematic":"Cinematic Effects",
        "spectator":"Spectator, Streaming & Replays",
        "guilds":"Guilds, Factions & Headquarters",
        "creator":"Architect Creator Tools",
        "testing":"Architect Testing Realm",
        "trust":"Reputation & Trust System",
        "museumplus":"Architect Museum, Legacy & Trophy Room"
    }
    return render_template("system_detail.html", user=current_user(), title=titles.get(section, section.title()), section=section)


@app.route("/casino/settle", methods=["POST"])
def casino_settle():
    if not validate_session():
        return jsonify({"ok": False, "error": "Not logged in."}), 401
    user = current_user()
    data = request.get_json(silent=True) or {}
    game = str(data.get("game", "casino"))[:60]
    details = str(data.get("details", "Casino game result."))[:300]
    try:
        amount = int(data.get("amount", 0))
    except Exception:
        amount = 0
    # Browser games are for in-site Ghost Shards only. This endpoint prevents negative balances.
    if amount == 0:
        return jsonify({"ok": True, "credits": user.get("credits", 0), "message": "No credit change."})
    target = supabase.table("users").select("*").eq("id", user["id"]).execute().data
    if not target:
        return jsonify({"ok": False, "error": "User not found."}), 404
    balance = target[0].get("credits") or 0
    if amount < 0 and balance + amount < 0:
        return jsonify({"ok": False, "error": "Not enough Ghost Shards.", "credits": balance})
    add_credits(user["id"], amount, f"casino_{game}", details)
    refresh_session_user()
    log_action("casino_game", user["username"], f"{game}: {details} ({amount})")
    try:
        supabase.table("casino_history").insert({
            "user_id": user["id"],
            "username": user["username"],
            "game": game,
            "amount": amount,
            "details": details
        }).execute()
    except Exception as e:
        print("CASINO HISTORY ERROR:", e)
    return jsonify({"ok": True, "credits": current_user().get("credits", balance + amount), "amount": amount, "message": details})


# ===== V10 FINAL ROADMAP ROUTES =====
@app.route("/realtime-center")
def realtime_center_v10():
    if not validate_session(): return redirect("/login")
    return render_template("websocket_status.html", user=current_user())

@app.route("/auctions")
def auctions_v10():
    if not validate_session(): return redirect("/login")
    return render_template("auctions.html", user=current_user())

@app.route("/architect/event-creator")
def event_creator_v10():
    if not validate_session(): return redirect("/login")
    if current_user().get("role") != "architect": return redirect("/dashboard")
    return render_template("event_creator.html", user=current_user())

@app.route("/ai-assistant")
def ai_assistant_v10():
    if not validate_session(): return redirect("/login")
    return render_template("ai_assistant.html", user=current_user())

@app.route("/headquarters-customizer")
def hq_customizer_v10():
    if not validate_session(): return redirect("/login")
    return render_template("headquarters_customizer.html", user=current_user())

@app.route("/investigation-tools")
def investigation_tools_v10():
    if not validate_session(): return redirect("/login")
    return render_template("investigation_tools.html", user=current_user())

@app.route("/casino-stats")
def casino_stats_v10():
    if not validate_session(): return redirect("/login")
    return render_template("casino_stats.html", user=current_user())

@app.route("/architect/sandbox")
def architect_sandbox_v10():
    if not validate_session(): return redirect("/login")
    if current_user().get("role") != "architect": return redirect("/dashboard")
    return render_template("architect_sandbox.html", user=current_user())

@app.route("/community")
def community_v10():
    if not validate_session(): return redirect("/login")
    return render_template("community.html", user=current_user())

@app.route("/architect/cosmetic-creator")
def cosmetic_creator_v10():
    if not validate_session(): return redirect("/login")
    if current_user().get("role") != "architect": return redirect("/dashboard")
    return render_template("cosmetic_creator.html", user=current_user())

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8000, debug=True)
