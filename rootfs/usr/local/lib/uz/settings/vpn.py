"""VPN (Travel): sing-box config for the `sing-box-uz` service that `uz-mode travel` starts.

Secrets (uuid, passwords, keys, short_id…) are written to /etc/uz/sing-box.json (0600) and never
returned, logged or echoed: the UI only ever sees summary() output, which is built from a whitelist."""
import copy, ipaddress, json, os, re, shutil, subprocess, tempfile, threading, time
from urllib.parse import parse_qs, unquote, urlsplit

CONF = os.environ.get('UZ_VPN_CONF', '/etc/uz/sing-box.json')
UNIT = 'sing-box-uz'
TUN = 'tun-uz'
TS_NET = '100.64.0.0/10'                 # Tailscale CGNAT range stays outside the tunnel
MAX_JSON = 65536
INSTALL_LOG = '/var/log/uz-sing-box-install.log'
SECRET_KEYS = {'uuid', 'password', 'private_key', 'public_key', 'short_id', 'pre_shared_key', 'psk', 'auth',
               'auth_str', 'token', 'key', 'secret', 'obfs_password', 'certificate_key', 'id'}

HOST_RE = re.compile(r'(?=.{1,253}$)(?:[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?\.)*[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?')
UUID_RE = re.compile(r'[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}')
PBK_RE = re.compile(r'[A-Za-z0-9_-]{43}=?')
SID_RE = re.compile(r'(?:[0-9a-fA-F]{2}){0,8}')
SVC_RE = re.compile(r'[A-Za-z0-9._/-]{0,128}')
FINGERPRINTS = ('chrome', 'firefox', 'safari', 'ios', 'android', 'edge', '360', 'qq', 'random', 'randomized')
FLOWS = ('', 'xtls-rprx-vision')


# ---------------------------------------------------------------- parsing / building (pure, unit-tested)

def valid_host(h):
    if not isinstance(h, str) or not h: return False
    try: ipaddress.ip_address(h); return True
    except ValueError: return bool(HOST_RE.fullmatch(h)) and not h.replace('.', '').isdigit()


def parse_vless(link):
    """vless://uuid@host:port?security=reality&sni=…&pbk=…&sid=…&fp=…&flow=…&type=tcp#name -> dict.
    Raises ValueError with a message that never contains the uuid / keys."""
    if not isinstance(link, str): raise ValueError('link must be text')
    link = link.strip()
    if len(link) > 4096 or any(ord(c) < 32 for c in link): raise ValueError('link is too long or has control characters')
    if not link.lower().startswith('vless://'): raise ValueError('only vless:// links are supported')
    u = urlsplit(link)
    uid = unquote(u.username or '')
    if not UUID_RE.fullmatch(uid): raise ValueError('link: user part is not a valid UUID')
    try: host, port = u.hostname, u.port
    except ValueError: raise ValueError('link: invalid port') from None
    if not host or not valid_host(host): raise ValueError('link: invalid server host')
    if not port or not 0 < port < 65536: raise ValueError('link: port is missing')
    q = {k: v[-1].strip() for k, v in parse_qs(u.query, keep_blank_values=True).items()}
    sec = q.get('security', '').lower()
    if sec != 'reality': raise ValueError(f'link: security={sec or "none"} — only Reality links are supported; paste a full sing-box JSON instead')
    enc = q.get('encryption', 'none').lower()
    if enc not in ('', 'none'): raise ValueError('link: unsupported encryption')
    sni = q.get('sni') or q.get('peer') or ''
    if not valid_host(sni): raise ValueError('link: sni (Reality server name) is missing or invalid')
    pbk = q.get('pbk', '')
    if not pbk: raise ValueError('link: pbk (Reality public key) is missing')
    if not PBK_RE.fullmatch(pbk): raise ValueError('link: pbk is not a valid Reality public key')
    sid = q.get('sid', '')
    if not SID_RE.fullmatch(sid): raise ValueError('link: sid must be 0-16 hex digits')
    fp = (q.get('fp') or 'chrome').lower()
    if fp not in FINGERPRINTS: raise ValueError('link: unknown fingerprint (fp)')
    flow = q.get('flow', '')
    if flow not in FLOWS: raise ValueError('link: unsupported flow')
    net = (q.get('type') or 'tcp').lower()
    if net not in ('tcp', 'grpc'): raise ValueError(f'link: transport type={net} is not supported here; paste a full sing-box JSON instead')
    svc = q.get('serviceName', '')
    if net == 'grpc':
        if not SVC_RE.fullmatch(svc): raise ValueError('link: invalid gRPC serviceName')
        if flow: raise ValueError('link: flow xtls-rprx-vision does not work over gRPC')
    name = ''.join(c for c in unquote(u.fragment or '') if c.isprintable())[:64].strip()
    return {'uuid': uid.lower(), 'host': host, 'port': port, 'sni': sni, 'pbk': pbk, 'sid': sid.lower(),
            'fp': fp, 'flow': flow, 'type': net, 'service_name': svc, 'name': name}


