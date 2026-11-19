#!/usr/bin/env python3
"""Tests for settings/leds.py and uz-led's auto mapping (fake sysfs + stub commands).
Run: python3 dev/tests/leds_test.py"""
import atexit, hashlib, importlib.util, json, os, shutil, subprocess, sys, tempfile, unittest

R = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))
FX = os.path.join(R, 'dev', 'fixtures', 'leds')
UZLED = os.path.join(R, 'rootfs/usr/local/bin/uz-led')
TMP = tempfile.mkdtemp(prefix='uzled-')
atexit.register(shutil.rmtree, TMP, True)
os.environ['UZ_LED_MAP'] = os.path.join(TMP, 'etc', 'led-map.conf')
os.environ['UZ_LED_VAR'] = os.path.join(TMP, 'var')
spec = importlib.util.spec_from_file_location('leds', os.path.join(R, 'rootfs/usr/local/lib/uz/settings/leds.py'))
leds = importlib.util.module_from_spec(spec); spec.loader.exec_module(leds)


def rd(p, d=None):
    try:
        with open(p) as f: return f.read().strip()
    except OSError: return d


def wr(p, t):
    os.makedirs(os.path.dirname(p), exist_ok=True)
    with open(p, 'w') as f: f.write(t)


class Ctx: cache = {}


class Parse(unittest.TestCase):
    def test_map_fixture(self):
        self.assertEqual(leds.parse_map(rd(os.path.join(FX, 'led-map.conf'))), {'red': 'sms', 'green': 'usb', 'blue': 'lte'})
        self.assertEqual(leds.parse_map(''), leds.DEFAULT)
        self.assertEqual(leds.parse_map(leds.render({'red': 'off', 'green': 'heartbeat', 'blue': 'tailscale'})),
                         {'red': 'off', 'green': 'heartbeat', 'blue': 'tailscale'})

    def test_validate(self):
        self.assertEqual(leds.validate({'red': 'usb'}, leds.DEFAULT), {'red': 'usb', 'green': 'wifi', 'blue': 'lte'})
        for bad in ({'red': 'disco'}, {'purple': 'off'}, {'red': ['off']}, {'red': 'off; reboot'}, 'x'):
            with self.subTest(bad), self.assertRaises(ValueError): leds.validate(bad, leds.DEFAULT)

    def test_status(self):
        st = leds.parse_status(rd(os.path.join(FX, 'uz-led-status.txt')))
        self.assertEqual(st['green'], {'mode': 'off', 'auto': 'wifi', 'trigger': 'none', 'on': '0'})
        self.assertEqual(set(st), {'red', 'green', 'blue'})

    def test_hash_matches_shell(self):
        last = [l for l in rd(os.path.join(FX, 'sms.jsonl')).splitlines() if l.startswith('{"dir": "in"')][-1]
        exp = hashlib.md5((last + '\n').encode()).hexdigest()
        self.assertEqual(leds.last_incoming_hash(os.path.join(FX, 'sms.jsonl')), exp)
        tool = ['md5sum'] if shutil.which('md5sum') else ['md5', '-q'] if shutil.which('md5') else None
        if tool:
            out = subprocess.run(['sh', '-c', 'printf "%s\\n" "$1" | ' + ' '.join(tool), 'x', last], capture_output=True, text=True).stdout
            self.assertEqual(out.split()[0], exp)


class Actions(unittest.TestCase):
    def test_set_and_get(self):
        os.makedirs(os.path.dirname(leds.MAP), exist_ok=True)
        r = leds.map_set({'red': 'tailscale', 'blue': 'sms'}, Ctx)
        self.assertNotIn('error', r, r)
        self.assertEqual(leds.read_map(), {'red': 'tailscale', 'green': 'wifi', 'blue': 'sms'})
        self.assertEqual(leds.status(Ctx)['map']['red'], 'tailscale')
        self.assertIn('error', leds.map_set({'green': 'rainbow'}, Ctx))
        self.assertEqual(leds.read_map()['green'], 'wifi')
        g = leds.get({}, Ctx)
        self.assertEqual(g['sources'], list(leds.SOURCES))


# ---------------------------------------------------------------- uz-led against a fake sysfs
STUBS = {
    'ip': '''case "$*" in *"route show default"*) [ -n "$FAKE_NODEFAULT" ] || echo "default via 10.0.0.1 dev wwan0";;
             *"addr show"*) [ -n "$FAKE_NOLTE" ] || echo "    inet 10.0.0.2/30 scope global wwan0";; esac''',
    'ping': '[ -z "$FAKE_OFFLINE" ]',
    'tailscale': '[ -n "$FAKE_TS_DOWN" ] && echo \'{"BackendState": "Stopped"}\' || echo \'{"BackendState": "Running", "Self": {}}\'',
    'pgrep': 'exit 1', 'pkill': 'exit 0', 'modprobe': 'exit 0',
    'md5sum': 'python3 -c "import hashlib,sys; print(hashlib.md5(sys.stdin.buffer.read()).hexdigest(), \' -\')"',
}


