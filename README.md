# OpenStick Dashboard

A tvOS-style web dashboard and a set of small services that turn a cheap **MSM8916 4G USB stick** (UZ801 and friends) running [OpenStick](https://openstick.org/) Debian or postmarketOS into a remote-managed 4G gateway, SMS gateway, USB keyboard/drive and network probe — reachable only through your **Tailscale** tailnet.

> Tested on a UZ801 (modem firmware `UZ801_V3.3`) running openstick.org v0.0.6 (Debian 13, kernel 6.6). The services also run on postmarketOS (`zhihe-generic`, kernel 6.12) with the `qmicli` backend.

## Features

| | |
|---|---|
| **Dashboard** | Apple TV–style UI (ambient light, focus lift, parallax tiles, arrow-key navigation), English / Tiếng Việt / 中文 |
| **4G** | Operator, signal bars, RSRP/SNR, data usage; reconnect. ModemManager (`mmcli`) on Debian, `qmicli` keeper (`uz-lte`) on pmOS |
| **Network** | Public IP + country (Cloudflare trace), latency to 1.1.1.1, Wi-Fi SSID and signal, USB host / Internet-sharing detection |
| **Roles** | `home` (NAT for the USB host, Tailscale exit node) and `travel` (own Wi-Fi hotspot over 4G or the USB host's Internet Sharing; refuses to strand you, auto-reverts after 3 min offline) |
| **Tailscale** | Account / tailnet info, exit-node toggle (shows admin approval), **re-pair to another account** with sign-in link + QR |
| **SMS** | Inbox, send, forward to Telegram, and **SMS remote control** (`<PIN> status/where/wifi/mode/lte/ts/reboot`, works without data) |
| **USB gadget** | Emulated USB keyboard (type text, key combos, live passthrough) and USB drive (upload `.img`/`.iso`, attach read-write / read-only / CD-ROM, blank FAT drives) |
| **GPS** | Modem GNSS via ModemManager, last fix + map link, Telegram `/where` (needs sky view; most sticks have no GPS antenna) |
| **Hotspot** | Set the Wi-Fi password, show a join QR code (generated on the stick with `qrencode`) |
| **LEDs** | Status LEDs (power/Internet, Wi-Fi traffic, 4G searching/traffic), manual modes, "find my stick" blink |
| **Uptime checks** | HTTPS / TCP / ping targets with latency, over whatever uplink is active; Telegram alert on change |
| **System** | Storage bars, RAM, temperature, services, logs; zram swap and storage trimming for 3–4 GB eMMC |
| **Passkeys** | Optional WebAuthn sign-in: once a passkey exists, the dashboard requires it |
| **Settings** | Notifications (Telegram + signed webhooks per event), Wi-Fi networks (scan/join/forget with automatic rollback), Cellular (APN, roaming, network mode, SIM PIN), SMS allow-list, uptime check targets + interval, hotspot channel/hidden/clients, System (hostname with Tailscale-name pinning, time zone, apt pin to `trixie`, safe `apt upgrade`, scheduled restart), VPN for Travel (VLESS link / sing-box JSON import), LED event mapping |
| **USB link** | Address-only by default (the host keeps its own Internet); optional "share Internet with the USB computer" |

## Security model

* `uz-web` listens on `:8080`. Requests that come through **`tailscale serve`** must carry the `Tailscale-User-Login` of the node's owner.
* **Direct local-IP access is only allowed while the stick is not paired** with any Tailscale account (first setup / after "Pair with another account"). It also requires a private source address and an IP-literal `Host` header (blocks DNS rebinding). Anyone on that LAN can use the dashboard during that window — pair before joining untrusted networks.
* State-changing requests need `X-UZ: 1` and `Sec-Fetch-Site: same-origin` (CSRF).
* **Passkeys** (WebAuthn, ES256 / EdDSA / RS256, user verification required, attestation `none`) are bound to the tailnet hostname. With at least one passkey, every API except the sign-in ceremony returns `401` without a session cookie (`HttpOnly; Secure; SameSite=Strict`, 24 h). Passkeys need HTTPS, so on a local IP a passkey-protected stick only offers Tailscale re-pairing. "Pair with another account" deletes passkeys (they cannot work on a new hostname). Recovery: `uz-passkey reset` over Tailscale SSH or USB.
* SMS commands need a PIN (`/etc/uz/sms.pin`); 5 wrong attempts per hour lock commands. OTP-style messages (`123456 is your code`) are forwarded, never treated as commands.
* Secrets live on the stick only, mode `0600`: `/etc/uz/{hotspot.psk,sms.pin,telegram.env,passkeys.json}`.

## Layout

```
rootfs/                     files copied to / on the stick
  usr/local/bin/uz-web       dashboard server (Python stdlib + python3-cryptography for passkeys)
  usr/local/share/uz/index.html  the UI (single file, no external requests)
  usr/local/lib/uz/webauthn.py   passkey relying party
  usr/local/bin/uz-*         services and helpers (sms, gps, led, mode, gadget, probe, zram, lte, passkey…)
  etc/systemd/system/        units
  etc/uz/uz.conf             settings (role, backend, exit node…)
  usr/local/lib/uz/settings/  settings modules (server side) — see docs/settings-modules.md
  usr/local/share/uz/settings/ settings modules (UI)
tools/
  stick-setup.sh             runs on the stick: installs files, enables services (idempotent)
  deploy.sh                  from your computer: setup | ssh | root | push (Tailscale SSH, or USB + password)
  customize-openstick-image.sh   bake everything into an OpenStick full_emmc.bin rootfs before flashing
  telegram-setup.sh          install the Telegram bot token + chat id on the stick
  pty-auth.py                answers password prompts for the USB/SSH fallback
```

## Install

### On a stick that already runs OpenStick Debian or postmarketOS

1. Get the stick on the Internet (Wi-Fi: `nmcli dev wifi connect <SSID> --ask`) and install Tailscale; `tailscale up --ssh`.
2. From your computer (with Tailscale):
   ```sh
   UZ_TS_HOST=<stick-name> tools/deploy.sh setup
   ```
   On Debian this also installs `qrencode` and `python3-cryptography`. Without Tailscale yet, use the USB link
   (`192.168.5.1` on OpenStick, `172.16.42.1` on pmOS): `UZ_VIA=usb UZ_PASSWORD_FILE=~/.config/uz801/password tools/deploy.sh setup`.
3. Open `https://<stick-name>.<tailnet>.ts.net` (the setup runs `tailscale serve --bg 8080`).

### Baking it into an OpenStick image before flashing

On an arm64 Linux machine (a VM is fine), loop-mount the rootfs partition of openstick.org's `full_emmc.bin` and run

```sh
sudo tools/customize-openstick-image.sh /mnt/os ./new-user-password [carried-state.tgz]
```

It installs Python, Tailscale, `qrencode` and the dashboard, sets a real password for `user` (the image ships with `1`), locks root's password, **deletes the SSH host keys baked into the public image** (regenerated on first boot), clears `machine-id`, and stops the default `Openstick` hotspot (well-known password) from auto-starting. Inject your stick's own calibration partitions (`modemst1/2`, `fsg`, `fsc`, `persist`, `sec`, `modem`) into the image before flashing — never another device's.

### Telegram (optional)

Create a bot with @BotFather, send it `/start`, then `UZ801_TG_TOKEN=<token> tools/telegram-setup.sh`.

## Notes and gotchas

* The OpenStick image's apt sources say `stable`; pin them to `trixie` so a future Debian release isn't pulled onto a custom kernel.
* On that image Tailscale logs `iptables: unknown option "--nfmask"` (CONNMARK); exit-node forwarding may need a kernel/iptables fix.
* About 200 MB of the 512 MB RAM is reserved by firmware (the modem's `mpss` region alone is 85 MB on kernel 6.6). zram swap is enabled by `uz-zram`.
* macOS ignores a new USB network interface while the screen is locked; if the stick's USB link never appears, unlock and re-plug (or reset the USB device).
* Never pipe `fastboot` output into `head` — cutting the response hangs lk1st/lk2nd's fastboot.

## Development

`dev/run.sh` serves the dashboard on `http://127.0.0.1:18080` with auth disabled; `for t in dev/tests/*_test.py; do python3 -I $t; done` runs the module tests (fixtures in `dev/fixtures/`). New settings areas are self-contained modules — see [docs/settings-modules.md](docs/settings-modules.md).

## License

MIT
