#!/usr/bin/env python3
"""Unit tests for the Wi-Fi settings module: python3 dev/tests/wifi_test.py"""
import importlib.util, json, os, subprocess, sys, tempfile, time, unittest
from types import SimpleNamespace

R = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))
FX = os.path.join(R, 'dev', 'fixtures', 'wifi')
spec = importlib.util.spec_from_file_location('wifi', os.path.join(R, 'rootfs/usr/local/lib/uz/settings/wifi.py'))
wifi = importlib.util.module_from_spec(spec); spec.loader.exec_module(wifi)

def fx(name): return open(os.path.join(FX, name), encoding='utf-8').read()

HOME = '1b2c3d4e-0000-4000-8000-000000000001'
CAFE = '1b2c3d4e-0000-4000-8000-000000000002'
OFFICE = '1b2c3d4e-0000-4000-8000-000000000003'
UZHS = '1b2c3d4e-0000-4000-8000-0000000000aa'


class FakeNM:
    """Stands in for subprocess.run; answers nmcli/ip calls from fixtures and records every argv."""
    def __init__(self, active='active_client.txt', route='route_with_4g.txt', rescan_fails=False, fail=()):
        self.calls, self.active, self.route, self.rescan_fails, self.fail = [], active, route, rescan_fails, set(fail)

    def __call__(self, args, **kw):
        assert isinstance(args, list), 'must use argument lists'
        assert not kw.get('shell'), 'never shell=True'
        self.calls.append(args)
        ok = lambda out='': SimpleNamespace(returncode=0, stdout=out, stderr='')
        bad = lambda err: SimpleNamespace(returncode=10, stdout='', stderr=err)
        if args[:2] == ['ip', '-4']: return ok(fx(self.route))
        if 'list' in args and 'wifi' in args:
            if self.rescan_fails and args[-1] == 'yes': return bad('Error: Scanning not allowed immediately following previous scan.')
            return ok(fx('scan.txt'))
        if args[-1] == '--active': return ok(fx(self.active))
        if args[-2:] == ['connection', 'show']: return ok(fx('con_list.txt'))
        if args[:4] == ['nmcli', '-e', 'no', '-t']:
            p = os.path.join(FX, f'props-{args[-1][-12:]}.txt')
            return ok(fx(os.path.basename(p))) if os.path.exists(p) else ok('')
        if 'delete' in args or 'modify' in args:
            return bad('Error: boom.') if 'write' in self.fail else ok('')
        raise AssertionError(f'unexpected command {args}')


class Ctx:
    def __init__(self, tmp):
        self.cache, self.bg, self.secrets, self.tmp = {}, [], {}, tmp
    def run_bg(self, cmd): self.bg.append(cmd)
    def write_secret(self, path, text):
        fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
        with os.fdopen(fd, 'w') as f: f.write(text)
        self.secrets[path] = text


