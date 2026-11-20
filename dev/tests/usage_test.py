#!/usr/bin/env python3
"""Tests for settings/usage.py (bearer parsing, delta accounting, buckets, cycles, cap alerts, actions).
Run: python3 dev/tests/usage_test.py"""
import atexit, importlib.util, json, os, shutil, sys, tempfile, time, unittest
from datetime import date, datetime

R = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))
TMP = tempfile.mkdtemp(prefix='uzusage-')
atexit.register(shutil.rmtree, TMP, True)
os.environ['UZ_ETC'] = os.path.join(TMP, 'etc'); os.environ['UZ_VAR'] = os.path.join(TMP, 'var')
os.environ['TZ'] = 'Asia/Singapore'; time.tzset()
spec = importlib.util.spec_from_file_location('usage', os.path.join(R, 'rootfs/usr/local/lib/uz/settings/usage.py'))
U = importlib.util.module_from_spec(spec); spec.loader.exec_module(U)

BEARER = """bearer.dbus-path                         : /org/freedesktop/ModemManager1/Bearer/0
bearer.status.connected                  : yes
bearer.stats.start-date                  : 1795144112
bearer.stats.duration                    : 180
bearer.stats.bytes-rx                    : 7528
bearer.stats.bytes-tx                    : 2872
bearer.stats.total-bytes-rx              : 8352
"""

def ts(y, m, d, h=12): return time.mktime((y, m, d, h, 0, 0, 0, 0, -1))
class Ctx: cache = {}


