#!/bin/sh
# Runs ON the stick as root (via doas). Idempotent.
set -e
cd /tmp/uz
echo "== packages"
if command -v apk >/dev/null; then
NEW=""
for f in $(ls ./pkgs/*.apk 2>/dev/null); do
  b=$(basename $f .apk); n=$(echo $b | sed -E 's/-[0-9][^-]*-r[0-9]+$//')
  apk info -e "$n" >/dev/null 2>&1 || NEW="$NEW $f"
done
echo "installing:$(for f in $NEW; do printf ' %s' $(basename $f .apk); done)"
[ -n "$NEW" ] && apk add -q --no-interactive --no-network $NEW
fi
command -v apt-get >/dev/null && { ! command -v qrencode >/dev/null || ! python3 -c 'import cryptography' 2>/dev/null; } && DEBIAN_FRONTEND=noninteractive apt-get install -y -qq --no-install-recommends qrencode python3-cryptography >/dev/null 2>&1 || true
echo "== files"
[ -f /etc/uz/telegram.env ] && cp /etc/uz/telegram.env /tmp/uz/telegram.env.keep
[ -f /etc/uz/uz.conf ] && cp /etc/uz/uz.conf /tmp/uz/uz.conf.keep
cp -r rootfs/* /
[ -f /tmp/uz/telegram.env.keep ] && mv /tmp/uz/telegram.env.keep /etc/uz/telegram.env
[ -f /tmp/uz/uz.conf.keep ] && mv /tmp/uz/uz.conf.keep /etc/uz/uz.conf
if command -v mmcli >/dev/null && systemctl is-enabled -q ModemManager 2>/dev/null; then
  sed -i 's/interface-name:wwan0;//' /etc/NetworkManager/conf.d/uz.conf; fi
chmod 755 /usr/local/bin/uz-*; chmod 700 /etc/uz; mkdir -p /var/lib/uz
[ -s /etc/uz/hotspot.psk ] || { tr -dc 'A-Za-z0-9' </dev/urandom | head -c 16 > /etc/uz/hotspot.psk; }
[ -s /etc/uz/sms.pin ] || { tr -dc '0-9' </dev/urandom | head -c 6 > /etc/uz/sms.pin; }
chmod 600 /etc/uz/sms.pin
chmod 600 /etc/uz/hotspot.psk /etc/uz/telegram.env 2>/dev/null || true
if [ ! -f /usr/lib/systemd/system/tailscaled.service ] && [ ! -f /etc/systemd/system/tailscaled.service ]; then
  cp /etc/uz/tailscaled.service.fallback /etc/systemd/system/tailscaled.service; fi
sysctl -q -p /etc/sysctl.d/90-uz.conf || true
systemctl daemon-reload
nmcli general reload conf 2>/dev/null || systemctl reload NetworkManager 2>/dev/null || true
command -v apk >/dev/null && { systemctl disable --now ModemManager 2>/dev/null || true; }
echo "== services"
if command -v mmcli >/dev/null && systemctl is-enabled -q ModemManager; then
  systemctl disable --now uz-lte.service 2>/dev/null; rm -f /etc/systemd/system/uz-lte.service
  systemctl enable --now tailscaled.service uz-probe.timer
else
  systemctl enable --now uz-lte.service tailscaled.service uz-probe.timer
fi
systemctl enable uz-sms.service uz-mode.service
command -v mmcli >/dev/null && systemctl enable --now uz-gps.service
systemctl enable --now uz-web.service uz-led.service uz-zram.service
grep -q '^UZ_USB_SHARE=' /etc/uz/uz.conf || echo 'UZ_USB_SHARE=0' >> /etc/uz/uz.conf
systemctl enable uz-usbnet.service; /usr/local/bin/uz-usbnet || true
# pick up new code in long-running services
for u in uz-web uz-sms uz-gps uz-led; do systemctl is-active -q $u && systemctl restart $u; done; true
tailscale status >/dev/null 2>&1 && tailscale serve --bg 8080 >/dev/null 2>&1 || echo "NOTE: run tailscale up, then: tailscale serve --bg 8080"
systemctl restart uz-sms.service || true
echo "== done"
