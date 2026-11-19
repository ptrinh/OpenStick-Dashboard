#!/usr/bin/env python3
"""Unit tests for the Cellular settings module. Run: python3 dev/tests/cellular_test.py"""
import importlib.util, json, os, subprocess, sys, time, unittest

R = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
FX = os.path.join(R, 'dev', 'fixtures', 'cellular')
spec = importlib.util.spec_from_file_location('cellular', os.path.join(R, 'rootfs/usr/local/lib/uz/settings/cellular.py'))
cell = importlib.util.module_from_spec(spec); spec.loader.exec_module(cell)

def fx(n):
    with open(os.path.join(FX, n)) as f: return f.read()

PIN, PW, ICCID, IMSI = '4711', 'S3cr3t-pw', '8984048000012345678', '452041234567890'


class Ctx:
    def __init__(self): self.cache, self.bg = {}, []
    def run_bg(self, cmd): self.bg.append(cmd)
    def conf(self): return {}


class Fake:
    """Stands in for subprocess.run; answers from fixtures and records every argv."""
    def __init__(self, modem, sim=None, nm='nm_lte.txt'):
        self.modem, self.sim, self.nm, self.calls, self.fail = modem, sim, nm, [], {}

    def __call__(self, args, **kw):
        assert isinstance(args, list), 'shell strings are forbidden'
        self.calls.append(args)
        out, rc, err = '', 0, ''
        if args[:2] == ['mmcli', '-m'] and args[-1] == '-K': out = fx(self.modem)
        elif args[:2] == ['mmcli', '-i'] and args[-1] == '-K': out = fx(self.sim) if self.sim else ''
        elif args[:3] == ['nmcli', '-g', 'gsm.apn,gsm.username,gsm.password-flags,gsm.home-only,ipv4.method,ipv6.method']:
            if self.nm: out = fx(self.nm)
            else: rc, err = 10, 'Error: lte - no such connection profile.'
        for k, (frc, ferr) in self.fail.items():
            if any(k in a for a in args): rc, err = frc, ferr
        return subprocess.CompletedProcess(args, rc, out, err)


class Base(unittest.TestCase):
    def setUp(self):
        self._run = cell.subprocess.run
        cell._backend['v'] = True
        cell._state.update(t=time.time(), busy=False)     # keep background refresh threads quiet
        os.environ.pop('UZ_BACKEND', None)
        self.ctx = Ctx()

    def tearDown(self):
        cell.subprocess.run = self._run

    def use(self, *a, **k):
        f = Fake(*a, **k); cell.subprocess.run = f; return f

    def assertNoSecrets(self, obj, *secrets):
        s = json.dumps(obj, ensure_ascii=False)
        for x in secrets: self.assertNotIn(x, s)


class Parsers(unittest.TestCase):
    def test_kv_multi_and_empty(self):
        m = cell.parse_kv(fx('modem_roaming.txt'))
        self.assertEqual(len(m['modem.generic.supported-modes']), 7)
        self.assertEqual(m['modem.generic.supported-modes'][4], 'allowed: 3g, 4g; preferred: 4g')
        self.assertEqual(m['modem.3gpp.pco'], '')
        self.assertEqual(m['modem.generic.own-numbers'], ['+84912345678'])
        self.assertEqual(cell.parse_kv(fx('modem_nosim.txt'))['modem.generic.supported-modes'], [])

    def test_retries(self):
        self.assertEqual(cell.parse_retries(['sim-pin (2)', 'sim-puk (10)']), {'sim-pin': 2, 'sim-puk': 10})

    def test_sim_state(self):
        self.assertEqual(cell.sim_state(cell.parse_kv(fx('modem_nosim.txt'))), 'missing')
        self.assertEqual(cell.sim_state(cell.parse_kv(fx('modem_locked.txt'))), 'locked')
        self.assertEqual(cell.sim_state(cell.parse_kv(fx('modem_roaming.txt'))), 'ready')
        self.assertEqual(cell.sim_state({}), 'unknown')

    def test_nm(self):
        d = cell.parse_nm(fx('nm_lte.txt'))
        self.assertEqual((d['apn'], d['ip_type'], d['roaming_allowed']), ('internet', 'ipv4v6', True))
        d = cell.parse_nm(fx('nm_lte_user.txt'))
        self.assertEqual((d['username'], d['ip_type'], d['roaming_allowed']), ('user:name', 'ipv4', False))

    def test_mode_args(self):
        self.assertEqual(cell.mode_args('allowed: 4g; preferred: none'), ['--set-allowed-modes=4g'])
        self.assertEqual(cell.mode_args('allowed: 2g, 3g, 4g; preferred: 4g'),
                         ['--set-allowed-modes=2g|3g|4g', '--set-preferred-mode=4g'])
        self.assertIsNone(cell.mode_args('allowed: 4g; preferred: none; rm -rf /'))
        self.assertIsNone(cell.mode_args('allowed: 6g; preferred: none'))

    def test_masks(self):
        self.assertEqual(cell.mask_tail(ICCID), '•' * 15 + '5678')
        self.assertEqual(cell.mask_imsi(IMSI), '45204' + '•' * 10)
        self.assertEqual(cell.mask_tail(''), '')


