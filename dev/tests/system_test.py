#!/usr/bin/env python3
"""Unit tests for rootfs/usr/local/lib/uz/settings/system.py — run: python3 dev/tests/system_test.py
Every filesystem path is redirected into a temp dir (mod.ROOT); subprocess and `which` are monkeypatched,
so nothing on this machine is read for real config or modified."""
import importlib.util, json, os, shutil, sys, tempfile, unittest

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(os.path.dirname(HERE))
FIX = os.path.join(REPO, 'dev', 'fixtures', 'system')
SRC = os.path.join(REPO, 'rootfs', 'usr', 'local', 'lib', 'uz', 'settings', 'system.py')


def load():
    spec = importlib.util.spec_from_file_location('uz_system_under_test', SRC)
    m = importlib.util.module_from_spec(spec); spec.loader.exec_module(m)
    return m


def fx(name):
    with open(os.path.join(FIX, name)) as f: return f.read()


class Base(unittest.TestCase):
    TOOLS = {'apt-get', 'hostnamectl', 'timedatectl', 'systemctl', 'systemd-run'}

    def setUp(self):
        self.m = load()
        self.root = tempfile.mkdtemp(prefix='uz-sys-test-')
        self.m.ROOT = self.root
        for d in ('etc/apt/sources.list.d', 'etc/systemd/system/timers.target.wants', 'var/lib/uz', 'var/log',
                  'proc/sys/kernel/random', 'usr/share/zoneinfo/Asia', 'usr/share/zoneinfo/Europe'):
            os.makedirs(os.path.join(self.root, d), exist_ok=True)
        self.put('/proc/sys/kernel/random/boot_id', 'boot-1\n')
        self.put('/proc/meminfo', fx('meminfo'))
        self.put('/etc/hosts', fx('hosts'))
        self.put('/etc/hostname', 'openstick\n')
        self.calls = []
        self.results = {}          # tuple(args prefix) -> (rc, out, err)
        tools = set(self.TOOLS)
        self.m._which = lambda c: f'/usr/bin/{c}' if c in tools else None
        self.tools = tools
        self.m._run = self.fake_run
        self.m.disk_free_mb = lambda path='/': 1000

    def tearDown(self):
        shutil.rmtree(self.root, ignore_errors=True)

    def fake_run(self, args, t=30, env=None):
        self.calls.append(list(args))
        for n in range(len(args), 0, -1):
            if tuple(args[:n]) in self.results: return self.results[tuple(args[:n])]
        return 0, '', ''

    def put(self, path, text):
        p = self.root + path; os.makedirs(os.path.dirname(p), exist_ok=True)
        with open(p, 'w') as f: f.write(text)

    def get(self, path):
        with open(self.root + path) as f: return f.read()


class Validators(Base):
    def test_hostname(self):
        v = self.m.valid_hostname
        for ok in ('a', 'uz801', 'my-stick-2', 'a' * 63, '0abc'):
            self.assertTrue(v(ok), ok)
        for bad in ('', '-a', 'a-', 'A', 'uz_801', 'a.b', 'a' * 64, 'ä', 'a b', None, 5, 'a\n'):
            self.assertFalse(v(bad), repr(bad))

    def test_tz_syntax(self):
        v = self.m.valid_tz_syntax
        for ok in ('UTC', 'Asia/Singapore', 'America/Argentina/Buenos_Aires', 'Etc/GMT+8', 'Etc/GMT-14'):
            self.assertTrue(v(ok), ok)
        for bad in ('', '../etc/passwd', 'Asia/../../x', '/Asia', 'Asia/', 'Asia/Sing apore', 'Asia;rm', 'a' * 65, None):
            self.assertFalse(v(bad), repr(bad))

    def test_time(self):
        for ok in ('00:00', '04:30', '23:59', '19:05'): self.assertTrue(self.m.valid_time(ok), ok)
        for bad in ('24:00', '4:30', '04:60', '04:30:00', '', 'aa:bb', None, 430): self.assertFalse(self.m.valid_time(bad), repr(bad))

    def test_days(self):
        n = self.m.norm_days
        self.assertEqual(n(['sun', 'mon', 'mon']), ['mon', 'sun'])
        self.assertEqual(n([]), [])
        self.assertIsNone(n(['monday']))
        self.assertIsNone(n('mon'))
        self.assertIsNone(n(['mon', 1]))
        self.assertIsNone(n(['mon'] * 8))

    def test_on_calendar(self):
        oc = self.m.on_calendar
        self.assertEqual(oc('04:30', ['mon', 'thu']), 'Mon,Thu *-*-* 04:30:00')
        self.assertEqual(oc('00:05', ['sun']), 'Sun *-*-* 00:05:00')
        self.assertEqual(oc('23:00', list(self.m.DAYS)), '*-*-* 23:00:00')


