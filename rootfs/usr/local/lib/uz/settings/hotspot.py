"""Hotspot (advanced): channel and hidden SSID of the NetworkManager profile "uz-hotspot", plus connected clients.

The UZ801 has one wcn36xx radio: 2.4 GHz only (band fixed to bg), WPA2-PSK only (WPA3/SAE needs management-frame
protection that this driver/firmware is not known to handle in AP mode). Name/password stay in uz-web
(hotspot-psk / hotspot-set). Preferences are also kept in /etc/uz/uz.conf (UZ_HOTSPOT_CHANNEL, UZ_HOTSPOT_HIDDEN)
so they survive the profile being re-created by uz-mode."""
import os, re, shutil, subprocess, time

CON = 'uz-hotspot'
FIELDS = ['802-11-wireless.band', '802-11-wireless.channel', '802-11-wireless.hidden', '802-11-wireless-security.key-mgmt']
CHANNELS = range(0, 14)          # 0 = auto; 12-13 only where the regulatory domain allows them
SECURITY = {'wpa2': 'wpa-psk'}   # only what wcn36xx AP mode is known to do
IFACE_RE = re.compile(r'[A-Za-z0-9_.-]{1,15}')
MAC_RE = re.compile(r'[0-9a-fA-F]{2}(?::[0-9a-fA-F]{2}){5}')
ONLINE = ('REACHABLE', 'DELAY', 'PROBE')


def _nm_dir(): return os.environ.get('UZ_NM_DIR', '/var/lib/NetworkManager')


def _read(path):
    try:
        with open(path) as f: return f.read()
    except (OSError, UnicodeDecodeError): return ''


def _run(args, t=10):
    """-> (returncode, stdout, stderr); never raises."""
    try:
        r = subprocess.run(args, capture_output=True, text=True, timeout=t)
        return r.returncode, r.stdout, r.stderr
    except Exception as e:
        return -1, '', type(e).__name__


# ---------- parsers ----------
def parse_profile(out):
    """`nmcli -g band,channel,hidden,key-mgmt connection show uz-hotspot` (one value per line)."""
    v = (out or '').splitlines() + [''] * 4
    ch = v[1].strip()
    return {'band': v[0].strip(), 'channel': int(ch) if ch.isdigit() else 0,
            'hidden': v[2].strip().lower() in ('yes', 'true', '1'), 'key_mgmt': v[3].strip()}


def split_terse(line):
    """Split an `nmcli -t/-g` line on unescaped ':' and unescape '\\:' / '\\\\'."""
    parts, cur, i = [], '', 0
    while i < len(line):
        c = line[i]
        if c == '\\' and i + 1 < len(line): cur += line[i + 1]; i += 2; continue
        if c == ':': parts.append(cur); cur = ''
        else: cur += c
        i += 1
    return parts + [cur]


def active_device(out):
    """`nmcli -g NAME,DEVICE connection show --active` -> device of uz-hotspot or ''."""
    for line in (out or '').splitlines():
        p = split_terse(line)
        if len(p) >= 2 and p[0] == CON and IFACE_RE.fullmatch(p[1]): return p[1]
    return ''


def parse_leases(text, now=None):
    """dnsmasq lease file: `expiry mac ip hostname clientid` (expiry 0 = infinite). Expired leases are dropped."""
    now = time.time() if now is None else now
    out = []
    for line in (text or '').splitlines():
        f = line.split()
        if len(f) < 4 or not f[0].isdigit() or not MAC_RE.fullmatch(f[1]): continue
        exp = int(f[0])
        if exp and exp < now: continue
        host = '' if f[3] == '*' else ''.join(c for c in f[3] if c.isprintable())[:63]
        out.append({'mac': f[1].lower(), 'ip': f[2], 'hostname': host, 'expires': exp})
    return out


def parse_neigh(text):
    """`ip neigh show dev X` -> {ip: {'mac', 'state'}} (entries without lladdr keep mac '')."""
    out = {}
    for line in (text or '').splitlines():
        f = line.split()
        if not f: continue
        mac = f[f.index('lladdr') + 1].lower() if 'lladdr' in f and f.index('lladdr') + 1 < len(f) else ''
        out[f[0]] = {'mac': mac, 'state': f[-1].upper() if f[-1].isalpha() else ''}
    return out


def mask_mac(mac):
    p = mac.split(':')
    return ':'.join(p[:3] + ['xx', 'xx'] + p[5:]) if len(p) == 6 else 'xx'


def clients(leases, neigh):
    res, seen = [], set()
    for l in leases:
        n = neigh.get(l['ip'], {})
        st = n.get('state', '') if n.get('mac') in ('', l['mac']) else ''
        res.append({'hostname': l['hostname'], 'ip': l['ip'], 'mac': mask_mac(l['mac']), 'state': st,
                    'online': st in ONLINE}); seen.add(l['ip'])
    for ip, n in neigh.items():           # static-IP clients without a lease
        if ip in seen or not n['mac'] or n['state'] in ('FAILED', 'INCOMPLETE', ''): continue
        res.append({'hostname': '', 'ip': ip, 'mac': mask_mac(n['mac']), 'state': n['state'], 'online': n['state'] in ONLINE})
    res.sort(key=lambda c: (not c['online'], c['hostname'] == '', c['hostname'].lower(), c['ip']))
    return res