class Get(Base):
    def test_no_sim(self):
        self.use('modem_nosim.txt')
        r = cell.ACTIONS['cell-get']({}, self.ctx)
        self.assertEqual(r['sim']['state'], 'missing')
        self.assertEqual(r['sim']['failed_reason'], 'sim-missing')
        self.assertEqual(r['modes']['supported'], [])
        self.assertEqual(self.ctx.cache['cellular']['sim'], 'missing')

    def test_locked(self):
        self.use('modem_locked.txt', 'sim_locked.txt')
        r = cell.ACTIONS['cell-get']({}, self.ctx)
        self.assertEqual((r['sim']['state'], r['sim']['unlock_required']), ('locked', 'sim-pin'))
        self.assertEqual(r['sim']['unlock_retries']['sim-pin'], 2)
        self.assertEqual(r['sim']['iccid'][-4:], '5678')
        self.assertNoSecrets(r, ICCID, ICCID[:-4])

    def test_roaming(self):
        f = self.use('modem_roaming.txt', 'sim_ready.txt')
        r = cell.ACTIONS['cell-get']({}, self.ctx)
        self.assertEqual(r['sim']['state'], 'ready')
        self.assertTrue(r['network']['roaming'])
        self.assertTrue(r['sim']['pin_lock'])
        self.assertEqual(r['sim']['operator'], 'Viettel')
        self.assertEqual(r['profile']['apn'], 'internet')
        self.assertEqual(r['modes']['current'], 'allowed: 2g, 3g, 4g; preferred: 4g')
        self.assertNoSecrets(r, ICCID, IMSI, '1234567890')
        self.assertNotIn('password', json.dumps(r['profile']).replace('password_flags', ''))
        self.assertIn(['mmcli', '-i', '/org/freedesktop/ModemManager1/SIM/0', '-K'], f.calls)
        self.assertEqual(cell.summarize(cell.parse_kv(fx('modem_roaming.txt')), cell.parse_nm(fx('nm_lte.txt')))['roaming'], True)

    def test_no_profile(self):
        self.use('modem_roaming.txt', 'sim_ready.txt', nm=None)
        r = cell.ACTIONS['cell-get']({}, self.ctx)
        self.assertIsNone(r['profile'])
        self.assertIn('not found', cell.ACTIONS['cell-roaming-set']({'allow': True}, self.ctx)['error'])


