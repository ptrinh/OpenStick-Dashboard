#!/usr/bin/env python3
"""Unit tests for the Hotspot (advanced) settings module. Run: python3 dev/tests/hotspot_test.py"""
import importlib.util, os, shutil, sys, tempfile, unittest
from unittest import mock

R = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
FX = os.path.join(R, 'dev', 'fixtures', 'hotspot')
spec = importlib.util.spec_from_file_location('hotspot', os.path.join(R, 'rootfs/usr/local/lib/uz/settings/hotspot.py'))
m = importlib.util.module_from_spec(spec); spec.loader.exec_module(m)
NOW = 1_800_000_000


def fx(n):
    with open(os.path.join(FX, n)) as f: return f.read()


class Ctx:
    def __init__(self, conf=None): self.cache, self._conf, self.set = {}, dict(conf or {}), []
    def conf(self): return dict(self._conf)
    def set_conf(self, k, v): self.set.append((k, v)); self._conf[k] = v


class NM:
    """Stands in for subprocess.run (nmcli / ip)."""
    def __init__(self, profile='nmcli_profile.txt', active='nmcli_active.txt', modify_rc=0):
        self.profile, self.active, self.modify_rc, self.calls = profile, active, modify_rc, []
    def __call__(self, args, **kw):
        assert isinstance(args, list), 'shell strings are forbidden'
        self.calls.append(args); out, rc, err = '', 0, ''
        if args[0] == 'nmcli' and args[-2:] == ['show', 'uz-hotspot'] or args[-1] == 'uz-hotspot' and 'show' in args:
            if self.profile: out = fx(self.profile) if args[2] != 'connection.id' else 'uz-hotspot\n'
            else: rc, err = 10, 'Error: uz-hotspot - no such connection profile.'
        elif args[0] == 'nmcli' and '--active' in args: out = fx(self.active)
        elif args[:2] == ['nmcli', 'connection'] and args[2] == 'modify': rc = self.modify_rc; err = 'Error: bad' if rc else ''
        elif args[:2] == ['ip', 'neigh']: out = fx('ip_neigh.txt')
        return mock.Mock(returncode=rc, stdout=out, stderr=err)


class Parse(unittest.TestCase):
    def test_profile(self):
        self.assertEqual(m.parse_profile(fx('nmcli_profile.txt')), {'band': 'bg', 'channel': 6, 'hidden': True, 'key_mgmt': 'wpa-psk'})
        self.assertEqual(m.parse_profile(fx('nmcli_profile_auto.txt'))['channel'], 0)
        self.assertEqual(m.parse_profile(''), {'band': '', 'channel': 0, 'hidden': False, 'key_mgmt': ''})

    def test_active(self):
        self.assertEqual(m.active_device(fx('nmcli_active.txt')), 'wlan0')
        self.assertEqual(m.active_device(fx('nmcli_active_off.txt')), '')
        self.assertEqual(m.split_terse('Home\\: Wi-Fi:wlan0'), ['Home: Wi-Fi', 'wlan0'])
        self.assertEqual(m.active_device('uz-hotspot:wlan0;rm\n'), '')

    def test_leases(self):
        ls = m.parse_leases(fx('dnsmasq-wlan0.leases'), now=NOW)
        self.assertEqual([l['ip'] for l in ls], ['10.42.0.23', '10.42.0.57', '10.42.0.99'])   # expired + garbage dropped
        self.assertEqual(ls[0]['hostname'], 'Phils-iPhone'); self.assertEqual(ls[1]['hostname'], '')
        self.assertEqual(m.parse_leases('1999999999 aa:bb:cc:dd:ee:ff 10.0.0.2 ev\x07il *', now=NOW)[0]['hostname'], 'evil')

    def test_neigh_and_clients(self):
        n = m.parse_neigh(fx('ip_neigh.txt'))
        self.assertEqual(n['10.42.0.23'], {'mac': 'a4:83:e7:12:34:5c', 'state': 'REACHABLE'})
        self.assertEqual(n['10.42.0.99'], {'mac': '', 'state': 'FAILED'})
        cs = m.clients(m.parse_leases(fx('dnsmasq-wlan0.leases'), now=NOW), n)
        self.assertEqual([(c['ip'], c['online'], c['state']) for c in cs],
                         [('10.42.0.23', True, 'REACHABLE'), ('10.42.0.200', True, 'DELAY'),
                          ('10.42.0.99', False, 'FAILED'), ('10.42.0.57', False, 'STALE')])
        self.assertEqual(cs[0]['mac'], 'a4:83:e7:xx:xx:5c')
        self.assertTrue(all('xx:xx' in c['mac'] for c in cs))
        self.assertNotIn('12:34', repr(cs))

    def test_validate(self):
        self.assertEqual(m.validate({'channel': 0, 'hidden': False}), (0, False, None))
        self.assertEqual(m.validate({'channel': 13, 'hidden': True, 'security': 'wpa2'}), (13, True, None))
        for b in ({'channel': 14, 'hidden': False}, {'channel': -1, 'hidden': False}, {'channel': '6', 'hidden': False},
                  {'channel': True, 'hidden': False}, {'channel': 6, 'hidden': 'yes'}, {'channel': 6, 'hidden': False, 'security': 'wpa2-wpa3'},
                  {'channel': 6}, [], None):
            self.assertIsNotNone(m.validate(b)[2], b)

    def test_prefs(self):
        self.assertEqual(m.prefs({'UZ_HOTSPOT_CHANNEL': '11', 'UZ_HOTSPOT_HIDDEN': '1'}), {'channel': 11, 'hidden': True, 'set': True})
        self.assertEqual(m.prefs({'UZ_HOTSPOT_CHANNEL': '99'})['channel'], 0)
        self.assertFalse(m.prefs({})['set'])