class Base(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(); wifi.RUN = self.tmp.name
        self.ctx = Ctx(self.tmp.name)
        self._run, self._which = subprocess.run, wifi.shutil.which
        wifi.shutil.which = lambda n: '/usr/bin/' + n
        self.nm = FakeNM(); wifi.subprocess.run = self.nm
    def tearDown(self):
        wifi.subprocess.run, wifi.shutil.which = self._run, self._which
        self.tmp.cleanup()
    def use(self, **kw): self.nm = FakeNM(**kw); wifi.subprocess.run = self.nm
    def cmds(self, word): return [c for c in self.nm.calls if word in c]


class Parsers(unittest.TestCase):
    def test_split_terse(self):
        self.assertEqual(wifi.split_terse(r' :Café\:Corner:F0\:9F:1'), [' ', 'Café:Corner', 'F0:9F', '1'])
        self.assertEqual(wifi.split_terse(r'a\\:b'), ['a\\', 'b'])
        self.assertEqual(wifi.split_terse('::'), ['', '', ''])

    def test_scan_merge(self):
        nets, hidden = wifi.parse_scan(fx('scan.txt'))
        by = {n['ssid']: n for n in nets}
        self.assertEqual(hidden, 2)                                    # '' and '--'
        self.assertEqual(len(nets), 8)
        h = by['HomeNet']
        self.assertEqual((h['signal'], h['aps'], h['chan']), (84, 3, '11'))   # strongest BSSID wins
        self.assertTrue(h['connected'])                                 # in-use flag survives the merge
        self.assertEqual(h['bssid'], 'A4:2B:B0:11:22:34')
        self.assertIn('Café:Corner', by)                               # escaped colon in SSID
        self.assertIn('Corp\\Net', by)                                 # escaped backslash
        self.assertEqual(by['Corp\\Net']['kind'], 'enterprise')
        self.assertEqual(by['星巴克WiFi']['kind'], 'open')
        self.assertEqual(by['Airport Free']['kind'], 'open')
        self.assertEqual(by['Airport Free']['security'], '')
        self.assertEqual(by['Nhà Trọ 3 Tầng']['kind'], 'wpa')
        self.assertEqual(by['OldRouter']['kind'], 'wep')
        self.assertFalse(by['Café:Corner']['connected'])

    def test_con_list(self):
        rows = wifi.parse_con_list(fx('con_list.txt'))
        self.assertEqual([r['name'] for r in rows], ['HomeNet', 'Café:Corner', 'Office 5G', 'uz-hotspot', 'hotspot'])
        self.assertEqual(rows[0]['priority'], 10); self.assertTrue(rows[0]['active']); self.assertEqual(rows[0]['device'], 'wlan0')
        self.assertIsNone(rows[2]['last']); self.assertEqual(rows[2]['priority'], -5); self.assertFalse(rows[2]['autoconnect'])

    def test_props_unescaped(self):
        self.assertEqual(wifi.parse_props(fx('props-000000000002.txt'))['802-11-wireless.ssid'], 'Café:Corner')

    def test_validation(self):
        V = wifi.valid_ssid
        self.assertTrue(V('a')); self.assertTrue(V('x' * 32)); self.assertTrue(V('星巴克WiFi'))
        self.assertFalse(V('')); self.assertFalse(V('x' * 33)); self.assertFalse(V('星' * 11))  # 33 bytes
        self.assertFalse(V('a\nb')); self.assertFalse(V('a\x00')); self.assertFalse(V(5))
        P = wifi.valid_psk
        self.assertTrue(P('12345678')); self.assertTrue(P('a' * 63)); self.assertTrue(P('0f' * 32)); self.assertTrue(P('p@ss w0rd!'))
        self.assertFalse(P('1234567')); self.assertFalse(P('g' * 64)); self.assertFalse(P('mật khẩu12')); self.assertFalse(P('abc\tdefgh'))


class Actions(Base):
    def test_no_nmcli(self):
        wifi.shutil.which = lambda n: None
        for a in wifi.ACTIONS.values():
            self.assertIn('not available', a({}, self.ctx)['error'])

    def test_scan(self):
        r = wifi.ACTIONS['wifi-scan']({}, self.ctx)
        self.assertNotIn('error', r)
        self.assertEqual(self.cmds('list')[0], ['nmcli', '-t', '-f', 'IN-USE,SSID,BSSID,CHAN,FREQ,SIGNAL,SECURITY', 'dev', 'wifi', 'list', '--rescan', 'yes'])
        n = r['networks']
        self.assertEqual(n[0]['ssid'], 'HomeNet'); self.assertTrue(n[0]['saved'] and n[0]['connected'])
        self.assertTrue(n[1]['saved']); self.assertEqual(n[1]['ssid'], 'Café:Corner')
        self.assertEqual(r['hidden'], 2)
        self.assertEqual(self.ctx.cache['wifi_scan']['nets']['Corp\\Net'], 'enterprise')

    def test_scan_rescan_fallback(self):
        self.use(rescan_fails=True)
        r = wifi.ACTIONS['wifi-scan']({}, self.ctx)
        self.assertTrue(r['cached']); self.assertEqual(self.cmds('list')[1][-1], 'no')

    def test_scan_refused_in_hotspot(self):
        self.use(active='active_hotspot.txt')
        r = wifi.ACTIONS['wifi-scan']({}, self.ctx)
        self.assertIn('hotspot', r['error']); self.assertFalse(self.cmds('list'))

    def test_saved_hides_hotspots(self):
        r = wifi.ACTIONS['wifi-saved']({}, self.ctx)
        names = [p['name'] for p in r['saved']]
        self.assertEqual(names, ['HomeNet', 'Café:Corner', 'Office 5G'])   # active first, then priority
        self.assertNotIn('uz-hotspot', names); self.assertNotIn('hotspot', names)
        self.assertEqual(r['saved'][0]['last'], 1763611111)

    # --- connect ---
    def connect(self, body):
        return wifi.ACTIONS['wifi-connect'](body, self.ctx)

    def test_connect_new_network(self):
        pw = 'Sup3r secret!'
        r = self.connect({'ssid': 'Nhà Trọ 3 Tầng', 'password': pw})
        self.assertNotIn('error', r); self.assertIn('up to a minute', r['out']); self.assertEqual(r['previous'], 'HomeNet')
        self.assertNotIn(pw, json.dumps(r))
        self.assertEqual(len(self.ctx.bg), 1)
        cmd = self.ctx.bg[0]
        self.assertEqual(cmd, f"exec python3 {self.tmp.name}/uz-wifi-guard.py {self.tmp.name}/uz-wifi-job.json")
        self.assertNotIn(pw, cmd); self.assertNotIn('Nhà', cmd)       # nothing user-supplied in the shell string
        job_path = os.path.join(self.tmp.name, 'uz-wifi-job.json')
        self.assertEqual(os.stat(job_path).st_mode & 0o777, 0o600)
        job = json.load(open(job_path))
        self.assertEqual(job['ssid'], 'Nhà Trọ 3 Tầng'); self.assertEqual(job['password'], pw)
        self.assertEqual(job['prev'], HOME); self.assertIsNone(job['use_uuid']); self.assertEqual(job['ifname'], 'wlan0')
        self.assertIn(UZHS, job['before']); self.assertIn(HOME, job['before'])
        self.assertTrue(os.path.exists(os.path.join(self.tmp.name, 'uz-wifi-guard.py')))
        self.assertFalse(self.cmds('connect'), 'the switch itself must run detached, not in the request')

    def test_connect_saved_uses_profile(self):
        r = self.connect({'ssid': 'Café:Corner'})
        self.assertNotIn('error', r)
        job = json.load(open(os.path.join(self.tmp.name, 'uz-wifi-job.json')))
        self.assertEqual(job['use_uuid'], CAFE); self.assertEqual(job['password'], '')

    def test_connect_already(self):
        r = self.connect({'ssid': 'HomeNet'})
        self.assertIn('already', r['out']); self.assertFalse(self.ctx.bg)

    def test_connect_validation(self):
        for body, word in [({'ssid': ''}, 'SSID'), ({'ssid': 'x' * 33}, 'SSID'), ({'ssid': 'a\nb'}, 'SSID'), ({'ssid': 7}, 'SSID'),
                           ({'ssid': 'X', 'password': 'short'}, 'password'), ({'ssid': 'X', 'password': 'g' * 64}, 'password'),
                           ({'ssid': 'X', 'password': 12345678}, 'password'), ({'ssid': 'X', 'hidden': 'yes'}, 'hidden')]:
            r = self.connect(body)
            self.assertIn(word, r.get('error', ''), body)
        self.assertFalse(self.ctx.bg)
        self.assertIn('bad request', wifi.ACTIONS['wifi-connect']([], self.ctx)['error'])

    def test_connect_needs_password_and_enterprise(self):
        wifi.ACTIONS['wifi-scan']({}, self.ctx)
        self.assertIn('needs a password', self.connect({'ssid': 'Nhà Trọ 3 Tầng'})['error'])
        self.assertIn('Enterprise', self.connect({'ssid': 'Corp\\Net', 'password': '12345678'})['error'])
        self.assertNotIn('error', self.connect({'ssid': 'Airport Free'}))

    def test_connect_open_hidden(self):
        r = self.connect({'ssid': 'Secret Lab', 'hidden': True})
        self.assertNotIn('error', r)
        job = json.load(open(os.path.join(self.tmp.name, 'uz-wifi-job.json')))
        self.assertTrue(job['hidden']); self.assertEqual(job['password'], '')

    def test_connect_refused_in_hotspot(self):
        self.use(active='active_hotspot.txt')
        self.assertIn('hotspot', self.connect({'ssid': 'X', 'password': '12345678'})['error'])
        self.assertFalse(self.ctx.bg)

    def test_connect_own_hotspot_ssid(self):
        self.assertIn('own hotspot', self.connect({'ssid': 'OpenStick'})['error'])

    def test_connect_busy(self):
        json.dump({'state': 'checking', 't': time.time()}, open(os.path.join(self.tmp.name, 'uz-wifi-guard.json'), 'w'))
        self.assertIn('in progress', self.connect({'ssid': 'Airport Free'})['error'])

    # --- forget ---
    def forget(self, body): return wifi.ACTIONS['wifi-forget'](body, self.ctx)

    def test_forget_inactive(self):
        r = self.forget({'name': 'Café:Corner'})
        self.assertEqual(r['out'], 'forgot Café:Corner')
        self.assertEqual(self.cmds('delete'), [['nmcli', 'connection', 'delete', 'uuid', CAFE]])

    def test_forget_protected(self):
        for n in ('uz-hotspot', 'hotspot', UZHS):
            self.assertIn('hotspot', self.forget({'name': n})['error'])
        self.assertFalse(self.cmds('delete'))

    def test_forget_active(self):
        self.assertIn('in use', self.forget({'name': 'HomeNet'})['error'])
        self.use(route='route_wifi_only.txt')
        self.assertIn('no other uplink', self.forget({'name': 'HomeNet', 'force': True})['error'])
        self.assertFalse(self.ctx.bg)
        self.use(route='route_with_4g.txt')
        r = self.forget({'name': 'HomeNet', 'force': True})
        self.assertIn('wwan0', r['out'])
        self.assertEqual(self.ctx.bg, [f'sleep 1; nmcli connection delete uuid {HOME}'])
        self.assertFalse(self.cmds('delete'))

    def test_forget_bad(self):
        self.assertIn('bad', self.forget({'name': ''})['error'])
        self.assertIn('no such', self.forget({'name': 'Nope'})['error'])
        self.assertIn('force', self.forget({'name': 'HomeNet', 'force': 'yes'})['error'])

    def test_forget_nmcli_error(self):
        self.use(fail=('write',))
        self.assertIn('boom', self.forget({'name': 'Office 5G'})['error'])

    # --- priority ---
    def prio(self, body): return wifi.ACTIONS['wifi-priority'](body, self.ctx)

    def test_priority(self):
        r = self.prio({'name': 'Office 5G', 'priority': -20, 'autoconnect': True})
        self.assertNotIn('error', r)
        self.assertEqual(self.cmds('modify'), [['nmcli', 'connection', 'modify', 'uuid', OFFICE,
                                                'connection.autoconnect-priority', '-20', 'connection.autoconnect', 'yes']])

    def test_priority_validation(self):
        for b in [{'name': 'HomeNet', 'priority': 1000, 'autoconnect': True}, {'name': 'HomeNet', 'priority': '5', 'autoconnect': True},
                  {'name': 'HomeNet', 'priority': True, 'autoconnect': True}, {'name': 'HomeNet', 'priority': 1.5, 'autoconnect': True},
                  {'name': 'HomeNet', 'priority': 1, 'autoconnect': 'no'}]:
            self.assertIn('error', self.prio(b), b)
        self.assertIn('hotspot', self.prio({'name': 'uz-hotspot', 'priority': 1, 'autoconnect': True})['error'])
        self.assertFalse(self.cmds('modify'))

    def test_priority_last_autoconnect_guard(self):
        # HomeNet active; Café also autoconnects -> allowed
        self.assertNotIn('error', self.prio({'name': 'HomeNet', 'priority': 0, 'autoconnect': False}))
        # only auto-connecting network, no 4G/USB -> refused unless force
        real = wifi.profiles
        wifi.profiles = lambda include_protected=False: [dict(p, autoconnect=p['active']) for p in real(include_protected)]
        try:
            self.use(route='route_wifi_only.txt')
            self.assertIn('unreachable', self.prio({'name': 'HomeNet', 'priority': 0, 'autoconnect': False})['error'])
            self.assertFalse(self.cmds('modify'))
            self.assertNotIn('error', self.prio({'name': 'HomeNet', 'priority': 0, 'autoconnect': False, 'force': True}))
        finally: wifi.profiles = real


class Status(Base):
    def test_status_cheap(self):
        self.ctx.cache['net'] = {'ssid': 'HomeNet', 'wifi_mode': 'infrastructure', 'wifi_signal': '80'}
        s = wifi.status(self.ctx)
        self.assertEqual((s['ssid'], s['mode'], s['signal']), ('HomeNet', 'client', '80'))
        self.ctx.cache['net'] = {'ssid': 'UZ801-ab12', 'wifi_mode': 'ap'}
        self.assertEqual(wifi.status(self.ctx)['mode'], 'hotspot')
        self.ctx.cache['net'] = {}
        self.assertEqual(wifi.status(self.ctx)['mode'], 'off')
        time.sleep(0.3)
        self.assertEqual(wifi._COUNT['n'], 3)                  # background refresh, protected profiles excluded

    def test_status_switch_state(self):
        json.dump({'state': 'rolled-back', 'ssid': 'X', 'msg': 'no Internet after switch', 't': time.time()},
                  open(os.path.join(self.tmp.name, 'uz-wifi-guard.json'), 'w'))
        self.assertEqual(wifi.status(self.ctx)['switch']['state'], 'rolled-back')


class Guard(unittest.TestCase):
    """Runs the shipped guard script against a fake `nmcli`/`ping` on PATH."""
    def run_guard(self, connect_rc=0, ping_rc=0):
        d = tempfile.mkdtemp(); b = os.path.join(d, 'bin'); os.mkdir(b)
        log = os.path.join(d, 'calls.log')
        fake = f'''#!/bin/sh
printf '%s\\n' "$(basename "$0") $*" >> {log}
case "$*" in
  *"device wifi connect"*) echo "Error: Connection activation failed: Secrets were required." >&2; exit {connect_rc};;
  *"-t -f UUID,TYPE connection show"*) printf 'OLD-1:802-11-wireless\\nNEW-1:802-11-wireless\\nETH:802-3-ethernet\\n';;
  *"802-11-wireless.ssid connection show NEW-1"*) echo "New Net";;
esac
exit 0
'''
        for n in ('nmcli', 'ping'):
            p = os.path.join(b, n); open(p, 'w').write(fake.replace('exit 0\n', f'exit {ping_rc if n == "ping" else 0}\n')); os.chmod(p, 0o755)
        old = wifi.RUN; wifi.RUN = d
        try:
            job = wifi.build_job('New Net', 'hunter2hunter2', False, 'OLD-1', ['OLD-1'])
            job['check_after'] = 0
            open(os.path.join(d, 'uz-wifi-job.json'), 'w').write(json.dumps(job))
            open(os.path.join(d, 'uz-wifi-guard.py'), 'w').write(wifi.GUARD_SRC)
            env = dict(os.environ, PATH=b + ':' + os.environ['PATH'])
            subprocess.run(['sh', '-c', wifi.guard_cmd()], env=env, check=True, timeout=30)
        finally: wifi.RUN = old
        st = json.load(open(os.path.join(d, 'uz-wifi-guard.json')))
        self.assertFalse(os.path.exists(os.path.join(d, 'uz-wifi-job.json')), 'job file (password) must be deleted')
        self.assertNotIn('hunter2', open(os.path.join(d, 'uz-wifi-guard.json')).read())
        return st, open(log).read().splitlines()

    def test_success(self):
        st, calls = self.run_guard()
        self.assertEqual(st['state'], 'ok')
        self.assertEqual(calls[0], 'nmcli -w 45 device wifi connect New Net password hunter2hunter2 ifname wlan0')
        self.assertFalse([c for c in calls if 'delete' in c or 'connection up' in c])

    def test_no_internet_rolls_back(self):
        st, calls = self.run_guard(ping_rc=1)
        self.assertEqual(st['state'], 'rolled-back')
        self.assertIn('nmcli connection delete uuid NEW-1', calls)
        self.assertIn('nmcli -w 60 connection up uuid OLD-1', calls)
        self.assertFalse([c for c in calls if 'delete uuid OLD-1' in c])

    def test_connect_failure_rolls_back_immediately(self):
        st, calls = self.run_guard(connect_rc=4)
        self.assertEqual(st['state'], 'rolled-back'); self.assertIn('Secrets were required', st['msg'])
        self.assertFalse([c for c in calls if c.startswith('ping')])


if __name__ == '__main__':
    unittest.main(verbosity=1)
