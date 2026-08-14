import os
import json
from datetime import datetime
from config import ADMIN_IDS, PREMIUM_FILE  # PREMIUM_FILE may be used for migration

# ============= PROXY STORAGE =============
user_proxies: dict = {}

def load_user_proxies():
    global user_proxies
    if os.path.exists("user_proxies.json"):
        try:
            with open("user_proxies.json", 'r') as f:
                user_proxies = {int(k): v for k, v in json.load(f).items()}
        except:
            user_proxies = {}

def save_user_proxies():
    with open("user_proxies.json", 'w') as f:
        json.dump({str(k): v for k, v in user_proxies.items()}, f)

def get_user_proxy_list(uid) -> list:
    return user_proxies.get(uid, [])

def set_user_proxies(uid, proxies: list):
    user_proxies[uid] = [p for p in proxies if p]
    save_user_proxies()

def remove_user_proxy(uid):
    user_proxies.pop(uid, None)
    save_user_proxies()

def load_user_pool():
    if os.path.exists("user_pool.json"):
        try:
            with open("user_pool.json", 'r') as f:
                return {int(k): v for k, v in json.load(f).items()}
        except:
            return {}
    return {}

def save_user_pool(data):
    with open("user_pool.json", 'w') as f:
        json.dump({str(k): v for k, v in data.items()}, f)

user_pool_enabled = load_user_pool()

# ============= PREMIUM USERS (with expiry) =============
PREMIUM_DB = "premium_users.json"

def load_premium_users_dict():
    if not os.path.exists(PREMIUM_DB):
        # Migrate from old premium.txt if exists
        if os.path.exists(PREMIUM_FILE):
            with open(PREMIUM_FILE, 'r') as f:
                old_list = [l.strip() for l in f if l.strip()]
            default = {str(uid): None for uid in ADMIN_IDS}
            for uid in old_list:
                default[uid] = None
            save_premium_users_dict(default)
            return default
        default = {str(uid): None for uid in ADMIN_IDS}
        save_premium_users_dict(default)
        return default
    try:
        with open(PREMIUM_DB, 'r') as f:
            return json.load(f)
    except:
        return {str(uid): None for uid in ADMIN_IDS}

def save_premium_users_dict(data):
    with open(PREMIUM_DB, 'w') as f:
        json.dump(data, f, indent=4)

def add_premium_user(user_id, expiry_timestamp=None):
    data = load_premium_users_dict()
    uid = str(user_id)
    data[uid] = expiry_timestamp
    save_premium_users_dict(data)
    return True

def remove_premium_user(user_id):
    data = load_premium_users_dict()
    uid = str(user_id)
    if uid in data:
        del data[uid]
        save_premium_users_dict(data)
        return True
    return False

def is_premium(user_id):
    data = load_premium_users_dict()
    uid = str(user_id)
    if uid not in data:
        return False
    expiry = data[uid]
    if expiry is None:
        return True
    if datetime.now().timestamp() > float(expiry):
        del data[uid]
        save_premium_users_dict(data)
        return False
    return True

def get_user_limit(user_id):
    return 999999 if is_premium(user_id) else 0

async def cleanup_expired_premium():
    while True:
        await asyncio.sleep(3600)
        data = load_premium_users_dict()
        now = datetime.now().timestamp()
        changed = False
        for uid, expiry in list(data.items()):
            if expiry is not None and now > float(expiry):
                del data[uid]
                changed = True
        if changed:
            save_premium_users_dict(data)
            print("🗑️ Cleaned up expired premium users.")

# ============= OLD COMPATIBILITY =============
def get_file_lines(filepath):
    if not os.path.exists(filepath):
        return []
    try:
        with open(filepath, 'r', encoding='utf-8', errors='ignore') as f:
            return [line.strip() for line in f if line.strip()]
    except:
        return []

def load_premium_users():
    # For backward compatibility – returns list of premium user IDs (all, including expired)
    data = load_premium_users_dict()
    return list(data.keys())

def load_sites():
    return get_file_lines("sites.txt")

def load_proxies():
    return get_file_lines("proxy.txt")  # global proxy file

def get_proxies_for_user(uid):
    user_list = get_user_proxy_list(uid)
    pool = load_proxies()
    pool_on = user_pool_enabled.get(uid, True)
    if uid in ADMIN_IDS:
        if user_list:
            return (user_list + pool) if pool_on else user_list
        return pool
    if not user_list:
        return []
    return (user_list + pool) if pool_on else user_list

def is_admin(uid):
    return uid in ADMIN_IDS

def extract_cc(text):
    import re
    matches = re.findall(r'(\d{15,16})\|(\d{2})\|(\d{2,4})\|(\d{3,4})', text)
    cards = []
    for card, month, year, cvv in matches:
        if len(year) == 2:
            year = '20' + year
        cards.append(f"{card}|{month}|{year}|{cvv}")
    return cards

def make_progress_bar(current, total, width=20):
    if total == 0:
        return f"[{'░'*width}] 0/0 (0%)"
    filled = int(width * current / total)
    pct = int(100 * current / total)
    return f"[{'█'*filled}{'░'*(width-filled)}] {current}/{total} ({pct}%)"
