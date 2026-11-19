"""Uptime checks: edit /etc/uz/probe.list (targets for uz-probe) and the uz-probe.timer interval.

Target grammar (what uz-probe understands): https://… | http://… | tcp:host:port | ping:host.
The interval lives in a drop-in /etc/systemd/system/uz-probe.timer.d/interval.conf, so the shipped unit stays
untouched. Comments in probe.list are kept: a comment block stays attached to the target that follows it."""
import ipaddress, os, re, shutil, subprocess
from urllib.parse import urlsplit

MAX_TARGETS = 20
MAX_URL = 200
INTERVALS = range(1, 61)
DEFAULT_HEADER = ['# One target per line: https://url | tcp:host:port | ping:host  (checked over the current uplink)']
LABEL_RE = re.compile(r'[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?')
DROPIN = 'uz-probe.timer.d/interval.conf'


def _etc(): return os.environ.get('UZ_ETC', '/etc/uz')
def _sysd(): return os.environ.get('UZ_SYSTEMD_DIR', '/etc/systemd/system')
def _list_path(): return os.path.join(_etc(), 'probe.list')
def _dropin_path(): return os.path.join(_sysd(), DROPIN)


def _read(path):
    try:
        with open(path) as f: return f.read()
    except (OSError, UnicodeDecodeError): return ''


# ---------- validation ----------
def valid_host(h):
    """Hostname or IPv4 address (uz-probe splits tcp: targets on ':', so IPv6 literals can't work)."""
    if not isinstance(h, str) or not 1 <= len(h) <= 253: return False
    labels = h.rstrip('.').split('.') if h != '.' else ['']
    if all(l.isdigit() for l in labels):          # looks numeric -> must be a real IPv4 address
        try: ipaddress.IPv4Address(h); return True
        except ValueError: return False
    return all(LABEL_RE.fullmatch(l) for l in labels)


def kind(t):
    for k in ('https', 'http'):
        if t.startswith(k + '://'): return k
    for k in ('tcp', 'ping'):
        if t.startswith(k + ':'): return k
    return ''


def normalize(raw):
    """-> (target, None) or (None, error). Lower-cases the type prefix (uz-probe is case-sensitive)."""
    if not isinstance(raw, str): return None, 'target must be text'
    t = raw.strip()
    m = re.match(r'(https?://|tcp:|ping:)', t, re.I)
    if m: t = m[1].lower() + t[m.end():]
    k = kind(t)
    if k in ('https', 'http'):
        if len(t) > MAX_URL: return None, f'URL longer than {MAX_URL} characters'
        if any(ord(c) <= 32 or ord(c) >= 127 for c in t): return None, 'URL: ASCII only, no spaces (percent-encode other characters)'
        try:
            u = urlsplit(t); host, port = u.hostname or '', u.port   # .port raises ValueError if invalid
        except ValueError: return None, f'invalid URL: {t[:60]}'
        if port == 0: return None, f'invalid port in URL: {t[:60]}'
        if ':' in host:
            try: ipaddress.IPv6Address(host)
            except ValueError: return None, f'invalid host in URL: {t[:60]}'
        elif not valid_host(host): return None, f'invalid host in URL: {t[:60]}'
        return t, None
    if k == 'tcp':
        parts = t.split(':')
        if len(parts) != 3: return None, f'use tcp:host:port — {t[:60]}'
        _, h, p = parts
        if not valid_host(h): return None, f'invalid host: {h[:60]}'
        if not (re.fullmatch(r'[0-9]{1,5}', p) and 1 <= int(p) <= 65535): return None, f'port must be 1–65535: {t[:60]}'
        return f'tcp:{h}:{int(p)}', None
    if k == 'ping':
        h = t[5:]
        if not valid_host(h): return None, f'invalid host: {h[:60]}'
        return t, None
    return None, f'unknown target type (https://, http://, tcp:host:port, ping:host): {t[:60]}'


