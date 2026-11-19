#!/usr/bin/env python3
"""Unit tests for uz-calls (daemon + CLI), the Calls settings module and the uz-probe / uz-notify hooks.
Run: python3 -I dev/tests/calls_test.py
mmcli is replaced by dev/fixtures/calls/bin/mmcli (state in $FAKE_MM_DIR, every call logged); notifications and
trigger actions are captured in-process. No network, no device."""
import json, os, re, shutil, stat, subprocess, sys, tempfile, unittest
from importlib.machinery import SourceFileLoader
from importlib.util import module_from_spec, spec_from_file_location, spec_from_loader

R = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))
FIX = os.path.join(R, 'dev', 'fixtures', 'calls')
BIN = os.path.join(R, 'rootfs', 'usr', 'local', 'bin', 'uz-calls')
MOD = os.path.join(R, 'rootfs', 'usr', 'local', 'lib', 'uz', 'settings', 'calls.py')
NOTIFY = os.path.join(R, 'rootfs', 'usr', 'local', 'bin', 'uz-notify')
NOTIFY_JS = os.path.join(R, 'rootfs', 'usr', 'local', 'share', 'uz', 'settings', 'notify.js')
PROBE = os.path.join(R, 'rootfs', 'usr', 'local', 'bin', 'uz-probe')
sys.dont_write_bytecode = True
C0, C1, C2 = (f'/org/freedesktop/ModemManager1/Call/{i}' for i in range(3))

def load(path, name):
    ld = SourceFileLoader(name, path); m = module_from_spec(spec_from_loader(name, ld)); ld.exec_module(m); return m

def rd(path):
    with open(path) as f: return f.read()

def rjson(path): return json.loads(rd(path))

def fix(name):
    with open(os.path.join(FIX, name)) as f: return f.read()

class Clock:
    def __init__(self, t=1_800_000_000): self.t = t
    def __call__(self): return self.t