class UzLed(unittest.TestCase):
    def setUp(self):
        self.d = tempfile.mkdtemp(dir=TMP)
        self.sys = os.path.join(self.d, 'sys')
        for l in ('red:power', 'green:wlan', 'blue:wan'):
            wr(f'{self.sys}/class/leds/{l}/trigger', 'none [timer] heartbeat netdev\n'); wr(f'{self.sys}/class/leds/{l}/brightness', '0\n')
        wr(f'{self.sys}/class/net/wlan0/operstate', 'up\n'); wr(f'{self.sys}/class/net/usb0/carrier', '1\n')
        bindir = os.path.join(self.d, 'bin'); os.makedirs(bindir)
        for n, body in STUBS.items():
            wr(f'{bindir}/{n}', '#!/bin/sh\n' + body + '\n'); os.chmod(f'{bindir}/{n}', 0o755)
        self.var = os.path.join(self.d, 'var'); os.makedirs(self.var)
        self.env = {'PATH': bindir + ':/usr/bin:/bin', 'UZ_LED_SYSFS': self.sys, 'UZ_LED_CONF': os.path.join(self.d, 'led.conf'),
                    'UZ_LED_MAP': os.path.join(self.d, 'led-map.conf'), 'UZ_LED_VAR': self.var}

    def run_led(self, *args, **env):
        r = subprocess.run([os.environ.get('UZ_TEST_SH', 'sh'), UZLED, *args], env={**self.env, **env}, capture_output=True, text=True, timeout=20)
        self.assertEqual(r.returncode, 0, r.stderr); return r.stdout

    def led(self, name, f): return rd(f'{self.sys}/class/leds/{name}/{f}')

    def test_defaults_are_old_behaviour(self):
        self.run_led('once')
        self.assertEqual((self.led('red:power', 'trigger'), self.led('red:power', 'brightness')), ('none', '1'))
        self.assertEqual((self.led('green:wlan', 'trigger'), self.led('green:wlan', 'device_name')), ('netdev', 'wlan0'))
        self.assertEqual((self.led('blue:wan', 'trigger'), self.led('blue:wan', 'device_name')), ('netdev', 'wwan0'))

    def test_offline_and_no_wifi(self):
        wr(f'{self.sys}/class/net/wlan0/operstate', 'down\n')
        self.run_led('once', FAKE_OFFLINE='1', FAKE_NOLTE='1')
        self.assertEqual((self.led('red:power', 'trigger'), self.led('red:power', 'delay_on')), ('timer', '150'))
        self.assertEqual((self.led('green:wlan', 'trigger'), self.led('green:wlan', 'brightness')), ('none', '0'))
        self.assertEqual((self.led('blue:wan', 'trigger'), self.led('blue:wan', 'brightness')), ('none', '0'))

    def test_mapping(self):
        wr(self.env['UZ_LED_MAP'], 'red=usb\ngreen=tailscale\nblue=heartbeat\n')
        self.run_led('once')
        self.assertEqual((self.led('red:power', 'trigger'), self.led('red:power', 'brightness')), ('none', '1'))
        self.assertEqual((self.led('green:wlan', 'trigger'), self.led('green:wlan', 'brightness')), ('none', '1'))
        self.assertEqual(self.led('blue:wan', 'trigger'), 'heartbeat')
        wr(f'{self.sys}/class/net/usb0/carrier', '0\n')
        self.run_led('once', FAKE_TS_DOWN='1')
        self.assertEqual(self.led('red:power', 'brightness'), '0'); self.assertEqual(self.led('green:wlan', 'brightness'), '0')
        out = self.run_led('status')
        self.assertIn('red mode=auto auto=usb', out); self.assertIn('blue mode=auto auto=heartbeat trigger=heartbeat', out)

    def test_invalid_map_falls_back(self):
        wr(self.env['UZ_LED_MAP'], 'red=$(reboot)\ngreen=rainbow\n')
        self.run_led('once')
        self.assertEqual(self.led('red:power', 'brightness'), '1')
        self.assertEqual(self.led('green:wlan', 'device_name'), 'wlan0')
        self.assertIn('red mode=auto auto=internet', self.run_led('status'))

    def test_manual_mode_wins(self):
        wr(self.env['UZ_LED_CONF'], 'green=heartbeat\nred=off\n')
        wr(self.env['UZ_LED_MAP'], 'green=usb\n')
        self.run_led('once')
        self.assertEqual(self.led('green:wlan', 'trigger'), 'heartbeat')
        self.assertEqual(self.led('red:power', 'brightness'), '0')

    def test_sms(self):
        wr(self.env['UZ_LED_MAP'], 'blue=sms\n')
        log = os.path.join(self.var, 'sms.jsonl')
        shutil.copy(os.path.join(FX, 'sms.jsonl'), log)
        self.run_led('once')                                            # first run marks existing SMS seen
        self.assertTrue(rd(os.path.join(self.var, 'sms.seen')))
        self.assertEqual(self.led('blue:wan', 'brightness'), '0')
        with open(log, 'a') as f: f.write(json.dumps({'dir': 'in', 'peer': '+1', 'text': 'new', 'ts': 't'}) + '\n')
        self.run_led('once')
        self.assertEqual((self.led('blue:wan', 'trigger'), self.led('blue:wan', 'delay_on')), ('timer', '150'))
        leds.VAR = self.var                                             # dashboard "mark seen"
        self.assertEqual(leds.sms_seen({}, Ctx)['out'], 'SMS marked as seen')
        self.run_led('once')
        self.assertEqual((self.led('blue:wan', 'trigger'), self.led('blue:wan', 'brightness')), ('none', '0'))
        with open(log, 'a') as f: f.write(json.dumps({'dir': 'out', 'peer': '+1', 'text': 'reply', 'ts': 't'}) + '\n')
        self.run_led('once')                                            # outgoing SMS does not count
        self.assertEqual(self.led('blue:wan', 'brightness'), '0')

    def test_cli_unchanged(self):
        self.assertIn('usage: uz-led daemon', self.run_led())
        r = subprocess.run([os.environ.get('UZ_TEST_SH', 'sh'), UZLED, 'set', 'red', 'disco'], env=self.env, capture_output=True, text=True)
        self.assertEqual(r.returncode, 1)
        self.assertEqual(self.run_led('set', 'red', 'slow').strip(), 'red=slow')
        self.assertEqual(rd(self.env['UZ_LED_CONF']), 'red=slow')


if __name__ == '__main__':
    unittest.main(verbosity=1)
