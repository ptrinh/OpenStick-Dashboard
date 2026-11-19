"""Wi-Fi networks (client): scan, saved profiles, safe switch with auto-rollback, forget, priority.

Safety: the dashboard is usually reached over Tailscale whose uplink is this very Wi-Fi, so
* switching networks runs detached (systemd-run) through a guard script that re-activates the previous
  connection (and deletes a newly created profile) unless Internet works 60 s after the switch;
* the stick's own hotspot profiles ("uz-hotspot", "hotspot", any non-infrastructure mode) are hidden
  and can never be changed or deleted here;
* the active profile is only forgotten with force=true while another uplink (wwan0/usb0) has a default route.
Wi-Fi passwords are never logged, written to a state file or returned.
"""
import json, os, re, shlex, shutil, subprocess, threading, time

IF = 'wlan0'
PROTECTED = ('uz-hotspot', 'hotspot')
RUN = os.environ.get('UZ_WIFI_RUN', '/run')
GUARD = 'uz-wifi-guard.py'          # guard script, rewritten on every switch
JOB = 'uz-wifi-job.json'            # 0600, holds the password; the guard deletes it as soon as it is read
STATE = 'uz-wifi-guard.json'        # guard progress (never contains the password)
CHECK_AFTER = 60                    # seconds after the switch before the Internet check
WIFI_TYPE = '802-11-wireless'
UUID_RE = re.compile(r'[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}')
NO_NMCLI = {'error': 'nmcli not available on this host'}


# ---------- helpers ----------
def _p(name): return os.path.join(RUN, name)

def _run(args, t=20):
    """Run an argument list (never a shell). Returns (rc, stdout, stderr)."""
    try:
        r = subprocess.run(args, capture_output=True, text=True, timeout=t)
        return r.returncode, r.stdout, r.stderr
    except subprocess.TimeoutExpired: return 124, '', 'timed out'
    except Exception as e: return 127, '', type(e).__name__

def _have_nmcli(): return bool(shutil.which('nmcli'))

def split_terse(line):
    """Split one line of `nmcli -t` output: fields are ':'-separated, ':' and '\\' inside values are escaped."""
    out, cur, i = [], [], 0
    while i < len(line):
        c = line[i]
        if c == '\\' and i + 1 < len(line): cur.append(line[i + 1]); i += 2; continue
        if c == ':': out.append(''.join(cur)); cur = []
        else: cur.append(c)
        i += 1
    out.append(''.join(cur))
    return out

def _err(stderr, stdout=''):
    m = (stderr or stdout or '').strip().splitlines()
    return re.sub(r'^Error:\s*', '', m[-1])[:200] if m else 'nmcli failed'

def sec_kind(sec):
    s = (sec or '').strip()
    if s in ('', '--'): return 'open'
    if '802.1X' in s: return 'enterprise'
    if 'WPA' in s or 'SAE' in s: return 'wpa'
    if 'WEP' in s: return 'wep'
    if 'OWE' in s: return 'owe'
    return 'wpa'


# ---------- parsers (pure; unit-tested with captured output) ----------
def parse_scan(text):
    """`nmcli -t -f IN-USE,SSID,BSSID,CHAN,FREQ,SIGNAL,SECURITY dev wifi list` -> (networks merged by SSID, hidden count)."""
    best, hidden = {}, 0
    for line in text.splitlines():
        if not line.strip(): continue
        f = split_terse(line)
        if len(f) < 7: continue
        inuse, ssid, bssid, chan, freq, sig, sec = f[:7]
        try: sig = int(sig)
        except ValueError: sig = 0
        if ssid in ('', '--'): hidden += 1; continue
        ap = {'ssid': ssid, 'bssid': bssid.upper(), 'chan': chan, 'freq': freq, 'signal': sig,
              'security': '' if sec.strip() == '--' else sec.strip(), 'connected': inuse.strip() == '*', 'aps': 1}
        ap['kind'] = sec_kind(ap['security'])
        cur = best.get(ssid)
        if cur is None: best[ssid] = ap; continue
        conn, n = cur['connected'] or ap['connected'], cur['aps'] + 1
        if ap['signal'] > cur['signal']: best[ssid] = cur = ap
        cur['connected'], cur['aps'] = conn, n
    return list(best.values()), hidden

