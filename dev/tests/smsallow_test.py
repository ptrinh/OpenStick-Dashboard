#!/usr/bin/env python3
"""Unit tests for the SMS allow-list settings module. Run: python3 dev/tests/smsallow_test.py"""
import importlib.util, os, stat, sys, tempfile, unittest

R = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
spec = importlib.util.spec_from_file_location('smsallow', os.path.join(R, 'rootfs/usr/local/lib/uz/settings/smsallow.py'))
m = importlib.util.module_from_spec(spec); spec.loader.exec_module(m)


def rd(p):
    with open(p) as f: return f.read()


def wr(p, s):
    with open(p, 'w') as f: f.write(s)


def uz_sms_allows(file_text, sender):
    """The exact matching logic of uz-sms on_sms() (allow-list part)."""
    allow = [x.strip() for x in file_text.strip().splitlines() if x.strip()]
    return not allow or any(sender.endswith(a.lstrip('+')[-9:]) for a in allow)


class Ctx: cache = {}


class T(unittest.TestCase):
    def setUp(self):
        self.d = tempfile.TemporaryDirectory(); os.environ['UZ_ETC'] = self.d.name
        self.p = os.path.join(self.d.name, 'sms.allow')

    def tearDown(self):
        os.environ.pop('UZ_ETC', None); self.d.cleanup()

    def test_parse(self):
        nums, other = m.parse('# header\n\n+84912345678\n 0987654321 \nfoo\n# x 123\n')
        self.assertEqual(nums, ['+84912345678', '0987654321']); self.assertEqual(other, ['foo'])

    def test_validate(self):
        self.assertEqual(m.validate(['+84 912-345.678', '(0)987654321'])[0], ['+84912345678', '0987654321'])
        for bad in (['12345'], ['+1234567890123456'], ['++84912345678'], ['84912a45678'], [84912345678], [None], 'x'):
            self.assertIsNotNone(m.validate(bad)[1], bad)
        # same last 9 digits = same entry for uz-sms -> deduped
        self.assertEqual(m.validate(['+84912345678', '0912345678'])[0], ['+84912345678'])
        self.assertIsNotNone(m.validate([f'+8491234{i:04d}' for i in range(21)])[1])
        self.assertIsNone(m.validate([f'+8491234{i:04d}' for i in range(20)])[1])

    def test_set_get_roundtrip_and_mode(self):
        r = m.set_({'numbers': ['+84912345678', '0987 654 321']}, Ctx)
        self.assertNotIn('error', r)
        self.assertEqual(stat.S_IMODE(os.stat(self.p).st_mode), 0o644)
        text = rd(self.p)
        self.assertTrue(text.startswith('#'))
        g = m.get({}, Ctx)
        self.assertEqual(g['numbers'], ['+84912345678', '0987654321']); self.assertFalse(g['pin_set'])
        self.assertEqual(m.status(Ctx), {'count': 2})
        # header lines never let a stranger in with the current uz-sms matching
        self.assertTrue(uz_sms_allows(text, '+84912345678'))
        self.assertTrue(uz_sms_allows(text, '84987654321'))
        self.assertFalse(uz_sms_allows(text, '+84900000000'))
        self.assertFalse(os.path.exists(self.p + '.tmp'))

    def test_empty_list_is_empty_file(self):
        m.set_({'numbers': ['+84912345678']}, Ctx)
        r = m.set_({'numbers': []}, Ctx)
        self.assertIn('cleared', r['out'])
        text = rd(self.p)
        self.assertEqual(text, '')                      # header-only file would block everyone in uz-sms
        self.assertTrue(uz_sms_allows(text, '+15550001111'))

    def test_errors(self):
        self.assertIn('error', m.set_({'numbers': ['abc']}, Ctx))
        self.assertIn('error', m.set_({}, Ctx))
        self.assertIn('error', m.set_([], Ctx))
        os.environ['UZ_ETC'] = os.path.join(self.d.name, 'missing')
        self.assertIn('not available', m.set_({'numbers': []}, Ctx)['error'])
        self.assertEqual(m.get({}, Ctx)['numbers'], [])
        self.assertEqual(m.status(Ctx), {'count': 0})

    def test_pin_flag(self):
        wr(os.path.join(self.d.name, 'sms.pin'), '1234')
        self.assertTrue(m.get({}, Ctx)['pin_set'])
        self.assertNotIn('1234', repr(m.get({}, Ctx)))


if __name__ == '__main__':
    unittest.main(verbosity=1 if len(sys.argv) == 1 else 2)