def parse_version(text):
    m = re.search(r'sing-box version (\d+)\.(\d+)\.(\d+)', text or '')
    return tuple(int(x) for x in m.groups()) if m else None


def modern(ver):
    """sing-box ≥ 1.12 (new DNS server format, rule actions; legacy `sniff` inbound fields were removed in 1.13).
    Unknown version (not installed yet) -> modern: a fresh install gets a current release."""
    return ver is None or ver >= (1, 12, 0)


def tun_inbound(ver):
    t = {'type': 'tun', 'tag': 'tun-in', 'interface_name': TUN, 'address': ['172.19.0.1/30'],
         'auto_route': True, 'auto_redirect': True, 'strict_route': True, 'route_exclude_address': [TS_NET]}
    if not modern(ver): t['sniff'] = True; del t['tag']
    return t


def vless_outbound(p):
    o = {'type': 'vless', 'tag': 'vless', 'server': p['host'], 'server_port': p['port'], 'uuid': p['uuid']}
    if p['flow']: o['flow'] = p['flow']
    o['tls'] = {'enabled': True, 'server_name': p['sni'], 'utls': {'enabled': True, 'fingerprint': p['fp']},
                'reality': {'enabled': True, 'public_key': p['pbk'], 'short_id': p['sid']}}
    if p['type'] == 'grpc': o['transport'] = {'type': 'grpc', 'service_name': p['service_name']}
    return o


def build_config(p, ver=None):
    """Same shape as rootfs/etc/uz/sing-box.json.example (legacy ≤1.11) or its 1.12+ equivalent."""
    if modern(ver):
        return {'log': {'level': 'warn'},
                'dns': {'servers': [{'type': 'tls', 'tag': 'remote', 'server': '1.1.1.1', 'detour': 'vless'},
                                    {'type': 'local', 'tag': 'local'}], 'final': 'remote'},
                'inbounds': [tun_inbound(ver)],
                'outbounds': [vless_outbound(p), {'type': 'direct', 'tag': 'direct'}],
                'route': {'rules': [{'action': 'sniff'}, {'protocol': 'dns', 'action': 'hijack-dns'}],
                          'final': 'vless', 'auto_detect_interface': True, 'default_domain_resolver': 'local'}}
    return {'log': {'level': 'warn'},
            'dns': {'servers': [{'tag': 'remote', 'address': 'tls://1.1.1.1', 'detour': 'vless'}]},
            'inbounds': [tun_inbound(ver)],
            'outbounds': [vless_outbound(p), {'type': 'direct', 'tag': 'direct'}],
            'route': {'final': 'vless', 'auto_detect_interface': True}}


