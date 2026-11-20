# OpenStick Dashboard

A tvOS-style web dashboard and a set of small services that turn a cheap **MSM8916 4G USB stick** (UZ801 and friends) running [OpenStick](https://openstick.org/) Debian or postmarketOS into a remote-managed 4G gateway, SMS gateway, USB keyboard/drive and network probe — reachable only through your **Tailscale** tailnet.

> Tested on a UZ801 (modem firmware `UZ801_V3.3`) running openstick.org v0.0.6 (Debian 13, kernel 6.6). The services also run on postmarketOS (`zhihe-generic`, kernel 6.12) with the `qmicli` backend.

## Features

| | |
|---|---|
| **Dashboard** | Apple TV–style UI with Status / Statistics / Settings tabs (ambient light, focus lift, parallax tiles, arrow-key navigation), English / Tiếng Việt / 中文 |
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
| **Data usage** | 4G traffic per hour/day from ModemManager bearer counters: 24 h / 7 d / 30 d / billing-cycle charts on the Statistics tab, cycle start day, monthly cap with 80 % / 100 % notifications |
| **USB link** | Address-only by default (the host keeps its own Internet); optional "share Internet with the USB computer" |

## Security model

* `uz-web` listens on port 80. Requests that come through **`tailscale serve`** must carry the `Tailscale-User-Login` of the node's owner.
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
install.sh                   runs on the stick: installs packages + Tailscale, then tools/stick-setup.sh
tools/
  stick-setup.sh             runs on the stick: installs files, enables services (idempotent)
  deploy.sh                  from your computer: setup | ssh | root | push (Tailscale SSH, or USB + password)
  customize-openstick-image.sh   bake everything into an OpenStick full_emmc.bin rootfs before flashing
  telegram-setup.sh          install the Telegram bot token + chat id on the stick
  pty-auth.py                answers password prompts for the USB/SSH fallback
```

## Setup guide (from a stock stick to the dashboard)

Budget about 45 minutes. You need the stick, a computer (macOS, Linux or Windows) with a USB port, a free
[Tailscale](https://tailscale.com) account, and optionally a SIM card with data.

> ⚠️ Flashing replaces the stick's Android firmware. Keep the backup the installer makes (step 2): it holds your
> stick's own modem calibration (IMEI, RF tuning). It is unique to your device — never share it or use another stick's.

### 1. Check your board

Supported by the OpenStick installer: **UZ801** (v3.x), **HMUF02**, **HM-MIFIB** — see
[openstick.org](https://openstick.org/getting-started/firmware-downloads/) for the current list and how to identify
your board. This dashboard is tested on a UZ801 (modem firmware `UZ801_V3.3`).

### 2. Flash OpenStick Debian (official 1-Click installer)

Follow [openstick.org's UZ801 guide](https://openstick.org/boards/uz801/flashing/); in short:

1. Plug the stick in, join its stock Wi-Fi and open `http://192.168.100.1/usbdebug.html` (some builds:
   `usbdebug.htm`) to enable ADB.
2. Download [openstick-installer](https://github.com/Basistiy/openstick-installer) (zip, or
   `git clone https://github.com/Basistiy/openstick-installer.git`) and start it: `./run.sh` on Linux,
   `run.command` on macOS, `run.bat` on Windows. It sets up its own Python environment and tools (`edl`, …).
3. Choose your board (`1` = UZ801), answer **`Y`** to the backup, then **Install Linux (Debian)**.
   The installer dumps the whole eMMC to `backups/…/full_emmc.bin`, extracts the calibration partitions,
   writes them into the Debian image and flashes it. It takes about 15 minutes.
4. **Copy the `backups/` folder somewhere safe.**

Windows: if the stick shows up as an unknown 9008 device, bind WinUSB to it with Zadig. If it gets stuck, unplug it,
hold the reset button and plug it back in (EDL mode) — details in the installer's README.

### 3. First login and basic hardening