def parse_con_list(text):
    """`nmcli -t -f NAME,UUID,TYPE,AUTOCONNECT,AUTOCONNECT-PRIORITY,TIMESTAMP,ACTIVE,DEVICE con show` -> Wi-Fi rows."""
    rows = []
    for line in text.splitlines():
        f = split_terse(line)
        if len(f) < 8 or f[2] not in (WIFI_TYPE, 'wifi'): continue
        try: prio = int(f[4])
        except ValueError: prio = 0
        try: ts = int(f[5])
        except ValueError: ts = 0
        rows.append({'name': f[0], 'uuid': f[1], 'autoconnect': f[3] == 'yes', 'priority': prio,
                     'last': ts or None, 'active': f[6] == 'yes', 'device': '' if f[7] == '--' else f[7]})
    return rows

def parse_props(text):
    """`nmcli -e no -t -f a,b con show X` (multi-line 'name:value') -> dict; values are unescaped, split at first ':'."""
    d = {}
    for line in text.splitlines():
        if ':' in line:
            k, v = line.split(':', 1); d[k.strip()] = v
    return d


# ---------- NetworkManager queries ----------
def _props(uuid, fields):
    rc, out, _ = _run(['nmcli', '-e', 'no', '-t', '-f', ','.join(fields), 'connection', 'show', uuid], 10)
    return parse_props(out) if rc == 0 else {}

def profiles(include_protected=False):
    """All Wi-Fi profiles with ssid/mode; client profiles only unless include_protected."""
    rc, out, err = _run(['nmcli', '-t', '-f', 'NAME,UUID,TYPE,AUTOCONNECT,AUTOCONNECT-PRIORITY,TIMESTAMP,ACTIVE,DEVICE',
                         'connection', 'show'], 15)
    if rc != 0: raise RuntimeError(_err(err))
    res = []
    for r in parse_con_list(out):
        p = _props(r['uuid'], ['802-11-wireless.ssid', '802-11-wireless.mode', '802-11-wireless.hidden',
                               '802-11-wireless-security.key-mgmt'])
        r['ssid'] = p.get('802-11-wireless.ssid', '')
        r['mode'] = p.get('802-11-wireless.mode', '') or 'infrastructure'
        r['hidden'] = p.get('802-11-wireless.hidden', '') == 'yes'
        r['secured'] = p.get('802-11-wireless-security.key-mgmt', '') not in ('', '--')
        r['protected'] = r['name'] in PROTECTED or r['mode'] != 'infrastructure'
        if include_protected or not r['protected']: res.append(r)
    return res

def wlan_active():
    """The connection currently active on wlan0: {'uuid','name','mode'} or None."""
    rc, out, _ = _run(['nmcli', '-t', '-f', 'UUID,NAME,TYPE,DEVICE', 'connection', 'show', '--active'], 10)
    for line in out.splitlines() if rc == 0 else []:
        f = split_terse(line)
        if len(f) >= 4 and f[3] == IF and f[2] in (WIFI_TYPE, 'wifi'):
            mode = _props(f[0], ['802-11-wireless.mode']).get('802-11-wireless.mode', '') or 'infrastructure'
            return {'uuid': f[0], 'name': f[1], 'mode': mode}
    return None

def other_uplink():
    """Device name of a non-Wi-Fi default route (wwan0 / usb0), or ''."""
    rc, out, _ = _run(['ip', '-4', 'route', 'show', 'default'], 5)
    for line in out.splitlines() if rc == 0 else []:
        m = re.search(r'\bdev (\S+)', line)
        if m and m[1] in ('wwan0', 'usb0'): return m[1]
    return ''

def hotspot_reason(ctx):
    """Non-empty error string while wlan0 is acting as a hotspot (Travel mode)."""
    a = wlan_active()
    if a and (a['mode'] != 'infrastructure' or a['name'] in PROTECTED):
        return 'wlan0 is running the hotspot (Travel mode) — switch to Home mode first; scanning or joining would drop it'
    return ''

def find_profile(name, include_protected=True):
    for p in profiles(include_protected=include_protected):
        if name in (p['name'], p['uuid']): return p
    return None

def guard_busy():
    try: st = json.load(open(_p(STATE)))
    except Exception: return False
    return st.get('state') in ('connecting', 'checking') and time.time() - st.get('t', 0) < CHECK_AFTER + 120