def validate_targets(targets):
    if not isinstance(targets, list): return None, 'targets must be a list'
    out = []
    for raw in targets:
        t, err = normalize(raw)
        if err: return None, err
        if t not in out: out.append(t)
    if len(out) > MAX_TARGETS: return None, f'at most {MAX_TARGETS} targets'
    return out, None


def validate_interval(v):
    if isinstance(v, bool) or not isinstance(v, int) or v not in INTERVALS: return None, 'interval: 1–60 minutes'
    return v, None


# ---------- probe.list ----------
def parse_list(text):
    """-> {'header': [...], 'items': [{'target', 'comments'}], 'trailer': [...]}.
    Mirrors uz-probe: a non-blank line not starting with '#' is a target."""
    header, items, pending = [], [], []
    for line in text.splitlines():
        s = line.strip()
        if not s: continue
        if s.startswith('#'):
            pending.append(s); continue
        if not items and pending and not header:
            # first comment block before the first target is the file header
            header, pending = pending, []
        items.append({'target': s, 'comments': pending}); pending = []
    if not items: header, pending = pending, []
    return {'header': header, 'items': items, 'trailer': pending}


def render_list(old, targets):
    by = {}
    for it in old['items']: by.setdefault(it['target'], []).extend(it['comments'])
    lines = list(old['header'] or DEFAULT_HEADER)
    for t in targets: lines += by.pop(t, []) + [t]
    orphans = [c for cs in by.values() for c in cs]
    lines += orphans + old['trailer']
    return '\n'.join(lines) + '\n'


# ---------- interval ----------
UNITS = {'us': 1e-6, 'usec': 1e-6, 'ms': 1e-3, 'msec': 1e-3, 's': 1, 'sec': 1, 'second': 1, 'seconds': 1,
         'm': 60, 'min': 60, 'minute': 60, 'minutes': 60, 'h': 3600, 'hr': 3600, 'hour': 3600, 'hours': 3600,
         'd': 86400, 'day': 86400, 'days': 86400, 'w': 604800, 'week': 604800, 'weeks': 604800}


def span_seconds(s):
    """systemd time span ('5min', '1h 30min', '90', '1min 30s') -> seconds, or None."""
    s = (s or '').strip()
    if not s: return None
    total, pos = 0.0, 0
    for m in re.finditer(r'\s*([0-9]+(?:\.[0-9]+)?)\s*([a-z]*)', s):
        if m.start() != pos: return None
        u = m[2] or 's'
        if u not in UNITS: return None
        total += float(m[1]) * UNITS[u]; pos = m.end()
    return total if pos == len(s) and pos else None


def interval_from_unit(text):
    """Last effective OnUnitActiveSec= in a unit/drop-in (an empty assignment resets)."""
    val = None
    for line in text.splitlines():
        m = re.match(r'\s*OnUnitActiveSec\s*=\s*(.*?)\s*$', line)
        if m: val = m[1] or None
    return span_seconds(val) if val else None


def interval_from_show(text):
    """`systemctl show uz-probe.timer -p TimersMonotonic` -> seconds of OnUnitActiveUSec, or None."""
    m = re.search(r'OnUnitActiveUSec=([^;}]+)', text or '')
    return span_seconds(m[1]) if m else None


def minutes(sec):
    return None if sec is None else max(1, round(sec / 60)) if sec >= 30 else round(sec / 60, 2)


def interval_files():
    """Cheap: drop-in, then the shipped unit; None if unknown."""
    sec = interval_from_unit(_read(_dropin_path()))
    if sec is None: sec = interval_from_unit(_read(os.path.join(_sysd(), 'uz-probe.timer')))
    return sec


def render_dropin(n):
    return ('# Written by the dashboard (Uptime checks). Delete this file to restore the default.\n'
            '[Timer]\nOnUnitActiveSec=\n' f'OnUnitActiveSec={n}min\n')


