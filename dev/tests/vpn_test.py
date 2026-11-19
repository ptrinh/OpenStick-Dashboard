#!/usr/bin/env python3
"""Unit tests for rootfs/usr/local/lib/uz/settings/vpn.py — run: python3 dev/tests/vpn_test.py"""
import atexit, importlib.util, json, os, shutil, stat, sys, tempfile, unittest

R = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))
FX = os.path.join(R, 'dev', 'fixtures', 'vpn')
def rd(p):
    with open(p) as f: return f.read()


TMP = tempfile.mkdtemp(prefix='uzvpn-')
atexit.register(shutil.rmtree, TMP, True)
os.environ['UZ_VPN_CONF'] = os.path.join(TMP, 'sing-box.json')
spec = importlib.util.spec_from_file_location('vpn', os.path.join(R, 'rootfs/usr/local/lib/uz/settings/vpn.py'))
vpn = importlib.util.module_from_spec(spec); spec.loader.exec_module(vpn)

LINKS = json.loads(rd(os.path.join(FX, 'links.json')))
UUID = '0f1e2d3c-4b5a-6978-8a9b-0c1d2e3f4a5b'
PBK = 'AbCdEfGhIjKlMnOpQrStUvWxYz0123456789-_AbCdE'
SID = '6ba85179e30d4fc2'
SECRETS = (UUID, PBK, SID, 's3cr3t-hy2-pass', 'aPrivKeyBase64ShouldNeverLeak')


class Ctx:
    def __init__(self, mode='home'): self.cache, self.bg, self.mode = {}, [], mode
    def conf(self): return {'UZ_MODE': self.mode}
    def run_bg(self, cmd): self.bg.append(cmd)


def no_secret(tc, obj):
    s = json.dumps(obj, ensure_ascii=False)
    for x in SECRETS: tc.assertNotIn(x, s)


class Link(unittest.TestCase):
    def test_valid(self):
        p = vpn.parse_vless(LINKS['valid'])
        self.assertEqual((p['uuid'], p['host'], p['port'], p['sni'], p['pbk'], p['sid'], p['fp'], p['flow'], p['type']),
                         (UUID, 'vpn.example.net', 443, 'www.microsoft.com', PBK, SID, 'chrome', 'xtls-rprx-vision', 'tcp'))
        self.assertEqual(p['name'], 'SG home 🇸🇬')           # percent-encoded name

    def test_ipv6_brackets(self):
        p = vpn.parse_vless(LINKS['ipv6'])
        self.assertEqual((p['host'], p['port'], p['sid'], p['fp'], p['flow']), ('2001:db8::7', 8443, '', 'chrome', ''))
        c = vpn.build_config(p)
        self.assertEqual(c['outbounds'][0]['server'], '2001:db8::7')
        self.assertNotIn('flow', c['outbounds'][0])

    def test_grpc_and_cjk_name(self):
        p = vpn.parse_vless(LINKS['grpc'])
        self.assertEqual((p['host'], p['type'], p['service_name'], p['name']), ('203.0.113.9', 'grpc', 'gsvc', '旅行'))
        self.assertEqual(vpn.build_config(p)['outbounds'][0]['transport'], {'type': 'grpc', 'service_name': 'gsvc'})

    def test_rejects(self):
        for k, frag in (('missing_pbk', 'pbk'), ('tls_not_reality', 'Reality'), ('bad_uuid', 'UUID'), ('bad_port', 'port'),
                        ('no_port', 'port'), ('bad_sid', 'sid'), ('shell_host', 'host'), ('vision_grpc', 'gRPC')):
            with self.subTest(k):
                with self.assertRaises(ValueError) as cm: vpn.parse_vless(LINKS[k])
                self.assertIn(frag, str(cm.exception))
                no_secret(self, str(cm.exception))
        for bad in ('vmess://abc', '', 'vless://' + 'a' * 5000, 'vless://x@y:1\n'):
            with self.assertRaises(ValueError): vpn.parse_vless(bad)

    def test_modern_config_shape(self):
        c = vpn.build_config(vpn.parse_vless(LINKS['valid']), (1, 12, 12))
        tun = c['inbounds'][0]
        self.assertEqual(tun['interface_name'], 'tun-uz'); self.assertTrue(tun['auto_route'])
        self.assertIn('100.64.0.0/10', tun['route_exclude_address']); self.assertNotIn('sniff', tun)
        self.assertEqual(c['dns']['servers'][0], {'type': 'tls', 'tag': 'remote', 'server': '1.1.1.1', 'detour': 'vless'})
        self.assertEqual(c['route']['final'], 'vless'); self.assertEqual(c['route']['default_domain_resolver'], 'local')
        self.assertEqual([o['type'] for o in c['outbounds']], ['vless', 'direct'])

    def test_legacy_matches_example(self):
        """For sing-box < 1.12 the generated config has exactly the shape of rootfs/etc/uz/sing-box.json.example."""
        ex = json.loads(rd(os.path.join(R, 'rootfs/etc/uz/sing-box.json.example')))
        p = vpn.parse_vless(LINKS['valid'])
        p.update(host='CHANGE_ME_DDNS_HOST', port=443, uuid='CHANGE_ME_UUID', sni='CHANGE_ME_SNI', pbk='CHANGE_ME_PBK', sid='CHANGE_ME_SID')
        self.assertEqual(vpn.build_config(p, (1, 11, 0)), ex)

    def test_version(self):
        self.assertEqual(vpn.parse_version(rd(os.path.join(FX, 'version.txt'))), (1, 12, 12))
        self.assertIsNone(vpn.parse_version('garbage'))
        self.assertTrue(vpn.modern(None)); self.assertFalse(vpn.modern((1, 11, 9)))


