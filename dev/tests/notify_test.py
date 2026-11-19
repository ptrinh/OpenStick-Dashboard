"""Unit tests for uz-notify + the Notifications settings module. Run: python3 -I dev/tests/notify_test.py
No network: urllib.request.urlopen (Telegram) and uz-notify._post (webhook) are replaced by fakes."""
import hashlib, hmac, io, json, os, socket, stat, sys, tempfile, unittest, urllib.error, urllib.request
from importlib.machinery import SourceFileLoader
from importlib.util import module_from_spec, spec_from_file_location, spec_from_loader

R = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))
FIX = os.path.join(R, 'dev', 'fixtures', 'notify')
BIN = os.path.join(R, 'rootfs', 'usr', 'local', 'bin', 'uz-notify')
MOD = os.path.join(R, 'rootfs', 'usr', 'local', 'lib', 'uz', 'settings', 'notify.py')
sys.dont_write_bytecode = True

def load_un():
    ld = SourceFileLoader('uznotify_test', BIN); m = module_from_spec(spec_from_loader('uznotify_test', ld)); ld.exec_module(m); return m

def load_mod():
    sp = spec_from_file_location('notify_mod_test', MOD); m = module_from_spec(sp); sp.loader.exec_module(m); return m

TOKEN = '123456789:AAFakeTokenForTests_abcdefghijklmnopq'
SECRET = 'w3bh00k-s3cret-XYZ'
URL = 'https://hooks.example.com/services/T0000/B0000/abcdefghijklmnopqrstuvwx'

def fix(name):
    with open(os.path.join(FIX, name), 'rb') as f: return f.read()

class Resp(io.BytesIO):
    def __init__(self, b, status=200): super().__init__(b); self.status = status

def http_error(url, code, body=b'{}'):
    return urllib.error.HTTPError(url, code, 'err', {}, io.BytesIO(body))