class Ctx:
    def __init__(self): self.cache = {}
    def write_secret(self, path, text):
        fd = os.open(path + '.tmp', os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
        with os.fdopen(fd, 'w') as f: f.write(text)
        os.replace(path + '.tmp', path)

class Base(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(); d = self.tmp.name
        self.etc, self.var, self.run, self.mm = (os.path.join(d, x) for x in ('etc', 'var', 'run', 'mm'))
        for x in (self.etc, self.var, self.run, self.mm): os.makedirs(x)
        self._env = {k: os.environ.get(k) for k in ('UZ_ETC', 'UZ_VAR', 'UZ_RUN', 'FAKE_MM_DIR', 'PATH', 'UZ_CALLS_BIN')}
        os.environ.update(UZ_ETC=self.etc, UZ_VAR=self.var, UZ_RUN=self.run, FAKE_MM_DIR=self.mm, UZ_CALLS_BIN=BIN,
                          PATH=os.path.join(FIX, 'bin') + os.pathsep + (self._env['PATH'] or ''))
        self.uc = load(BIN, 'uzcalls_test')
        self.clock = Clock(); self.notes, self.acts = [], []
        self.d = self.uc.Daemon(notify=lambda ev, text, data=None: self.notes.append((ev, text, data)),
                                now=self.clock, act=lambda a: self.acts.append(a) or f'did {a}')
        self.mmset('modem', 'modem-registered.txt'); self.mmset('list', 'list-none.txt')
        self.uc.err = lambda msg: self.stderr.append(msg); self.stderr = []

    def tearDown(self):
        for k, v in self._env.items():
            if v is None: os.environ.pop(k, None)
            else: os.environ[k] = v
        self.tmp.cleanup()

    def mmset(self, name, fixture=None, text=None):
        with open(os.path.join(self.mm, name), 'w') as f: f.write(fix(fixture) if fixture else text)
    def mmrc(self, verb, rc):
        with open(os.path.join(self.mm, verb + '.rc'), 'w') as f: f.write(str(rc))
    def mmlog(self):
        try:
            with open(os.path.join(self.mm, 'log')) as f: return [json.loads(l) for l in f]
        except FileNotFoundError: return []
    def verbs(self, flag):
        return [a for a in self.mmlog() if any(x == flag or x.startswith(flag + '=') for x in a)]
    def policy(self, **kw):
        p = self.uc.default_policy(); p.update(kw)
        with open(os.path.join(self.etc, 'calls.json'), 'w') as f: json.dump(p, f)
    def log(self): return self.uc.read_log()
    def events(self): return [n[0] for n in self.notes]

# ---------------------------------------------------------------- parsing
class Parse(Base):
    def test_call_list(self):
        self.assertEqual(self.uc.parse_call_list(fix('list-none.txt')), [])
        self.assertEqual(self.uc.parse_call_list(fix('list-two.txt')), [C0, C1])

    def test_call_info(self):
        c = self.uc.parse_call(fix('call0-ringing-in.txt'))
        self.assertEqual(c, {'path': C0, 'number': '+84912345678', 'dir': 'incoming', 'state': 'ringing-in', 'reason': 'incoming-new'})
        self.assertEqual(self.uc.parse_call(fix('call3-withheld.txt'))['number'], '')
        self.assertEqual(self.uc.parse_call(fix('call2-dialing.txt'))['dir'], 'outgoing')

    def test_modem(self):
        self.assertEqual(self.uc.modem_info(fix('modem-nosim.txt')), ('missing', 'failed'))
        self.assertEqual(self.uc.modem_info(fix('modem-registered.txt')), ('ready', 'registered'))
        self.assertEqual(self.uc.modem_info(''), ('unknown', 'unknown'))

    def test_numbers(self):
        u = self.uc
        self.assertTrue(u.same_number('+84912345678', '0912345678'))
        self.assertTrue(u.same_number('84 912-345.678', '(0)912345678'.replace('(0)', '0')))
        self.assertFalse(u.same_number('+84912345678', '+84912345679'))
        self.assertFalse(u.same_number('', ''))
        self.assertEqual(u.mask('+84912345678'), '••5678'); self.assertEqual(u.mask(''), 'unknown')
        for ok in ('+84912345678', '911', '123456789012345'): self.assertTrue(u.valid_number(ok), ok)
        for bad in ('12', '+', '0912 345', '1234567890123456', '+84;rm', '-1', None): self.assertFalse(u.valid_number(bad), bad)

    def test_short_error_masks_numbers(self):
        self.assertEqual(self.uc.short_error('foo\nerror: call +84912345678 failed\n'), 'error: call ••5678 failed')

# ---------------------------------------------------------------- lifecycle
class Lifecycle(Base):
    def ring_in(self, n=0, fixture='call0-ringing-in.txt', lst='list-one.txt'):
        self.mmset('list', lst); self.mmset(f'call-{n}', fixture)
        return self.d.poll()

    def test_missed(self):
        self.assertEqual(self.ring_in(), self.uc.POLL_S)
        self.assertEqual(self.events(), ['call_incoming']); self.assertIn('+84912345678', self.notes[0][1])
        st = rjson(os.path.join(self.run, 'uz-calls.json'))
        self.assertTrue(st['voice']); self.assertEqual(st['active_calls'][0]['state'], 'ringing-in')
        self.assertEqual(stat.S_IMODE(os.stat(os.path.join(self.run, 'uz-calls.json')).st_mode), 0o600)
        self.d.poll(); self.assertEqual(self.events(), ['call_incoming'])          # no duplicate while ringing
        self.mmset('call-0', 'call0-terminated.txt'); self.clock.t += 20; self.d.poll()
        self.assertEqual(self.events(), ['call_incoming', 'call_missed'])
        L = self.log(); self.assertEqual(len(L), 1)
        self.assertEqual({k: L[0][k] for k in ('number', 'dir', 'outcome')}, {'number': '+84912345678', 'dir': 'in', 'outcome': 'missed'})
        self.assertEqual(L[0]['ts'], self.clock.t)
        self.assertEqual(self.verbs('--voice-delete-call'), [['-m', 'any', f'--voice-delete-call={C0}']])
        self.assertEqual(self.verbs('--hangup'), [])                               # notify mode never touches the call
        self.assertEqual(self.verbs('--accept'), [])
        self.mmset('list', 'list-none.txt'); self.d.poll()
        self.assertEqual(len(self.log()), 1); self.assertEqual(self.d.calls, {})
        self.assertFalse(any('+84912345678' in s or '912345678' in s for s in self.stderr), self.stderr)
        self.assertTrue(any('••5678' in s for s in self.stderr))

    def test_answered(self):
        self.ring_in()
        self.mmset('call-0', 'call0-active.txt'); self.d.poll()
        self.mmset('call-0', 'call0-terminated.txt'); self.d.poll()
        self.assertEqual(self.log()[0]['outcome'], 'answered'); self.assertEqual(self.events(), ['call_incoming'])

    def test_vanished_is_missed(self):
        self.ring_in(); self.mmset('list', 'list-none.txt'); self.d.poll()
        self.assertEqual(self.log()[0]['outcome'], 'missed'); self.assertEqual(self.verbs('--voice-delete-call'), [])

    def test_first_seen_terminated(self):
        self.ring_in(fixture='call0-terminated-refused.txt')
        self.assertEqual(self.log()[0]['outcome'], 'missed'); self.assertEqual(self.events(), ['call_missed'])

    def test_waiting_call(self):
        self.mmset('list', 'list-two.txt'); self.mmset('call-0', 'call0-active.txt'); self.mmset('call-1', 'call1-waiting.txt')
        self.d.poll()
        self.assertEqual(self.events(), ['call_incoming']); self.assertIn('0987654321', self.notes[0][1])
        self.assertEqual(len(self.d.active()), 2)
        self.mmset('call-0', 'call0-terminated.txt'); self.mmset('call-1', 'call1-terminated.txt'); self.d.poll()
        self.assertEqual({e['number']: e['outcome'] for e in self.log()}, {'+84912345678': 'answered', '0987654321': 'missed'})

    def test_outgoing_not_logged_or_deleted(self):
        self.mmset('list', 'list-one.txt'); self.mmset('call-0', 'call2-dialing.txt')
        self.d.poll(); self.assertEqual(self.d.active()[0]['dir'], 'outgoing')
        self.mmset('call-0', 'call2-terminated.txt'); self.d.poll()
        self.assertEqual(self.log(), []); self.assertEqual(self.notes, []); self.assertEqual(self.verbs('--voice-delete-call'), [])

    def test_notify_off(self):
        self.policy(notify=False); self.ring_in(); self.mmset('call-0', 'call0-terminated.txt'); self.d.poll()
        self.assertEqual(self.notes, []); self.assertEqual(self.log()[0]['outcome'], 'missed')

    def test_backoff(self):
        self.mmrc('list', 1)
        self.assertEqual(self.d.poll(), self.uc.IDLE_S)
        st = rjson(os.path.join(self.run, 'uz-calls.json')); self.assertFalse(st['voice'])
        os.remove(os.path.join(self.mm, 'list.rc')); self.mmset('modem', 'modem-nosim.txt')
        self.d.modem_t = 0; self.assertEqual(self.d.poll(), self.uc.IDLE_S)        # voice ok, but no SIM
        self.assertEqual(self.d.sim, 'missing')
        self.mmset('modem', 'modem-registered.txt'); self.clock.t += 31; self.assertEqual(self.d.poll(), self.uc.POLL_S)

    def test_voice_lost_mid_call(self):
        self.ring_in(); self.mmrc('list', 1); self.d.poll()
        self.assertEqual(self.log()[0]['outcome'], 'missed'); self.assertEqual(self.d.calls, {})

    def test_log_trim_and_mode(self):
        for i in range(305): self.uc.append_log({'ts': i, 'number': '1', 'dir': 'in', 'outcome': 'missed'})
        L = self.log(); self.assertEqual(len(L), 300); self.assertEqual(L[0]['ts'], 5)
        self.assertEqual(stat.S_IMODE(os.stat(os.path.join(self.var, 'calls.jsonl')).st_mode), 0o600)

# ---------------------------------------------------------------- policy
class Policy(Base):
    def test_decide(self):
        u = self.uc; P = u.default_policy()
        self.assertEqual(u.decide(P, '+84912345678'), (None, None))
        P['block'] = ['0912345678']
        self.assertEqual(u.decide(P, '+84912345678'), ('blocked', None))
        P['block'] = []; P['mode'] = 'reject_all'
        self.assertEqual(u.decide(P, '+84912345678'), ('rejected', None))
        P['mode'] = 'allow_list'; P['allow'] = ['0912345678']
        self.assertEqual(u.decide(P, '+84912345678'), (None, None))
        self.assertEqual(u.decide(P, '+84999999999'), ('rejected', None))
        self.assertEqual(u.decide(P, ''), ('rejected', None))                    # withheld number
        tr = {'number': '912345678', 'action': 'status', 'reply_sms': True}
        P['triggers'] = [tr]; P['mode'] = 'reject_all'
        self.assertEqual(u.decide(P, '+84912345678'), ('trigger', tr))         # trigger beats reject_all
        P['block'] = ['+84912345678']
        self.assertEqual(u.decide(P, '+84912345678'), ('blocked', None))        # block beats trigger

    def test_star_trigger_needs_flag(self):
        u = self.uc; P = u.default_policy(); star = {'number': '*', 'action': 'ts', 'reply_sms': False}
        P['triggers'] = [star]
        self.assertEqual(u.decide(P, '+84911111111', ['0911111111']), (None, None))
        P['triggers_from_sms_allow'] = True
        self.assertEqual(u.decide(P, '+84911111111', ['0911111111']), ('trigger', star))
        self.assertEqual(u.decide(P, '+84922222222', ['0911111111']), (None, None))
        with open(os.path.join(self.etc, 'sms.allow'), 'w') as f: f.write('# trusted\n+84 911 111 111\nbogus\n')
        self.assertEqual(u.sms_allow(), ['+84911111111'])

    def test_normalize_strict(self):
        u = self.uc; N = lambda r: u.normalize_policy(r, strict=True)
        p, e = N({'mode': 'allow_list', 'allow': ['+84 912-345.678', '0912345678', '0987654321'],
                  'triggers': [{'number': '(0)911 222 333'.replace('(0)', '0'), 'action': 'reboot', 'reply_sms': True}],
                  'alarm': {'enabled': True, 'number': '+84 911 222 333', 'ring_s': 30}})
        self.assertIsNone(e)
        self.assertEqual(p['allow'], ['+84912345678', '0987654321'])               # normalised + de-duplicated by last 9
        self.assertEqual(p['triggers'][0]['number'], '0911222333'); self.assertEqual(p['alarm']['number'], '+84911222333')
        for bad in ({'mode': 'x'}, {'allow': ['12']}, {'allow': [str(10**8 + i) for i in range(51)]}, {'block': 'x'},
                    {'triggers': [{'number': '0911', 'action': 'rm -rf', 'reply_sms': False}]},
                    {'triggers': [{'number': '0911222333', 'action': 'ts', 'reply_sms': 'yes'}]},
                    {'triggers': [{'number': '0911222333', 'action': 'ts'}, {'number': '+84911222333', 'action': 'lte'}]},
                    {'triggers': [{'number': f'09112223{i:02d}', 'action': 'ts'} for i in range(11)]},
                    {'alarm': {'enabled': True, 'number': '', 'ring_s': 20}}, {'alarm': {'enabled': False, 'number': '1', 'ring_s': 20}},
                    {'alarm': {'enabled': False, 'number': '', 'ring_s': 4}}, {'alarm': {'enabled': False, 'number': '', 'ring_s': 61}},
                    {'alarm': {'enabled': False, 'number': '', 'ring_s': True}}, {'notify': 'yes'}, []):
            self.assertIsNotNone(N(bad)[1], bad)

    def test_load_lenient(self):
        with open(os.path.join(self.etc, 'calls.json'), 'w') as f:
            json.dump({'mode': 'nope', 'block': ['0912345678', 'evil;'], 'triggers': [{'number': 'x', 'action': 'ts'}, {'number': '0911222333', 'action': 'ts'}]}, f)
        p = self.uc.load_policy()
        self.assertEqual(p['mode'], 'notify'); self.assertEqual(p['block'], ['0912345678']); self.assertEqual(len(p['triggers']), 1)
        with open(os.path.join(self.etc, 'calls.json'), 'w') as f: f.write('{broken')
        self.assertEqual(self.uc.load_policy(), self.uc.default_policy())

    def ring(self, n=0, fixture='call0-ringing-in.txt', lst='list-one.txt'):
        self.mmset('list', lst); self.mmset(f'call-{n}', fixture); self.d.poll()

    def end(self, n=0, fixture='call0-terminated.txt'):
        self.mmset(f'call-{n}', fixture); self.d.poll(); self.mmset('list', 'list-none.txt'); self.d.poll()

    def test_blocked_and_rejected_flow(self):
        self.policy(block=['0912345678'])
        self.ring()
        self.assertEqual(self.verbs('--hangup'), [['-c', C0, '--hangup']])
        self.assertEqual(self.events(), ['call_incoming']); self.assertIn('Blocked', self.notes[0][1])
        self.end()
        L = self.log(); self.assertEqual(len(L), 1); self.assertEqual(L[0]['outcome'], 'blocked')
        self.assertEqual(self.events(), ['call_incoming'])                        # no "missed" for a rejected call
        self.policy(mode='reject_all', notify=False); self.notes.clear(); self.ring()
        self.assertEqual(self.log()[-1]['outcome'], 'rejected'); self.assertEqual(self.notes, [])

    def test_hangup_failure_recorded(self):
        self.policy(mode='reject_all'); self.mmrc('hangup', 1); self.ring()
        self.assertEqual(self.log()[0]['hangup'], 'failed')

    def test_trigger_flow(self):
        self.policy(mode='reject_all', triggers=[{'number': '0912345678', 'action': 'status', 'reply_sms': True}])
        self.ring()
        self.assertEqual(self.verbs('--hangup'), [['-c', C0, '--hangup']])
        self.assertEqual(self.acts, ['status'])
        self.assertEqual(self.events(), ['call_trigger']); self.assertEqual(self.notes[0][2]['action'], 'status')
        L = self.log()[0]
        self.assertEqual((L['outcome'], L['action'], L['result'], L['sms']), ('trigger', 'status', 'did status', 'queued'))
        ob = os.path.join(self.var, 'outbox'); files = os.listdir(ob)
        self.assertEqual(len(files), 1); self.assertRegex(files[0], r'^call-[0-9a-f]{32}\.json$')
        self.assertEqual(rjson(os.path.join(ob, files[0])), {'to': '+84912345678', 'text': 'status: did status'})
        # same caller again within 60 s (new call object): rejected, action NOT run, no SMS
        self.end(); self.clock.t += 30
        self.ring(n=1, fixture='call1-waiting.txt', lst='list-two.txt')            # different number → no trigger
        self.assertEqual(self.acts, ['status'])
        self.mmset('list', 'list-one.txt'); self.mmset('call-0', 'call0-ringing-in.txt'); self.d.calls.clear(); self.d.poll()
        self.assertEqual(self.acts, ['status']); self.assertEqual(self.log()[-1]['result'], 'skipped (cooldown)')
        self.assertEqual(len(os.listdir(ob)), 1)
        self.clock.t += 61; self.d.calls.clear(); self.d.poll()
        self.assertEqual(self.acts, ['status', 'status'])

    def test_trigger_action_exception(self):
        self.policy(triggers=[{'number': '0912345678', 'action': 'lte', 'reply_sms': False}])
        self.d.act = lambda a: 1 / 0
        self.ring(); self.assertEqual(self.log()[0]['result'], 'error (ZeroDivisionError)')
        self.assertFalse(os.path.exists(os.path.join(self.var, 'outbox')))

    def test_limiter(self):
        L = self.uc.Limiter(now=self.clock)
        self.assertIsNone(L.check('+84912345678', 'status'))
        self.assertEqual(L.check('0912345678', 'status'), 'cooldown')             # last-9 match
        self.assertIsNone(L.check('0912345678', 'ts'))                            # other action: ok
        for i in range(18): self.assertIsNone(L.check(f'09000000{i:02d}', 'status'))
        self.assertEqual(L.check('0911111111', 'status'), 'rate limit')           # 21st in the hour
        L2 = self.uc.Limiter(now=self.clock)                                      # persisted (survives restart/reboot)
        self.assertEqual(L2.check('0911111111', 'status'), 'rate limit')
        self.clock.t += 3601; self.assertIsNone(L2.check('0911111111', 'status'))
        self.assertEqual(stat.S_IMODE(os.stat(os.path.join(self.var, 'calls-triggers.json')).st_mode), 0o600)

    def test_outbox_cleanup(self):
        ob = os.path.join(self.var, 'outbox'); os.makedirs(ob)
        for n in ('call-a.done', 'other.done', 'call-b.json'):
            open(os.path.join(ob, n), 'w').close(); os.utime(os.path.join(ob, n), (1, 1))
        self.uc.clean_outbox(); self.assertEqual(sorted(os.listdir(ob)), ['call-b.json', 'other.done'])

# ---------------------------------------------------------------- ring / alarm
class Ring(Base):
    def setUp(self):
        super().setUp(); self.mmset('create', 'create-call.txt'); self.mmset('call-2', 'call2-dialing.txt')
        self.sleeps = []

    def sleep(self, s): self.sleeps.append(s)

    def test_unanswered(self):
        self.mmset('call-2.after-start', 'call2-ringing-out.txt')
        ok, out = self.uc.ring('+84 911 222 333', 5, sleep=self.sleep)
        self.assertEqual((ok, out), (True, 'unanswered')); self.assertEqual(len(self.sleeps), 5)
        self.assertIn(['-m', 'any', '--voice-create-call=number=+84911222333'], self.mmlog())
        self.assertEqual(self.verbs('--hangup'), [['-c', C2, '--hangup']])
        self.assertEqual(self.verbs('--voice-delete-call'), [['-m', 'any', f'--voice-delete-call={C2}']])
        e = self.log()[-1]; self.assertEqual((e['dir'], e['outcome'], e['number']), ('out', 'unanswered', '+84911222333'))

    def test_answered_stops_early(self):
        self.mmset('call-2.after-start', 'call0-active.txt')
        self.assertEqual(self.uc.ring('0911222333', 30, sleep=self.sleep), (True, 'answered'))
        self.assertEqual(len(self.sleeps), 1); self.assertEqual(len(self.verbs('--hangup')), 1)

    def test_start_fails_still_hangs_up(self):
        self.mmrc('start', 1)
        ok, why = self.uc.ring('0911222333', 5, sleep=self.sleep)
        self.assertFalse(ok); self.assertIn('start failed', why)
        self.assertEqual(self.verbs('--hangup'), [['-c', C2, '--hangup']])
        self.assertEqual(self.log()[-1]['outcome'], 'failed')

    def test_interrupted_still_hangs_up(self):
        def boom(s): raise SystemExit(143)                                       # SIGTERM handler during the wait
        with self.assertRaises(SystemExit): self.uc.ring('0911222333', 20, sleep=boom)
        self.assertEqual(self.verbs('--hangup'), [['-c', C2, '--hangup']])
        self.assertEqual(len(self.verbs('--voice-delete-call')), 1)

    def test_create_fails_hangs_up_outgoing_only(self):
        self.mmrc('create', 1); self.mmset('list', 'list-two.txt')
        self.mmset('call-0', 'call0-active.txt'); self.mmset('call-1', 'call2-dialing.txt')
        ok, _ = self.uc.ring('0911222333', 5, sleep=self.sleep)
        self.assertFalse(ok); self.assertEqual(self.verbs('--hangup'), [['-c', C1, '--hangup']])  # never the incoming call

    def test_hangup_fails_retries(self):
        self.mmset('call-2.after-start', 'call2-ringing-out.txt'); self.mmrc('hangup', 1)
        self.mmset('list', 'list-one.txt'); self.mmset('call-0', 'call2-ringing-out.txt')
        self.uc.ring('0911222333', 5, sleep=self.sleep)
        self.assertEqual([a[1] for a in self.verbs('--hangup')], [C2, C0])

    def test_validation(self):
        for n, s in (('12', 5), ('+84;reboot', 5), ('0911222333', 4), ('0911222333', 61), ('0911222333', '5')):
            self.assertFalse(self.uc.ring(n, s, sleep=self.sleep)[0])
        self.assertEqual(self.mmlog(), [])

    def test_alarm_rate_limit(self):
        rang = []; ringer = lambda n, s, source: rang.append((n, s, source))
        self.assertEqual(self.uc.alarm(now=1000, ringer=ringer), 'disabled')
        self.policy(alarm={'enabled': True, 'number': '+84911222333', 'ring_s': 15})
        self.assertEqual(self.uc.alarm(now=1000, ringer=ringer), 'rang')
        self.assertEqual(self.uc.alarm(now=1000 + 1799, ringer=ringer), 'rate limited')
        self.assertEqual(self.uc.alarm(now=1000 + 1800, ringer=ringer), 'rang')
        self.assertEqual(rang, [('+84911222333', 15, 'alarm')] * 2)
        self.assertEqual(stat.S_IMODE(os.stat(os.path.join(self.var, 'calls-alarm.ts')).st_mode), 0o600)

    def test_probe_hook(self):
        src = rd(PROBE)
        self.assertIn("['systemd-run', '--collect', '--quiet', '--unit=uz-calls-alarm', '/usr/local/bin/uz-calls', 'alarm']", src)
        self.assertIn('went_down = went_down or not ok', src)
        compile(src, PROBE, 'exec')

# ---------------------------------------------------------------- USSD + CLI
class Ussd(Base):
    def test_validation(self):
        u = self.uc
        for ok in ('*101#', '#123#', '*100*1234567890123#', '12'): self.assertTrue(u.valid_ussd(ok), ok)
        for bad in ('*', '*101#;reboot', '*101# ', 'abc', '*' * 31, None): self.assertFalse(u.valid_ussd(bad), bad)
        self.assertTrue(u.valid_ussd_text('1')); self.assertTrue(u.valid_ussd_text("it's ok"))
        for bad in ('', 'x' * 161, 'a\nb', 'a\x00'): self.assertFalse(u.valid_ussd_text(bad), bad)
        self.assertIn('error', u.ussd('*101#;ls')); self.assertIn('error', u.ussd_respond('a\nb')); self.assertEqual(self.mmlog(), [])

    def test_initiate_expects_input(self):
        self.mmset('ussd-out', 'ussd-initiate.txt'); self.mmset('ussd-status', 'ussd-status-user-response.txt')
        r = self.uc.ussd('*101#')
        self.assertTrue(r['reply'].startswith('TK chinh: 12.345d')); self.assertIn('2. Goi cuoc', r['reply'])
        self.assertTrue(r['expects_input']); self.assertIn(['-m', 'any', '--3gpp-ussd-initiate=*101#'], self.mmlog())
        self.mmset('ussd-out', 'ussd-respond.txt'); self.mmset('ussd-status', 'ussd-status-idle.txt')
        r = self.uc.ussd_respond("1 'x'")
        self.assertEqual((r['reply'], r['expects_input']), ('Cam on quy khach', False))
        self.assertIn(['-m', 'any', "--3gpp-ussd-respond=1 'x'"], self.mmlog())
        self.assertEqual(self.uc.ussd_cancel()['state'], 'idle')

    def test_error(self):
        self.mmrc('ussd', 1); self.assertIn('error', self.uc.ussd('*101#'))

    def test_no_mmcli(self):
        os.environ['PATH'] = '/nonexistent'
        self.assertEqual(self.uc.ussd('*101#'), {'error': 'not available on this host'})
        self.assertEqual(self.d.poll(), self.uc.IDLE_S)

    def test_cli(self):
        self.mmset('ussd-out', 'ussd-respond.txt'); self.mmset('ussd-status', 'ussd-status-idle.txt')
        r = subprocess.run([sys.executable, '-I', BIN, 'ussd', '*101#'], capture_output=True, text=True, env=os.environ.copy())
        self.assertEqual((r.returncode, r.stdout.strip()), (0, 'Cam on quy khach'))
        r = subprocess.run([sys.executable, '-I', BIN, 'ring', '+84;reboot', '5'], capture_output=True, text=True, env=os.environ.copy())
        self.assertEqual(r.returncode, 1)
        r = subprocess.run([sys.executable, '-I', BIN, 'ring', '0911222333', 'x'], capture_output=True, text=True, env=os.environ.copy())
        self.assertEqual(r.returncode, 2)
        r = subprocess.run([sys.executable, '-I', BIN, 'hangup-all'], capture_output=True, text=True, env=os.environ.copy())
        self.assertEqual(r.returncode, 0); self.assertIn(['-m', 'any', '--voice-hangup-all'], self.mmlog())

# ---------------------------------------------------------------- notify events
class Events(Base):
    def test_events(self):
        un = load(NOTIFY, 'uznotify_calls_test')
        for e in ('call_incoming', 'call_missed', 'call_trigger'):
            self.assertIn(e, un.EVENTS); self.assertIn(e, un.defaults()['telegram']['events'])
        js = rd(NOTIFY_JS)
        evs = re.findall(r'ev: \{([^}]*)\}', js); self.assertEqual(len(evs), 3)
        for block in evs:
            keys = set(re.findall(r'(\w+):', block))
            self.assertTrue(set(un.EVENTS) <= keys, set(un.EVENTS) - keys)

    def test_daemon_uses_known_events(self):
        un = load(NOTIFY, 'uznotify_calls_test2')
        src = rd(BIN)
        used = set(re.findall(r"notify\('([a-z_]+)'", src))
        self.assertEqual(used, {'call_incoming', 'call_missed', 'call_trigger'}); self.assertTrue(used <= set(un.EVENTS))

# ---------------------------------------------------------------- settings module
class Module(Base):
    def setUp(self):
        super().setUp()
        sp = spec_from_file_location('calls_mod_test', MOD); self.m = module_from_spec(sp); sp.loader.exec_module(self.m)
        self.ctx = Ctx()

    def state(self, **kw):
        st = {'voice': True, 'sim': 'ready', 'modem': 'registered', 'active_calls': [], 'last': None, 'ts': int(__import__('time').time())}
        st.update(kw)
        with open(os.path.join(self.run, 'uz-calls.json'), 'w') as f: json.dump(st, f)

    def test_status(self):
        s = self.m.status(self.ctx)
        self.assertEqual((s['available'], s['daemon'], s['missed_unseen'], s['active']), (False, False, 0, 0))
        self.state(active_calls=[{'path': C0, 'number': '+84912345678', 'dir': 'incoming', 'state': 'ringing-in'}])
        for ts in (100, 200, 300): self.uc.append_log({'ts': ts, 'number': '1', 'dir': 'in', 'outcome': 'missed'})
        self.uc.append_log({'ts': 400, 'number': '1', 'dir': 'in', 'outcome': 'rejected'})
        s = self.m.status(self.ctx)
        self.assertEqual((s['available'], s['active'], s['ringing'], s['missed_unseen']), (True, 1, '+84912345678', 3))
        with open(os.path.join(self.var, 'calls.seen'), 'w') as f: f.write('200')
        self.assertEqual(self.m.status(self.ctx)['missed_unseen'], 1)
        self.assertEqual(self.m.ACTIONS['calls-seen']({}, self.ctx)['out'], 'ok')
        self.assertEqual(self.m.status(self.ctx)['missed_unseen'], 0)
        self.state(ts=1)                                                        # stale → daemon down
        self.assertFalse(self.m.status(self.ctx)['daemon'])

    def test_get_set(self):
        A = self.m.ACTIONS
        r = A['calls-get']({}, self.ctx); self.assertEqual(r['policy'], self.uc.default_policy()); self.assertFalse(r['daemon'])
        self.assertIn('error', A['calls-set']({'policy': {'mode': 'evil'}}, self.ctx))
        r = A['calls-set']({'policy': {'mode': 'allow_list', 'allow': ['+84 912 345 678'], 'block': [], 'notify': True,
                                       'triggers': [{'number': '*', 'action': 'ts', 'reply_sms': False}], 'triggers_from_sms_allow': True,
                                       'alarm': {'enabled': True, 'number': '0911222333', 'ring_s': 10}}}, self.ctx)
        self.assertEqual(r['out'], 'call policy saved')
        p = os.path.join(self.etc, 'calls.json'); self.assertEqual(stat.S_IMODE(os.stat(p).st_mode), 0o600)
        self.assertEqual(rjson(p)['allow'], ['+84912345678'])
        self.assertEqual(A['calls-get']({}, self.ctx)['policy']['alarm']['ring_s'], 10)

    def test_action_validation(self):
        A = self.m.ACTIONS
        self.assertIn('error', A['calls-hangup']({'path': '/org/x; reboot'}, self.ctx))
        self.assertIn('error', A['calls-ring']({'number': '+84;reboot', 'seconds': 10}, self.ctx))
        self.assertIn('error', A['calls-ring']({'number': '0911222333', 'seconds': 99}, self.ctx))
        self.assertIn('error', A['calls-ring']({'number': '0911222333', 'seconds': True}, self.ctx))
        self.assertIn('error', A['calls-ussd']({'code': '*101#|sh'}, self.ctx))
        self.assertIn('error', A['calls-ussd-respond']({'text': 'x' * 200}, self.ctx))
        self.assertIn('error', A['calls-log-clear']({}, self.ctx))
        self.assertIn('error', A['calls-set']('junk', self.ctx)); self.assertIn('error', A['calls-set']({}, self.ctx))
        self.assertFalse(os.path.exists(os.path.join(self.etc, 'calls.json')))
        self.assertEqual(self.mmlog(), [])

    def test_ring_spawn_args(self):
        calls = []
        class P:
            def __init__(s, args, **kw): calls.append((args, kw))
        orig_popen, orig_which = self.m.subprocess.Popen, self.m.shutil.which
        self.m.subprocess.Popen = P
        self.m.shutil.which = lambda c: None if c == 'systemd-run' else orig_which(c)
        try: r = self.m.ACTIONS['calls-ring']({'number': '+84 911 222 333', 'seconds': 7}, self.ctx)
        finally: self.m.subprocess.Popen, self.m.shutil.which = orig_popen, orig_which
        self.assertEqual(r['out'], 'ringing for 7 s')
        self.assertEqual(calls[0][0][1:], [os.path.abspath(BIN), 'ring', '+84911222333', '7'])
        self.assertTrue(calls[0][1]['start_new_session'])

    def test_hangup_and_ussd_through_module(self):
        A = self.m.ACTIONS
        self.assertEqual(A['calls-hangup']({'path': C0}, self.ctx), {'out': 'hung up'})
        self.assertEqual(A['calls-hangup']({}, self.ctx), {'out': 'all calls hung up'})
        self.mmset('ussd-out', 'ussd-initiate.txt'); self.mmset('ussd-status', 'ussd-status-user-response.txt')
        self.assertTrue(A['calls-ussd']({'code': '*101#'}, self.ctx)['expects_input'])

    def test_no_mmcli(self):
        os.environ['PATH'] = '/nonexistent'
        A = self.m.ACTIONS
        for a, b in (('calls-hangup', {}), ('calls-ussd', {'code': '*101#'}), ('calls-ussd-cancel', {}),
                     ('calls-ring', {'number': '0911222333', 'seconds': 5})):
            self.assertEqual(A[a](b, self.ctx), {'error': 'not available on this host'}, a)

    def test_log_clear(self):
        self.uc.append_log({'ts': 1, 'number': '1', 'dir': 'in', 'outcome': 'missed'})
        self.assertEqual(self.m.ACTIONS['calls-log-clear']({'confirm': True}, self.ctx)['out'], 'call log cleared')
        self.assertEqual(self.m.ACTIONS['calls-get']({}, self.ctx)['log'], [])

if __name__ == '__main__':
    unittest.main(verbosity=1)
