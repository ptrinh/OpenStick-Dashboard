"""System settings: hostname, time zone, Debian release pin, package updates, scheduled restart.

Actions (prefix sys-): sys-get, sys-hostname-set, sys-timezones, sys-timezone-set, sys-apt-pin,
sys-apt-check, sys-apt-upgrade, sys-apt-status, sys-reboot-schedule.

Long apt work runs in its own transient systemd unit (uz-apt-check / uz-apt-upgrade) so it is outside
uz-web's MemoryMax and survives a dashboard restart. The unit runs this same file as a script
(`python3 -I system.py --apt-check|--apt-upgrade`), which writes JSON state files that status() reads.

All absolute paths go through P() so tests can point them at a fixture tree with UZ_ROOT=<dir>.
"""
import json, os, re, shutil, subprocess, sys, time

ROOT = os.environ.get('UZ_ROOT', '')          # test prefix for every filesystem path
SELF = os.path.abspath(__file__)


def P(path):
    return ROOT + path


CHECK_JSON = '/var/lib/uz/apt-check.json'
UPGRADE_JSON = '/var/lib/uz/apt-upgrade.json'
CHECK_LOG = '/var/log/uz-apt-check.log'
UPGRADE_LOG = '/var/log/uz-apt-upgrade.log'
TIMER = '/etc/systemd/system/uz-reboot.timer'
SERVICE = '/etc/systemd/system/uz-reboot.service'
TIMER_WANTS = '/etc/systemd/system/timers.target.wants/uz-reboot.timer'
MIN_DISK_MB = 150
MIN_MEM_MB = 120          # MemAvailable + SwapFree needed for apt-get upgrade
SUITE = 'trixie'
DAYS = ['mon', 'tue', 'wed', 'thu', 'fri', 'sat', 'sun']

HOST_RE = re.compile(r'[a-z0-9]([a-z0-9-]{0,61}[a-z0-9])?')
TZ_RE = re.compile(r'[A-Za-z_]+(/[A-Za-z0-9_+-]+)*')
TIME_RE = re.compile(r'([01][0-9]|2[0-3]):([0-5][0-9])')


# ---------- small helpers (monkeypatched in tests) ----------
def _run(args, t=30, env=None):
    """subprocess with an argument list; returns (rc, stdout, stderr). Never raises."""
    try:
        r = subprocess.run(args, capture_output=True, text=True, timeout=t, env=env)
        return r.returncode, r.stdout, r.stderr
    except FileNotFoundError:
        return 127, '', f'{args[0]}: not found'
    except subprocess.TimeoutExpired:
        return 124, '', f'{args[0]}: timed out'
    except Exception as e:
        return 1, '', f'{type(e).__name__}: {e}'


def _which(cmd):
    return shutil.which(cmd)


def _rd(path, default=''):
    try:
        with open(P(path)) as f: return f.read()
    except (OSError, UnicodeDecodeError):
        return default


def _json(path):
    try:
        with open(P(path)) as f: return json.load(f)
    except Exception:
        return {}


def _write_atomic(path, text, mode=None):
    """Write P(path) atomically, keeping the original file mode."""
    real = P(path)
    if mode is None:
        try: mode = os.stat(real).st_mode & 0o7777
        except OSError: mode = 0o644
    tmp = real + '.uz-tmp'
    with open(tmp, 'w') as f: f.write(text)
    os.chmod(tmp, mode)
    os.replace(tmp, real)


def _write_json(path, data):
    os.makedirs(os.path.dirname(P(path)), exist_ok=True)
    _write_atomic(path, json.dumps(data), 0o644)


def _tail(path, n=40):
    txt = _rd(path)
    return '\n'.join(txt.splitlines()[-n:])[-6000:]


def _boot_id():
    return _rd('/proc/sys/kernel/random/boot_id').strip()


def _pkg_mgr():
    if _which('apt-get'): return 'apt'
    if _which('apk'): return 'apk'
    return None