class Apn(Base):
    def test_validation(self):
        f = self.use('modem_roaming.txt')
        for body in ({'apn': 'bad apn'}, {'apn': 'x;rm'}, {'apn': 'a' * 64}, {'apn': 5}, {'apn': 'ok', 'ip_type': 'ipx'},
                     {'apn': 'ok', 'password': 'a\nb'}, {'apn': 'ok', 'username': 'x' * 65}):
            self.assertIn('error', cell.ACTIONS['cell-apn-set'](body, self.ctx), body)
        self.assertFalse([c for c in f.calls if 'modify' in c])

    def test_apply(self):
        f = self.use('modem_roaming.txt')
        r = cell.ACTIONS['cell-apn-set']({'apn': 'v-internet', 'username': 'u', 'password': PW, 'ip_type': 'ipv4'}, self.ctx)
        self.assertNotIn('error', r)
        mod = [c for c in f.calls if 'modify' in c][0]
        self.assertEqual(mod[:4], ['nmcli', 'connection', 'modify', 'lte'])
        a = dict(zip(mod[4::2], mod[5::2]))
        self.assertEqual((a['gsm.apn'], a['gsm.auto-config'], a['ipv4.method'], a['ipv6.method'], a['gsm.password']),
                         ('v-internet', 'no', 'auto', 'disabled', PW))
        self.assertNoSecrets(r, PW)
        self.assertTrue(self.ctx.bg and 'nmcli connection up lte' in self.ctx.bg[0])

    def test_auto_and_keep_password(self):
        f = self.use('modem_roaming.txt')
        cell.ACTIONS['cell-apn-set']({'apn': '', 'ip_type': 'ipv4v6'}, self.ctx)
        mod = [c for c in f.calls if 'modify' in c][0]
        self.assertNotIn('gsm.password', mod)
        self.assertEqual(mod[mod.index('gsm.auto-config') + 1], 'yes')

    def test_error_scrubbed(self):
        f = self.use('modem_roaming.txt')
        f.fail['gsm.password'] = (2, f"Error: failed to modify gsm.password: '{PW}' invalid")
        r = cell.ACTIONS['cell-apn-set']({'apn': 'x', 'password': PW}, self.ctx)
        self.assertIn('error', r); self.assertNoSecrets(r, PW)


class Roaming(Base):
    def test(self):
        f = self.use('modem_roaming.txt')
        self.assertIn('error', cell.ACTIONS['cell-roaming-set']({'allow': 'yes'}, self.ctx))
        cell.ACTIONS['cell-roaming-set']({'allow': False}, self.ctx)
        self.assertIn(['nmcli', 'connection', 'modify', 'lte', 'gsm.home-only', 'yes'], f.calls)
        cell.ACTIONS['cell-roaming-set']({'allow': True}, self.ctx)
        self.assertIn(['nmcli', 'connection', 'modify', 'lte', 'gsm.home-only', 'no'], f.calls)


class Mode(Base):
    def test(self):
        f = self.use('modem_roaming.txt')
        self.assertIn('error', cell.ACTIONS['cell-mode-set']({'mode': 'allowed: 5g; preferred: none'}, self.ctx))
        self.assertIn('error', cell.ACTIONS['cell-mode-set']({'mode': 'allowed: 4g; preferred: none '}, self.ctx))
        self.assertIn('error', cell.ACTIONS['cell-mode-set']({'mode': ['x']}, self.ctx))
        r = cell.ACTIONS['cell-mode-set']({'mode': 'allowed: 3g, 4g; preferred: 4g'}, self.ctx)
        self.assertNotIn('error', r)
        self.assertIn(['mmcli', '-m', 'any', '--set-allowed-modes=3g|4g', '--set-preferred-mode=4g'], f.calls)


