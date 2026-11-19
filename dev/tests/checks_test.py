#!/usr/bin/env python3
"""Unit tests for the Uptime checks settings module. Run: python3 dev/tests/checks_test.py"""
import importlib.util, os, shutil, stat, sys, tempfile, unittest
from unittest import mock

R = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
FX = os.path.join(R, 'dev', 'fixtures', 'checks')
spec = importlib.util.spec_from_file_location('checks', os.path.join(R, 'rootfs/usr/local/lib/uz/settings/checks.py'))
m = importlib.util.module_from_spec(spec); spec.loader.exec_module(m)


def rd(p):
    with open(p) as f: return f.read()


def wr(p, s):
    with open(p, 'w') as f: f.write(s)


def fx(n):
    with open(os.path.join(FX, n)) as f: return f.read()


class Ctx: cache = {}


class Run:
    """Stands in for subprocess.run; records argv, answers systemctl show from the fixture."""
    def __init__(self, fail=None): self.calls, self.fail = [], fail or set()
    def __call__(self, args, **kw):
        assert isinstance(args, list), 'shell strings are forbidden'
        self.calls.append(args)
        out = fx('systemctl_show_timers.txt') if args[:2] == ['systemctl', 'show'] else ''
        rc = 1 if args[1] in self.fail else 0
        return mock.Mock(returncode=rc, stdout=out, stderr='boom' if rc else '')


class Parse(unittest.TestCase):
    def test_parse_list_keeps_comments(self):
        p = m.parse_list(fx('probe.list'))
        self.assertEqual(len(p['header']), 2)
        self.assertEqual([i['target'] for i in p['items']],
                         ['https://google.com', 'ping:1.1.1.1', 'tcp:home.example.net:22', 'HTTPS://Example.ORG/health', 'ftp://bad.example.com'])
        self.assertEqual(p['items'][1]['comments'], ['# DNS over 4G'])
        self.assertEqual(p['trailer'], ['# trailing note'])

    def test_render_reorder_remove_add(self):
        p = m.parse_list(fx('probe.list'))
        out = m.render_list(p, ['tcp:home.example.net:22', 'https://new.example.com'])
        lines = out.splitlines()
        self.assertEqual(lines[:2], p['header'])
        self.assertEqual(lines[2:4], ['# home server SSH', 'tcp:home.example.net:22'])
        self.assertIn('https://new.example.com', lines)
        self.assertIn('# DNS over 4G', lines)          # comment of a removed target is kept (moved to the end)
        self.assertEqual(lines[-1], '# trailing note')
        # what uz-probe would read back
        self.assertEqual([l.strip() for l in out.splitlines() if l.strip() and not l.startswith('#')],
                         ['tcp:home.example.net:22', 'https://new.example.com'])

    def test_render_default_header(self):
        out = m.render_list(m.parse_list(''), ['ping:8.8.8.8'])
        self.assertTrue(out.startswith('# One target per line'))
        self.assertEqual(m.parse_list('# only comments\n')['header'], ['# only comments'])

    def test_targets(self):
        ok = {'https://google.com': 'https://google.com', 'HTTPS://Example.ORG/health': 'https://Example.ORG/health',
              'http://192.168.1.1:8080/x?y=1': 'http://192.168.1.1:8080/x?y=1', 'https://[2606:4700::1111]/': 'https://[2606:4700::1111]/',
              ' tcp:1.1.1.1:53 ': 'tcp:1.1.1.1:53', 'TCP:home.example.net:022': 'tcp:home.example.net:22',
              'ping:1.1.1.1': 'ping:1.1.1.1', 'ping:router.lan': 'ping:router.lan'}
        for raw, want in ok.items():
            self.assertEqual(m.normalize(raw), (want, None), raw)
        bad = ['ftp://x.com', 'https://', 'https://exa mple.com', 'https://-bad.com', 'https://x.com:99999/',
               'https://x.com/' + 'a' * 200, 'https://exämple.com', 'tcp:host', 'tcp:host:0', 'tcp:host:65536',
               'tcp:host:-1', 'tcp:[::1]:22', 'tcp:::1:22', 'tcp:h;rm -rf /:22', 'ping:', 'ping:-c1000', 'ping:1.2.3.999',
               'ping:a b', 'ping:$(reboot)', 'example.com', '', 5, None]
        for raw in bad:
            self.assertIsNotNone(m.normalize(raw)[1], raw)

    def test_validate_targets(self):
        self.assertEqual(m.validate_targets(['ping:a.b', 'ping:a.b'])[0], ['ping:a.b'])
        self.assertIsNotNone(m.validate_targets([f'ping:h{i}.example' for i in range(21)])[1])
        self.assertIsNotNone(m.validate_targets('ping:x')[1])

    def test_interval_parsing(self):
        self.assertEqual(m.span_seconds('5min'), 300); self.assertEqual(m.span_seconds('1h 30min'), 5400)
        self.assertEqual(m.span_seconds('90'), 90); self.assertEqual(m.span_seconds('1min 30s'), 90)
        self.assertIsNone(m.span_seconds('soon')); self.assertIsNone(m.span_seconds(''))
        self.assertEqual(m.interval_from_show(fx('systemctl_show_timers.txt')), 600)
        self.assertIsNone(m.interval_from_show('{ OnBootUSec=3min ; next_elapse=0 }'))
        self.assertEqual(m.interval_from_unit(rd(os.path.join(R, 'rootfs/etc/systemd/system/uz-probe.timer'))), 300)
        self.assertEqual(m.interval_from_unit(m.render_dropin(15)), 900)
        self.assertIsNone(m.interval_from_unit('[Timer]\nOnUnitActiveSec=\n'))
        for v in (0, 61, '5', 5.0, True, None): self.assertIsNotNone(m.validate_interval(v)[1], v)
        self.assertEqual(m.validate_interval(60), (60, None))


