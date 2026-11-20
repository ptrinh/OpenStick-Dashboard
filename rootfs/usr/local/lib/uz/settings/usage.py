"""Data usage over the SIM: samples ModemManager's bearer byte counters (bam-dmux leaves the kernel's wwan0
counters at 0), accumulates them into hourly / daily buckets and reports 24 h / 7 d / 30 d / billing-cycle views,
with an optional monthly cap that notifies at 80 % and 100 %.

Counters: `bearer.stats.bytes-rx/tx` are per connection. A connection is identified by (bearer path, start-date);
a new connection, or a counter that went backwards, starts a new baseline (its bytes so far are counted once).
Storage: /var/lib/uz/usage.json (written at most every 10 min, or after 5 MB), settings /etc/uz/usage.json.
Local time (the stick's time zone) defines hours, days and the billing cycle."""
import calendar, json, os, re, shutil, subprocess, threading, time
from datetime import date, datetime, timedelta
from importlib.machinery import SourceFileLoader
from importlib.util import module_from_spec, spec_from_loader

SAMPLE_S = 60
FLUSH_S = 600
FLUSH_BYTES = 5_000_000
KEEP_HOURS = 49
KEEP_DAYS = 400
LOCK = threading.Lock()
_ST = {'data': None, 'dirty': 0, 'flushed': 0.0, 'thread': None}
_NOTIFY = {}


def etc(n=''): return os.path.join(os.environ.get('UZ_ETC', '/etc/uz'), n)
def var(n=''): return os.path.join(os.environ.get('UZ_VAR', '/var/lib/uz'), n)


def read_json(path, default):
    try:
        with open(path) as f: return json.load(f)
    except Exception: return default


def write_json(path, obj, mode=0o644):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = path + '.tmp'
    with open(tmp, 'w') as f: json.dump(obj, f, separators=(',', ':'))
    os.chmod(tmp, mode); os.replace(tmp, path)


# ---------------- settings ----------------
def load_conf():
    c = read_json(etc('usage.json'), {})
    d = c.get('cycle_day'); cap = c.get('cap_mb')
    return {'cycle_day': d if isinstance(d, int) and 1 <= d <= 28 else 1,
            'cap_mb': cap if isinstance(cap, int) and 0 <= cap <= 10_000_000 else 0}


# ---------------- pure helpers (tested) ----------------
def parse_bearer(text):
    """`mmcli -b PATH -K` → {'key': (path,start), 'rx': int, 'tx': int} or None when not connected."""
    kv = {}
    for l in (text or '').splitlines():
        if ':' in l:
            k, v = l.split(':', 1); kv[k.strip()] = v.strip()
    if kv.get('bearer.status.connected') not in (None, 'yes'): return None
    rx, tx, start = kv.get('bearer.stats.bytes-rx', ''), kv.get('bearer.stats.bytes-tx', ''), kv.get('bearer.stats.start-date', '')
    if not (rx.isdigit() and tx.isdigit()): return None
    return {'key': f"{kv.get('bearer.dbus-path', '')}@{start}", 'rx': int(rx), 'tx': int(tx)}


def delta(last, cur):
    """Bytes to add for sample `cur` given the previous sample `last` (same shape as parse_bearer)."""
    if not cur: return 0, 0
    if not last or last.get('key') != cur['key'] or cur['rx'] < last['rx'] or cur['tx'] < last['tx']:
        return cur['rx'], cur['tx']                     # new connection: count what it carried so far
    return cur['rx'] - last['rx'], cur['tx'] - last['tx']


def empty(): return {'v': 1, 'last': None, 'hours': {}, 'days': {}, 'alert': {}}


def add(data, rx, tx, now):
    if not (rx or tx): return
    lt = time.localtime(now)
    h, d = time.strftime('%Y-%m-%dT%H', lt), time.strftime('%Y-%m-%d', lt)
    for bucket, k in ((data['hours'], h), (data['days'], d)):
        v = bucket.get(k, [0, 0]); bucket[k] = [v[0] + rx, v[1] + tx]


def prune(data, now):
    lt = datetime.fromtimestamp(now)
    hmin = (lt - timedelta(hours=KEEP_HOURS)).strftime('%Y-%m-%dT%H')
    dmin = (lt.date() - timedelta(days=KEEP_DAYS)).isoformat()
    data['hours'] = {k: v for k, v in data['hours'].items() if k >= hmin}
    data['days'] = {k: v for k, v in data['days'].items() if k >= dmin}