After the reboot the stick comes up with the image's defaults (from the installer's README): hotspot **`Openstick`**
(password `openstick`, stick at `192.168.4.1`), USB network `192.168.5.1`, SSH user **`user`**, password **`1`**.
These are public, so change them first:

```sh
ssh user@192.168.5.1          # or ssh user@192.168.4.1 over the Openstick hotspot
passwd                        # new password for `user`
sudo rm /etc/ssh/ssh_host_* && sudo ssh-keygen -A && sudo systemctl restart ssh   # unique host keys (the image ships shared ones)
```

Your SSH client will then warn that the host key changed — expected; remove the old entry
(`ssh-keygen -R 192.168.5.1`) and reconnect.

### 4. Get the stick online

Either insert a SIM (then **restart the stick** — the modem only reads the SIM at power-up), or join a Wi-Fi network:

```sh
sudo nmcli dev wifi connect "<your Wi-Fi>" --ask
```

Joining Wi-Fi turns the `Openstick` hotspot off (one radio), so reconnect over USB, or to the stick's new IP on
your Wi-Fi.

### 5. Install the dashboard

On the stick:

```sh
curl -fsSL https://github.com/ptrinh/OpenStick-Dashboard/archive/refs/heads/main.tar.gz | tar -xz
cd OpenStick-Dashboard-main && sudo sh install.sh
```

`install.sh` installs Python, `qrencode`, `python3-cryptography` and Tailscale (from pkgs.tailscale.com), copies
the dashboard and its services, and prints the addresses to open. Re-run it to update; settings in `/etc/uz` are kept.

*From your computer instead:* clone this repo and run `UZ_VIA=usb UZ_PASSWORD_FILE=<file holding the stick password> tools/deploy.sh setup`
(zsh; needs the packages above already on the stick).

### 6. Open the dashboard and pair Tailscale

1. Open `http://192.168.5.1` (USB) or `http://<the stick's IP>` (same Wi-Fi) — plain HTTP, no port.
   While the stick is not paired with Tailscale this works from the local network; anyone on that network can use it,
   so do the next step right away.
2. On the **Status** tab open the **Tailscale** card → **Sign in to Tailscale**: scan the QR code or open the link and approve the stick in
   your tailnet.
3. From now on use **`https://<stick-name>.<your-tailnet>.ts.net`** (HTTPS from `tailscale serve`). Local-IP access
   closes automatically once the stick is paired.

### 7. Finish in Settings

* **Security → Passkeys**: add a passkey; afterwards the dashboard requires it.
* **Messaging → Notifications**: save a bot token from @BotFather, press **Detect chat**, then send `/start` to your bot within 20 seconds.
* **Network → Cellular** (APN, roaming, SIM PIN) and **Data plan** (billing day, monthly cap).
* **Device → System**: time zone, pin apt to `trixie`, install updates.

### Advanced: bake the dashboard into the image before flashing

On an arm64 Linux machine (a VM is fine), loop-mount the rootfs partition of the installer's `full_emmc.bin` and run

```sh
sudo tools/customize-openstick-image.sh /mnt/os ./new-user-password [carried-state.tgz]
```

It installs Python, Tailscale, `qrencode` and the dashboard, sets the password for `user`, locks root's password,
deletes the image's shared SSH host keys (regenerated on first boot) and clears `machine-id`. The `Openstick` hotspot
stays on for cable-free setup at `http://192.168.4.1`; once the stick joins a Wi-Fi network `uz-web` stops it from
auto-starting. Inject your stick's own calibration partitions (`modemst1/2`, `fsg`, `fsc`, `persist`, `sec`, `modem`)
into the image before flashing — never another device's.

### postmarketOS

The services also run on postmarketOS with the `qmicli` backend: get the stick on the network, then from your
computer run `UZ_VIA=usb UZ_PASSWORD_FILE=<file> tools/deploy.sh setup` (USB address `172.16.42.1`).

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