def err(msg):
    return {'error': msg}


# ---------- validators ----------
def valid_hostname(h):
    return isinstance(h, str) and len(h) <= 63 and bool(HOST_RE.fullmatch(h))


def valid_tz_syntax(tz):
    return isinstance(tz, str) and 0 < len(tz) <= 64 and bool(TZ_RE.fullmatch(tz)) and '..' not in tz


def valid_time(s):
    return isinstance(s, str) and bool(TIME_RE.fullmatch(s))


def norm_days(days):
    """list of day keys -> ordered unique list, or None if anything is invalid."""
    if not isinstance(days, list) or len(days) > 7: return None
    if not all(isinstance(d, str) and d in DAYS for d in days): return None
    return [d for d in DAYS if d in days]


def on_calendar(time_s, days):
    """'04:30', ['mon','thu'] -> 'Mon,Thu *-*-* 04:30:00'; all days -> '*-*-* 04:30:00'."""
    hh, mm = time_s.split(':')
    when = f'*-*-* {hh}:{mm}:00'
    if len(days) == 7: return when
    return ','.join(d.capitalize() for d in days) + ' ' + when


# ---------- apt sources ----------
DEB_HOST_RE = re.compile(r'^[a-z][a-z0-9+.-]*://(?:[^/@]*@)?(deb|security)\.debian\.org(?::\d+)?(/|$)', re.I)
SUITE_MAP = {'stable': 'trixie', 'stable-security': 'trixie-security', 'stable-updates': 'trixie-updates',
             'stable-backports': 'trixie-backports', 'stable-proposed-updates': 'trixie-proposed-updates'}
ONELINE_RE = re.compile(r'^(\s*deb(?:-src)?\s+(?:\[[^\]]*\]\s+)?)(\S+)(\s+)(\S+)(.*)$')


def source_files():
    out = []
    if os.path.isfile(P('/etc/apt/sources.list')): out.append('/etc/apt/sources.list')
    d = P('/etc/apt/sources.list.d')
    if os.path.isdir(d):
        for f in sorted(os.listdir(d)):
            if re.fullmatch(r'[A-Za-z0-9_.-]+\.(list|sources)', f) and os.path.isfile(os.path.join(d, f)):
                out.append('/etc/apt/sources.list.d/' + f)
    return out


def _is_debian_uri(uri):
    return bool(DEB_HOST_RE.match(uri))


def rewrite_oneline(text):
    """returns (new_text, suites_seen[list], changes[list of 'old -> new'])"""
    lines, seen, changes = [], [], []
    for line in text.splitlines(keepends=True):
        body = line.rstrip('\r\n'); nl = line[len(body):]
        m = ONELINE_RE.match(body)
        if m and _is_debian_uri(m[2]):
            suite = m[4]; seen.append(suite)
            new = SUITE_MAP.get(suite)
            if new:
                body = m[1] + m[2] + m[3] + new + m[5]; changes.append(f'{suite} -> {new}')
        lines.append(body + nl)
    return ''.join(lines), seen, changes