class Ctx:
    def __init__(self): self.bg = []
    def write_secret(self, path, text):
        fd = os.open(path + '.tmp', os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
        with os.fdopen(fd, 'w') as f: f.write(text)
        os.replace(path + '.tmp', path)
    def run_bg(self, cmd): self.bg.append(cmd)

class Base(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(); os.environ['UZ_ETC'] = self.tmp.name
        os.environ['UZ_NOTIFY_BIN'] = BIN
        self.un = load_un(); self.mod = load_mod(); self.mod._UN['m'] = self.un; self.ctx = Ctx()
        self.tg_calls, self.posts = [], []
        self._urlopen, self._sleep = urllib.request.urlopen, self.un.time.sleep
        self.un.time.sleep = lambda s: None
        self.tg_reply = lambda url, data: Resp(b'{"ok":true,"result":{}}')
        def fake_urlopen(url, data=None, timeout=None):
            self.tg_calls.append((url, data)); return self.tg_reply(url, data)
        urllib.request.urlopen = fake_urlopen
        self.wh_reply = lambda req: Resp(b'ok', 200)
        def fake_post(req, timeout):
            self.posts.append(req); return self.wh_reply(req)
        self.un._post = fake_post
    def tearDown(self):
        urllib.request.urlopen = self._urlopen; self.un.time.sleep = self._sleep; self.tmp.cleanup()
    def p(self, n): return os.path.join(self.tmp.name, n)
    def write(self, n, s):
        with open(self.p(n), 'w') as f: f.write(s)
    def write_env(self, **kw): self.write('telegram.env', ''.join(f'{k}={v}\n' for k, v in kw.items()))
    def write_cfg(self, c): self.write('notify.json', json.dumps(c))

class Signature(Base):
    def test_hmac_header_matches_raw_body(self):
        self.write_cfg({'webhook': {'enabled': True, 'url': URL, 'secret': SECRET}})
        ok, _ = self.un.webhook_send('test', 'hello', {'a': 1})
        self.assertTrue(ok)
        req = self.posts[0]; body = req.data
        want = 'sha256=' + hmac.new(SECRET.encode(), body, hashlib.sha256).hexdigest()
        self.assertEqual(req.get_header('X-uz-signature'), want)
        self.assertEqual(req.get_method(), 'POST')
        j = json.loads(body)
        self.assertEqual(set(j), {'event', 'text', 'data', 'host', 'ts'})
        self.assertEqual((j['event'], j['text'], j['data']), ('test', 'hello', {'a': 1}))
        self.assertIsInstance(j['ts'], int)

    def test_known_vector(self):
        self.assertEqual(self.un.sign(b'{"a":1}', 'key'),
                         'sha256=' + hmac.new(b'key', b'{"a":1}', hashlib.sha256).hexdigest())

    def test_no_header_without_secret(self):
        self.write_cfg({'webhook': {'enabled': True, 'url': URL}})
        self.un.webhook_send('test', 'x')
        self.assertIsNone(self.posts[0].get_header('X-uz-signature'))

    def test_retries_and_errors(self):
        self.write_cfg({'webhook': {'enabled': True, 'url': URL, 'secret': SECRET}})
        def fail(req): raise http_error(req.full_url, 500)
        self.wh_reply = fail
        ok, detail = self.un.webhook_send('test', 'x')
        self.assertFalse(ok); self.assertEqual(len(self.posts), 3); self.assertEqual(detail, 'HTTP 500')
        self.posts.clear()
        def notfound(req): raise http_error(req.full_url, 404)
        self.wh_reply = notfound
        self.assertFalse(self.un.webhook_send('test', 'x')[0]); self.assertEqual(len(self.posts), 1)   # 4xx: no retry
        self.posts.clear()
        def to(req): raise urllib.error.URLError(socket.timeout('timed out'))
        self.wh_reply = to
        ok, detail = self.un.webhook_send('test', 'x')
        self.assertEqual((ok, detail, len(self.posts)), (False, 'timeout', 3))
        self.assertNotIn('hooks.example.com', detail); self.assertNotIn(SECRET, detail)

class Routing(Base):
    def test_defaults_when_config_absent(self):
        c = self.un.load_config()
        self.assertTrue(c['telegram']['enabled']); self.assertEqual(c['telegram']['events'], list(self.un.EVENTS))
        self.assertFalse(c['webhook']['enabled']); self.assertEqual(c['webhook']['url'], '')

    def test_default_sends_every_event_to_telegram(self):
        self.write_env(TG_TOKEN=TOKEN, TG_CHAT='42')
        for ev in self.un.EVENTS:
            self.assertEqual(list(self.un.notify(ev, 'hi')), ['telegram'])
        self.assertEqual(len(self.tg_calls), len(self.un.EVENTS)); self.assertEqual(self.posts, [])
        self.assertIn(b'chat_id=42', self.tg_calls[0][1])

    def test_event_filtering(self):
        self.write_env(TG_TOKEN=TOKEN, TG_CHAT='42')
        self.write_cfg({'telegram': {'enabled': True, 'events': ['sms_received']},
                        'webhook': {'enabled': True, 'url': URL, 'secret': SECRET, 'events': ['uptime_change', 'bogus']}})
        self.assertEqual(self.un.load_config()['webhook']['events'], ['uptime_change'])
        self.assertEqual(list(self.un.notify('sms_received', 'a')), ['telegram'])
        self.assertEqual(list(self.un.notify('uptime_change', 'b', {'target': 'x'})), ['webhook'])
        self.assertEqual(self.un.notify('lte_up', 'c'), {})
        self.assertEqual(sorted(self.un.notify(self.un.GENERIC, 'd')), ['telegram', 'webhook'])   # plain `uz-notify text`
        self.assertEqual(json.loads(self.posts[0].data)['data'], {'target': 'x'})

    def test_disabled_channel_and_unconfigured(self):
        self.write_env(TG_TOKEN=TOKEN)                         # no chat → not configured
        self.write_cfg({'webhook': {'enabled': False, 'url': URL}})
        self.assertEqual(self.un.notify('test', 'x'), {})

    def test_broken_config_falls_back_to_defaults(self):
        self.write('notify.json', '{not json')
        self.assertEqual(self.un.load_config(), self.un.defaults())

    def test_send_backward_compatible(self):
        self.write_env(TG_TOKEN=TOKEN, TG_CHAT='42')
        self.write_cfg({'telegram': {'enabled': False}})       # send() ignores routing, like before
        self.assertTrue(self.un.send('hello'))
        self.assertTrue(self.tg_calls[0][0].endswith('/sendMessage'))

    def test_cli(self):
        self.write_env(TG_TOKEN=TOKEN, TG_CHAT='42')
        self.assertEqual(self.un.main(['--event', 'nope', 'x']), 2)
        self.assertEqual(self.un.main(['--event', 'lte_up', '--data', '{"ip":"10.0.0.2"}', 'LTE up']), 0)
        self.assertEqual(self.un.main(['plain', 'text']), 0)
        self.assertEqual(self.un.main(['--data', 'notjson', 'x']), 2)

class Validation(Base):
    def test_token_format(self):
        bad = ['', 'abc', '12345:' + 'a' * 35, '123456789:short', '123456789:' + 'a' * 35 + '!', '123456789:aaaaaaaaaaaaaaa\naaaaaaaaaaaaaaaaaaaa', 42]
        for t in bad:
            self.assertIn('error', self.mod.ACTIONS['notify-telegram-set']({'token': t}, self.ctx), t)
        self.assertEqual(self.tg_calls, [])                   # never reached the network
        self.assertTrue(self.mod.TOKEN_RE.fullmatch(TOKEN))

    def test_urls(self):
        ok = ['https://example.com/hook', 'https://hooks.slack.com/services/A/B/C', 'http://192.168.1.5:8123/api/webhook/x',
              'https://10.0.0.2/x', 'http://[fd00::5]/x']
        bad = ['ftp://example.com/x', 'http://example.com/x', 'http://8.8.8.8/x', 'http://127.0.0.1/x', 'https://127.0.0.1/x',
               'https://169.254.169.254/x', 'https://user:pw@example.com/x', 'https://exa mple.com/x', 'https://example.com/x#f',
               'https://' + 'a' * 600 + '.com/', 'https://-bad-.com/x', 'https://example.com:99999/x', 'javascript:alert(1)', 123]
        for u in ok: self.assertIsNone(self.mod.check_url(u), u)
        for u in bad: self.assertIsNotNone(self.mod.check_url(u), u)

    def test_secret_and_events(self):
        self.assertIsNone(self.mod.check_secret(SECRET))
        for s in ('short', 'has space inside', 'x' * 300, 'tab\there!', 5): self.assertIsNotNone(self.mod.check_secret(s))
        A = self.mod.ACTIONS['notify-events-set']
        self.assertIn('error', A({'telegram': ['sms_received', 'evil']}, self.ctx))
        self.assertIn('error', A({'telegram': 'sms_received'}, self.ctx))
        self.assertIn('error', A({}, self.ctx))
        self.assertEqual(A({'telegram': ['lte_up', 'sms_received', 'lte_up'], 'webhook': []}, self.ctx), {'out': 'events saved'})
        c = self.un.load_config()
        self.assertEqual(c['telegram']['events'], ['sms_received', 'lte_up']); self.assertEqual(c['webhook']['events'], [])
        self.assertEqual(stat.S_IMODE(os.stat(self.p('notify.json')).st_mode), 0o600)

    def test_webhook_set(self):
        A = self.mod.ACTIONS['notify-webhook-set']
        self.assertIn('error', A({'secret': SECRET}, self.ctx))                 # no URL yet
        self.assertIn('error', A({'url': 'http://example.com/x'}, self.ctx))
        self.assertIn('error', A({'url': URL, 'secret': 'bad secret'}, self.ctx))
        self.assertFalse(os.path.exists(self.p('notify.json')))
        self.assertIn('out', A({'url': URL, 'secret': SECRET}, self.ctx))
        w = self.un.load_config()['webhook']
        self.assertEqual((w['url'], w['secret'], w['enabled']), (URL, SECRET, True))
        self.assertIn('out', A({'url': 'https://other.example.org/h'}, self.ctx))   # secret kept
        self.assertEqual(self.un.load_config()['webhook']['secret'], SECRET)
        A({'remove_secret': True}, self.ctx)
        self.assertEqual(self.un.load_config()['webhook']['secret'], '')
        self.assertEqual(self.mod.ACTIONS['notify-webhook-clear']({}, self.ctx), {'out': 'webhook removed'})
        self.assertEqual(self.un.load_config()['webhook'], self.un.defaults()['webhook'])

    def test_bad_body_never_raises(self):
        for name, fn in self.mod.ACTIONS.items():
            for body in (None, [], {'token': None, 'url': {}, 'secret': [], 'channel': 7, 'telegram': None}):
                r = fn(body, self.ctx)
                self.assertIsInstance(r, dict, name)

class Secrets(Base):
    def test_get_hides_secrets(self):
        self.write_env(TG_TOKEN=TOKEN, TG_CHAT='424242', TG_BOT='uz801_test_bot')
        self.write_cfg({'webhook': {'enabled': True, 'url': URL, 'secret': SECRET}})
        r = self.mod.ACTIONS['notify-get']({}, self.ctx); s = json.dumps(r)
        self.assertNotIn(TOKEN, s); self.assertNotIn(TOKEN.split(':')[1][:-4], s); self.assertNotIn(SECRET, s)
        self.assertNotIn('abcdefghijklmnopqrstuvwx', s)               # token-like webhook path segment
        self.assertEqual(r['telegram']['token'], 'set'); self.assertEqual(r['telegram']['token_hint'], '…' + TOKEN[-4:])
        self.assertEqual(r['telegram']['chat'], '424242'); self.assertEqual(r['webhook']['secret'], 'set')
        self.assertTrue(r['webhook']['url'].startswith('https://hooks.example.com/'))
        st = self.mod.status(self.ctx)
        self.assertEqual(st, {'telegram': True, 'webhook': True}); self.assertNotIn(TOKEN, json.dumps(st))

    def test_get_when_nothing_configured(self):
        r = self.mod.ACTIONS['notify-get']({}, self.ctx)
        self.assertEqual((r['telegram']['token'], r['webhook']['secret'], r['webhook']['url']), ('not set', 'not set', ''))
        self.assertEqual(self.mod.status(self.ctx), {'telegram': False, 'webhook': False})

    def test_errors_never_contain_token(self):
        self.tg_reply = lambda url, data: (_ for _ in ()).throw(http_error(url, 401, fix('getMe-401.json')))
        r = self.mod.ACTIONS['notify-telegram-set']({'token': TOKEN}, self.ctx)
        self.assertIn('error', r); self.assertIn('401', r['error']); self.assertNotIn(TOKEN, json.dumps(r))
        self.assertFalse(os.path.exists(self.p('telegram.env')))
        def boom(url, data): raise urllib.error.URLError(OSError(f'cannot reach {url}'))
        self.tg_reply = boom
        r = self.mod.ACTIONS['notify-telegram-set']({'token': TOKEN}, self.ctx)
        self.assertNotIn(TOKEN, json.dumps(r)); self.assertNotIn(TOKEN.split(':')[1], json.dumps(r))
        self.write_env(TG_TOKEN=TOKEN, TG_CHAT='1')
        r = self.mod.ACTIONS['notify-test']({'channel': 'telegram'}, self.ctx)
        self.assertIn('error', r); self.assertNotIn(TOKEN.split(':')[1], json.dumps(r))

class Telegram(Base):
    def test_set_detect_test_clear(self):
        self.mod.shutil.which = lambda n: '/bin/systemctl'           # pretend we're on the device
        self.mod.subprocess.run = lambda *a, **k: None
        self.write_env(TG_CHAT='999', OTHER='keep')
        self.tg_reply = lambda url, data: Resp(fix('getMe.json'))
        r = self.mod.ACTIONS['notify-telegram-set']({'token': ' ' + TOKEN + ' '}, self.ctx)
        self.assertEqual(r['bot'], 'uz801_test_bot')
        e = self.un.env()
        self.assertEqual((e['TG_TOKEN'], e['TG_CHAT'], e['TG_BOT'], e['OTHER']), (TOKEN, '999', 'uz801_test_bot', 'keep'))
        self.assertEqual(stat.S_IMODE(os.stat(self.p('telegram.env')).st_mode), 0o600)
        self.assertEqual(self.ctx.bg, ['systemctl restart uz-sms'])

        self.mod.DETECT_WAIT = 0
        self.tg_reply = lambda url, data: Resp(fix('getUpdates-empty.json'))
        r = self.mod.ACTIONS['notify-telegram-detect']({}, self.ctx)
        self.assertIn('@uz801_test_bot', r['error'])
        self.tg_reply = lambda url, data: Resp(fix('getUpdates.json'))
        r = self.mod.ACTIONS['notify-telegram-detect']({}, self.ctx)
        self.assertEqual(r['chat'], '222222')                         # latest *private* chat, not the group
        self.assertEqual(self.un.env()['TG_CHAT'], '222222')
        self.assertIn('getUpdates', self.tg_calls[-1][0])

        self.tg_reply = lambda url, data: Resp(b'{"ok":true,"result":{}}')
        self.assertEqual(self.mod.ACTIONS['notify-test']({'channel': 'telegram'}, self.ctx)['ok'], True)
        self.assertIn('error', self.mod.ACTIONS['notify-test']({'channel': 'sms'}, self.ctx))
        self.assertIn('error', self.mod.ACTIONS['notify-test']({'channel': 'webhook'}, self.ctx))   # not configured
        self.mod.ACTIONS['notify-telegram-clear']({}, self.ctx)
        self.assertFalse(os.path.exists(self.p('telegram.env')))
        self.assertEqual(self.mod.status(self.ctx)['telegram'], False)

    def test_detect_needs_token(self):
        self.assertIn('token', self.mod.ACTIONS['notify-telegram-detect']({}, self.ctx)['error'])

    def test_webhook_test_action(self):
        self.write_cfg({'webhook': {'enabled': True, 'url': URL, 'secret': SECRET, 'events': []}})
        r = self.mod.ACTIONS['notify-test']({'channel': 'webhook'}, self.ctx)      # test ignores the event filter
        self.assertTrue(r['ok']); self.assertEqual(json.loads(self.posts[0].data)['event'], 'test')

if __name__ == '__main__':
    unittest.main(verbosity=1)