# ---------- validation ----------
CTRL = re.compile(r'[\x00-\x1f\x7f-\x9f]')

def valid_ssid(s):
    return isinstance(s, str) and 1 <= len(s.encode('utf-8')) <= 32 and not CTRL.search(s)

def valid_psk(pw):
    if not isinstance(pw, str): return False
    if re.fullmatch(r'[0-9A-Fa-f]{64}', pw): return True
    return 8 <= len(pw) <= 63 and all(0x20 <= ord(c) <= 0x7e for c in pw)

def valid_name(s):
    return isinstance(s, str) and 1 <= len(s) <= 255 and not CTRL.search(s)


# ---------- guard (shipped inside the module, run detached) ----------
GUARD_SRC = r'''#!/usr/bin/env python3
# uz-wifi-guard (written by the dashboard's wifi module): switch wlan0 to another Wi-Fi network,
# then roll back unless Internet works CHECK_AFTER seconds later. Never prints the password.
import json, os, subprocess, sys, time
job_path = sys.argv[1]
state_path = os.path.join(os.path.dirname(job_path), 'uz-wifi-guard.json')
try:
    job = json.load(open(job_path))
finally:
    try: os.unlink(job_path)
    except OSError: pass
pw = job.pop('password', '') or ''

def run(args, t=60):
    try:
        r = subprocess.run(args, capture_output=True, text=True, timeout=t)
        return r.returncode, r.stdout, r.stderr
    except Exception as e:
        return 1, '', type(e).__name__

def clean(s):
    s = (s or '').strip().splitlines()
    s = s[-1] if s else ''
    return (s.replace(pw, '***') if pw else s)[:200]

def state(st, msg=''):
    tmp = state_path + '.tmp'
    with open(tmp, 'w') as f:
        json.dump({'state': st, 'ssid': job['ssid'], 'msg': msg, 't': time.time()}, f)
    os.replace(tmp, state_path)

def wifi_uuids():
    rc, out, _ = run(['nmcli', '-t', '-f', 'UUID,TYPE', 'connection', 'show'], 15)
    return [l.split(':', 1)[0] for l in out.splitlines() if l.endswith(':802-11-wireless')]

def rollback(why):
    removed = 0
    for u in wifi_uuids():
        if u in job['before']: continue
        rc, ssid, _ = run(['nmcli', '-e', 'no', '-g', '802-11-wireless.ssid', 'connection', 'show', u], 10)
        if ssid.strip() == job['ssid']:
            run(['nmcli', 'connection', 'delete', 'uuid', u], 20); removed += 1
    if job.get('prev'):
        rc, out, err = run(['nmcli', '-w', '60', 'connection', 'up', 'uuid', job['prev']], 75)
        back = 'restored previous network' if rc == 0 else 'could not restore previous network: ' + clean(err)
    else:
        back = 'no previous network to restore'
    state('rolled-back', why + '; ' + back + ('; removed new profile' if removed else ''))

state('connecting')
if job.get('use_uuid'):
    cmd = ['nmcli', '-w', '45', 'connection', 'up', 'uuid', job['use_uuid']]
else:
    cmd = ['nmcli', '-w', '45', 'device', 'wifi', 'connect', job['ssid']]
    if pw: cmd += ['password', pw]
    cmd += ['ifname', job['ifname']]
    if job.get('hidden'): cmd += ['hidden', 'yes']
rc, out, err = run(cmd, 60)
if rc != 0:
    rollback('connect failed: ' + clean(err or out))
    sys.exit(0)
state('checking')
time.sleep(job.get('check_after', 60))
if run(['ping', '-I', 'wlan0', '-c', '3', '-W', '3', '1.1.1.1'], 20)[0] == 0:
    state('ok', 'connected; Internet works')
else:
    rollback('no Internet after switch')
'''

def build_job(ssid, password, hidden, prev, before, use_uuid=None):
    return {'ssid': ssid, 'password': password or '', 'hidden': bool(hidden), 'ifname': IF,
            'prev': prev, 'before': before, 'use_uuid': use_uuid, 'check_after': CHECK_AFTER}

def guard_cmd():
    return f'exec python3 {shlex.quote(_p(GUARD))} {shlex.quote(_p(JOB))}'

def _write(path, text, mode=0o600):
    fd = os.open(path + '.tmp', os.O_WRONLY | os.O_CREAT | os.O_TRUNC, mode)
    with os.fdopen(fd, 'w') as f: f.write(text)
    os.replace(path + '.tmp', path)


