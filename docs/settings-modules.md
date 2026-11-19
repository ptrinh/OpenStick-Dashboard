# Settings modules

Each settings area is **two files** and nothing else:

| File | Role |
|---|---|
| `rootfs/usr/local/lib/uz/settings/<name>.py` | server actions + a cheap `status()` |
| `rootfs/usr/local/share/uz/settings/<name>.js` | registers a tile on the **Settings** shelf and renders its sheet |

`uz-web` loads every `*.py` at start (`load_modules`), the UI loads every `*.js` after the first status.
Do **not** edit `uz-web` or `index.html` from a module — if you need something from them, say so.

## Python contract (`<name>.py`, `[a-z0-9_]+`)

```python
def init(ctx): ...                 # optional, called once at start
def status(ctx) -> dict: ...       # optional; must be FAST (<50 ms, no network, no qmicli/mmcli calls) —
                                   # it runs on every /api/status (every 10 s). Cache slow data in ctx.cache.
ACTIONS = {                        # action names: '<prefix>-<verb>', globally unique, [a-z-]+
    'wifi-scan': lambda body, ctx: {...},
}
```
* An action gets the parsed JSON `body` (≤ 32 KB) and returns a dict: `{'out': 'message'}` for success,
  `{'error': 'message'}` for failure (English, short — shown as a toast), plus any data fields.
* Raise nothing: catch your own exceptions. Validate every input strictly (regex / ranges); never pass user
  input through a shell — use `subprocess.run([...])` with an argument list.
* Long work (apt, network changes that may cut the connection): run it detached with `ctx.run_bg(cmd)`
  (systemd-run) and expose progress through `status()` / a log file.
* Auth, CSRF and passkey gating are done by `uz-web` before your action runs.

`ctx` helpers: `sh(cmd, t)` (shell, returns stdout), `rd(path, default)`, `run_bg(cmd)`, `conf()` (dict of
`/etc/uz/uz.conf`), `set_conf('UZ_KEY', value)`, `write_secret(path, text)` (0600 atomic), `nm_get(*nmcli -g args)`,
`cache` (shared dict).

Status data appears to the UI as `S.settings.<name>`.

## JavaScript contract (`<name>.js`)

```js
UZ.register({
  id: 'wifi', order: 20,                 // shelf position
  color: 'green',                        // gradient key: blue green teal orange purple gray pink yellow red
  icon: 'wifi',                          // built-in icon name, or iconSvg: '<path d="…"/>' (24×24, stroke)
  title: {en: 'Wi-Fi', vi: 'Wi-Fi', zh: 'Wi-Fi'},
  sub: S => '…',                         // tile subtitle (string, {en,vi,zh}, or function of status)
  open(S) {                              // open a sheet
    UZ.openSheet('green', 'wifi', 'Title', 'Description', `<div>…</div><div class="actions">${UZ.closeBtn()}</div>`);
    UZ.$('#my-btn').onclick = async () => { const r = await UZ.post('wifi-scan', {}); UZ.toast(r.error || r.out); };
  },
});
```
* Every user-visible string must exist in **en, vi, zh** — keep a local `const T = {en:{…}, vi:{…}, zh:{…}}`
  and pick with `UZ.tr(...)` / `UZ.lang`.
* Escape everything you interpolate with `UZ.esc()`.
* Available: `UZ.S` (status), `UZ.post(action, body)`, `UZ.act(action, body)` (post + toast + reload),
  `UZ.openSheet(color, icon, title, desc, html)`, `UZ.closeSheet()`, `UZ.closeBtn()`, `UZ.toast(msg)`,
  `UZ.reload()`, `UZ.$(sel)` / `UZ.$$(sel)` (inside the open sheet), `UZ.esc`, `UZ.svg(name)`, `UZ.G`, `UZ.I`.
* Reuse the page's classes: `.btn .btn.primary .btn.red .btn.sm`, `.field`, `.chips .chip .chip.on`,
  `.stat .l .n`, `.kv`, `.list .item`, `.actions`, `.dot.ok/.warn/.bad`. Mark focusable controls `data-focus`.
* Don't use `confirm()/alert()`; confirm destructive steps inside the sheet.
* Script must not throw at load; no external requests (CSP: same-origin only).

## Local test

```sh
dev/run.sh            # serves the UI + your modules on http://127.0.0.1:18080 with auth disabled
```
`status()` and actions run on your Mac in dev mode: guard device-only commands (check `shutil.which`, file
existence) so they return a clear `{'error': 'not available on this host'}` instead of crashing.
Unit-test parsers with captured command output (keep fixtures in `dev/fixtures/<name>/`).