class Actions(unittest.TestCase):
    def setUp(self):
        self.d = tempfile.TemporaryDirectory()
        self.etc = os.path.join(self.d.name, 'etc-uz'); self.sysd = os.path.join(self.d.name, 'systemd')
        os.makedirs(self.etc); os.makedirs(self.sysd)
        shutil.copy(os.path.join(FX, 'probe.list'), os.path.join(self.etc, 'probe.list'))
        shutil.copy(os.path.join(R, 'rootfs/etc/systemd/system/uz-probe.timer'), self.sysd)
        os.environ.update(UZ_ETC=self.etc, UZ_SYSTEMD_DIR=self.sysd)

    def tearDown(self):
        for k in ('UZ_ETC', 'UZ_SYSTEMD_DIR'): os.environ.pop(k, None)
        self.d.cleanup()

    def test_get(self):
        run = Run()
        with mock.patch.object(m.subprocess, 'run', run), mock.patch.object(m.shutil, 'which', lambda x: '/bin/' + x):
            r = m.get({}, Ctx)
        self.assertEqual(r['interval_min'], 10); self.assertEqual(r['interval_src'], 'systemd')
        self.assertEqual([t['kind'] for t in r['targets']], ['https', 'ping', 'tcp', '', ''])
        self.assertEqual([t['valid'] for t in r['targets']], [True, True, True, True, False])
        self.assertEqual(r['targets'][2]['note'], 'home server SSH')
        with mock.patch.object(m.shutil, 'which', lambda x: None):
            r = m.get({}, Ctx)
        self.assertEqual((r['interval_min'], r['interval_src']), (5, 'file'))
        self.assertEqual(m.status(Ctx), {'count': 5, 'interval_min': 5})

    def test_set_targets_and_interval(self):
        run = Run()
        with mock.patch.object(m.subprocess, 'run', run), mock.patch.object(m.shutil, 'which', lambda x: '/bin/' + x):
            r = m.set_({'targets': ['ping:9.9.9.9', 'https://google.com'], 'interval_min': 15}, Ctx)
        self.assertNotIn('error', r, r)
        self.assertEqual(run.calls, [['systemctl', 'daemon-reload'], ['systemctl', 'restart', 'uz-probe.timer']])
        dropin = rd(os.path.join(self.sysd, 'uz-probe.timer.d/interval.conf'))
        self.assertIn('[Timer]\nOnUnitActiveSec=\nOnUnitActiveSec=15min\n', dropin)
        self.assertEqual(stat.S_IMODE(os.stat(os.path.join(self.etc, 'probe.list')).st_mode), 0o644)
        text = rd(os.path.join(self.etc, 'probe.list'))
        self.assertEqual([l for l in text.splitlines() if not l.startswith('#')], ['ping:9.9.9.9', 'https://google.com'])
        self.assertIn('# my own header note', text)
        self.assertEqual(m.status(Ctx), {'count': 2, 'interval_min': 15})
        # same interval again -> no reload
        run2 = Run()
        with mock.patch.object(m.subprocess, 'run', run2), mock.patch.object(m.shutil, 'which', lambda x: '/bin/' + x):
            m.set_({'targets': ['ping:9.9.9.9'], 'interval_min': 15}, Ctx)
        self.assertEqual(run2.calls, [])

    def test_set_rejects_before_writing(self):
        before = rd(os.path.join(self.etc, 'probe.list'))
        for body in ({'targets': ['ping:ok.example', 'tcp:x:0']}, {'targets': ['ping:a'], 'interval_min': 0},
                     {'interval_min': '5'}, {}, []):
            self.assertIn('error', m.set_(body, Ctx), body)
        with mock.patch.object(m.shutil, 'which', lambda x: None):
            self.assertIn('not available', m.set_({'targets': ['ping:a'], 'interval_min': 7}, Ctx)['error'])
        self.assertEqual(rd(os.path.join(self.etc, 'probe.list')), before)
        self.assertFalse(os.path.exists(os.path.join(self.sysd, 'uz-probe.timer.d')))

    def test_reload_failure_reported(self):
        with mock.patch.object(m.subprocess, 'run', Run(fail={'restart'})), mock.patch.object(m.shutil, 'which', lambda x: '/bin/' + x):
            r = m.set_({'interval_min': 2}, Ctx)
        self.assertIn('restart uz-probe.timer failed', r['error'])

    def test_run_now(self):
        run = Run()
        with mock.patch.object(m.subprocess, 'run', run), mock.patch.object(m.shutil, 'which', lambda x: '/bin/' + x):
            self.assertNotIn('error', m.run_now({}, Ctx))
        self.assertEqual(run.calls, [['systemctl', 'start', '--no-block', 'uz-probe.service']])
        with mock.patch.object(m.shutil, 'which', lambda x: None):
            self.assertIn('error', m.run_now({}, Ctx))

    def test_missing_etc(self):
        os.environ['UZ_ETC'] = os.path.join(self.d.name, 'nope')
        self.assertIn('not available', m.set_({'targets': []}, Ctx)['error'])
        with mock.patch.object(m.shutil, 'which', lambda x: None):
            self.assertEqual(m.get({}, Ctx)['warn'], 'not available on this host')


if __name__ == '__main__':
    unittest.main(verbosity=1 if len(sys.argv) == 1 else 2)