def rewrite_deb822(text):
    """deb822 .sources: rewrite Suites: in stanzas whose URIs are Debian. Same return shape as rewrite_oneline."""
    seen, changes = [], []
    lines = text.splitlines(keepends=True)
    # split into stanzas (index ranges) on blank lines
    stanzas, cur = [], []
    for i, l in enumerate(lines):
        if l.strip() == '':
            if cur: stanzas.append(cur); cur = []
        else:
            cur.append(i)
    if cur: stanzas.append(cur)
    for st in stanzas:
        fields, last = {}, None          # field name (lower) -> list of line indexes (first + continuations)
        for i in st:
            l = lines[i]
            if l.lstrip().startswith('#'): last = None; continue
            if l[:1] in (' ', '\t') and last: fields[last].append(i); continue
            m = re.match(r'([A-Za-z0-9-]+)\s*:', l)
            if m: last = m[1].lower(); fields[last] = [i]
            else: last = None
        if 'enabled' in fields and re.search(r':\s*no\b', lines[fields['enabled'][0]], re.I): continue
        if 'uris' not in fields or 'suites' not in fields: continue
        uri_txt = ' '.join(lines[i] for i in fields['uris']).split(':', 1)[1]
        if not any(_is_debian_uri(u) for u in uri_txt.split()): continue
        for i in fields['suites']:
            l = lines[i]; body = l.rstrip('\r\n'); nl = l[len(body):]
            if i == fields['suites'][0]:
                k, v = body.split(':', 1); prefix = k + ':'
            else:
                prefix, v = '', body
            toks = re.split(r'(\s+)', v)
            for j, tok in enumerate(toks):
                if tok and not tok.isspace():
                    seen.append(tok)
                    if tok in SUITE_MAP:
                        changes.append(f'{tok} -> {SUITE_MAP[tok]}'); toks[j] = SUITE_MAP[tok]
            lines[i] = prefix + ''.join(toks) + nl
    return ''.join(lines), seen, changes


def _rewrite(path, text):
    return rewrite_deb822(text) if path.endswith('.sources') else rewrite_oneline(text)


def pin_state():
    """{'pinned': bool, 'suites': [...], 'files': n}. pinned = Debian sources exist and none use a
    moving alias (stable/testing/unstable/sid…); every Debian suite starts with 'trixie'."""
    suites = []
    for f in source_files():
        _, seen, _ = _rewrite(f, _rd(f))
        suites += seen
    uniq = sorted(set(suites))
    pinned = bool(uniq) and all(s == SUITE or s.startswith(SUITE + '-') for s in uniq)
    return {'pinned': pinned, 'suites': uniq, 'debian_sources': bool(uniq)}


def apt_pin(body, ctx=None):
    if body.get('suite', SUITE) != SUITE: return err("only suite 'trixie' is supported")
    if _pkg_mgr() != 'apt': return err('apt is not available on this host')
    files = source_files()
    if not files: return err('no apt sources found')
    changed, all_changes, seen_any = [], [], False
    try:
        for f in files:
            old = _rd(f)
            new, seen, changes = _rewrite(f, old)
            seen_any = seen_any or bool(seen)
            if not changes: continue
            shutil.copy2(P(f), P(f) + '.bak')
            _write_atomic(f, new)
            changed.append(f); all_changes += [f'{os.path.basename(f)}: {c}' for c in changes]
    except OSError as e:
        return err(f'could not rewrite sources: {e.strerror or e}')
    if not seen_any: return err('no deb.debian.org / security.debian.org sources found')
    st = pin_state()
    if not changed:
        return {'out': 'already pinned to trixie' if st['pinned'] else 'nothing to change', 'changed': [], 'pin': st}
    return {'out': f"pinned to trixie ({len(all_changes)} change{'s' if len(all_changes) != 1 else ''}; .bak kept) — run Check for updates",
            'changed': changed, 'changes': all_changes, 'pin': st}


# ---------- background apt jobs ----------
def _job_state(path):
    """state file -> dict with 'state' normalised: a 'running' state from a previous boot is 'interrupted'."""
    st = _json(path)
    if st.get('state') == 'running' and st.get('boot_id') and st.get('boot_id') != _boot_id():
        st['state'] = 'interrupted'
    return st


def _running():
    return _job_state(CHECK_JSON).get('state') == 'running' or _job_state(UPGRADE_JSON).get('state') == 'running'


def _start_unit(unit, mode):
    """systemd-run a transient unit running this file in worker mode. Returns error string or None."""
    if not _which('systemd-run'): return 'systemd-run is not available on this host'
    py = sys.executable if os.path.basename(sys.executable or '').startswith('python3') else '/usr/bin/python3'
    rc, _, e = _run(['systemd-run', f'--unit={unit}', '--collect', '--quiet', '--property=Nice=10',
                     '--property=IOSchedulingClass=idle', py, '-I', SELF, mode], 15)
    if rc != 0: return (e.strip().splitlines() or ['systemd-run failed'])[-1][:200]
    return None


