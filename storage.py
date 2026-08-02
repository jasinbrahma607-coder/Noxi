import os
import re
import json
import time
from config import (
    PREMIUM_FILE, SITES_FILE, PROXY_FILE, USER_PROXY_FILE, USER_POOL_FILE,
    ADMIN_IDS, _DEFAULT_ADMINS, LIMITS,
)

user_proxies: dict = {}

def _to_list(val) -> list:
    if val is None:
        return []
    if isinstance(val, list):
        return [p for p in val if p]
    return [val] if val else []

def load_user_proxies():
    global user_proxies
    if os.path.exists(USER_PROXY_FILE):
        try:
            with open(USER_PROXY_FILE, 'r') as f:
                raw = json.load(f)
                user_proxies = {int(k): _to_list(v) for k, v in raw.items()}
        except:
            user_proxies = {}

def save_user_proxies():
    try:
        with open(USER_PROXY_FILE, 'w') as f:
            json.dump({str(k): v for k, v in user_proxies.items()}, f)
    except:
        pass

def get_user_proxy_list(uid) -> list:
    return list(user_proxies.get(uid, []))

def set_user_proxies(uid, proxies: list):
    user_proxies[uid] = [p for p in proxies if p]
    save_user_proxies()

def remove_user_proxy(uid):
    user_proxies.pop(uid, None)
    save_user_proxies()

user_pool_enabled: dict = {}

def load_user_pool():
    global user_pool_enabled
    if os.path.exists(USER_POOL_FILE):
        try:
            with open(USER_POOL_FILE, 'r') as f:
                user_pool_enabled = {int(k): v for k, v in json.load(f).items()}
        except:
            user_pool_enabled = {}

def save_user_pool():
    try:
        with open(USER_POOL_FILE, 'w') as f:
            json.dump({str(k): v for k, v in user_pool_enabled.items()}, f)
    except:
        pass

def get_file_lines(fp):
    if not os.path.exists(fp):
        return []
    try:
        with open(fp, 'r', encoding='utf-8', errors='ignore') as f:
            return [l.strip() for l in f if l.strip()]
    except:
        return []

def load_premium_users(): return get_file_lines(PREMIUM_FILE)
def load_sites():         return get_file_lines(SITES_FILE)
def load_proxies():       return get_file_lines(PROXY_FILE)

# ==================== Admin check ====================
def is_admin(uid: int) -> bool:
    return uid in ADMIN_IDS or uid in _DEFAULT_ADMINS

# ==================== Key Management ====================
KEYS_FILE     = 'keys.json'
REDEEMED_FILE = 'redeemed.json'

def _load_keys() -> dict:
    try:
        with open(KEYS_FILE, 'r') as f:
            return json.load(f)
    except:
        return {}

def _save_keys(keys: dict):
    with open(KEYS_FILE, 'w') as f:
        json.dump(keys, f, indent=2)

def _load_redeemed() -> dict:
    try:
        with open(REDEEMED_FILE, 'r') as f:
            return json.load(f)
    except:
        return {}

def _save_redeemed(redeemed: dict):
    with open(REDEEMED_FILE, 'w') as f:
        json.dump(redeemed, f, indent=2)

def generate_keys(amount: int, hours: int, user_limit: int, price: float = 0.0) -> list:
    import random, string
    keys = _load_keys()
    new_keys = []
    expiry = int(time.time()) + hours * 3600
    for _ in range(amount):
        key = ''.join(random.choices(string.ascii_uppercase + string.digits, k=16))
        keys[key] = {
            "expiry": expiry,
            "limit": user_limit,
            "price": price,
            "used_by": None
        }
        new_keys.append(key)
    _save_keys(keys)
    return new_keys

def redeem_key(user_id: int, key: str) -> dict:
    keys = _load_keys()
    if key not in keys:
        return {'success': False, 'message': '❌ Invalid key.'}
    entry = keys[key]
    if entry.get('used_by') is not None:
        return {'success': False, 'message': '❌ This key has already been used.'}
    if entry['expiry'] < int(time.time()):
        return {'success': False, 'message': '❌ This key has expired.'}
    entry['used_by'] = user_id
    _save_keys(keys)
    redeemed = _load_redeemed()
    if str(user_id) not in redeemed:
        redeemed[str(user_id)] = []
    redeemed[str(user_id)].append({
        "key": key,
        "expiry": entry['expiry'],
        "limit": entry['limit'],
        "price": entry.get('price', 0)
    })
    _save_redeemed(redeemed)
    return {
        'success': True,
        'message': f'✅ Key redeemed successfully!\n📋 Limit: {entry["limit"]} cards\n⏳ Expires: {time.ctime(entry["expiry"])}',
        'limit': entry['limit'],
        'expiry': entry['expiry']
    }

def get_user_redeemed(user_id: int) -> list:
    redeemed = _load_redeemed()
    return redeemed.get(str(user_id), [])

def get_valid_redeemed(user_id: int) -> list:
    now = int(time.time())
    return [r for r in get_user_redeemed(user_id) if r.get('expiry', 0) > now]

def is_premium(uid: int) -> bool:
    if is_admin(uid):
        return True
    if str(uid) in load_premium_users():
        return True
    valid = get_valid_redeemed(uid)
    return len(valid) > 0

def get_user_limit(uid: int) -> int:
    if is_admin(uid):
        return LIMITS["admin"]
    if str(uid) in load_premium_users():
        return LIMITS["premium"]
    valid = get_valid_redeemed(uid)
    if valid:
        return max(r['limit'] for r in valid)
    return 0

def get_proxies_for_user(uid: int) -> list:
    user_list = get_user_proxy_list(uid)
    pool      = load_proxies()
    pool_on   = user_pool_enabled.get(uid, True)
    if is_admin(uid):
        if user_list:
            return (user_list + pool) if pool_on else user_list
        return pool
    if not user_list:
        return []
    return (user_list + pool) if pool_on else user_list

def extract_cc(text: str) -> list:
    matches = re.findall(r'(\d{15,16})\|(\d{2})\|(\d{2,4})\|(\d{3,4})', text)
    cards = []
    for card, month, year, cvv in matches:
        if len(year) == 2:
            year = '20' + year
        cards.append(f"{card}|{month}|{year}|{cvv}")
    return cards

def make_progress_bar(current, total, width=20) -> str:
    if total == 0:
        return f"[{'░'*width}] 0/0 (0%)"
    filled = int(width * current / total)
    pct    = int(100 * current / total)
    return f"[{'█'*filled}{'░'*(width-filled)}] {current}/{total} ({pct}%)"

load_user_proxies()
load_user_pool()