class Sources(Base):
    def test_oneline_stable(self):
        new, seen, ch = self.m.rewrite_oneline(fx('sources-stable.list'))
        self.assertEqual(seen, ['stable', 'stable-updates', 'stable-security'])
        self.assertEqual(len(ch), 3)
        self.assertIn('deb http://deb.debian.org/debian trixie main contrib non-free-firmware\n', new)
        self.assertIn('trixie-updates', new); self.assertIn('trixie-security', new)
        self.assertNotIn(' stable', new.split('\n', 1)[1])
        self.assertTrue(new.startswith('# openstick.org image default\n'))

    def test_oneline_idempotent(self):
        new, _, _ = self.m.rewrite_oneline(fx('sources-stable.list'))
        again, seen, ch = self.m.rewrite_oneline(new)
        self.assertEqual(again, new); self.assertEqual(ch, [])
        _, _, ch2 = self.m.rewrite_oneline(fx('sources-pinned.list'))
        self.assertEqual(ch2, [])

    def test_oneline_mixed(self):
        src = fx('sources-mixed.list')
        new, seen, ch = self.m.rewrite_oneline(src)
        lines = new.splitlines()
        self.assertEqual(lines[1], 'deb [arch=arm64 signed-by=/usr/share/keyrings/debian-archive-keyring.gpg] https://deb.debian.org/debian trixie main')
        self.assertEqual(lines[2], 'deb http://deb.debian.org/debian trixie-updates main')
        self.assertEqual(lines[3], '#deb http://deb.debian.org/debian stable-backports main')     # comments untouched
        self.assertEqual(lines[4], 'deb-src http://deb.debian.org/debian trixie main')
        self.assertEqual(lines[5], '\tdeb   http://security.debian.org/debian-security   trixie-security   main')  # spacing kept
        self.assertEqual(lines[6], 'deb https://example.com/repo stable main')                     # third party untouched
        self.assertEqual(lines[7], 'deb http://deb.debian.org.evil.example/debian stable main')    # look-alike host untouched
        self.assertEqual(len(ch), 3)

    def test_tailscale_untouched(self):
        src = fx('tailscale.list')
        new, seen, ch = self.m.rewrite_oneline(src)
        self.assertEqual(new, src); self.assertEqual(seen, [])

    def test_deb822(self):
        src = fx('debian-stable.sources')
        new, seen, ch = self.m.rewrite_deb822(src)
        self.assertIn('Suites: trixie trixie-updates\n', new)
        self.assertIn('Suites: trixie-security\n', new)
        self.assertIn('Suites: stable-backports\n', new)            # Enabled: no stanza untouched
        self.assertIn('URIs: https://example.com/other\nSuites: stable\n', new)   # third party untouched
        self.assertEqual(sorted(seen), ['stable', 'stable-security', 'stable-updates'])
        self.assertEqual(len(ch), 3)
        again, _, ch2 = self.m.rewrite_deb822(new)
        self.assertEqual(again, new); self.assertEqual(ch2, [])
        _, _, ch3 = self.m.rewrite_deb822(fx('debian-pinned.sources'))
        self.assertEqual(ch3, [])

    def test_pin_state(self):
        self.put('/etc/apt/sources.list', fx('sources-stable.list'))
        self.put('/etc/apt/sources.list.d/tailscale.list', fx('tailscale.list'))
        st = self.m.pin_state()
        self.assertFalse(st['pinned']); self.assertTrue(st['debian_sources'])
        self.put('/etc/apt/sources.list', fx('sources-pinned.list'))
        self.assertTrue(self.m.pin_state()['pinned'])
        self.put('/etc/apt/sources.list.d/debian.sources', fx('debian-stable.sources'))
        self.assertFalse(self.m.pin_state()['pinned'])            # one stable file is enough to be unpinned
        os.remove(self.root + '/etc/apt/sources.list'); os.remove(self.root + '/etc/apt/sources.list.d/debian.sources')
        st = self.m.pin_state()
        self.assertFalse(st['pinned']); self.assertFalse(st['debian_sources'])   # only tailscale: no Debian lines

    def test_apt_pin_action(self):
        self.put('/etc/apt/sources.list', fx('sources-stable.list'))
        self.put('/etc/apt/sources.list.d/debian.sources', fx('debian-stable.sources'))
        self.put('/etc/apt/sources.list.d/tailscale.list', fx('tailscale.list'))
        os.chmod(self.root + '/etc/apt/sources.list', 0o640)
        r = self.m.ACTIONS['sys-apt-pin']({'suite': 'trixie'})
        self.assertNotIn('error', r, r)
        self.assertEqual(sorted(r['changed']), ['/etc/apt/sources.list', '/etc/apt/sources.list.d/debian.sources'])
        self.assertEqual(len(r['changes']), 6)
        self.assertTrue(r['pin']['pinned'])
        self.assertEqual(self.get('/etc/apt/sources.list.bak'), fx('sources-stable.list'))
        self.assertEqual(self.get('/etc/apt/sources.list.d/debian.sources.bak'), fx('debian-stable.sources'))
        self.assertFalse(os.path.exists(self.root + '/etc/apt/sources.list.d/tailscale.list.bak'))
        self.assertEqual(os.stat(self.root + '/etc/apt/sources.list').st_mode & 0o777, 0o640)
        self.assertEqual(self.get('/etc/apt/sources.list.d/tailscale.list'), fx('tailscale.list'))
        r2 = self.m.ACTIONS['sys-apt-pin']({'suite': 'trixie'})
        self.assertEqual(r2['out'], 'already pinned to trixie'); self.assertEqual(r2['changed'], [])
        self.assertEqual(self.get('/etc/apt/sources.list.bak'), fx('sources-stable.list'))   # .bak not clobbered

    def test_apt_pin_refusals(self):
        self.assertIn('error', self.m.ACTIONS['sys-apt-pin']({'suite': 'stable'}))
        self.assertIn('error', self.m.ACTIONS['sys-apt-pin']({'suite': 'forky'}))
        self.assertIn('no apt sources', self.m.ACTIONS['sys-apt-pin']({})['error'])
        self.put('/etc/apt/sources.list.d/tailscale.list', fx('tailscale.list'))
        self.assertIn('no deb.debian.org', self.m.ACTIONS['sys-apt-pin']({})['error'])
        self.tools.discard('apt-get')
        self.assertIn('not available', self.m.ACTIONS['sys-apt-pin']({})['error'])


