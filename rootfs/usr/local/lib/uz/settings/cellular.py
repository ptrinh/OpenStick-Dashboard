"""Cellular (4G) settings: SIM / PIN, APN, roaming, network mode, reconnect.

ModemManager + NetworkManager backend only (Debian/openstick image, NM profile "lte").
On hosts without mmcli/nmcli, with ModemManager disabled, or with UZ_BACKEND=qmi (postmarketOS
`uz-lte`), every action returns {'error': 'not supported on this backend'}.

Privacy: the SIM PIN and APN password are never logged or returned; ICCID / IMSI are masked.
"""
import os, re, shutil, subprocess, threading, time

PROFILE = 'lte'
UNSUPPORTED = {'error': 'not supported on this backend'}
REFRESH_S = 60
SIM_PATH_RE = re.compile(r'/org/freedesktop/ModemManager1/SIM/\d+')
APN_RE = re.compile(r'[A-Za-z0-9.-]{1,63}')
PIN_RE = re.compile(r'\d{4,8}')
CRED_RE = re.compile(r'[\x20-\x7e]{0,64}')        # printable ASCII, no newlines
MODE_TOKEN_RE = re.compile(r'(?:2g|3g|4g|5g|cs|any|none)')
IP_TYPES = {'ipv4': ('auto', 'disabled'), 'ipv6': ('disabled', 'auto'), 'ipv4v6': ('auto', 'auto')}
LOCKED_STATES = ('sim-pin', 'sim-puk', 'sim-pin2', 'sim-puk2', 'ph-sim-pin', 'ph-fsim-pin', 'ph-fsim-puk',
                 'ph-net-pin', 'ph-net-puk', 'ph-netsub-pin', 'ph-sp-pin', 'ph-corp-pin')

_lock = threading.Lock()
_state = {'t': 0.0, 'busy': False}
_backend = {'v': None}


# ---------------- subprocess helpers (arg lists only, never a shell) ----------------
def _run(args, t=20):
    """Run an argument list; returns (rc, stdout, stderr). Never raises."""
    try:
        p = subprocess.run(args, capture_output=True, text=True, timeout=t)
        return p.returncode, p.stdout, p.stderr
    except FileNotFoundError:
        return 127, '', 'command not found'
    except subprocess.TimeoutExpired:
        return 124, '', 'timed out'
    except Exception as e:
        return 1, '', type(e).__name__


def supported(ctx=None):
    """MM backend available? Cached after the first positive/negative probe."""
    if os.environ.get('UZ_BACKEND') == 'qmi':
        return False
    try:
        if ctx is not None and (ctx.conf() or {}).get('UZ_BACKEND') == 'qmi':
            return False
    except Exception:
        pass
    if _backend['v'] is None:
        ok = bool(shutil.which('mmcli') and shutil.which('nmcli'))
        if ok and shutil.which('systemctl'):
            ok = _run(['systemctl', 'is-enabled', '-q', 'ModemManager'], 5)[0] == 0
        _backend['v'] = ok
    return _backend['v']


# ---------------- parsers (pure, unit-tested with fixtures) ----------------
def parse_kv(text):
    """Parse `mmcli -K` output into a dict; multi-value keys become lists; '--' becomes ''."""
    d, arrays = {}, {}
    for line in (text or '').splitlines():
        if ':' not in line:
            continue
        k, v = line.split(':', 1)
        k, v = k.strip(), v.strip()
        if v == '--':
            v = ''
        m = re.fullmatch(r'(.+)\.value\[(\d+)\]', k)
        if m:
            arrays.setdefault(m[1], []).append((int(m[2]), v))
            continue
        if k.endswith('.length'):
            arrays.setdefault(k[:-7], [])
            continue
        d[k] = v
    for k, items in arrays.items():
        d[k] = [v for _, v in sorted(items) if v]
    return d


def parse_retries(values):
    """['sim-pin (3)', 'sim-puk (10)'] -> {'sim-pin': 3, 'sim-puk': 10}."""
    out = {}
    for v in values or []:
        m = re.fullmatch(r'([a-z0-9-]+)\s*\((\d+)\)', v.strip())
        if m:
            out[m[1]] = int(m[2])
    return out


def parse_nm(text):
    """Output of `nmcli -g gsm.apn,gsm.username,gsm.password-flags,gsm.home-only,ipv4.method,ipv6.method`."""
    keys = ('apn', 'username', 'password_flags', 'home_only', 'ipv4', 'ipv6')
    lines = (text or '').split('\n')
    vals = [re.sub(r'\\(.)', r'\1', l) for l in lines[:len(keys)]]
    vals += [''] * (len(keys) - len(vals))
    d = dict(zip(keys, vals))
    v4, v6 = d['ipv4'], d['ipv6']
    on = lambda m: m not in ('disabled', 'ignore', '')
    d['ip_type'] = 'ipv4v6' if on(v4) and on(v6) else 'ipv6' if on(v6) else 'ipv4'
    d['home_only'] = d['home_only'] == 'yes'
    d['roaming_allowed'] = not d['home_only']
    return d


