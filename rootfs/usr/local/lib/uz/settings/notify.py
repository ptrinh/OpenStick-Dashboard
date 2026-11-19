"""Notifications: Telegram bot + signed webhook, per-channel event routing.

Config: /etc/uz/telegram.env (TG_TOKEN, TG_CHAT, TG_BOT — shared with uz-sms's bot) and /etc/uz/notify.json
(routing + webhook url/secret), both 0600. Sending is done by uz-notify (loaded as a module).
Secrets (bot token, webhook secret, webhook URL path) never leave this module in full."""
import ipaddress, json, os, re, shutil, subprocess, threading, time, urllib.parse
from importlib.machinery import SourceFileLoader
from importlib.util import module_from_spec, spec_from_loader

TOKEN_RE = re.compile(r'\d{6,12}:[A-Za-z0-9_-]{30,50}')
HOST_RE = re.compile(r'(?=.{1,253}$)([A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?\.)*[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?')
LOCK = threading.Lock()
DETECT_WAIT = 25          # seconds notify-telegram-detect listens for /start
_UN = {}

def etc(name=''): return os.path.join(os.environ.get('UZ_ETC', '/etc/uz'), name)

def un():
    """The uz-notify script, loaded as a module (device path, or the repo copy next to this file)."""
    if 'm' not in _UN:
        here = os.path.dirname(os.path.abspath(__file__))
        for p in (os.environ.get('UZ_NOTIFY_BIN', ''), os.path.join(here, '../../../bin/uz-notify'), '/usr/local/bin/uz-notify'):
            if p and os.path.isfile(p):
                loader = SourceFileLoader('uznotify_web', p)
                m = module_from_spec(spec_from_loader('uznotify_web', loader)); loader.exec_module(m)
                _UN['m'] = m; break
        else: raise RuntimeError('uz-notify not installed')
    return _UN['m']

# ---------- config I/O ----------
def write_secret(ctx, path, text):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    ctx.write_secret(path, text)

def save_config(ctx, cfg):
    write_secret(ctx, etc('notify.json'), json.dumps(cfg, indent=1) + '\n')

def save_env(ctx, e):
    keys = [k for k in ('TG_TOKEN', 'TG_CHAT', 'TG_BOT') if e.get(k)] + [k for k in e if k not in ('TG_TOKEN', 'TG_CHAT', 'TG_BOT') and e[k]]
    write_secret(ctx, etc('telegram.env'), ''.join(f'{k}={e[k]}\n' for k in keys))

def restart_sms(ctx):
    """uz-sms's Telegram bot reads the token at start."""
    if shutil.which('systemctl'): ctx.run_bg('systemctl restart uz-sms')

def mask_url(url):
    """scheme://host[:port]/… — path segments and query may hold tokens (Slack/Discord-style webhooks)."""
    try: u = urllib.parse.urlsplit(url)
    except ValueError: return ''
    if not u.scheme or not u.netloc: return ''
    segs = [s if len(s) <= 12 and not re.search(r'\d{5,}', s) else '…' + s[-3:] for s in u.path.split('/')]
    return f'{u.scheme}://{u.netloc}' + '/'.join(segs) + ('?…' if u.query else '')

# ---------- validation ----------
def check_url(url):
    """→ error message or None. https anywhere; http only to a private (LAN) IP literal."""
    if not isinstance(url, str) or not (10 <= len(url) <= 500): return 'URL: 10–500 characters'
    if any(ord(c) <= 32 or ord(c) == 127 for c in url): return 'URL: no spaces or control characters'
    try:
        u = urllib.parse.urlsplit(url); host = u.hostname or ''; u.port
    except ValueError: return 'URL: invalid'
    if u.scheme not in ('https', 'http'): return 'URL must start with https://'
    if u.username is not None or u.password is not None: return 'URL: credentials in the URL are not supported — use the secret'
    if u.fragment: return 'URL: no #fragment'
    try: ip = ipaddress.ip_address(host)
    except ValueError: ip = None
    if ip is None and not HOST_RE.fullmatch(host): return 'URL: invalid host name'
    if ip is not None and (ip.is_loopback or ip.is_link_local or ip.is_unspecified or ip.is_multicast):
        return 'URL: loopback, link-local and multicast addresses are not allowed'
    if u.scheme == 'http' and (ip is None or not ip.is_private):
        return 'URL must use https:// (plain http only for a private LAN IP address)'
    return None