class Apt(Base):
    def pinned(self):
        self.put('/etc/apt/sources.list', fx('sources-pinned.list'))

    def test_parse_simulate(self):
        pkgs, held = self.m.parse_simulate(fx('apt-simulate.txt'))
        self.assertEqual(pkgs, ['libc6', 'libc-bin', 'tailscale']); self.assertEqual(held, 1)
        self.assertEqual(self.m.parse_simulate('0 upgraded, 0 newly installed, 0 to remove and 0 not upgraded.'), ([], 0))

    def test_upgrade_refusals(self):
        up = self.m.ACTIONS['sys-apt-upgrade']
        self.assertIn('confirmation', up({})['error'])
        self.assertIn('confirmation', up({'confirm': 'true'})['error'])
        self.put('/etc/apt/sources.list', fx('sources-stable.list'))
        e = up({'confirm': True})['error']
        self.assertIn("not pinned to 'trixie'", e); self.assertIn('next Debian release', e)
        self.pinned()
        self.m.disk_free_mb = lambda path='/': 120
        self.assertIn('120 MB free', up({'confirm': True})['error'])
        self.m.disk_free_mb = lambda path='/': 1000
        self.put('/proc/meminfo', 'MemAvailable: 60000 kB\nSwapFree: 20000 kB\n')
        self.assertIn('RAM+swap', up({'confirm': True})['error'])
        self.put('/proc/meminfo', fx('meminfo'))
        self.m._write_json(self.m.CHECK_JSON, {'state': 'running', 'boot_id': 'boot-1'})
        self.assertIn('already running', up({'confirm': True})['error'])
        self.assertFalse(any(c[0] == 'systemd-run' for c in self.calls))

    def test_upgrade_starts_unit(self):
        self.pinned()
        r = self.m.ACTIONS['sys-apt-upgrade']({'confirm': True})
        self.assertNotIn('error', r, r)
        c = [c for c in self.calls if c[0] == 'systemd-run'][0]
        self.assertIn('--unit=uz-apt-upgrade', c); self.assertEqual(c[-1], '--apt-upgrade'); self.assertEqual(c[-2], self.m.SELF)
        self.assertIn('-I', c)

    def test_stale_running_from_previous_boot(self):
        self.pinned()
        self.m._write_json(self.m.UPGRADE_JSON, {'state': 'running', 'boot_id': 'old-boot'})
        self.assertEqual(self.m._job_state(self.m.UPGRADE_JSON)['state'], 'interrupted')
        self.assertFalse(self.m.status()['apt']['running'])
        self.assertNotIn('error', self.m.ACTIONS['sys-apt-upgrade']({'confirm': True}))

    def test_reconcile_dead_unit(self):
        self.m._write_json(self.m.UPGRADE_JSON, {'state': 'running', 'boot_id': 'boot-1'})
        self.results[('systemctl', 'is-active', 'uz-apt-upgrade')] = (3, 'inactive\n', '')
        st = self.m.ACTIONS['sys-apt-status']({})
        self.assertEqual(st['upgrade']['state'], 'failed'); self.assertIsNone(st['running'])
        self.results[('systemctl', 'is-active', 'uz-apt-upgrade')] = (0, 'active\n', '')
        self.m._write_json(self.m.UPGRADE_JSON, {'state': 'running', 'boot_id': 'boot-1'})
        self.put(self.m.UPGRADE_LOG, 'line1\nline2\n')
        st = self.m.ACTIONS['sys-apt-status']({})
        self.assertEqual(st['running'], 'upgrade'); self.assertEqual(st['log'], 'line1\nline2')

    def test_check(self):
        r = self.m.ACTIONS['sys-apt-check']({})
        self.assertNotIn('error', r, r)
        self.assertIn('--unit=uz-apt-check', [c for c in self.calls if c[0] == 'systemd-run'][0])
        self.results[('systemd-run',)] = (1, '', 'Failed to start transient service unit: Unit uz-apt-check.service already exists.\n')
        self.assertIn('already exists', self.m.ACTIONS['sys-apt-check']({})['error'])

    def test_apk_and_none(self):
        self.tools.discard('apt-get'); self.tools.add('apk')
        self.assertIn('postmarketOS', self.m.ACTIONS['sys-apt-check']({})['error'])
        self.assertIn('postmarketOS', self.m.ACTIONS['sys-apt-upgrade']({'confirm': True})['error'])
        self.tools.discard('apk')
        self.assertIn('not available', self.m.ACTIONS['sys-apt-check']({})['error'])

    def test_no_systemd_run(self):
        self.tools.discard('systemd-run')
        self.assertIn('systemd-run', self.m.ACTIONS['sys-apt-check']({})['error'])

    def test_worker_check(self):
        sim = fx('apt-simulate.txt')
        real_run = self.m.subprocess.run

        class R:  # apt-get update stub
            returncode = 0
        self.m.subprocess.run = lambda *a, **k: R()
        self.results[('apt-get', '-s')] = (0, sim, '')
        try:
            self.assertEqual(self.m.worker_check(), 0)
        finally:
            self.m.subprocess.run = real_run
        st = json.loads(self.get(self.m.CHECK_JSON))
        self.assertEqual((st['state'], st['count'], st['held']), ('done', 3, 1))
        self.assertEqual(st['packages'], ['libc6', 'libc-bin', 'tailscale'])
        s = self.m.status()
        self.assertEqual(s['apt']['updates'], 3); self.assertFalse(s['apt']['running'])

    def test_worker_upgrade_refuses_unpinned(self):
        self.put('/etc/apt/sources.list', fx('sources-stable.list'))
        real_run = self.m.subprocess.run
        self.m.subprocess.run = lambda *a, **k: self.fail('apt-get must not run when unpinned')
        try:
            self.assertEqual(self.m.worker_upgrade(), 1)
        finally:
            self.m.subprocess.run = real_run
        st = json.loads(self.get(self.m.UPGRADE_JSON))
        self.assertEqual(st['state'], 'failed'); self.assertIn('not pinned', st['error'])

    def test_worker_upgrade_command(self):
        self.pinned()
        seen = []
        real_run = self.m.subprocess.run

        class R:
            returncode = 0
        def fake(args, **k):
            seen.append((args, k.get('env', {}).get('DEBIAN_FRONTEND'))); return R()
        self.m.subprocess.run = fake
        self.results[('apt-get', '-s')] = (0, '0 upgraded, 0 newly installed, 0 to remove and 0 not upgraded.', '')
        try:
            self.assertEqual(self.m.worker_upgrade(), 0)
        finally:
            self.m.subprocess.run = real_run
        self.assertEqual(seen[0][0], ['apt-get', '-q', 'update'])
        self.assertEqual(seen[1][0], ['apt-get', '-y', '-o', 'Dpkg::Options::=--force-confold', 'upgrade'])
        self.assertEqual(seen[1][1], 'noninteractive')
        self.assertFalse(any('dist-upgrade' in a or 'full-upgrade' in a for a, _ in seen))
        self.assertEqual(json.loads(self.get(self.m.UPGRADE_JSON))['state'], 'done')
        self.assertEqual(json.loads(self.get(self.m.CHECK_JSON))['count'], 0)
        self.assertIn('finished with exit code 0', self.get(self.m.UPGRADE_LOG))