def _reconcile(path, unit):
    """status says running but the unit is gone (killed, OOM) -> mark failed. Not used by status()."""
    st = _job_state(path)
    if st.get('state') == 'running' and _which('systemctl'):
        rc, out, _ = _run(['systemctl', 'is-active', unit], 5)
        if out.strip() not in ('active', 'activating'):
            # the worker may have just finished: re-read before declaring it dead
            st = _job_state(path)
            if st.get('state') == 'running':
                st.update(state='failed', error='job stopped unexpectedly', finished=int(time.time()))
                try: _write_json(path, st)
                except OSError: pass
    return st


def mem_free_mb():
    m = {}
    for l in _rd('/proc/meminfo').splitlines():
        k, _, v = l.partition(':')
        try: m[k] = int(v.split()[0])
        except (ValueError, IndexError): pass
    return (m.get('MemAvailable', 0) + m.get('SwapFree', 0)) // 1024


def disk_free_mb(path='/'):
    try:
        s = os.statvfs(P(path) or '/')
        return s.f_bavail * s.f_frsize // 1048576
    except OSError:
        return 0


def apt_check(body, ctx=None):
    pm = _pkg_mgr()
    if pm == 'apk': return err('update check is not supported on postmarketOS (apk) yet — use apk over SSH')
    if pm != 'apt': return err('apt is not available on this host')
    if _running(): return err('an apt job is already running')
    e = _start_unit('uz-apt-check', '--apt-check')
    if e: return err(e)
    return {'out': 'checking for updates…'}


def apt_upgrade(body, ctx=None):
    if body.get('confirm') is not True: return err('confirmation required')
    pm = _pkg_mgr()
    if pm == 'apk': return err('installing updates is not supported on postmarketOS (apk) yet — use apk upgrade over SSH')
    if pm != 'apt': return err('apt is not available on this host')
    pin = pin_state()
    if not pin['pinned']:
        return err("refused: apt sources are not pinned to 'trixie' — with 'stable' an upgrade could pull the next "
                   "Debian release onto this custom kernel. Pin to trixie first.")
    if _running(): return err('an apt job is already running')
    disk = disk_free_mb('/')
    if disk < MIN_DISK_MB: return err(f'refused: only {disk} MB free on / (need {MIN_DISK_MB} MB)')
    mem = mem_free_mb()
    if mem < MIN_MEM_MB: return err(f'refused: only {mem} MB RAM+swap available (need {MIN_MEM_MB} MB) — free some memory first')
    e = _start_unit('uz-apt-upgrade', '--apt-upgrade')
    if e: return err(e)
    return {'out': 'installing updates in the background…'}


def apt_status(body=None, ctx=None):
    chk = _reconcile(CHECK_JSON, 'uz-apt-check')
    up = _reconcile(UPGRADE_JSON, 'uz-apt-upgrade')
    running = 'upgrade' if up.get('state') == 'running' else 'check' if chk.get('state') == 'running' else None
    return {'check': {k: chk.get(k) for k in ('state', 'count', 'packages', 'held', 'checked', 'error')},
            'upgrade': {k: up.get(k) for k in ('state', 'rc', 'started', 'finished', 'error')},
            'running': running,
            'log': _tail(UPGRADE_LOG if running != 'check' else CHECK_LOG, 40)}


def parse_simulate(out):
    """`apt-get -s upgrade` output -> (packages, held_back_count)"""
    pkgs = [m[1] for m in re.finditer(r'^Inst (\S+)', out, re.M)]
    m = re.search(r'(\d+) not upgraded', out)
    return pkgs, int(m[1]) if m else 0


def _apt_env():
    env = dict(os.environ, DEBIAN_FRONTEND='noninteractive', LC_ALL='C.UTF-8', LANG='C.UTF-8')
    env['PATH'] = env.get('PATH') or '/usr/sbin:/usr/bin:/sbin:/bin'
    return env