def prefs(conf):
    ch = str(conf.get('UZ_HOTSPOT_CHANNEL', ''))
    return {'channel': int(ch) if ch.isdigit() and int(ch) in CHANNELS else 0,
            'hidden': conf.get('UZ_HOTSPOT_HIDDEN', '0') == '1',
            'set': 'UZ_HOTSPOT_CHANNEL' in conf or 'UZ_HOTSPOT_HIDDEN' in conf}


def validate(body):
    """-> (channel, hidden, error)."""
    if not isinstance(body, dict): return None, None, 'bad request'
    ch, hid, sec = body.get('channel'), body.get('hidden'), body.get('security', 'wpa2')
    if isinstance(ch, bool) or not isinstance(ch, int) or ch not in CHANNELS: return None, None, 'channel: 0 (auto) or 1–13'
    if not isinstance(hid, bool): return None, None, 'hidden must be true or false'
    if sec not in SECURITY: return None, None, 'security: only WPA2 (wpa2) is supported on this radio'
    return ch, hid, None


# ---------- actions ----------
def _conf(ctx):
    try: return ctx.conf()
    except Exception: return {}


def get(body, ctx):
    p = prefs(_conf(ctx))
    r = {'profile': False, 'active': False, 'prefs': p, 'clients': [], 'channels': list(CHANNELS)}
    if not shutil.which('nmcli'):
        r['error'] = 'nmcli not available on this host'; return r
    rc, out, err = _run(['nmcli', '-g', ','.join(FIELDS), 'connection', 'show', CON])
    if rc == 0:
        r['profile'] = True; r.update(parse_profile(out))
    elif rc == -1:
        r['error'] = 'nmcli failed: ' + err; return r
    rc, out, _ = _run(['nmcli', '-g', 'NAME,DEVICE', 'connection', 'show', '--active'])
    dev = active_device(out) if rc == 0 else ''
    r['active'], r['device'] = bool(dev), dev
    if dev:
        leases = parse_leases(_read(os.path.join(_nm_dir(), f'dnsmasq-{dev}.leases')))
        rc, out, _ = _run(['ip', 'neigh', 'show', 'dev', dev], 5)
        r['clients'] = clients(leases, parse_neigh(out) if rc == 0 else {})
    try: ctx.cache['hotspot_adv'] = {k: r.get(k) for k in ('profile', 'channel', 'hidden')}
    except Exception: pass
    return r


def set_(body, ctx):
    ch, hid, err = validate(body)
    if err: return {'error': err}
    if not shutil.which('nmcli'): return {'error': 'nmcli not available on this host'}
    try:
        ctx.set_conf('UZ_HOTSPOT_CHANNEL', str(ch)); ctx.set_conf('UZ_HOTSPOT_HIDDEN', '1' if hid else '0')
    except Exception as e:
        return {'error': f'could not save preference: {type(e).__name__}'}
    rc, _, err = _run(['nmcli', '-g', 'connection.id', 'connection', 'show', CON])
    if rc != 0:
        return {'out': 'saved — applies when Travel mode first creates the hotspot', 'pending': True}
    rc, _, err = _run(['nmcli', 'connection', 'modify', CON, '802-11-wireless.band', 'bg',
                       '802-11-wireless.channel', str(ch), '802-11-wireless.hidden', 'yes' if hid else 'no'], 15)
    # key-mgmt is left as is (wpa-psk from uz-mode); 'security' only accepts wpa2 for now
    if rc != 0: return {'error': (err or 'nmcli modify failed').strip()[:200]}
    rc, out, _ = _run(['nmcli', '-g', 'NAME,DEVICE', 'connection', 'show', '--active'])
    if rc == 0 and active_device(out):
        # re-up detached: clients (maybe this browser) drop for a few seconds
        cmd = ['nmcli', 'connection', 'up', CON]
        if shutil.which('systemd-run'): cmd = ['systemd-run', '--collect', '--quiet', *cmd]
        try: subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, start_new_session=True)
        except OSError as e: return {'error': f'saved, but restart failed: {type(e).__name__}'}
        return {'out': 'saved — hotspot restarting, clients reconnect in a few seconds', 'restarting': True}
    return {'out': 'saved — applies next time the hotspot starts'}


def status(ctx):
    """Cheap: uz.conf + lease file only."""
    c = getattr(ctx, 'cache', {}).get('hotspot_adv') or {}
    p = prefs(_conf(ctx))
    n = len(parse_leases(_read(os.path.join(_nm_dir(), 'dnsmasq-wlan0.leases'))))
    return {'channel': c.get('channel') if c.get('profile') else p['channel'],
            'hidden': c.get('hidden') if c.get('profile') else p['hidden'], 'leases': n}


ACTIONS = {'hotspot-adv-get': get, 'hotspot-adv-set': set_}