def cycle_start(today, day):
    """Most recent date ≤ today whose day-of-month is `day` (1–28)."""
    if today.day >= day: return today.replace(day=day)
    y, m = (today.year, today.month - 1) if today.month > 1 else (today.year - 1, 12)
    return date(y, m, day)


def next_cycle(start):
    y, m = (start.year, start.month + 1) if start.month < 12 else (start.year + 1, 1)
    return date(y, m, start.day)


def series(data, rng, now, cycle_day):
    """→ {'points': [{'k','rx','tx'}], 'rx','tx', ...} for '24h' | '7d' | '30d' | 'month'."""
    lt = datetime.fromtimestamp(now); today = lt.date()
    pts = []
    if rng == '24h':
        for i in range(23, -1, -1):
            k = (lt - timedelta(hours=i)).strftime('%Y-%m-%dT%H')
            v = data['hours'].get(k, [0, 0]); pts.append({'k': k, 'rx': v[0], 'tx': v[1]})
        extra = {}
    else:
        if rng == 'month':
            start = cycle_start(today, cycle_day); end = next_cycle(start)
            days = (today - start).days + 1
            prev = cycle_start(start - timedelta(days=1), cycle_day)
            p = [data['days'].get((prev + timedelta(days=i)).isoformat(), [0, 0]) for i in range((start - prev).days)]
            extra = {'start': start.isoformat(), 'end': (end - timedelta(days=1)).isoformat(),
                     'days_left': (end - today).days, 'prev_rx': sum(x[0] for x in p), 'prev_tx': sum(x[1] for x in p),
                     'prev_complete': prev.isoformat() >= min(data['days'], default='9999')}
        else:
            days = 7 if rng == '7d' else 30; extra = {}
        for i in range(days - 1, -1, -1):
            k = (today - timedelta(days=i)).isoformat()
            v = data['days'].get(k, [0, 0]); pts.append({'k': k, 'rx': v[0], 'tx': v[1]})
    out = {'range': rng, 'points': pts, 'rx': sum(p['rx'] for p in pts), 'tx': sum(p['tx'] for p in pts)}
    out.update(extra)
    return out


def cap_level(used, cap_mb):
    """0, 80 or 100 — the highest threshold `used` bytes has crossed for a cap in MB (0 = no cap)."""
    if cap_mb <= 0: return 0
    pct = used / (cap_mb * 1e6) * 100
    return 100 if pct >= 100 else 80 if pct >= 80 else 0


# ---------------- sampler ----------------
def _mmcli(args, t=15):
    try: return subprocess.run(['mmcli', *args], capture_output=True, text=True, timeout=t).stdout
    except Exception: return ''


def read_bearer():
    m = _mmcli(['-m', 'any', '-K'])
    paths = [v.split(':', 1)[1].strip() for v in m.splitlines() if v.startswith('modem.generic.bearers.value[')]
    for p in paths:
        if p.startswith('/org/freedesktop/ModemManager1/Bearer/'):
            b = parse_bearer(_mmcli(['-b', p, '-K']))
            if b: return b
    return None


def _notify(event, text, data):
    try:
        if 'm' not in _NOTIFY:
            p = next((x for x in ('/usr/local/bin/uz-notify',) if os.path.isfile(x)), None)
            if not p: return
            ld = SourceFileLoader('uznotify_usage', p); m = module_from_spec(spec_from_loader('uznotify_usage', ld))
            ld.exec_module(m); _NOTIFY['m'] = m
        _NOTIFY['m'].notify(event, text, data)
    except Exception:
        pass


def _fmt(b):
    return f'{b / 1e9:.2f} GB' if b >= 1e9 else f'{b / 1e6:.0f} MB'


def check_cap(data, now, conf, send=_notify):
    if conf['cap_mb'] <= 0: return
    s = series(data, 'month', now, conf['cycle_day'])
    used = s['rx'] + s['tx']; lvl = cap_level(used, conf['cap_mb'])
    a = data.setdefault('alert', {})
    if a.get('cycle') != s['start']: a.clear(); a['cycle'] = s['start']; a['level'] = 0
    if lvl > a.get('level', 0):
        a['level'] = lvl
        send('data_cap', f"4G data: {_fmt(used)} of {_fmt(conf['cap_mb'] * 1e6)} used this cycle ({lvl}%+)",
             {'used_bytes': used, 'cap_mb': conf['cap_mb'], 'level': lvl, 'cycle_start': s['start']})