class T(unittest.TestCase):
    def setUp(self):
        shutil.rmtree(TMP, True); os.makedirs(TMP)
        U._ST.update({'data': U.empty(), 'dirty': 0, 'flushed': 0.0})

    def test_parse(self):
        b = U.parse_bearer(BEARER)
        self.assertEqual(b, {'key': '/org/freedesktop/ModemManager1/Bearer/0@1795144112', 'rx': 7528, 'tx': 2872})
        self.assertIsNone(U.parse_bearer(BEARER.replace('connected                  : yes', 'connected                  : no')))
        self.assertIsNone(U.parse_bearer(BEARER.replace('7528', '--')))
        self.assertIsNone(U.parse_bearer(''))

    def test_delta(self):
        a = {'key': 'k@1', 'rx': 100, 'tx': 10}
        self.assertEqual(U.delta(None, a), (100, 10))                          # first sample: count it
        self.assertEqual(U.delta(a, {'key': 'k@1', 'rx': 150, 'tx': 30}), (50, 20))
        self.assertEqual(U.delta(a, {'key': 'k@2', 'rx': 5, 'tx': 1}), (5, 1))  # reconnect
        self.assertEqual(U.delta(a, {'key': 'k@1', 'rx': 4, 'tx': 1}), (4, 1))  # counter reset
        self.assertEqual(U.delta(a, None), (0, 0))

    def test_sample_accumulates_and_persists(self):
        t0 = ts(2026, 11, 20, 10)
        U.sample(t0, {'key': 'k@1', 'rx': 1000, 'tx': 100})
        U.sample(t0 + 60, {'key': 'k@1', 'rx': 3000, 'tx': 300})
        U.sample(t0 + 120, None)                                               # disconnected: nothing
        U.sample(t0 + 3600, {'key': 'k@2', 'rx': 500, 'tx': 50})               # new connection next hour
        d = U._ST['data']
        self.assertEqual(d['days']['2026-11-20'], [3500, 350])
        self.assertEqual(d['hours']['2026-11-20T10'], [3000, 300])
        self.assertEqual(d['hours']['2026-11-20T11'], [500, 50])
        U.flush(force=True)
        self.assertEqual(json.load(open(os.path.join(TMP, 'var', 'usage.json')))['days']['2026-11-20'], [3500, 350])

    def test_flush_throttled(self):
        U._ST['flushed'] = time.time()
        U.sample(time.time(), {'key': 'k', 'rx': 1000, 'tx': 0})
        self.assertFalse(os.path.exists(os.path.join(TMP, 'var', 'usage.json')))
        U.sample(time.time(), {'key': 'k', 'rx': 1000 + U.FLUSH_BYTES, 'tx': 0})
        self.assertTrue(os.path.exists(os.path.join(TMP, 'var', 'usage.json')))

    def test_cycle(self):
        self.assertEqual(U.cycle_start(date(2026, 11, 20), 1), date(2026, 11, 1))
        self.assertEqual(U.cycle_start(date(2026, 11, 20), 25), date(2026, 10, 25))
        self.assertEqual(U.cycle_start(date(2026, 1, 3), 15), date(2025, 12, 15))
        self.assertEqual(U.next_cycle(date(2025, 12, 15)), date(2026, 1, 15))

    def test_series(self):
        d = U.empty()
        d['days'] = {'2026-10-26': [10, 1], '2026-11-01': [100, 10], '2026-11-20': [5, 5], '2026-10-01': [7, 7]}
        d['hours'] = {'2026-11-20T09': [3, 3]}
        now = ts(2026, 11, 20, 12)
        s = U.series(d, '24h', now, 1)
        self.assertEqual(len(s['points']), 24); self.assertEqual((s['rx'], s['tx']), (3, 3))
        self.assertEqual(s['points'][-1]['k'], '2026-11-20T12')
        s = U.series(d, '7d', now, 1); self.assertEqual(len(s['points']), 7); self.assertEqual(s['rx'], 5)
        s = U.series(d, '30d', now, 1); self.assertEqual(len(s['points']), 30); self.assertEqual(s['rx'], 115)
        m = U.series(d, 'month', now, 1)
        self.assertEqual((m['start'], m['end'], m['days_left']), ('2026-11-01', '2026-11-30', 11))
        self.assertEqual(len(m['points']), 20); self.assertEqual(m['rx'], 105)
        self.assertEqual((m['prev_rx'], m['prev_tx']), (17, 8)); self.assertTrue(m['prev_complete'])
        m = U.series(d, 'month', now, 25)
        self.assertEqual(m['start'], '2026-10-25'); self.assertEqual(m['rx'], 115)

    def test_prune(self):
        d = U.empty(); now = ts(2026, 11, 20, 12)
        d['hours'] = {'2026-11-17T01': [1, 1], '2026-11-20T11': [1, 1]}
        d['days'] = {'2024-01-01': [1, 1], '2026-11-20': [1, 1]}
        U.prune(d, now)
        self.assertEqual(list(d['hours']), ['2026-11-20T11']); self.assertEqual(list(d['days']), ['2026-11-20'])

    def test_cap_alerts_once_per_level(self):
        sent = []
        send = lambda e, t, data: sent.append((e, data['level']))
        d = U.empty(); now = ts(2026, 11, 20); conf = {'cycle_day': 1, 'cap_mb': 1000}
        d['days'] = {'2026-11-20': [500_000_000, 0]}
        U.check_cap(d, now, conf, send); self.assertEqual(sent, [])
        d['days']['2026-11-20'] = [850_000_000, 0]
        U.check_cap(d, now, conf, send); U.check_cap(d, now, conf, send)
        self.assertEqual(sent, [('data_cap', 80)])
        d['days']['2026-11-20'] = [1_000_000_000, 10]
        U.check_cap(d, now, conf, send); self.assertEqual(sent[-1], ('data_cap', 100)); self.assertEqual(len(sent), 2)
        d['days']['2026-12-01'] = [900_000_000, 0]                               # new cycle re-arms
        U.check_cap(d, ts(2026, 12, 1), conf, send); self.assertEqual(sent[-1], ('data_cap', 80))
        U.check_cap(d, now, {'cycle_day': 1, 'cap_mb': 0}, send); self.assertEqual(len(sent), 3)

    def test_actions(self):
        A = U.ACTIONS
        self.assertIn('error', A['usage-get']({'range': 'year'}, Ctx))
        self.assertEqual(A['usage-get']({'range': '7d'}, Ctx)['range'], '7d')
        self.assertIn('error', A['usage-set']({'cycle_day': 29}, Ctx))
        self.assertIn('error', A['usage-set']({'cycle_day': True}, Ctx))
        self.assertIn('error', A['usage-set']({'cap_mb': -1}, Ctx))
        self.assertIn('error', A['usage-set']({'cap_mb': '5'}, Ctx))
        r = A['usage-set']({'cycle_day': 15, 'cap_mb': 20000}, Ctx)
        self.assertEqual((r['cycle_day'], r['cap_mb']), (15, 20000))
        self.assertEqual(U.load_conf(), {'cycle_day': 15, 'cap_mb': 20000})
        self.assertIn('error', A['usage-reset']({}, Ctx))
        U._ST['data']['days'] = {'2026-11-20': [1, 1]}; U._ST['data']['last'] = {'key': 'k', 'rx': 9, 'tx': 9}
        self.assertEqual(A['usage-reset']({'confirm': True}, Ctx)['out'], 'usage history cleared')
        self.assertEqual(U._ST['data']['days'], {}); self.assertEqual(U._ST['data']['last']['rx'], 9)

    def test_status_fast_and_shaped(self):
        U.load_conf()
        st = U.status(Ctx)
        for k in ('month_bytes', 'day_bytes', 'cap_mb', 'cycle_start'): self.assertIn(k, st)


if __name__ == '__main__':
    unittest.main(verbosity=1)