class Hostname(Base):
    def test_update_hosts(self):
        u = self.m.update_hosts
        self.assertIn('127.0.1.1\tnewname\n', u(fx('hosts'), 'newname'))
        self.assertNotIn('openstick', u(fx('hosts'), 'newname'))
        out = u('127.0.0.1 localhost\n::1 localhost\n', 'x')
        self.assertEqual(out.splitlines()[1], '127.0.1.1\tx')
        out = u('127.0.1.1 a\n127.0.1.1 b\n', 'c')
        self.assertEqual(out, '127.0.1.1\tc\n# 127.0.1.1 b\n')

    def test_set(self):
        r = self.m.ACTIONS['sys-hostname-set']({'hostname': ' My-Stick '})
        self.assertNotIn('error', r, r)
        self.assertEqual(self.calls, [['hostnamectl', 'set-hostname', 'my-stick']])
        self.assertIn('127.0.1.1\tmy-stick', self.get('/etc/hosts'))
        self.assertIn('Tailscale name unchanged', r['out'])
        self.assertFalse(any('tailscale' in c[0] for c in self.calls))

    def test_set_rejects(self):
        for bad in ('-x', 'x-', 'a.b', 'a_b', '', 'a' * 64, '$(reboot)', 5, None):
            r = self.m.ACTIONS['sys-hostname-set']({'hostname': bad})
            self.assertIn('error', r, repr(bad))
        self.assertEqual(self.calls, [])
        self.assertEqual(self.get('/etc/hosts'), fx('hosts'))

    def test_set_failure_keeps_hosts(self):
        self.results[('hostnamectl',)] = (1, '', 'Access denied\n')
        r = self.m.ACTIONS['sys-hostname-set']({'hostname': 'ok'})
        self.assertIn('Access denied', r['error']); self.assertEqual(self.get('/etc/hosts'), fx('hosts'))

    def test_no_hostnamectl(self):
        self.tools.discard('hostnamectl')
        self.assertIn('not available', self.m.ACTIONS['sys-hostname-set']({'hostname': 'ok'})['error'])
        self.assertEqual(self.get('/etc/hosts'), fx('hosts'))