# ---------- actions ----------
def _guarded(fn):
    def w(body, ctx):
        if not isinstance(body, dict): return {'error': 'bad request'}
        if not _have_nmcli(): return dict(NO_NMCLI)
        try: return fn(body, ctx)
        except Exception as e: return {'error': (str(e) or type(e).__name__)[:200]}
    return w

@_guarded
def a_scan(body, ctx):
    why = hotspot_reason(ctx)
    if why: return {'error': why}
    base = ['nmcli', '-t', '-f', 'IN-USE,SSID,BSSID,CHAN,FREQ,SIGNAL,SECURITY', 'dev', 'wifi', 'list']
    rc, out, err = _run(base + ['--rescan', 'yes'], 25)
    cached = False
    if rc != 0:   # e.g. "Scanning not allowed immediately following previous scan" — use NM's cached list
        rc, out, err2 = _run(base + ['--rescan', 'no'], 10); cached = True
        if rc != 0: return {'error': 'scan failed: ' + _err(err or err2)}
    nets, hidden = parse_scan(out)
    saved = {p['ssid']: p['name'] for p in profiles()}
    for n in nets:
        n['saved'] = n['ssid'] in saved; n['profile'] = saved.get(n['ssid'], '')
    nets.sort(key=lambda n: (not n['connected'], not n['saved'], -n['signal'], n['ssid'].lower()))
    ctx.cache['wifi_scan'] = {'t': time.time(), 'nets': {n['ssid']: n['kind'] for n in nets}}
    return {'out': f'{len(nets)} networks' + (' (cached list)' if cached else ''), 'networks': nets, 'hidden': hidden,
            'cached': cached}

@_guarded
def a_saved(body, ctx):
    ps = profiles()
    _COUNT.update(n=len(ps), t=time.time())
    keys = ('name', 'uuid', 'ssid', 'autoconnect', 'priority', 'last', 'active', 'hidden', 'secured')
    ps.sort(key=lambda p: (not p['active'], -p['priority'], p['name'].lower()))
    return {'out': f'{len(ps)} saved networks', 'saved': [{k: p[k] for k in keys} for p in ps]}

@_guarded
def a_connect(body, ctx):
    ssid, pw, hidden = body.get('ssid'), body.get('password') or '', body.get('hidden', False)
    if not valid_ssid(ssid): return {'error': 'SSID must be 1–32 bytes without control characters'}
    if pw and not valid_psk(pw): return {'error': 'password must be 8–63 printable ASCII characters or 64 hex digits'}
    if not isinstance(hidden, bool): return {'error': 'hidden must be true or false'}
    why = hotspot_reason(ctx)
    if why: return {'error': why}
    if guard_busy(): return {'error': 'a network switch is already in progress — wait a minute'}
    kind = ((ctx.cache.get('wifi_scan') or {}).get('nets') or {}).get(ssid)
    if kind == 'enterprise': return {'error': 'WPA-Enterprise (802.1X) networks are not supported here'}
    allp = profiles(include_protected=True)
    if any(p['protected'] and p['ssid'] == ssid for p in allp) and not any(not p['protected'] and p['ssid'] == ssid for p in allp):
        return {'error': "that SSID belongs to the stick's own hotspot"}
    client = [p for p in allp if not p['protected']]
    existing = next((p for p in client if p['ssid'] == ssid), None)
    active = wlan_active()
    if existing and active and active['uuid'] == existing['uuid'] and not pw:
        return {'out': f'already connected to {ssid}'}
    if not existing and not pw and kind in ('wpa', 'wep'): return {'error': 'this network needs a password'}
    use_uuid = existing['uuid'] if existing and not pw and not hidden else None
    job = build_job(ssid, pw, hidden, active['uuid'] if active else None, [p['uuid'] for p in allp], use_uuid)
    for f in (JOB, STATE):
        try: os.unlink(_p(f))
        except OSError: pass
    _write(_p(GUARD), GUARD_SRC, 0o700)
    ctx.write_secret(_p(JOB), json.dumps(job))
    ctx.run_bg(guard_cmd())
    _COUNT['t'] = 0
    return {'out': f'switching to {ssid} — the dashboard may disconnect for up to a minute; '
                   f'if there is no Internet after {CHECK_AFTER} s the previous network comes back automatically',
            'ssid': ssid, 'previous': active['name'] if active else ''}

