"""Calls: incoming-call policy (notify / reject all / allow-list, block list, call triggers), missed-call log,
alarm ring, USSD. The uz-calls daemon applies the policy; this module edits it and reads the daemon's files.

status() reads only small files: /run/uz-calls.json (daemon state), /var/lib/uz/calls.jsonl (cached by mtime)
and /var/lib/uz/calls.seen. Actions that talk to the modem (hang up, USSD) load /usr/local/bin/uz-calls as a
module (it has no import side effects) and call mmcli with argument lists."""
import json, os, re, shutil, subprocess, sys, threading, time
from importlib.machinery import SourceFileLoader
from importlib.util import module_from_spec, spec_from_loader

STALE_S = 120                      # daemon writes its state at least every 30 s
UNAVAILABLE = {'error': 'not available on this host'}
LOCK = threading.Lock()
_UC = {}

def etc(n=''): return os.path.join(os.environ.get('UZ_ETC', '/etc/uz'), n)
def var(n=''): return os.path.join(os.environ.get('UZ_VAR', '/var/lib/uz'), n)
def run_dir(n=''): return os.path.join(os.environ.get('UZ_RUN', '/run'), n)

def bin_path():
    here = os.path.dirname(os.path.abspath(__file__))
    for p in (os.environ.get('UZ_CALLS_BIN', ''), '/usr/local/bin/uz-calls', os.path.join(here, '../../../bin/uz-calls')):
        if p and os.path.isfile(p): return os.path.abspath(p)
    return None

def uc():
    """uz-calls loaded as a module."""
    if 'm' not in _UC:
        p = bin_path()
        if not p: raise RuntimeError('uz-calls not installed')
        ld = SourceFileLoader('uzcalls_web', p); m = module_from_spec(spec_from_loader('uzcalls_web', ld))
        ld.exec_module(m); _UC['m'] = m
    return _UC['m']

def has_mmcli(): return bool(shutil.which('mmcli'))

def read_json(path, default):
    try:
        with open(path) as f: return json.load(f)
    except Exception: return default

def daemon_state(now=None):
    st = read_json(run_dir('uz-calls.json'), None)
    now = time.time() if now is None else now
    if not isinstance(st, dict) or not isinstance(st.get('ts'), (int, float)) or now - st['ts'] > STALE_S: return None
    return st

def seen_marker():
    try:
        with open(var('calls.seen')) as f: return int(f.read().strip() or 0)
    except (OSError, ValueError): return 0

def _log_entries(ctx):
    """calls.jsonl, cached by mtime in ctx.cache."""
    p = var('calls.jsonl')
    try: mt = os.stat(p).st_mtime_ns
    except OSError: return []
    c = ctx.cache.get('calls_log') if hasattr(ctx, 'cache') else None
    if c and c[0] == mt: return c[1]
    out = []
    try:
        with open(p) as f:
            for l in f:
                try:
                    e = json.loads(l)
                    if isinstance(e, dict): out.append(e)
                except ValueError: pass
    except OSError: return []
    if hasattr(ctx, 'cache'): ctx.cache['calls_log'] = (mt, out)
    return out

def missed_unseen(entries, seen):
    return sum(1 for e in entries if e.get('outcome') == 'missed' and isinstance(e.get('ts'), (int, float)) and e['ts'] > seen)

# ---------------- status ----------------
def status(ctx):
    st = daemon_state()
    act = (st or {}).get('active_calls') or []
    ringing = next((c for c in act if c.get('dir') == 'incoming' and c.get('state') in ('ringing-in', 'waiting')), None)
    return {'available': bool(st and st.get('voice')), 'daemon': st is not None, 'sim': (st or {}).get('sim', 'unknown'),
            'active': len(act), 'ringing': (ringing.get('number') or '?') if ringing else '',
            'missed_unseen': missed_unseen(_log_entries(ctx), seen_marker())}

# ---------------- actions ----------------
def get(body, ctx):
    m = uc()
    st = daemon_state()
    log = _log_entries(ctx)[-100:][::-1]
    return {'out': 'ok', 'policy': m.load_policy(), 'log': log, 'seen': seen_marker(),
            'daemon': st is not None, 'voice': bool(st and st.get('voice')), 'sim': (st or {}).get('sim', 'unknown'),
            'modem': (st or {}).get('modem', 'unknown'), 'calls': (st or {}).get('active_calls') or [],
            'sms_allow': len(m.sms_allow()), 'mmcli': has_mmcli(), 'actions': list(m.ACTIONS),
            'limits': {'list': m.MAX_LIST, 'triggers': m.MAX_TRIGGERS, 'ring_min': m.RING_MIN, 'ring_max': m.RING_MAX}}