def _simulate():
    rc, out, e = _run(['apt-get', '-s', '-o', 'Debug::NoLocking=1', 'upgrade'], 300, _apt_env())
    if rc != 0: return None, None, (e.strip().splitlines() or ['apt-get -s failed'])[-1][:200]
    pkgs, held = parse_simulate(out)
    return pkgs, held, None


def worker_check():
    prev = _json(CHECK_JSON)
    st = {'state': 'running', 'started': int(time.time()), 'boot_id': _boot_id(),
          'count': prev.get('count'), 'packages': prev.get('packages'), 'checked': prev.get('checked')}
    _write_json(CHECK_JSON, st)
    try:
        with open(P(CHECK_LOG), 'w') as log:
            r = subprocess.run(['apt-get', '-q', 'update'], stdout=log, stderr=subprocess.STDOUT, env=_apt_env(), timeout=1200)
        if r.returncode != 0:
            st.update(state='failed', error='apt-get update failed (see log)')
        else:
            pkgs, held, e = _simulate()
            if e: st.update(state='failed', error=e)
            else: st.update(state='done', count=len(pkgs), packages=pkgs[:200], held=held, checked=int(time.time()), error=None)
    except Exception as e:
        st.update(state='failed', error=f'{type(e).__name__}: {e}'[:200])
    st['finished'] = int(time.time())
    _write_json(CHECK_JSON, st)
    return 0 if st['state'] == 'done' else 1


def worker_upgrade():
    st = {'state': 'running', 'started': int(time.time()), 'boot_id': _boot_id()}
    _write_json(UPGRADE_JSON, st)
    rc = 1
    try:
        with open(P(UPGRADE_LOG), 'w') as log:
            def say(msg): log.write(f'== {time.strftime("%Y-%m-%d %H:%M:%S")} {msg}\n'); log.flush()
            if not pin_state()['pinned']:          # re-check: sources may have changed since the request
                say('refused: sources are not pinned to trixie'); raise RuntimeError('sources not pinned to trixie')
            say('apt-get update')
            r = subprocess.run(['apt-get', '-q', 'update'], stdout=log, stderr=subprocess.STDOUT, env=_apt_env(), timeout=1200)
            if r.returncode != 0: raise RuntimeError('apt-get update failed')
            say('apt-get upgrade')
            r = subprocess.run(['apt-get', '-y', '-o', 'Dpkg::Options::=--force-confold', 'upgrade'],
                               stdout=log, stderr=subprocess.STDOUT, env=_apt_env(), timeout=6 * 3600)
            rc = r.returncode
            say(f'finished with exit code {rc}')
        if rc != 0: st.update(state='failed', rc=rc, error=f'apt-get upgrade exited {rc} (see log)')
        else: st.update(state='done', rc=0, error=None)
    except Exception as e:
        st.update(state='failed', rc=rc, error=str(e)[:200] or type(e).__name__)
    st['finished'] = int(time.time())
    _write_json(UPGRADE_JSON, st)
    # refresh the pending count without another apt-get update
    pkgs, held, e = _simulate()
    if not e:
        chk = _json(CHECK_JSON)
        chk.update(state='done', count=len(pkgs), packages=pkgs[:200], held=held, checked=int(time.time()), error=None)
        _write_json(CHECK_JSON, chk)
    return 0 if st['state'] == 'done' else 1


# ---------- hostname ----------
def get_hostname():
    h = _rd('/etc/hostname').strip()
    if h: return h
    try: return os.uname().nodename
    except Exception: return ''