@_guarded
def a_forget(body, ctx):
    name, force = body.get('name'), body.get('force', False)
    if not valid_name(name): return {'error': 'bad profile name'}
    if not isinstance(force, bool): return {'error': 'force must be true or false'}
    p = find_profile(name)
    if not p: return {'error': 'no such saved network'}
    if p['protected']: return {'error': "the stick's hotspot profile can't be removed here"}
    if not UUID_RE.fullmatch(p['uuid']): return {'error': 'unexpected profile id'}
    if p['active']:
        if not force: return {'error': 'this is the network in use — forgetting it disconnects Wi-Fi (resend with force)'}
        up = other_uplink()
        if not up: return {'error': 'refused: no other uplink (4G/USB) — forgetting the network in use would cut remote access'}
        ctx.run_bg(f'sleep 1; nmcli connection delete uuid {p["uuid"]}')   # uuid validated above
        _COUNT['t'] = 0
        return {'out': f'forgetting {p["name"]} — the dashboard continues over {up}'}
    rc, out, err = _run(['nmcli', 'connection', 'delete', 'uuid', p['uuid']], 20)
    _COUNT['t'] = 0
    return {'out': f'forgot {p["name"]}'} if rc == 0 else {'error': 'delete failed: ' + _err(err, out)}

@_guarded
def a_priority(body, ctx):
    name, prio, auto, force = body.get('name'), body.get('priority'), body.get('autoconnect'), body.get('force', False)
    if not valid_name(name): return {'error': 'bad profile name'}
    if isinstance(prio, bool) or not isinstance(prio, int) or not -999 <= prio <= 999:
        return {'error': 'priority must be an integer from -999 to 999'}
    if not isinstance(auto, bool): return {'error': 'autoconnect must be true or false'}
    if not isinstance(force, bool): return {'error': 'force must be true or false'}
    ps = profiles()
    p = next((x for x in ps if name in (x['name'], x['uuid'])), None)
    if not p:
        return {'error': "the stick's hotspot profile can't be changed here" if find_profile(name) else 'no such saved network'}
    if not auto and p['active'] and not force and not any(x['autoconnect'] for x in ps if x['uuid'] != p['uuid']) \
            and not other_uplink():
        return {'error': 'refused: this is the only auto-connecting network and there is no 4G/USB uplink — '
                         'after a reboot the stick would be unreachable (resend with force)'}
    rc, out, err = _run(['nmcli', 'connection', 'modify', 'uuid', p['uuid'], 'connection.autoconnect-priority', str(prio),
                         'connection.autoconnect', 'yes' if auto else 'no'], 15)
    return {'out': f'{p["name"]}: priority {prio}, auto-connect {"on" if auto else "off"}'} if rc == 0 \
        else {'error': 'update failed: ' + _err(err, out)}

ACTIONS = {'wifi-scan': a_scan, 'wifi-saved': a_saved, 'wifi-connect': a_connect,
           'wifi-forget': a_forget, 'wifi-priority': a_priority}


# ---------- status (cheap) ----------
_COUNT = {'n': None, 't': 0, 'busy': False}

def _refresh_count():
    try: _COUNT['n'] = len(profiles())
    except Exception: pass
    finally: _COUNT.update(t=time.time(), busy=False)

def init(ctx):
    try: os.unlink(_p(JOB))   # a job file left behind by a guard that never started
    except OSError: pass

def status(ctx):
    n = ctx.cache.get('net') or {}
    mode = 'hotspot' if n.get('wifi_mode') == 'ap' else 'client' if n.get('ssid') else 'off'
    s = {'ssid': n.get('ssid', ''), 'mode': mode, 'signal': n.get('wifi_signal', ''), 'saved': _COUNT['n'],
         'available': _have_nmcli()}
    if s['available'] and not _COUNT['busy'] and time.time() - _COUNT['t'] > 60:
        _COUNT['busy'] = True
        threading.Thread(target=_refresh_count, daemon=True).start()
    try:
        st = json.load(open(_p(STATE)))
        if time.time() - st.get('t', 0) < 600:
            s['switch'] = {k: st.get(k) for k in ('state', 'ssid', 'msg', 't')}
    except Exception: pass
    return s