class Timezone(Base):
    def test_set_valid(self):
        self.results[('timedatectl', 'list-timezones')] = (0, 'Asia/Singapore\nEurope/London\nUTC\n', '')
        r = self.m.ACTIONS['sys-timezone-set']({'tz': 'Asia/Singapore'})
        self.assertNotIn('error', r, r)
        self.assertEqual(self.calls[-1], ['timedatectl', 'set-timezone', 'Asia/Singapore'])
        self.assertEqual(self.m.ACTIONS['sys-timezones']({})['zones'], ['Asia/Singapore', 'Europe/London', 'UTC'])

    def test_set_rejects(self):
        self.results[('timedatectl', 'list-timezones')] = (0, 'Asia/Singapore\nUTC\n', '')
        for bad in ('Mars/Olympus', '../../etc/passwd', 'Asia/Singapore;reboot', '', None, 7):
            self.assertIn('error', self.m.ACTIONS['sys-timezone-set']({'tz': bad}), repr(bad))
        self.assertFalse(any(c[:2] == ['timedatectl', 'set-timezone'] for c in self.calls))

    def test_zoneinfo_fallback(self):
        self.results[('timedatectl', 'list-timezones')] = (1, '', 'Failed to connect to bus')
        for z in ('Asia/Singapore', 'Europe/London', 'UTC'):
            self.put('/usr/share/zoneinfo/' + z, 'TZif2...')
        self.put('/usr/share/zoneinfo/zone.tab', '# not a zone\n')
        self.put('/usr/share/zoneinfo/posix/UTC', 'TZif2...')
        self.assertTrue(self.m.tz_known('Asia/Singapore'))
        self.assertFalse(self.m.tz_known('Asia/Tokyo'))
        self.assertNotIn('zone.tab', self.m.timezones()); self.assertNotIn('posix/UTC', self.m.timezones())
        self.m._TZ_CACHE.update(t=0, list=[])
        self.put('/usr/share/zoneinfo/tzdata.zi', 'Z Asia/Singapore 6:55:25 - LMT 1905\nL Europe/London Europe/Jersey\nZ Europe/London 0 - GMT\n')
        self.assertEqual(self.m.timezones(), ['Asia/Singapore', 'Europe/London', 'UTC'])   # Jersey has no file here

    def test_cheap_tz(self):
        self.put('/etc/timezone', 'Asia/Singapore\n')
        self.assertEqual(self.m.get_tz_cheap(), 'Asia/Singapore')
        os.remove(self.root + '/etc/timezone')
        os.symlink('/usr/share/zoneinfo/Europe/London', self.root + '/etc/localtime')
        self.assertEqual(self.m.get_tz_cheap(), 'Europe/London')


