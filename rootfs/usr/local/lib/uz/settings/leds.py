"""LED mapping: what each LED shows in `auto` mode (/etc/uz/led-map.conf, read by uz-led)."""
import hashlib, os, re, shutil, subprocess

MAP = os.environ.get('UZ_LED_MAP', '/etc/uz/led-map.conf')
VAR = os.environ.get('UZ_LED_VAR', '/var/lib/uz')
LEDS = ('red', 'green', 'blue')
SOURCES = ('internet', 'wifi', 'lte', 'tailscale', 'usb', 'sms', 'heartbeat', 'off')
DEFAULT = {'red': 'internet', 'green': 'wifi', 'blue': 'lte'}
LINE = re.compile(r'\s*(red|green|blue)\s*=\s*([a-z]+)\s*')


def parse_map(text):
    """led-map.conf text -> {red,green,blue}; unknown lines / sources fall back to the defaults (last wins)."""
    m = dict(DEFAULT)
    for line in (text or '').splitlines():
        r = LINE.fullmatch(line)
        if r and r[2] in SOURCES: m[r[1]] = r[2]
    return m


def validate(body, current):
    """Merge {red,green,blue} from body into current; raise ValueError on anything not allowed."""
    if not isinstance(body, dict): raise ValueError('bad request')
    out = dict(current)
    for k, v in body.items():
        if k not in LEDS: raise ValueError(f'unknown LED: {str(k)[:16]}')
        if not isinstance(v, str) or v not in SOURCES: raise ValueError(f'{k}: choose one of ' + ', '.join(SOURCES))
        out[k] = v
    return out


def render(m):
    return '# what each LED shows in auto mode (uz-led); sources: ' + ' '.join(SOURCES) + '\n' + \
           ''.join(f'{k}={m[k]}\n' for k in LEDS)


def parse_status(text):
    """`uz-led status` lines ("red mode=auto auto=internet trigger=none on=1") -> {led: {k: v}}."""
    out = {}
    for line in (text or '').splitlines():
        p = line.split()
        if p and p[0] in LEDS:
            out[p[0]] = {k: v for k, _, v in (x.partition('=') for x in p[1:]) if re.fullmatch(r'[a-z_]+', k)}
    return out


def read_map():
    try:
        with open(MAP) as f: return parse_map(f.read())
    except OSError: return dict(DEFAULT)


def last_incoming_hash(path):
    """md5 of the last incoming line of sms.jsonl + '\\n' (same as uz-led's `printf '%s\\n' | md5sum`)."""
    try:
        with open(path, encoding='utf-8') as f:
            lines = [l.rstrip('\n') for l in f if l.startswith('{"dir": "in"')]
    except OSError: return None
    return hashlib.md5((lines[-1] + '\n').encode()).hexdigest() if lines else None


def status(ctx):
    return {'map': read_map()}


def get(body, ctx):
    st = {}
    if shutil.which('uz-led'):
        try: st = parse_status(subprocess.run(['uz-led', 'status'], capture_output=True, text=True, timeout=5).stdout)
        except Exception: st = {}
    return {'map': read_map(), 'sources': list(SOURCES), 'defaults': DEFAULT, 'state': st,
            'available': bool(st), 'sms_log': os.path.exists(os.path.join(VAR, 'sms.jsonl'))}


def map_set(body, ctx):
    try: m = validate(body, read_map())
    except ValueError as e: return {'error': str(e)}
    d = os.path.dirname(MAP)
    if not os.path.isdir(d): return {'error': 'not available on this host'}
    try:
        tmp = MAP + '.tmp'
        fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o644)
        with os.fdopen(fd, 'w') as f: f.write(render(m))
        os.replace(tmp, MAP)
    except OSError as e: return {'error': f'cannot write map: {e.strerror}'}
    if shutil.which('pkill'):
        try: subprocess.run(['pkill', '-HUP', '-f', 'uz-led daemon'], capture_output=True, timeout=5)
        except Exception: pass
    return {'out': 'LED map saved: ' + ', '.join(f'{k}={m[k]}' for k in LEDS), 'map': m}


def sms_seen(body, ctx):
    """Mark the newest incoming SMS as seen so an `sms` LED stops blinking."""
    h = last_incoming_hash(os.path.join(VAR, 'sms.jsonl'))
    if h is None: return {'out': 'no incoming SMS'}
    try:
        p = os.path.join(VAR, 'sms.seen')
        fd = os.open(p + '.tmp', os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
        with os.fdopen(fd, 'w') as f: f.write(h + '\n')
        os.replace(p + '.tmp', p)
    except OSError: return {'error': 'not available on this host'}
    return {'out': 'SMS marked as seen'}


ACTIONS = {'leds-get': get, 'leds-map-set': map_set, 'leds-sms-seen': sms_seen}