def check_json(text, ver=None):
    """Validate/fix a pasted sing-box config. Returns (config dict, [notes]). Raises ValueError."""
    if not isinstance(text, str) or not text.strip(): raise ValueError('config is empty')
    if len(text.encode()) > MAX_JSON: raise ValueError('config is larger than 64 KB')
    try: c = json.loads(text)
    except ValueError as e: raise ValueError(f'not valid JSON (line {getattr(e, "lineno", "?")})') from None
    if not isinstance(c, dict): raise ValueError('config must be a JSON object')
    obs = c.get('outbounds')
    if not isinstance(obs, list) or not obs: raise ValueError('config needs a non-empty "outbounds" list')
    if not all(isinstance(o, dict) and isinstance(o.get('type'), str) for o in obs):
        raise ValueError('every outbound must be an object with a "type"')
    notes = []
    ibs = c.get('inbounds')
    if ibs is None: ibs = c['inbounds'] = []
    if not isinstance(ibs, list) or not all(isinstance(i, dict) for i in ibs): raise ValueError('"inbounds" must be a list of objects')
    tuns = [i for i in ibs if i.get('type') == 'tun']
    if len(tuns) > 1: raise ValueError('config has more than one tun inbound; keep exactly one')
    if not tuns:
        ibs.insert(0, tun_inbound(ver))
        notes.append(f'added a tun inbound "{TUN}" (auto_route, Tailscale {TS_NET} excluded) so Travel mode routes through it')
    else:
        t = tuns[0]
        if t.get('interface_name') != TUN:
            t['interface_name'] = TUN
            notes.append(f'tun interface renamed to "{TUN}" (Travel mode NATs hotspot traffic out of it)')
        if t.get('auto_route') is not True:
            t['auto_route'] = True; notes.append('enabled auto_route on the tun inbound')
        ex = t.get('route_exclude_address')
        ex = [ex] if isinstance(ex, str) else ex if isinstance(ex, list) else []
        if TS_NET not in ex:
            t['route_exclude_address'] = ex + [TS_NET]
            notes.append(f'excluded {TS_NET} from the tunnel so Tailscale keeps working')
    return c, notes


def secrets_of(obj, out=None):
    """All string values stored under secret-looking keys (for redacting error messages)."""
    out = set() if out is None else out
    if isinstance(obj, dict):
        for k, v in obj.items():
            if isinstance(k, str) and k.lower() in SECRET_KEYS and isinstance(v, (str, int)) and str(v): out.add(str(v))
            else: secrets_of(v, out)
    elif isinstance(obj, list):
        for v in obj: secrets_of(v, out)
    return out


def redact(msg, secrets):
    for s in sorted(secrets, key=len, reverse=True):
        if len(s) >= 2: msg = msg.replace(s, '***')
    return msg


def _s(v, n=253):
    return v[:n] if isinstance(v, str) else None


def summary(c):
    """Whitelisted, secret-free view of a config."""
    if not isinstance(c, dict): return None
    outs = []
    for o in c.get('outbounds') or []:
        if not isinstance(o, dict): continue
        tls = o.get('tls') if isinstance(o.get('tls'), dict) else {}
        tr = o.get('transport') if isinstance(o.get('transport'), dict) else {}
        port = o.get('server_port')
        outs.append({'tag': _s(o.get('tag'), 64), 'type': _s(o.get('type'), 32), 'server': _s(o.get('server')),
                     'port': port if isinstance(port, int) and not isinstance(port, bool) else None,
                     'sni': _s(tls.get('server_name')) if tls.get('enabled') else None,
                     'transport': _s(tr.get('type'), 32) or ('tcp' if o.get('server') else None),
                     'reality': bool(isinstance(tls.get('reality'), dict) and tls['reality'].get('enabled')),
                     'flow': _s(o.get('flow'), 32) or None})
    tun = next((i for i in c.get('inbounds') or [] if isinstance(i, dict) and i.get('type') == 'tun'), {})
    route = c.get('route') if isinstance(c.get('route'), dict) else {}
    final = _s(route.get('final'), 64)
    main = next((o for o in outs if o['tag'] == final), None) or next((o for o in outs if o['server']), None)
    placeholder = any('CHANGE_ME' in (o['server'] or '') + (o['sni'] or '') for o in outs)
    return {'main': main, 'outbounds': outs[:8], 'tun': _s(tun.get('interface_name'), 32),
            'ts_excluded': TS_NET in (tun.get('route_exclude_address') or []), 'placeholder': placeholder}


def parse_trace(text):
    kv = dict(l.split('=', 1) for l in (text or '').splitlines() if '=' in l)
    ip = kv.get('ip', '')
    try: ipaddress.ip_address(ip)
    except ValueError: return None
    loc = kv.get('loc', '')
    return {'ip': ip, 'loc': loc if re.fullmatch(r'[A-Z]{2}', loc) else ''}


# ---------------------------------------------------------------- device helpers

def run(args, t=10, **kw):
    try: return subprocess.run(args, capture_output=True, text=True, timeout=t, **kw)
    except Exception: return None


def binary(): return shutil.which('sing-box')


def version(ctx):
    b = binary()
    if not b: return None
    try: key = (b, os.stat(b).st_mtime)
    except OSError: return None
    c = ctx.cache.get('vpn_ver')
    if not c or c[0] != key:
        r = run([b, 'version'], 10)
        c = (key, parse_version(r.stdout if r else ''))
        ctx.cache['vpn_ver'] = c
    return c[1]