def update_hosts(text, name):
    """set/insert the '127.0.1.1 <name>' line of /etc/hosts."""
    lines, done = text.splitlines(), False
    for i, l in enumerate(lines):
        if re.match(r'\s*127\.0\.1\.1\s', l):
            if not done: lines[i] = f'127.0.1.1\t{name}'; done = True
            else: lines[i] = '# ' + l
    if not done:
        idx = next((i + 1 for i, l in enumerate(lines) if re.match(r'\s*127\.0\.0\.1\s', l)), 0)
        lines.insert(idx, f'127.0.1.1\t{name}')
    return '\n'.join(lines) + '\n'


def hostname_set(body, ctx=None):
    h = body.get('hostname')
    if not isinstance(h, str): return err('hostname required')
    h = h.strip().lower()
    if not valid_hostname(h):
        return err('invalid hostname: 1–63 of a-z, 0-9 and -, not starting or ending with -')
    if not _which('hostnamectl'): return err('hostnamectl is not available on this host')
    old = get_hostname()
    # Pin the Tailscale node name first: otherwise tailscaled follows the OS hostname and the
    # MagicDNS name / HTTPS URL (and the passkeys bound to it) would change.
    if _which('tailscale'):
        rc, out, _ = _run(['tailscale', 'status', '--json'], 10)
        try: ts = (json.loads(out).get('Self') or {}).get('DNSName', '').split('.')[0] if rc == 0 else ''
        except ValueError: ts = ''
        if ts and valid_hostname(ts):
            rc, _, e = _run(['tailscale', 'set', f'--hostname={ts}'], 15)
            if rc != 0: return err('could not pin the Tailscale name, hostname left unchanged: ' + (e.strip().splitlines() or ['?'])[-1][:160])
    rc, _, e = _run(['hostnamectl', 'set-hostname', h], 15)
    if rc != 0: return err('hostnamectl failed: ' + (e.strip().splitlines() or ['?'])[-1][:160])
    try:
        _write_atomic('/etc/hosts', update_hosts(_rd('/etc/hosts'), h))
    except OSError as x:
        return err(f'hostname set, but /etc/hosts update failed: {x.strerror or x}')
    return {'out': f'hostname {old or "?"} -> {h} (Tailscale name unchanged)', 'hostname': h}


# ---------- time zone ----------
_TZ_CACHE = {'t': 0, 'list': []}


def timezones():
    if _TZ_CACHE['list'] and time.time() - _TZ_CACHE['t'] < 3600: return _TZ_CACHE['list']
    zones = []
    if _which('timedatectl'):
        rc, out, _ = _run(['timedatectl', 'list-timezones', '--no-pager'], 10)
        if rc == 0: zones = [z for z in out.split() if valid_tz_syntax(z)]
    if not zones:
        zones = zoneinfo_zones()
    if 'UTC' not in zones and zones: zones.append('UTC')
    _TZ_CACHE.update(t=time.time(), list=sorted(zones))
    return _TZ_CACHE['list']


def zoneinfo_zones():
    """fallback list from /usr/share/zoneinfo (tzdata.zi index, else a walk for TZif files)."""
    base = P('/usr/share/zoneinfo')
    if not os.path.isdir(base): return []
    tab = _rd('/usr/share/zoneinfo/tzdata.zi')
    if tab:
        names = set(re.findall(r'^Z (\S+)', tab, re.M)) | set(re.findall(r'^L \S+ (\S+)', tab, re.M))
    else:
        names = set()
        for d, dirs, files in os.walk(base):
            if d == base: dirs[:] = [x for x in dirs if x not in ('posix', 'right')]
            for f in files:
                full = os.path.join(d, f)
                try:
                    with open(full, 'rb') as fh:
                        if fh.read(4) != b'TZif': continue
                except OSError:
                    continue
                names.add(os.path.relpath(full, base))
    return sorted(z for z in names if valid_tz_syntax(z) and os.path.isfile(os.path.join(base, z)))


def tz_known(tz):
    if not valid_tz_syntax(tz): return False
    zones = timezones()
    if zones: return tz in zones
    f = os.path.join(P('/usr/share/zoneinfo'), tz)
    return os.path.isfile(f) and os.path.realpath(f).startswith(os.path.realpath(P('/usr/share/zoneinfo')) + os.sep)


