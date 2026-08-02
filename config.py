import os
import json

# ========== Telegram credentials ==========
API_ID    = 33657928
API_HASH  = "a61fde61442113b9a65c699f7020d59a"
BOT_TOKEN = "8517366800:AAGbU4pTheYVVCqMLYDqGvot4pa4FCGQhSw"

TG_API = f"https://api.telegram.org/bot{BOT_TOKEN}"

# ========== Brand & Owner ==========
BOT_BRAND      = 'NOXI'
OWNER_NAME     = 'NOXI'
OWNER_USERNAME = 'NOXI'
OWNER_ID       = 8871910561
DEV_LINE       = f'💻 <b>Dev</b>  »  <a href="https://t.me/{OWNER_USERNAME}">{OWNER_NAME}</a>'

MASS_WORKERS = int(os.environ.get('MASS_WORKERS', '30'))

# ========== Admin IDs ==========
_ADMIN_FILE     = os.path.join(os.path.dirname(__file__), 'admin.json')
_DEFAULT_ADMINS = {5826575488, 8871910561}

def _load_admin_ids() -> set:
    try:
        with open(_ADMIN_FILE) as f:
            data = json.load(f)
            ids  = data.get('admin_ids', [])
            return set(ids) | _DEFAULT_ADMINS if ids else _DEFAULT_ADMINS
    except Exception:
        return _DEFAULT_ADMINS

def _save_admin_ids(ids: set):
    try:
        with open(_ADMIN_FILE) as f:
            data = json.load(f)
    except Exception:
        data = {}
    data['admin_ids'] = list(ids)
    with open(_ADMIN_FILE, 'w') as f:
        json.dump(data, f)

ADMIN_IDS = _load_admin_ids()
ADMIN_ID  = OWNER_ID

# ========== Files ==========
PREMIUM_FILE    = 'premium.txt'
SITES_FILE      = 'sites.txt'
PROXY_FILE      = 'proxy.txt'
USER_PROXY_FILE = 'user_proxies.json'
USER_POOL_FILE  = 'user_pool.json'

# ========== Limits ==========
LIMITS = {
    "admin":   5000,
    "premium": 2500,
}

# ========== Channels ==========
CHANNEL_LOGS    = -1004381920430   # all logs (redeem, hits with masked CC)
CHANNEL_CHARGED = -1003965573664   # only charged CC with full details
CHANNEL_OTHER   = -1003902938287   # not used

CHANNEL_INVITE_LINK = "https://t.me/+7hJ8-jOuoWJkZTQ9"
GROUP_INVITE_LINK   = "https://t.me/+6rGC4rCRLek5NDVl"