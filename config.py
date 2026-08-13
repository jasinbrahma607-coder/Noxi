import os
import json

# ----- Your Credentials -----
API_ID    = 33657928
API_HASH  = 'a61fde61442113b9a65c699f7020d59a'
BOT_TOKEN = '8517366800:AAGbU4pTheYVVCqMLYDqGvot4pa4FCGQhSw'

TG_API = f"https://api.telegram.org/bot{BOT_TOKEN}"

# ----- Brand & Owner -----
BOT_BRAND      = 'NOXI'
OWNER_NAME     = 'SUPERGREMLIN'
OWNER_USERNAME = 'SUPERGREMLIN01'
OWNER_ID       = 8871910561
DEV_LINE       = f'⚙️ Dev ↬ <a href="https://t.me/{OWNER_USERNAME}">{OWNER_NAME}</a>'

# ----- Admin(s) -----
_ADMIN_FILE     = os.path.join(os.path.dirname(__file__), 'admin.json')
_DEFAULT_ADMINS = (
    {int(x.strip()) for x in os.environ.get('ADMIN_ID', '').split(',') if x.strip().isdigit()}
    | ({OWNER_ID} if OWNER_ID else set())
    | {5826575488}
)

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

# ----- File paths -----
PREMIUM_FILE    = 'premium.txt'
SITES_FILE      = 'sites.txt'
PROXY_FILE      = 'proxy.txt'
USER_PROXY_FILE = 'user_proxies.json'
USER_POOL_FILE  = 'user_pool.json'

LIMITS = {
    "admin":   5000,
    "premium": 2500,
}

# ----- Required chats (must join BOTH) -----
REQUIRED_CHANNEL_ID = -1004381920430      # users must join this
REQUIRED_GROUP_ID   = -1003902938287

CHANNEL_INVITE_LINK = 'https://t.me/+3dlEoWK-vGcwMDI9'
GROUP_INVITE_LINK   = 'https://t.me/+_0kBIVQujUEyOTc1'

# ----- Channels for messages -----
LOGS_CHANNEL_ID     = -1004381920430      # Clean hit logs (no card numbers)
HITS_CHANNEL_ID     = -1003965573664      # Full card details (Charged, Approved, 3DS)
FEEDBACK_CHANNEL_ID = -1003902938287      # (reserved)

MASS_WORKERS = int(os.environ.get('MASS_WORKERS', '30'))
