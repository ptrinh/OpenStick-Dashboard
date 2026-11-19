"""SMS remote-control allow-list: /etc/uz/sms.allow (one number per line; uz-sms matches the last 9 digits).

An empty list means any sender with the right PIN may run commands. The file is re-read by uz-sms on every
incoming SMS, so no restart is needed."""
import os, re

NUM_RE = re.compile(r'\+?[0-9]{6,15}')
MAX = 20
HEADER = ('# SMS remote-control allow-list, written by the dashboard.\n'
          '# One number per line; a sender matches when its last 9 digits match.\n'
          '# An empty file means any sender with the right PIN.\n')


def _etc():
    return os.environ.get('UZ_ETC', '/etc/uz')


def _path(name):
    return os.path.join(_etc(), name)


def _read(path):
    try:
        with open(path) as f: return f.read()
    except (OSError, UnicodeDecodeError): return ''


def parse(text):
    """Numbers in an allow-list file (comments/blank lines skipped). Returns (numbers, other_lines)."""
    nums, other = [], []
    for line in text.splitlines():
        s = line.strip()
        if not s or s.startswith('#'): continue
        (nums if NUM_RE.fullmatch(s) else other).append(s)
    return nums, other


def key(n):
    """What uz-sms compares: the last 9 digits."""
    return n.lstrip('+')[-9:]


def normalize(raw):
    """Strip common formatting ( spaces - . ( ) ); return the number or None if it isn't E.164-ish."""
    if not isinstance(raw, str) or len(raw) > 40: return None
    s = re.sub(r'[\s\-.()]', '', raw)
    return s if NUM_RE.fullmatch(s) else None


def validate(numbers):
    """-> (clean list, error or None). Dedupes numbers that uz-sms would treat as the same (last 9 digits)."""
    if not isinstance(numbers, list): return None, 'numbers must be a list'
    out, seen = [], set()
    for raw in numbers:
        n = normalize(raw)
        if n is None:
            shown = str(raw)[:24] if isinstance(raw, (str, int)) and not isinstance(raw, bool) else '?'
            return None, f'invalid number: {shown} (use +country code and 6–15 digits)'
        if key(n) in seen: continue
        seen.add(key(n)); out.append(n)
    if len(out) > MAX: return None, f'at most {MAX} numbers'
    return out, None


def render(numbers):
    # uz-sms (current version) treats every non-blank line, comments included, as an entry, so an empty list must
    # be an empty file — a header-only file would block every sender. Header lines never end in a digit, so they
    # can't accidentally match a sender number.
    return HEADER + ''.join(n + '\n' for n in numbers) if numbers else ''


def write_atomic(path, text, mode=0o644):
    tmp = path + '.tmp'
    fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, mode)
    try:
        with os.fdopen(fd, 'w') as f:
            f.write(text); f.flush(); os.fsync(f.fileno())
        os.chmod(tmp, mode)
        os.replace(tmp, path)
    except BaseException:
        try: os.remove(tmp)
        except OSError: pass
        raise


def get(body, ctx):
    path = _path('sms.allow')
    nums, other = parse(_read(path))
    return {'out': f'{len(nums)} number(s)', 'numbers': nums, 'ignored': other[:20],
            'pin_set': bool(_read(_path('sms.pin')).strip()), 'max': MAX}


def set_(body, ctx):
    nums, err = validate(body.get('numbers') if isinstance(body, dict) else None)
    if err: return {'error': err}
    if not os.path.isdir(_etc()): return {'error': f'{_etc()} not found — not available on this host'}
    try: write_atomic(_path('sms.allow'), render(nums))
    except OSError as e: return {'error': f'write failed: {e.strerror or type(e).__name__}'}
    return {'out': f'allow-list saved ({len(nums)} number{"s" if len(nums) != 1 else ""})' if nums
            else 'allow-list cleared — any sender with the PIN', 'numbers': nums}


def status(ctx):
    nums, _ = parse(_read(_path('sms.allow')))
    return {'count': len(nums)}


ACTIONS = {'smsallow-get': get, 'smsallow-set': set_}