def get_tz_cheap():
    tz = _rd('/etc/timezone').strip()
    if valid_tz_syntax(tz): return tz
    try:
        link = os.readlink(P('/etc/localtime'))
        m = re.search(r'zoneinfo/(.+)$', link)
        if m and valid_tz_syntax(m[1]): return m[1]
    except OSError:
        pass
    return None


def tz_list(body=None, ctx=None):
    zones = timezones()
    if not zones: return err('time zone list is not available on this host')
    return {'zones': zones}


def tz_set(body, ctx=None):
    tz = body.get('tz')
    if not isinstance(tz, str) or not valid_tz_syntax(tz.strip()): return err('invalid time zone')
    tz = tz.strip()
    if not _which('timedatectl'): return err('timedatectl is not available on this host')
    if not tz_known(tz): return err(f'unknown time zone: {tz}')
    rc, _, e = _run(['timedatectl', 'set-timezone', tz], 15)
    if rc != 0: return err('timedatectl failed: ' + (e.strip().splitlines() or ['?'])[-1][:160])
    return {'out': f'time zone set to {tz}', 'tz': tz}


# ---------- scheduled reboot ----------
def timer_text(time_s, days):
    return (f'# uz: time={time_s} days={",".join(days)}\n'
            '# Managed by the OpenStick dashboard (System > Scheduled restart). Edits are overwritten.\n'
            '[Unit]\nDescription=Scheduled restart (OpenStick dashboard)\n'
            f'[Timer]\nOnCalendar={on_calendar(time_s, days)}\nPersistent=false\nAccuracySec=1min\n'
            '[Install]\nWantedBy=timers.target\n')


SERVICE_TEXT = ('# Managed by the OpenStick dashboard (System > Scheduled restart).\n'
                '[Unit]\nDescription=Scheduled restart (OpenStick dashboard)\n'
                '[Service]\nType=oneshot\n'
                '# never reboot in the middle of a package upgrade\n'
                "ExecCondition=/bin/sh -c '! systemctl is-active --quiet uz-apt-upgrade.service'\n"
                'ExecStart=/bin/systemctl reboot\n')


def reboot_state():
    t = _rd(TIMER)
    m = re.search(r'^# uz: time=(\S+) days=(\S*)', t, re.M)
    time_s = m[1] if m and valid_time(m[1]) else None
    days = norm_days(m[2].split(',')) if m and m[2] else []
    return {'enabled': bool(t) and os.path.lexists(P(TIMER_WANTS)), 'time': time_s, 'days': days or []}


def reboot_schedule(body, ctx=None):
    enabled = body.get('enabled')
    if not isinstance(enabled, bool): return err('enabled must be true or false')
    if not _which('systemctl') or not os.path.isdir(P('/etc/systemd/system')):
        return err('systemd is not available on this host')
    if not enabled:
        if os.path.exists(P(TIMER)):
            rc, _, e = _run(['systemctl', 'disable', '--now', 'uz-reboot.timer'], 20)
            if rc != 0: return err('systemctl disable failed: ' + (e.strip().splitlines() or ['?'])[-1][:160])
        return {'out': 'scheduled restart off', 'reboot': reboot_state()}
    time_s, days = body.get('time'), norm_days(body.get('days'))
    if not valid_time(time_s): return err('time must be HH:MM (24 h)')
    if not days: return err('pick at least one day')
    try:
        _write_atomic(SERVICE, SERVICE_TEXT, 0o644)
        _write_atomic(TIMER, timer_text(time_s, days), 0o644)
    except OSError as e:
        return err(f'could not write timer: {e.strerror or e}')
    for args in (['systemctl', 'daemon-reload'], ['systemctl', 'enable', 'uz-reboot.timer'],
                 ['systemctl', 'restart', 'uz-reboot.timer']):
        rc, _, e = _run(args, 30)
        if rc != 0: return err(f'{" ".join(args[1:])} failed: ' + (e.strip().splitlines() or ['?'])[-1][:160])
    when = 'daily' if len(days) == 7 else ','.join(d.capitalize() for d in days)
    return {'out': f'restart scheduled {when} at {time_s}', 'reboot': reboot_state()}