class Reboot(Base):
    def test_enable(self):
        r = self.m.ACTIONS['sys-reboot-schedule']({'enabled': True, 'time': '04:30', 'days': ['thu', 'mon']})
        self.assertNotIn('error', r, r)
        timer = self.get(self.m.TIMER)
        self.assertIn('OnCalendar=Mon,Thu *-*-* 04:30:00\n', timer)
        self.assertIn('Persistent=false', timer); self.assertIn('WantedBy=timers.target', timer)
        svc = self.get(self.m.SERVICE)
        self.assertIn('ExecStart=/bin/systemctl reboot', svc); self.assertIn('uz-apt-upgrade', svc)
        self.assertEqual(self.calls, [['systemctl', 'daemon-reload'], ['systemctl', 'enable', 'uz-reboot.timer'],
                                      ['systemctl', 'restart', 'uz-reboot.timer']])
        os.symlink('../uz-reboot.timer', self.root + self.m.TIMER_WANTS)   # what `systemctl enable` would do
        self.assertEqual(self.m.reboot_state(), {'enabled': True, 'time': '04:30', 'days': ['mon', 'thu']})
        self.assertEqual(self.m.status()['reboot'], {'enabled': True, 'time': '04:30'})

    def test_daily(self):
        self.m.ACTIONS['sys-reboot-schedule']({'enabled': True, 'time': '03:00', 'days': list(self.m.DAYS)})
        self.assertIn('OnCalendar=*-*-* 03:00:00\n', self.get(self.m.TIMER))

    def test_disable(self):
        self.m.ACTIONS['sys-reboot-schedule']({'enabled': True, 'time': '03:00', 'days': ['sun']})
        self.calls.clear()
        r = self.m.ACTIONS['sys-reboot-schedule']({'enabled': False})
        self.assertNotIn('error', r, r)
        self.assertEqual(self.calls, [['systemctl', 'disable', '--now', 'uz-reboot.timer']])
        self.assertFalse(self.m.reboot_state()['enabled'])
        self.calls.clear(); os.remove(self.root + self.m.TIMER)
        self.assertNotIn('error', self.m.ACTIONS['sys-reboot-schedule']({'enabled': False}))
        self.assertEqual(self.calls, [])                                     # nothing to disable

    def test_rejects(self):
        rs = self.m.ACTIONS['sys-reboot-schedule']
        for body in ({}, {'enabled': 'yes'}, {'enabled': True, 'time': '25:00', 'days': ['mon']},
                     {'enabled': True, 'time': '04:00', 'days': []}, {'enabled': True, 'time': '04:00', 'days': ['funday']},
                     {'enabled': True, 'time': '04:00\nExecStart=/bin/sh', 'days': ['mon']},
                     {'enabled': True, 'time': '04:00', 'days': 'mon'}):
            self.assertIn('error', rs(body), body)
        self.assertEqual(self.calls, [])
        self.assertFalse(os.path.exists(self.root + self.m.TIMER))

    def test_no_systemd(self):
        self.tools.discard('systemctl')
        self.assertIn('systemd', self.m.ACTIONS['sys-reboot-schedule']({'enabled': True, 'time': '04:00', 'days': ['mon']})['error'])