def unit_state():
    if not shutil.which('systemctl'): return 'unavailable'
    r = run(['systemctl', 'is-active', UNIT], 5)
    return (r.stdout.strip() or 'unknown')[:20] if r else 'unknown'


def load_conf():
    try:
        with open(CONF) as f: return json.load(f)
    except (OSError, ValueError): return None


def os_id():
    try:
        with open('/etc/os-release') as f:
            for l in f:
                if l.startswith('ID='): return l[3:].strip().strip('"\'')[:32]
    except OSError: pass
    return ''


def arch():
    r = run(['dpkg', '--print-architecture'], 5) if shutil.which('dpkg') else None
    return r.stdout.strip()[:16] if r else ''


def apt_candidate():
    if not shutil.which('apt-cache'): return ''
    r = run(['apt-cache', 'policy', 'sing-box'], 20)
    m = re.search(r'Candidate:\s*(\S+)', r.stdout if r else '')
    return m[1] if m and m[1] != '(none)' else ''


def tail(path, n=4):
    try:
        with open(path, errors='replace') as f: return [l.rstrip()[:200] for l in f.readlines()[-n:]]
    except OSError: return []


def travel(ctx):
    return ctx.conf().get('UZ_MODE') == 'travel'


def tun_up(): return os.path.exists(f'/sys/class/net/{TUN}')


# ---------------------------------------------------------------- actions

def status(ctx):
    return {'installed': bool(binary()), 'configured': os.path.exists(CONF), 'active': tun_up()}


def get(body, ctx):
    b = binary(); ver = version(ctx)
    c = load_conf(); present = os.path.exists(CONF)
    d = {'installed': bool(b), 'version': '.'.join(map(str, ver)) if ver else '', 'unit_path_ok': b == '/usr/bin/sing-box' or os.path.exists('/usr/bin/sing-box'),
         'configured': present, 'config_valid': c is not None if present else None, 'summary': summary(c) if c else None,
         'service': unit_state(), 'tun': tun_up(), 'travel': travel(ctx), 'mode': ctx.conf().get('UZ_MODE', '')}
    if not b:
        d['install'] = {'os': os_id(), 'apt': bool(shutil.which('apt-get')), 'candidate': apt_candidate(),
                        'arch': arch(),
                        'log': tail(INSTALL_LOG)}
    return d


def install(body, ctx):
    if binary(): return {'out': 'sing-box is already installed'}
    if not shutil.which('apt-get'): return {'error': 'not available on this host (no apt-get)'}
    cand = apt_candidate()
    if not cand: return {'error': 'no apt source provides sing-box — add the official SagerNet repository first (see instructions)'}
    ctx.run_bg(f'DEBIAN_FRONTEND=noninteractive apt-get install -y sing-box >{INSTALL_LOG} 2>&1')
    return {'out': f'installing sing-box {cand[:32]} in the background — reopen this sheet in a minute'}


def write_conf(c, ver):
    """Validate with `sing-box check` (if installed), then install atomically as 0600. Returns error text or None."""
    d = os.path.dirname(CONF)
    if not os.path.isdir(d): return 'not available on this host'
    text = json.dumps(c, indent=2) + '\n'
    try:
        fd, tmp = tempfile.mkstemp(prefix='.sing-box.', suffix='.json', dir=d)
        os.fchmod(fd, 0o600)
        with os.fdopen(fd, 'w') as f: f.write(text)
    except OSError as e: return f'cannot write config: {e.strerror}'
    try:
        b = binary()
        if b:
            r = run([b, 'check', '-c', tmp], 30)
            if r is None: return 'sing-box check timed out'
            if r.returncode:
                msg = re.sub(r'\x1b\[[0-9;]*m', '', (r.stderr or r.stdout or 'check failed')).replace(tmp, 'config')
                return 'sing-box rejected the config: ' + redact(msg.strip(), secrets_of(c))[-300:]
        os.replace(tmp, CONF); tmp = None
        return None
    except OSError as e: return f'cannot install config: {e.strerror}'
    finally:
        if tmp and os.path.exists(tmp): os.remove(tmp)