def mask_tail(s, keep=4):
    s = re.sub(r'\D', '', s or '')
    if not s:
        return ''
    return '•' * max(len(s) - keep, 0) + s[-keep:] if len(s) > keep else '•' * len(s)


def mask_imsi(s):
    s = re.sub(r'\D', '', s or '')
    return s[:5] + '•' * (len(s) - 5) if len(s) > 5 else ('•' * len(s))


def sim_state(m):
    """'missing' | 'locked' | 'ready' | 'unknown' from parsed modem kv."""
    if not m:
        return 'unknown'
    if not m.get('modem.generic.sim') or m.get('modem.generic.state-failed-reason') in ('sim-missing', 'sim-error'):
        return 'missing'
    if m.get('modem.generic.unlock-required') in LOCKED_STATES or m.get('modem.generic.state') == 'locked':
        return 'locked'
    return 'ready'


def roaming_of(m):
    r = (m or {}).get('modem.3gpp.registration-state', '')
    return True if r == 'roaming' else False if r == 'home' else None


def mode_args(mode):
    """'allowed: 3g, 4g; preferred: 4g' -> ['--set-allowed-modes=3g|4g', '--set-preferred-mode=4g']."""
    m = re.fullmatch(r'allowed: ([a-z0-9, ]+); preferred: ([a-z0-9]+)', mode or '')
    if not m:
        return None
    allowed = [x.strip() for x in m[1].split(',')]
    if not allowed or not all(MODE_TOKEN_RE.fullmatch(x) for x in allowed) or not MODE_TOKEN_RE.fullmatch(m[2]):
        return None
    args = ['--set-allowed-modes=' + '|'.join(allowed)]
    if m[2] != 'none':
        args.append('--set-preferred-mode=' + m[2])
    return args


# ---------------- data gathering ----------------
def _modem():
    rc, out, _ = _run(['mmcli', '-m', 'any', '-K'])
    return parse_kv(out) if rc == 0 else {}


def _sim(path):
    if not path or not SIM_PATH_RE.fullmatch(path):
        return {}
    rc, out, _ = _run(['mmcli', '-i', path, '-K'])
    return parse_kv(out) if rc == 0 else {}


def _nm():
    rc, out, _ = _run(['nmcli', '-g', 'gsm.apn,gsm.username,gsm.password-flags,gsm.home-only,ipv4.method,ipv6.method',
                       'connection', 'show', PROFILE], 10)
    return parse_nm(out) if rc == 0 else None


def summarize(m, nm):
    return {'backend': 'mm', 'sim': sim_state(m), 'unlock': m.get('modem.generic.unlock-required', '') if m else '',
            'roaming': roaming_of(m), 'apn': (nm or {}).get('apn', ''), 'profile': nm is not None, 'modem': bool(m)}


def _refresh(ctx):
    try:
        m = _modem()
        nm = _nm()
        ctx.cache['cellular'] = summarize(m, nm)
    except Exception:
        pass
    finally:
        with _lock:
            _state['t'] = time.time()
            _state['busy'] = False


def _kick(ctx, force=False):
    """Start a background refresh if stale (or forced) and none is running. Never blocks."""
    with _lock:
        if _state['busy'] or (not force and time.time() - _state['t'] < REFRESH_S):
            return
        _state['busy'] = True
    threading.Thread(target=_refresh, args=(ctx,), daemon=True).start()


def _reup(ctx):
    ctx.run_bg(f'nmcli connection down {PROFILE}; sleep 2; nmcli connection up {PROFILE}')


def _err(stderr, secrets=()):
    """Short, secret-free error message from mmcli/nmcli stderr."""
    s = (stderr or '').strip().splitlines()
    s = s[-1] if s else 'failed'
    m = re.search(r"Error\.[A-Za-z]+\.([A-Za-z]+)", s)
    if m:
        s = m[1]
    s = re.sub(r"GDBus\.Error:\S+", '', s)
    for x in secrets:
        if x:
            s = s.replace(x, '•••')
    s = re.sub(r'\d{4,}', '•••', s)          # belt and braces: no PIN/ICCID-like digits in toasts
    return s.strip(' :')[:160] or 'failed'


# ---------------- module contract ----------------
def init(ctx):
    if supported(ctx):
        _kick(ctx, force=True)


def status(ctx):
    if not supported(ctx):
        return {'backend': 'none', 'sim': None, 'roaming': None, 'apn': ''}
    _kick(ctx)
    return dict(ctx.cache.get('cellular') or {'backend': 'mm', 'sim': 'unknown', 'roaming': None, 'apn': ''})