class Overview(Base):
    def test_sys_get_and_status(self):
        self.put('/etc/os-release', fx('os-release'))
        self.put('/proc/uptime', '12345.6 999.0\n')
        self.put('/etc/apt/sources.list', fx('sources-stable.list'))
        self.results[('timedatectl', 'show')] = (0, 'Timezone=Asia/Singapore\nNTPSynchronized=yes\nNTP=yes\n', '')
        g = self.m.ACTIONS['sys-get']({})
        self.assertNotIn('error', g, g)
        self.assertEqual((g['hostname'], g['tz'], g['ntp_synced'], g['os'], g['uptime'], g['pkg']),
                         ('openstick', 'Asia/Singapore', True, 'Debian GNU/Linux 13 (trixie)', 12345.6, 'apt'))
        self.assertFalse(g['pin']['pinned']); self.assertEqual(g['mem_free_mb'], 244)
        json.dumps(g)
        s = self.m.status()
        self.assertEqual(s['apt'], {'pinned': False, 'updates': None, 'running': False, 'upgrade': None})
        self.assertEqual(s['hostname'], 'openstick')

    def test_status_makes_no_subprocess_calls(self):
        self.m.status(); self.assertEqual(self.calls, [])

    def test_bad_body_types(self):
        for name, fn in self.m.ACTIONS.items():
            r = fn(None)   # non-dict body must not raise
            self.assertIsInstance(r, dict, name)

    def test_empty_root(self):
        # nothing present at all (like a Mac): no exceptions, clean errors
        self.m.ROOT = tempfile.mkdtemp(prefix='uz-sys-empty-')
        self.tools.clear()
        try:
            self.assertIn('hostname', self.m.ACTIONS['sys-get']({}))
            self.m.status()
            for name, body in (('sys-hostname-set', {'hostname': 'x'}), ('sys-timezone-set', {'tz': 'UTC'}),
                               ('sys-apt-pin', {}), ('sys-apt-check', {}), ('sys-apt-upgrade', {'confirm': True}),
                               ('sys-reboot-schedule', {'enabled': False}), ('sys-timezones', {})):
                self.assertIn('error', self.m.ACTIONS[name](body), name)
            self.assertEqual(self.calls, [])
        finally:
            shutil.rmtree(self.m.ROOT, ignore_errors=True)



class TailscalePin(Base):
    def test_pins_tailscale_name_before_hostname(self):
        self.tools.add('tailscale')
        self.results[('tailscale', 'status', '--json')] = (0, json.dumps({'Self': {'DNSName': '4g-stick-uz801.tail.ts.net.'}}), '')
        r = self.m.hostname_set({'hostname': 'newname'})
        self.assertNotIn('error', r)
        names = [c[:2] for c in self.calls]
        i_pin = self.calls.index(['tailscale', 'set', '--hostname=4g-stick-uz801'])
        i_host = names.index(['hostnamectl', 'set-hostname'])
        self.assertLess(i_pin, i_host)

    def test_pin_failure_leaves_hostname(self):
        self.tools.add('tailscale')
        self.results[('tailscale', 'status', '--json')] = (0, json.dumps({'Self': {'DNSName': 'uz.tail.ts.net.'}}), '')
        self.results[('tailscale', 'set')] = (1, '', 'boom')
        r = self.m.hostname_set({'hostname': 'newname'})
        self.assertIn('error', r)
        self.assertFalse(any(c[:1] == ['hostnamectl'] for c in self.calls))

if __name__ == '__main__':
    unittest.main(verbosity=1)