def import_(body, ctx):
    if not isinstance(body, dict): return {'error': 'bad request'}
    ver = version(ctx)
    link, cfg = body.get('link'), body.get('config')
    try:
        if link and cfg: return {'error': 'send either a link or a config, not both'}
        if isinstance(link, str) and link.strip():
            p = parse_vless(link); c = build_config(p, ver); notes = []
            label = p['name'] or p['host']
        elif isinstance(cfg, str) and cfg.strip():
            if cfg.lstrip().lower().startswith('vless://'): return import_({'link': cfg}, ctx)
            c, notes = check_json(cfg, ver); label = 'JSON config'
        else: return {'error': 'paste a vless:// link or a sing-box JSON config'}
    except ValueError as e: return {'error': str(e)}
    err = write_conf(c, ver)
    if err: return {'error': err}
    if not binary(): after = 'install sing-box to use it'
    elif unit_state() == 'active': ctx.run_bg(f'systemctl restart {UNIT}'); after = 'VPN restarting with the new config'
    elif travel(ctx): ctx.run_bg(f'systemctl start {UNIT}'); after = 'VPN starting (Travel mode)'
    else: after = 'it will be used next time Travel mode starts'
    out = f'imported {label[:64]} — {after}'
    if not binary(): out += ' (not checked: sing-box is not installed)'
    return {'out': out, 'notes': notes, 'summary': summary(c)}


def enable(body, ctx):
    on = body.get('on') if isinstance(body, dict) else None
    if not isinstance(on, bool): return {'error': '"on" must be true or false'}
    if not shutil.which('systemctl'): return {'error': 'not available on this host'}
    if on:
        if not binary(): return {'error': 'sing-box is not installed'}
        if not os.path.exists(CONF): return {'error': 'import a config first'}
        ctx.run_bg(f'systemctl start {UNIT}')
        return {'out': 'VPN starting' + ('' if travel(ctx) else ' — note: Home mode does not use it (switching to Home stops it); Travel mode starts it automatically')}
    ctx.run_bg(f'systemctl stop {UNIT}')
    return {'out': 'VPN stopping' + (' — Travel mode will start it again next time' if os.path.exists(CONF) else '')}


def remove(body, ctx):
    if not isinstance(body, dict) or body.get('confirm') is not True: return {'error': 'confirmation required'}
    if not os.path.exists(CONF): return {'out': 'no VPN config to remove'}
    if shutil.which('systemctl'): run(['systemctl', 'stop', UNIT], 20)
    try: os.remove(CONF)
    except OSError as e: return {'error': f'cannot remove config: {e.strerror}'}
    return {'out': 'VPN config removed and service stopped'}


def uplink():
    r = run(['ip', '-4', 'route', 'show', 'default'], 5)
    for l in (r.stdout if r else '').splitlines():
        m = re.search(r'\bdev (\S+)', l)
        if m and m[1] != TUN and re.fullmatch(r'[A-Za-z0-9_.-]{1,15}', m[1]): return m[1]
    return ''


def trace(iface):
    r = run(['curl', '-s', '-m', '8', '--interface', iface, 'https://1.1.1.1/cdn-cgi/trace'], 12)
    return parse_trace(r.stdout) if r and r.returncode == 0 else None


def test(body, ctx):
    if not shutil.which('curl') or not os.path.isdir('/sys/class/net'): return {'error': 'not available on this host'}
    if not tun_up(): return {'error': 'VPN is not running'}
    up = uplink()
    res = {}
    th = [threading.Thread(target=lambda k=k, i=i: res.__setitem__(k, trace(i))) for k, i in (('vpn', TUN), ('direct', up)) if i]
    for t in th: t.start()
    for t in th: t.join(15)
    v, d = res.get('vpn'), res.get('direct')
    if not v: return {'error': 'no answer through the tunnel — check the server and the sing-box log', 'direct': d, 'uplink': up}
    same = bool(d and d['ip'] == v['ip'])
    return {'out': f"VPN {v['ip']} {v['loc']}".strip() + (f" · direct {d['ip']} {d['loc']}".rstrip() if d else '') + (' — same IP: traffic is NOT tunnelled' if same else ''),
            'vpn': v, 'direct': d, 'uplink': up, 'same': same}


ACTIONS = {'vpn-get': get, 'vpn-import': import_, 'vpn-enable': enable, 'vpn-remove': remove,
           'vpn-test': test, 'vpn-install': install}