class Json(unittest.TestCase):
    def test_fix_tun_and_summary(self):
        c, notes = vpn.check_json(rd(os.path.join(FX, 'custom.json')))
        tun = c['inbounds'][0]
        self.assertEqual(tun['interface_name'], 'tun-uz'); self.assertIn('100.64.0.0/10', tun['route_exclude_address'])
        self.assertEqual(len(notes), 2)
        s = vpn.summary(c)
        self.assertEqual(s['main']['tag'], 'hy2'); self.assertEqual(s['main']['server'], 'hy.example.org')
        self.assertEqual(s['main']['port'], 8443); self.assertEqual(s['outbounds'][1]['transport'], 'grpc')
        self.assertTrue(s['outbounds'][1]['reality'])
        no_secret(self, s)
        no_secret(self, notes)

    def test_add_tun(self):
        c, notes = vpn.check_json(rd(os.path.join(FX, 'no-tun.json')))
        self.assertEqual(c['inbounds'][0]['interface_name'], 'tun-uz'); self.assertEqual(len(notes), 1)
        no_secret(self, vpn.summary(c))

    def test_rejects(self):
        for bad in ('', '[]', '{"outbounds": []}', '{"outbounds": [1]}', 'not json', '{"outbounds":[{"type":"direct"}],"inbounds":[{"type":"tun"},{"type":"tun"}]}',
                    '{"outbounds":[{"type":"direct"}],"inbounds":{}}', '{"outbounds":[{"type":"direct"}], "x": "' + 'a' * 70000 + '"}'):
            with self.subTest(bad[:40]):
                with self.assertRaises(ValueError): vpn.check_json(bad)

    def test_summary_link_config(self):
        s = vpn.summary(vpn.build_config(vpn.parse_vless(LINKS['valid'])))
        self.assertEqual(s['main'], {'tag': 'vless', 'type': 'vless', 'server': 'vpn.example.net', 'port': 443, 'sni': 'www.microsoft.com',
                                     'transport': 'tcp', 'reality': True, 'flow': 'xtls-rprx-vision'})
        self.assertTrue(s['ts_excluded']); self.assertFalse(s['placeholder'])
        no_secret(self, s)

    def test_redact(self):
        c = json.loads(rd(os.path.join(FX, 'custom.json')))
        msg = vpn.redact(f'bad uuid {UUID} / pass s3cr3t-hy2-pass / sid {SID}', vpn.secrets_of(c))
        no_secret(self, msg)

    def test_trace(self):
        self.assertEqual(vpn.parse_trace(rd(os.path.join(FX, 'trace.txt'))), {'ip': '203.0.113.77', 'loc': 'SG'})
        self.assertIsNone(vpn.parse_trace('ip=<script>'))