class Pin(Base):
    def test_validation(self):
        f = self.use('modem_locked.txt')
        for p in ('123', '123456789', '12a4', 1234, None, '1234\n'):
            self.assertIn('error', cell.ACTIONS['cell-pin-unlock']({'pin': p}, self.ctx))
        self.assertFalse([c for c in f.calls if any(a.startswith('--pin') for a in c)])

    def test_unlock_ok(self):
        f = self.use('modem_locked.txt')
        r = cell.ACTIONS['cell-pin-unlock']({'pin': PIN}, self.ctx)
        self.assertEqual(r, {'out': 'SIM unlocked'})
        self.assertIn(['mmcli', '-i', '/org/freedesktop/ModemManager1/SIM/0', '--pin=' + PIN], f.calls)

    def test_unlock_wrong(self):
        f = self.use('modem_locked.txt')
        f.fail['--pin='] = (1, "error: couldn't send PIN code to the SIM: 'GDBus.Error:org.freedesktop.ModemManager1.Error.MobileEquipment.IncorrectPassword: Incorrect password'")
        r = cell.ACTIONS['cell-pin-unlock']({'pin': PIN}, self.ctx)
        self.assertIn('IncorrectPassword', r['error']); self.assertIn('2 attempts left', r['error'])
        self.assertNoSecrets(r, PIN)

    def test_refuse_when_not_locked(self):
        f = self.use('modem_roaming.txt')
        self.assertIn('not waiting', cell.ACTIONS['cell-pin-unlock']({'pin': PIN}, self.ctx)['error'])
        self.use('modem_nosim.txt')
        self.assertIn('no SIM', cell.ACTIONS['cell-pin-unlock']({'pin': PIN}, self.ctx)['error'])

    def test_lock_and_change_need_confirm(self):
        f = self.use('modem_roaming.txt')
        self.assertIn('confirmation', cell.ACTIONS['cell-pin-lock']({'pin': PIN, 'enable': False}, self.ctx)['error'])
        self.assertIn('confirmation', cell.ACTIONS['cell-pin-change']({'pin': PIN, 'new_pin': '9999', 'confirm': 'yes'}, self.ctx)['error'])
        r = cell.ACTIONS['cell-pin-lock']({'pin': PIN, 'enable': False, 'confirm': True}, self.ctx)
        self.assertNotIn('error', r); self.assertNoSecrets(r, PIN)
        self.assertIn(['mmcli', '-i', '/org/freedesktop/ModemManager1/SIM/0', '--pin=' + PIN, '--disable-pin'], f.calls)
        r = cell.ACTIONS['cell-pin-change']({'pin': PIN, 'new_pin': '9876', 'confirm': True}, self.ctx)
        self.assertNoSecrets(r, PIN, '9876')
        self.assertIn(['mmcli', '-i', '/org/freedesktop/ModemManager1/SIM/0', '--pin=' + PIN, '--change-pin=9876'], f.calls)
        self.use('modem_locked.txt')
        self.assertIn('unlock the SIM', cell.ACTIONS['cell-pin-lock']({'pin': PIN, 'enable': True, 'confirm': True}, self.ctx)['error'])


class Backend(Base):
    def test_unsupported(self):
        f = self.use('modem_roaming.txt')
        os.environ['UZ_BACKEND'] = 'qmi'
        try:
            for a, fn in cell.ACTIONS.items():
                self.assertEqual(fn({'pin': PIN, 'apn': 'x', 'allow': True, 'mode': 'x', 'confirm': True}, self.ctx),
                                 {'error': 'not supported on this backend'}, a)
            self.assertEqual(cell.status(self.ctx)['backend'], 'none')
        finally:
            os.environ.pop('UZ_BACKEND')
        self.assertEqual(f.calls, [])

    def test_no_mmcli(self):
        cell._backend['v'] = None
        w = cell.shutil.which; cell.shutil.which = lambda n: None
        try:
            self.assertEqual(cell.ACTIONS['cell-get']({}, self.ctx), {'error': 'not supported on this backend'})
        finally:
            cell.shutil.which = w; cell._backend['v'] = True

    def test_status_fast_and_cached(self):
        self.use('modem_roaming.txt')
        cell._state.update(t=0, busy=False)
        t0 = time.time(); s = cell.status(self.ctx); dt = time.time() - t0
        self.assertLess(dt, 0.05); self.assertEqual(s['sim'], 'unknown')
        # stray refresh threads from earlier tests may still write the cache: wait for the expected value
        for _ in range(200):
            s = cell.status(self.ctx)
            if (s['sim'], s['roaming'], s['apn']) == ('ready', True, 'internet'): break
            if not cell._state['busy']: cell._kick(self.ctx, force=True)
            time.sleep(0.01)
        self.assertEqual((s['sim'], s['roaming'], s['apn']), ('ready', True, 'internet'))

    def test_bad_body(self):
        self.use('modem_roaming.txt')
        self.assertIn('error', cell.ACTIONS['cell-roaming-set'](None, self.ctx))


if __name__ == '__main__':
    unittest.main(verbosity=1)