def _run(args, t=20):
    try:
        r = subprocess.run(args, capture_output=True, text=True, timeout=t)
        return r.returncode, r.stdout, r.stderr
    except Exception as e:
        return -1, '', type(e).__name__


def write_atomic(path, text, mode=0o644):
    tmp = path + '.tmp'
    fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, mode)
    try:
        with os.fdopen(fd, 'w') as f:
            f.write(text); f.flush(); os.fsync(f.fileno())
        os.chmod(tmp, mode); os.replace(tmp, path)
    except BaseException:
        try: os.remove(tmp)
        except OSError: pass
        raise


# ---------- actions ----------
def get(body, ctx):
    text = _read(_list_path())
    p = parse_list(text)
    targets = []
    for it in p['items']:
        t, err = normalize(it['target'])
        targets.append({'target': it['target'], 'kind': kind(it['target']), 'valid': err is None,
                        'note': (it['comments'][-1].lstrip('# ').strip()[:80] if it['comments'] else '')})
    sec, src = None, ''
    if shutil.which('systemctl'):
        rc, out, _ = _run(['systemctl', 'show', 'uz-probe.timer', '-p', 'TimersMonotonic', '--value'], 10)
        if rc == 0: sec = interval_from_show(out); src = 'systemd' if sec is not None else ''
    if sec is None:
        sec = interval_files(); src = 'file' if sec is not None else ''
    r = {'targets': targets, 'interval_min': minutes(sec), 'interval_src': src, 'max': MAX_TARGETS,
         'list_exists': bool(text)}
    if not os.path.isdir(_etc()): r['warn'] = 'not available on this host'
    return r


def set_(body, ctx):
    body = body if isinstance(body, dict) else {}
    if 'targets' not in body and 'interval_min' not in body: return {'error': 'nothing to change'}
    targets = None
    if 'targets' in body:
        targets, err = validate_targets(body['targets'])
        if err: return {'error': err}
    n = None
    if body.get('interval_min') is not None:
        n, err = validate_interval(body['interval_min'])
        if err: return {'error': err}
        cur = interval_files()
        if cur is not None and abs(cur - n * 60) < 1: n = None   # unchanged
    # check everything we need before writing anything
    if targets is not None and not os.path.isdir(_etc()): return {'error': f'{_etc()} not found — not available on this host'}
    if n is not None and not shutil.which('systemctl'): return {'error': 'systemctl not available on this host'}
    done = []
    if targets is not None:
        try: write_atomic(_list_path(), render_list(parse_list(_read(_list_path())), targets))
        except OSError as e: return {'error': f'probe.list write failed: {e.strerror or type(e).__name__}'}
        done.append(f'{len(targets)} target{"s" if len(targets) != 1 else ""}')
    if n is not None:
        try:
            os.makedirs(os.path.dirname(_dropin_path()), exist_ok=True)
            write_atomic(_dropin_path(), render_dropin(n))
        except OSError as e: return {'error': f'timer drop-in write failed: {e.strerror or type(e).__name__}'}
        for args in (['systemctl', 'daemon-reload'], ['systemctl', 'restart', 'uz-probe.timer']):
            rc, _, err = _run(args, 30)
            if rc != 0: return {'error': f'{" ".join(args[1:])} failed: {(err or "").strip()[:150]}'}
        done.append(f'every {n} min')
    return {'out': 'saved: ' + ', '.join(done) if done else 'no changes'}


def run_now(body, ctx):
    if not shutil.which('systemctl'): return {'error': 'systemctl not available on this host'}
    rc, _, err = _run(['systemctl', 'start', '--no-block', 'uz-probe.service'], 10)
    if rc != 0: return {'error': f'could not start uz-probe: {(err or "").strip()[:150]}'}
    return {'out': 'checks started — results in about a minute'}


def status(ctx):
    p = parse_list(_read(_list_path()))
    return {'count': len(p['items']), 'interval_min': minutes(interval_files())}


ACTIONS = {'checks-get': get, 'checks-set': set_, 'checks-run': run_now}