def check_secret(s):
    if not isinstance(s, str) or not (8 <= len(s) <= 256) or not all(33 <= ord(c) <= 126 for c in s):
        return 'secret: 8–256 printable ASCII characters, no spaces'
    return None

def check_events(v, ev):
    if not isinstance(v, list) or len(v) > 20 or not all(isinstance(x, str) for x in v): return None
    if any(x not in ev for x in v): return None
    return [e for e in ev if e in v]

# ---------- actions ----------
def get(body, ctx):
    try: m = un()
    except Exception as e: return {'error': str(e)}
    cfg, e = m.load_config(), m.env()
    tok, w = e.get('TG_TOKEN', ''), cfg['webhook']
    return {'out': 'ok', 'events': list(m.EVENTS),
            'telegram': {'token': 'set' if tok else 'not set', 'token_hint': ('…' + tok[-4:]) if len(tok) >= 20 else '',
                         'bot': e.get('TG_BOT', ''), 'chat': e.get('TG_CHAT', ''), 'enabled': cfg['telegram']['enabled'],
                         'events': cfg['telegram']['events'], 'configured': bool(tok and e.get('TG_CHAT'))},
            'webhook': {'url': mask_url(w['url']), 'url_set': bool(w['url']), 'secret': 'set' if w['secret'] else 'not set',
                        'enabled': w['enabled'], 'events': w['events'], 'configured': bool(w['url'])}}

def telegram_set(body, ctx):
    tok = body.get('token')
    if not isinstance(tok, str) or not TOKEN_RE.fullmatch(tok.strip()):
        return {'error': 'token format: 123456789:ABC… (from @BotFather)'}
    tok = tok.strip()
    try: m = un()
    except Exception as e: return {'error': str(e)}
    ok, res = m.tg_api(tok, 'getMe', timeout=15)
    if not ok: return {'error': f'Telegram rejected the token or is unreachable: {m._scrub(res, tok)} — not saved'}
    bot = str((res or {}).get('username') or '')
    if not re.fullmatch(r'[A-Za-z0-9_]{1,64}', bot): bot = ''
    with LOCK:
        e = m.env(); e.update(TG_TOKEN=tok, TG_BOT=bot)   # TG_CHAT is kept: a private chat id is the user's id
        try: save_env(ctx, e)
        except OSError as x: return {'error': f'cannot write telegram.env ({type(x).__name__})'}
    restart_sms(ctx)
    return {'out': f'bot @{bot} saved' if bot else 'token saved', 'bot': bot}

def telegram_detect(body, ctx):
    """Find the chat id: the latest private chat that messaged the bot. uz-sms's bot long-polls the same
    updates (and acknowledges them), so it is stopped while we listen for up to `wait` seconds."""
    try: m = un()
    except Exception as e: return {'error': str(e)}
    e = m.env(); tok = e.get('TG_TOKEN', '')
    if not tok: return {'error': 'save the bot token first'}
    bot = e.get('TG_BOT', '')
    ask = f'send /start to @{bot}' if bot else 'send /start to your bot'
    systemd = bool(shutil.which('systemctl'))
    if systemd:
        try: subprocess.run(['systemctl', 'stop', 'uz-sms'], capture_output=True, timeout=20)
        except Exception: pass
    chat = None
    try:
        deadline = time.time() + DETECT_WAIT
        while True:
            wait = max(0, min(20, int(deadline - time.time())))
            ok, res = m.tg_api(tok, 'getUpdates', {'timeout': wait, 'allowed_updates': '["message"]'}, timeout=wait + 10)
            if not ok: return {'error': f'Telegram: {m._scrub(res, tok)}'}
            for up in sorted(res or [], key=lambda u: u.get('update_id', 0), reverse=True):
                c = (up.get('message') or {}).get('chat') or {}
                if c.get('type') == 'private' and isinstance(c.get('id'), int):
                    chat = c; break
            if chat is not None or wait == 0 or time.time() >= deadline: break
            if not res: time.sleep(1)
        if chat is None: return {'error': f'no private message found — press Detect, then {ask} within 20 s'}
        with LOCK:
            e = m.env(); e['TG_CHAT'] = str(chat['id'])
            try: save_env(ctx, e)
            except OSError as x: return {'error': f'cannot write telegram.env ({type(x).__name__})'}
    finally:
        if systemd: restart_sms(ctx)
    who = ' '.join(str(chat.get(k) or '') for k in ('first_name', 'last_name')).strip() or str(chat.get('username') or '')
    return {'out': f'chat found: {who[:40]} ({chat["id"]})' if who else f'chat found: {chat["id"]}', 'chat': str(chat['id'])}