def cell_get(body, ctx):
    if not supported(ctx):
        return dict(UNSUPPORTED)
    m = _modem()
    if not m:
        return {'error': 'no modem found (ModemManager)'}
    sim = _sim(m.get('modem.generic.sim', ''))
    nm = _nm()
    ctx.cache['cellular'] = summarize(m, nm)
    g = lambda k: m.get(k, '')
    out = {
        'out': 'ok',
        'sim': {
            'state': sim_state(m),
            'modem_state': g('modem.generic.state'),
            'failed_reason': g('modem.generic.state-failed-reason'),
            'unlock_required': g('modem.generic.unlock-required'),
            'unlock_retries': parse_retries(m.get('modem.generic.unlock-retries')),
            'pin_lock': 'sim' in (m.get('modem.3gpp.enabled-locks') or []),
            'iccid': mask_tail(sim.get('sim.properties.iccid')),
            'imsi': mask_imsi(sim.get('sim.properties.imsi')),
            'operator': sim.get('sim.properties.operator-name', ''),
            'own_numbers': list(m.get('modem.generic.own-numbers') or []),
        },
        'network': {
            'registration': g('modem.3gpp.registration-state'),
            'roaming': roaming_of(m),
            'operator': g('modem.3gpp.operator-name'),
            'access_tech': list(m.get('modem.generic.access-technologies') or []),
        },
        'modes': {'supported': list(m.get('modem.generic.supported-modes') or []), 'current': g('modem.generic.current-modes')},
        'profile': None,
    }
    if nm is not None:
        out['profile'] = {'apn': nm['apn'], 'username': nm['username'], 'ip_type': nm['ip_type'],
                          'roaming_allowed': nm['roaming_allowed'], 'password_flags': nm['password_flags']}
    return out


def _need_profile():
    if _nm() is None:
        return {'error': f'NetworkManager profile "{PROFILE}" not found'}
    return None


def cell_apn_set(body, ctx):
    if not supported(ctx):
        return dict(UNSUPPORTED)
    apn = body.get('apn', '')
    ip_type = body.get('ip_type', 'ipv4v6')
    if not isinstance(apn, str) or (apn and not APN_RE.fullmatch(apn)):
        return {'error': 'invalid APN (letters, digits, dot, dash; max 63) — empty = automatic'}
    if ip_type not in IP_TYPES:
        return {'error': 'ip_type must be ipv4, ipv6 or ipv4v6'}
    user, pw = body.get('username'), body.get('password')
    for name, v in (('username', user), ('password', pw)):
        if v is not None and (not isinstance(v, str) or not CRED_RE.fullmatch(v)):
            return {'error': f'invalid {name} (printable ASCII, max 64)'}
    e = _need_profile()
    if e:
        return e
    v4, v6 = IP_TYPES[ip_type]
    args = ['nmcli', 'connection', 'modify', PROFILE,
            'gsm.auto-config', 'no' if apn else 'yes', 'gsm.apn', apn,
            'ipv4.method', v4, 'ipv6.method', v6]
    if user is not None:
        args += ['gsm.username', user]
    if pw is not None:
        args += ['gsm.password-flags', '0', 'gsm.password', pw]
    rc, _, err = _run(args, 15)
    if rc != 0:
        return {'error': 'nmcli: ' + _err(err, (pw, user))}
    _reup(ctx)
    _kick(ctx, force=True)
    return {'out': f"APN {'set to ' + apn if apn else 'automatic'} ({ip_type}) — reconnecting"}


def cell_roaming_set(body, ctx):
    if not supported(ctx):
        return dict(UNSUPPORTED)
    allow = body.get('allow')
    if not isinstance(allow, bool):
        return {'error': 'allow must be true or false'}
    e = _need_profile()
    if e:
        return e
    rc, _, err = _run(['nmcli', 'connection', 'modify', PROFILE, 'gsm.home-only', 'no' if allow else 'yes'], 15)
    if rc != 0:
        return {'error': 'nmcli: ' + _err(err)}
    _reup(ctx)
    _kick(ctx, force=True)
    return {'out': 'data roaming ' + ('allowed' if allow else 'blocked') + ' — reconnecting'}


def cell_mode_set(body, ctx):
    if not supported(ctx):
        return dict(UNSUPPORTED)
    mode = body.get('mode')
    if not isinstance(mode, str) or len(mode) > 80:
        return {'error': 'invalid mode'}
    m = _modem()
    if not m:
        return {'error': 'no modem found (ModemManager)'}
    if mode not in (m.get('modem.generic.supported-modes') or []):
        return {'error': 'mode not supported by this modem'}
    args = mode_args(mode)
    if not args:
        return {'error': 'invalid mode'}
    rc, _, err = _run(['mmcli', '-m', 'any', *args], 30)
    if rc != 0:
        return {'error': 'mmcli: ' + _err(err)}
    _kick(ctx, force=True)
    return {'out': 'network mode set: ' + mode}