# ---------- overview ----------
def os_name():
    for l in _rd('/etc/os-release').splitlines():
        if l.startswith('PRETTY_NAME='): return l.split('=', 1)[1].strip().strip('"')
    return ''


def _timedate():
    """(tz, ntp_synced, ntp_enabled) via timedatectl, falling back to files."""
    if _which('timedatectl'):
        rc, out, _ = _run(['timedatectl', 'show', '-p', 'Timezone', '-p', 'NTPSynchronized', '-p', 'NTP'], 8)
        if rc == 0:
            kv = dict(l.split('=', 1) for l in out.splitlines() if '=' in l)
            return (kv.get('Timezone') or get_tz_cheap(),
                    {'yes': True, 'no': False}.get(kv.get('NTPSynchronized')), {'yes': True, 'no': False}.get(kv.get('NTP')))
    return get_tz_cheap(), None, None


def sys_get(body=None, ctx=None):
    try:
        tz, synced, ntp = _timedate()
        try: up = float(_rd('/proc/uptime').split()[0])
        except (ValueError, IndexError): up = None
        chk = _job_state(CHECK_JSON)
        return {
            'hostname': get_hostname(), 'tz': tz, 'ntp_synced': synced, 'ntp': ntp,
            'kernel': os.uname().release, 'os': os_name(), 'uptime': up, 'pkg': _pkg_mgr(),
            'pin': pin_state(),
            'updates': {k: chk.get(k) for k in ('state', 'count', 'packages', 'held', 'checked', 'error')},
            'apt': apt_status(),
            'last_upgrade': _tail(UPGRADE_LOG, 15),
            'reboot': reboot_state(),
            'mem_free_mb': mem_free_mb(), 'disk_free_mb': disk_free_mb('/'), 'min_disk_mb': MIN_DISK_MB, 'min_mem_mb': MIN_MEM_MB,
        }
    except Exception as e:
        return err(f'{type(e).__name__}: {e}'[:200])


def status(ctx=None):
    """Cheap: a handful of small file reads, no subprocess."""
    chk, up = _job_state(CHECK_JSON), _job_state(UPGRADE_JSON)
    r = reboot_state()
    return {'hostname': get_hostname(), 'tz': get_tz_cheap(),
            'apt': {'pinned': pin_state()['pinned'], 'updates': chk.get('count') if isinstance(chk.get('count'), int) else None,
                    'running': chk.get('state') == 'running' or up.get('state') == 'running',
                    'upgrade': up.get('state')},
            'reboot': {'enabled': r['enabled'], 'time': r['time']}}


def _safe(fn):
    def w(body, ctx=None):
        try: return fn(body if isinstance(body, dict) else {}, ctx)
        except Exception as e: return err(f'{type(e).__name__}: {e}'[:200])
    return w


ACTIONS = {
    'sys-get': _safe(sys_get),
    'sys-hostname-set': _safe(hostname_set),
    'sys-timezones': _safe(tz_list),
    'sys-timezone-set': _safe(tz_set),
    'sys-apt-pin': _safe(apt_pin),
    'sys-apt-check': _safe(apt_check),
    'sys-apt-upgrade': _safe(apt_upgrade),
    'sys-apt-status': _safe(apt_status),
    'sys-reboot-schedule': _safe(reboot_schedule),
}


if __name__ == '__main__':
    if sys.argv[1:] == ['--apt-check']: sys.exit(worker_check())
    if sys.argv[1:] == ['--apt-upgrade']: sys.exit(worker_upgrade())
    print('usage: system.py --apt-check | --apt-upgrade', file=sys.stderr); sys.exit(2)