def webhook_set(body, ctx):
    try: m = un()
    except Exception as e: return {'error': str(e)}
    url, secret = body.get('url'), body.get('secret')
    with LOCK:
        cfg = m.load_config(); w = cfg['webhook']
        if url in (None, '') and not w['url']: return {'error': 'URL required'}
        if url not in (None, ''):
            err = check_url(url)
            if err: return {'error': err}
            w['url'] = url
        if body.get('remove_secret') is True: w['secret'] = ''
        elif secret not in (None, ''):
            err = check_secret(secret)
            if err: return {'error': err}
            w['secret'] = secret
        w['enabled'] = True
        try: save_config(ctx, cfg)
        except OSError as x: return {'error': f'cannot write notify.json ({type(x).__name__})'}
    return {'out': 'webhook saved' + ('' if w['secret'] else ' (unsigned — no secret)')}

def events_set(body, ctx):
    try: m = un()
    except Exception as e: return {'error': str(e)}
    with LOCK:
        cfg, n = m.load_config(), 0
        for ch in ('telegram', 'webhook'):
            if ch in body:
                ev = check_events(body[ch], m.EVENTS)
                if ev is None: return {'error': f'{ch}: events must be a list of: {", ".join(m.EVENTS)}'}
                cfg[ch]['events'] = ev; n += 1
            if isinstance(body.get(ch + '_enabled'), bool): cfg[ch]['enabled'] = body[ch + '_enabled']; n += 1
        if not n: return {'error': 'nothing to change'}
        try: save_config(ctx, cfg)
        except OSError as x: return {'error': f'cannot write notify.json ({type(x).__name__})'}
    return {'out': 'events saved'}

def test(body, ctx):
    ch = body.get('channel')
    if ch not in ('telegram', 'webhook'): return {'error': 'channel: telegram or webhook'}
    try: m = un()
    except Exception as e: return {'error': str(e)}
    name = 'Telegram' if ch == 'telegram' else 'Webhook'
    try: ok, detail = m.test(ch)
    except Exception as e: return {'error': f'{name}: {type(e).__name__}'}
    return {'out': f'{name}: delivered ({detail})' if ch == 'webhook' else f'{name}: delivered', 'ok': True} if ok \
        else {'error': f'{name}: {detail}', 'ok': False}

def telegram_clear(body, ctx):
    with LOCK:
        try: os.remove(etc('telegram.env'))
        except FileNotFoundError: pass
        except OSError as x: return {'error': f'cannot remove telegram.env ({type(x).__name__})'}
    restart_sms(ctx)
    return {'out': 'Telegram removed'}

def webhook_clear(body, ctx):
    try: m = un()
    except Exception as e: return {'error': str(e)}
    with LOCK:
        cfg = m.load_config(); cfg['webhook'] = m.defaults()['webhook']
        try: save_config(ctx, cfg)
        except OSError as x: return {'error': f'cannot write notify.json ({type(x).__name__})'}
    return {'out': 'webhook removed'}

ACTIONS = {
    'notify-get': get, 'notify-telegram-set': telegram_set, 'notify-telegram-detect': telegram_detect,
    'notify-webhook-set': webhook_set, 'notify-events-set': events_set, 'notify-test': test,
    'notify-telegram-clear': telegram_clear, 'notify-webhook-clear': webhook_clear,
}

def _guard(fn):
    def run(body, ctx):
        try: return fn(body if isinstance(body, dict) else {}, ctx)
        except Exception as e: return {'error': f'notify: {type(e).__name__}'}
    return run
ACTIONS = {k: _guard(v) for k, v in ACTIONS.items()}

def status(ctx):
    """Cheap: two small file reads, no network."""
    tg = wh = False
    try:
        e = {}
        with open(etc('telegram.env')) as f:
            for l in f:
                if '=' in l: k, v = l.strip().split('=', 1); e[k] = v
        tg = bool(e.get('TG_TOKEN') and e.get('TG_CHAT'))
    except OSError: pass
    try:
        with open(etc('notify.json')) as f: c = json.load(f)
        t, w = c.get('telegram') or {}, c.get('webhook') or {}
        if t.get('enabled') is False: tg = False
        wh = bool(w.get('enabled') and w.get('url'))
    except Exception: pass
    return {'telegram': tg, 'webhook': wh}