class Actions(unittest.TestCase):
    def setUp(self):
        self.d = tempfile.TemporaryDirectory(); os.environ['UZ_NM_DIR'] = self.d.name
        shutil.copy(os.path.join(FX, 'dnsmasq-wlan0.leases'), self.d.name)
        self.which = mock.patch.object(m.shutil, 'which', lambda x: '/usr/bin/' + x); self.which.start()

    def tearDown(self):
        self.which.stop(); os.environ.pop('UZ_NM_DIR', None); self.d.cleanup()

    def test_get_active(self):
        nm, ctx = NM(), Ctx()
        with mock.patch.object(m.subprocess, 'run', nm):
            r = m.get({}, ctx)
        self.assertTrue(r['profile'] and r['active']); self.assertEqual((r['channel'], r['hidden']), (6, True))
        self.assertEqual(r['device'], 'wlan0'); self.assertEqual(len(r['clients']), 4)
        self.assertIn(['nmcli', '-g', ','.join(m.FIELDS), 'connection', 'show', 'uz-hotspot'], nm.calls)
        self.assertIn(['ip', 'neigh', 'show', 'dev', 'wlan0'], nm.calls)
        self.assertEqual(m.status(ctx)['channel'], 6)

    def test_get_no_profile(self):
        with mock.patch.object(m.subprocess, 'run', NM(profile=None, active='nmcli_active_off.txt')):
            r = m.get({}, Ctx({'UZ_HOTSPOT_CHANNEL': '1'}))
        self.assertFalse(r['profile'] or r['active']); self.assertEqual(r['prefs']['channel'], 1); self.assertEqual(r['clients'], [])

    def test_set_active_restarts(self):
        nm, ctx = NM(), Ctx()
        with mock.patch.object(m.subprocess, 'run', nm), mock.patch.object(m.subprocess, 'Popen') as po:
            r = m.set_({'channel': 11, 'hidden': False, 'security': 'wpa2'}, ctx)
        self.assertTrue(r.get('restarting'), r)
        self.assertIn(['nmcli', 'connection', 'modify', 'uz-hotspot', '802-11-wireless.band', 'bg',
                       '802-11-wireless.channel', '11', '802-11-wireless.hidden', 'no'], nm.calls)
        self.assertEqual(po.call_args[0][0], ['systemd-run', '--collect', '--quiet', 'nmcli', 'connection', 'up', 'uz-hotspot'])
        self.assertEqual(ctx.set, [('UZ_HOTSPOT_CHANNEL', '11'), ('UZ_HOTSPOT_HIDDEN', '0')])

    def test_set_inactive_no_restart(self):
        with mock.patch.object(m.subprocess, 'run', NM(active='nmcli_active_off.txt')), mock.patch.object(m.subprocess, 'Popen') as po:
            r = m.set_({'channel': 0, 'hidden': True}, Ctx())
        self.assertNotIn('error', r); po.assert_not_called()

    def test_set_no_profile_stores_pref(self):
        nm, ctx = NM(profile=None), Ctx()
        with mock.patch.object(m.subprocess, 'run', nm):
            r = m.set_({'channel': 6, 'hidden': True}, ctx)
        self.assertTrue(r['pending']); self.assertEqual(ctx.set, [('UZ_HOTSPOT_CHANNEL', '6'), ('UZ_HOTSPOT_HIDDEN', '1')])
        self.assertFalse(any(c[:3] == ['nmcli', 'connection', 'modify'] for c in nm.calls))

    def test_set_errors(self):
        with mock.patch.object(m.subprocess, 'run', NM(modify_rc=1)):
            self.assertEqual(m.set_({'channel': 6, 'hidden': False}, Ctx())['error'], 'Error: bad')
        self.assertIn('error', m.set_({'channel': 6, 'hidden': False, 'security': 'sae'}, Ctx()))
        bad = Ctx(); bad.set_conf = lambda k, v: (_ for _ in ()).throw(OSError('ro'))
        with mock.patch.object(m.subprocess, 'run', NM()):
            self.assertIn('could not save', m.set_({'channel': 6, 'hidden': False}, bad)['error'])

    def test_no_nmcli(self):
        self.which.stop()
        with mock.patch.object(m.shutil, 'which', lambda x: None):
            self.assertIn('not available', m.get({}, Ctx())['error'])
            self.assertIn('not available', m.set_({'channel': 6, 'hidden': False}, Ctx())['error'])
        self.which.start()


if __name__ == '__main__':
    unittest.main(verbosity=1 if len(sys.argv) == 1 else 2)