def _sim_path_and_modem():
    m = _modem()
    if not m:
        return None, None, {'error': 'no modem found (ModemManager)'}
    path = m.get('modem.generic.sim', '')
    if not SIM_PATH_RE.fullmatch(path or ''):
        return None, m, {'error': 'no SIM card'}
    return path, m, None


def _retries_msg(ctx, key='sim-pin'):
    m = _modem()
    n = parse_retries(m.get('modem.generic.unlock-retries')).get(key)
    return f' — {n} attempts left' if n is not None else ''


def cell_pin_unlock(body, ctx):
    if not supported(ctx):
        return dict(UNSUPPORTED)
    pin = body.get('pin')
    if not isinstance(pin, str) or not PIN_RE.fullmatch(pin):
        return {'error': 'PIN must be 4–8 digits'}
    path, m, e = _sim_path_and_modem()
    if e:
        return e
    req = m.get('modem.generic.unlock-required', '')
    if req != 'sim-pin':
        return {'error': 'SIM PUK required — unlock it in a phone' if req == 'sim-puk'
                else 'SIM is not waiting for a PIN' if req in ('', 'none') else f'unlock required: {req} (not supported here)'}
    rc, _, err = _run(['mmcli', '-i', path, '--pin=' + pin], 30)
    if rc != 0:
        _kick(ctx, force=True)
        return {'error': 'PIN rejected: ' + _err(err, (pin,)) + _retries_msg(ctx)}
    _kick(ctx, force=True)
    return {'out': 'SIM unlocked'}


def cell_pin_change(body, ctx):
    if not supported(ctx):
        return dict(UNSUPPORTED)
    if body.get('confirm') is not True:
        return {'error': 'confirmation required'}
    pin, new = body.get('pin'), body.get('new_pin')
    if not all(isinstance(x, str) and PIN_RE.fullmatch(x) for x in (pin, new)):
        return {'error': 'PINs must be 4–8 digits'}
    path, m, e = _sim_path_and_modem()
    if e:
        return e
    if sim_state(m) != 'ready':
        return {'error': 'unlock the SIM first'}
    if 'sim' not in (m.get('modem.3gpp.enabled-locks') or []):
        return {'error': 'turn the PIN lock on before changing the PIN'}
    rc, _, err = _run(['mmcli', '-i', path, '--pin=' + pin, '--change-pin=' + new], 30)
    if rc != 0:
        return {'error': 'PIN change failed: ' + _err(err, (pin, new)) + _retries_msg(ctx)}
    return {'out': 'SIM PIN changed'}


def cell_pin_lock(body, ctx):
    if not supported(ctx):
        return dict(UNSUPPORTED)
    if body.get('confirm') is not True:
        return {'error': 'confirmation required'}
    pin, enable = body.get('pin'), body.get('enable')
    if not isinstance(pin, str) or not PIN_RE.fullmatch(pin):
        return {'error': 'PIN must be 4–8 digits'}
    if not isinstance(enable, bool):
        return {'error': 'enable must be true or false'}
    path, m, e = _sim_path_and_modem()
    if e:
        return e
    if sim_state(m) != 'ready':
        return {'error': 'unlock the SIM first'}
    rc, _, err = _run(['mmcli', '-i', path, '--pin=' + pin, '--enable-pin' if enable else '--disable-pin'], 30)
    if rc != 0:
        return {'error': 'failed: ' + _err(err, (pin,)) + _retries_msg(ctx)}
    _kick(ctx, force=True)
    return {'out': 'SIM PIN lock ' + ('on' if enable else 'off')}


def cell_reconnect(body, ctx):
    if not supported(ctx):
        return dict(UNSUPPORTED)
    _reup(ctx)
    _kick(ctx, force=True)
    return {'out': 'reconnecting LTE…'}


def _safe(fn):
    def w(body, ctx):
        try:
            return fn(body if isinstance(body, dict) else {}, ctx)
        except Exception as e:
            return {'error': type(e).__name__}
    return w


ACTIONS = {k: _safe(v) for k, v in {
    'cell-get': cell_get,
    'cell-apn-set': cell_apn_set,
    'cell-roaming-set': cell_roaming_set,
    'cell-mode-set': cell_mode_set,
    'cell-pin-unlock': cell_pin_unlock,
    'cell-pin-change': cell_pin_change,
    'cell-pin-lock': cell_pin_lock,
    'cell-reconnect': cell_reconnect,
}.items()}