def set_policy(body, ctx):
    m = uc()
    raw = body.get('policy')
    if not isinstance(raw, dict): return {'error': 'policy required'}
    pol, err = m.normalize_policy(raw, strict=True)
    if err: return {'error': err}
    with LOCK:
        try:
            os.makedirs(etc(), exist_ok=True); ctx.write_secret(etc('calls.json'), json.dumps(pol, indent=1) + '\n')
        except OSError as x: return {'error': f'cannot write calls.json ({type(x).__name__})'}
    return {'out': 'call policy saved', 'policy': pol}

def hangup(body, ctx):
    if not has_mmcli(): return UNAVAILABLE
    m = uc(); path = body.get('path')
    if path not in (None, ''):
        if not isinstance(path, str) or not m.CALL_PATH_RE.fullmatch(path): return {'error': 'invalid call path'}
        return {'out': 'hung up'} if m.hangup(path) else {'error': 'hang-up failed'}
    bad = m.hangup_all()
    return {'out': 'all calls hung up'} if not bad else {'error': f'{bad} hang-up(s) failed'}

def ring(body, ctx):
    m = uc()
    num, s = m.clean_number(body.get('number', '')), body.get('seconds', m.RING_DEFAULT)
    if not m.valid_number(num): return {'error': 'number: optional +, then 3–15 digits'}
    if not isinstance(s, int) or isinstance(s, bool) or not m.RING_MIN <= s <= m.RING_MAX:
        return {'error': f'seconds: {m.RING_MIN}–{m.RING_MAX}'}
    if not has_mmcli(): return UNAVAILABLE
    b = bin_path()
    args = [b, 'ring', num, str(s)]      # validated: digits and an optional leading +
    try:
        if shutil.which('systemd-run'):
            r = subprocess.run(['systemd-run', '--unit=uz-calls-ring', '--collect', '--quiet', *args],
                               capture_output=True, text=True, timeout=15)
            if r.returncode != 0:
                return {'error': 'a test ring is already running' if 'already' in (r.stderr or '') else 'could not start the ring'}
        else:
            subprocess.Popen([sys.executable, *args], stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                             stderr=subprocess.DEVNULL, start_new_session=True)
    except Exception as x: return {'error': f'could not start the ring ({type(x).__name__})'}
    return {'out': f'ringing for {s} s'}

def ussd(body, ctx):
    m = uc(); code = body.get('code')
    if not m.valid_ussd(code): return {'error': 'USSD code: 2–30 of * # 0-9, e.g. *101#'}
    if not has_mmcli(): return UNAVAILABLE
    return m.ussd(code)

def ussd_respond(body, ctx):
    m = uc(); text = body.get('text')
    if not m.valid_ussd_text(text): return {'error': 'response: 1–160 printable characters'}
    if not has_mmcli(): return UNAVAILABLE
    return m.ussd_respond(text)

def ussd_cancel(body, ctx):
    if not has_mmcli(): return UNAVAILABLE
    return uc().ussd_cancel()

def seen(body, ctx):
    entries = _log_entries(ctx)
    ts = max([int(e['ts']) for e in entries if isinstance(e.get('ts'), (int, float))] + [int(time.time())])
    try:
        os.makedirs(var(), exist_ok=True); ctx.write_secret(var('calls.seen'), str(ts))
    except OSError as x: return {'error': f'cannot write calls.seen ({type(x).__name__})'}
    return {'out': 'ok', 'seen': ts}

def log_clear(body, ctx):
    if body.get('confirm') is not True: return {'error': 'confirm required'}
    with LOCK:
        try: os.remove(var('calls.jsonl'))
        except FileNotFoundError: pass
        except OSError as x: return {'error': f'cannot clear the log ({type(x).__name__})'}
    if hasattr(ctx, 'cache'): ctx.cache.pop('calls_log', None)
    return {'out': 'call log cleared'}

ACTIONS = {'calls-get': get, 'calls-set': set_policy, 'calls-hangup': hangup, 'calls-ring': ring,
           'calls-ussd': ussd, 'calls-ussd-respond': ussd_respond, 'calls-ussd-cancel': ussd_cancel,
           'calls-seen': seen, 'calls-log-clear': log_clear}

def _guard(fn):
    def run(body, ctx):
        try: return fn(body if isinstance(body, dict) else {}, ctx)
        except Exception as e: return {'error': f'calls: {type(e).__name__}'}
    return run
ACTIONS = {k: _guard(v) for k, v in ACTIONS.items()}