def _load():
    d = read_json(var('usage.json'), None)
    if not isinstance(d, dict) or d.get('v') != 1: d = empty()
    for k in ('hours', 'days'):
        if not isinstance(d.get(k), dict): d[k] = {}
    return d


def flush(force=False):
    with LOCK:
        d = _ST['data']
        if d is None: return
        if force or _ST['dirty'] >= FLUSH_BYTES or (_ST['dirty'] and time.time() - _ST['flushed'] >= FLUSH_S):
            try:
                write_json(var('usage.json'), d); _ST['dirty'] = 0; _ST['flushed'] = time.time()
            except OSError:
                pass


def sample(now=None, bearer=None):
    now = time.time() if now is None else now
    cur = read_bearer() if bearer is None else bearer
    with LOCK:
        d = _ST['data']
        if cur:
            rx, tx = delta(d.get('last'), cur)
            add(d, rx, tx, now); d['last'] = cur
            _ST['dirty'] += rx + tx
        prune(d, now)
        check_cap(d, now, load_conf())
    flush()


def _loop():
    while True:
        try: sample()
        except Exception: pass
        time.sleep(SAMPLE_S)


# ---------------- module contract ----------------
def init(ctx):
    with LOCK:
        if _ST['data'] is None: _ST['data'] = _load(); _ST['flushed'] = time.time()
    if shutil.which('mmcli') and _ST['thread'] is None:
        _ST['thread'] = threading.Thread(target=_loop, daemon=True); _ST['thread'].start()


def status(ctx):
    with LOCK:
        d = _ST['data']
        if d is None: return {'available': False}
        conf = load_conf(); now = time.time()
        m = series(d, 'month', now, conf['cycle_day']); day = series(d, '24h', now, conf['cycle_day'])
    used = m['rx'] + m['tx']
    return {'available': bool(shutil.which('mmcli')), 'month_bytes': used, 'day_bytes': day['rx'] + day['tx'],
            'cap_mb': conf['cap_mb'], 'cycle_start': m['start'],
            'cap_pct': round(used / (conf['cap_mb'] * 1e6) * 100) if conf['cap_mb'] else None}


RANGES = ('24h', '7d', '30d', 'month')


def get(body, ctx):
    rng = body.get('range', 'month')
    if rng not in RANGES: return {'error': 'range must be one of: ' + ', '.join(RANGES)}
    with LOCK:
        d = _ST['data'] or _load()
        conf = load_conf()
        s = series(d, rng, time.time(), conf['cycle_day'])
        since = min(d['days'], default=None)
    s.update({'out': 'ok', 'cycle_day': conf['cycle_day'], 'cap_mb': conf['cap_mb'], 'since': since,
              'available': bool(shutil.which('mmcli'))})
    return s


def set_conf(body, ctx):
    conf = load_conf()
    if 'cycle_day' in body:
        v = body['cycle_day']
        if not isinstance(v, int) or isinstance(v, bool) or not 1 <= v <= 28: return {'error': 'cycle_day must be 1–28'}
        conf['cycle_day'] = v
    if 'cap_mb' in body:
        v = body['cap_mb']
        if not isinstance(v, int) or isinstance(v, bool) or not 0 <= v <= 10_000_000: return {'error': 'cap_mb must be 0–10000000 (0 = no cap)'}
        conf['cap_mb'] = v
    try: write_json(etc('usage.json'), conf)
    except OSError as e: return {'error': f'could not save: {e.strerror}'}
    with LOCK:
        if _ST['data'] is not None: _ST['data']['alert'] = {}      # re-evaluate thresholds against the new cap
    return {'out': 'saved', **conf}


def reset(body, ctx):
    if body.get('confirm') is not True: return {'error': 'confirm required'}
    with LOCK:
        last = (_ST['data'] or {}).get('last')
        _ST['data'] = empty(); _ST['data']['last'] = last       # keep the baseline: don't recount this connection
        _ST['dirty'] = 1
    flush(force=True)
    return {'out': 'usage history cleared'}


def _guard(fn):
    def run(body, ctx):
        try: return fn(body if isinstance(body, dict) else {}, ctx)
        except Exception as e: return {'error': f'usage: {type(e).__name__}'}
    return run


ACTIONS = {k: _guard(v) for k, v in {'usage-get': get, 'usage-set': set_conf, 'usage-reset': reset}.items()}