class Actions(unittest.TestCase):
    def setUp(self):
        self.path = os.environ.get('PATH', '')
        if os.path.exists(vpn.CONF): os.remove(vpn.CONF)

    def tearDown(self): os.environ['PATH'] = self.path

    def fake_singbox(self, rc, out=''):
        d = tempfile.mkdtemp(dir=TMP)
        with open(os.path.join(d, 'sing-box'), 'w') as f:
            f.write(f'#!/bin/sh\ncase $1 in version) echo "sing-box version 1.12.12";; check) echo "{out}" >&2; exit {rc};; esac\n')
        os.chmod(os.path.join(d, 'sing-box'), 0o755)
        os.environ['PATH'] = d + os.pathsep + self.path

    def test_import_link_writes_0600_no_secrets(self):
        os.environ['PATH'] = '/usr/bin:/bin'          # no sing-box
        ctx = Ctx()
        r = vpn.import_({'link': LINKS['valid']}, ctx)
        self.assertNotIn('error', r, r); no_secret(self, r)
        self.assertEqual(stat.S_IMODE(os.stat(vpn.CONF).st_mode), 0o600)
        self.assertEqual(json.loads(rd(vpn.CONF))['outbounds'][0]['uuid'], UUID)
        self.assertEqual([f for f in os.listdir(TMP) if f.startswith('.sing-box.')], [])   # no temp file left
        self.assertEqual(vpn.status(ctx), {'installed': False, 'configured': True, 'active': False})
        g = vpn.get({}, ctx); no_secret(self, g)
        self.assertEqual(g['summary']['main']['server'], 'vpn.example.net')

    def test_import_json_text_and_link_in_config_field(self):
        os.environ['PATH'] = '/usr/bin:/bin'
        r = vpn.import_({'config': rd(os.path.join(FX, 'custom.json'))}, Ctx()); no_secret(self, r)
        self.assertEqual(len(r['notes']), 2)
        r = vpn.import_({'config': LINKS['valid']}, Ctx()); self.assertNotIn('error', r)
        self.assertIn('error', vpn.import_({'link': LINKS['valid'], 'config': '{}'}, Ctx()))
        self.assertIn('error', vpn.import_({}, Ctx()))
        self.assertIn('error', vpn.import_({'link': 5}, Ctx()))

    def test_check_failure_is_redacted_and_keeps_old(self):
        self.fake_singbox(0)
        ctx = Ctx()
        self.assertNotIn('error', vpn.import_({'link': LINKS['ipv6']}, ctx))
        before = rd(vpn.CONF)
        self.fake_singbox(1, f'FATAL decode outbounds[0]: uuid {UUID} public_key {PBK}')
        ctx.cache.clear()
        r = vpn.import_({'link': LINKS['valid']}, ctx)
        self.assertIn('rejected', r['error']); no_secret(self, r)
        self.assertEqual(rd(vpn.CONF), before)
        self.assertEqual([f for f in os.listdir(TMP) if f.startswith('.sing-box.')], [])

    def test_remove_and_enable_guards(self):
        os.environ['PATH'] = '/usr/bin:/bin'
        self.assertIn('error', vpn.remove({}, Ctx()))
        self.assertIn('error', vpn.remove({'confirm': 'yes'}, Ctx()))
        self.assertIn('error', vpn.enable({'on': 'true'}, Ctx()))
        self.assertIn('error', vpn.enable({}, Ctx()))


if __name__ == '__main__':
    unittest.main(verbosity=1)
