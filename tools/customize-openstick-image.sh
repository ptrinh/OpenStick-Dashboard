#!/bin/bash
# Customize a mounted OpenStick (Debian) rootfs before flashing it — run as root on an
# arm64 Linux host (native chroot), e.g. a VM.
#   usage: customize-openstick-image.sh <mounted-rootfs> <password-file> [state.tgz]
#   <password-file>  file holding the new password for `user` (the image ships with "1")
#   [state.tgz]      optional tarball (paths relative to /) carried over from a previous install,
#                    e.g. var/lib/tailscale + etc/NetworkManager/system-connections
set -euo pipefail
R=${1:?mounted rootfs}; PWFILE=${2:?password file}; STATE=${3:-}
REPO=$(cd "$(dirname "$0")/.." && pwd)
for d in proc sys dev dev/pts; do mountpoint -q $R/$d || mount --bind /$d $R/$d; done
cp -L /etc/resolv.conf $R/etc/resolv.conf.uz; mv $R/etc/resolv.conf $R/etc/resolv.conf.orig 2>/dev/null || true; cp $R/etc/resolv.conf.uz $R/etc/resolv.conf
printf '#!/bin/sh\nexit 101\n' > $R/usr/sbin/policy-rc.d; chmod 755 $R/usr/sbin/policy-rc.d
echo "== apt"
chroot $R /bin/bash -c 'export DEBIAN_FRONTEND=noninteractive
apt-get update -qq
apt-get install -y -qq --no-install-recommends python3 python3-cryptography jq curl ca-certificates busybox dosfstools gnupg qrencode >/dev/null
curl -fsSL https://pkgs.tailscale.com/stable/debian/trixie.noarmor.gpg -o /usr/share/keyrings/tailscale-archive-keyring.gpg
curl -fsSL https://pkgs.tailscale.com/stable/debian/trixie.tailscale-keyring.list -o /etc/apt/sources.list.d/tailscale.list
apt-get update -qq && apt-get install -y -qq tailscale >/dev/null
apt-get clean; tailscale version | head -1; python3 --version'
echo "== uz files"
cp -r $REPO/rootfs/* $R/
rm -f $R/etc/systemd/system/uz-lte.service
sed -i 's/interface-name:wwan0;//' $R/etc/NetworkManager/conf.d/uz.conf
chmod 755 $R/usr/local/bin/uz-*; mkdir -p $R/var/lib/uz/images; chmod 700 $R/etc/uz
echo "== carried state (tailscale identity, Wi-Fi, hotspot, uz conf)"
[ -n "$STATE" ] && tar -C $R -xzf "$STATE"
chmod 600 $R/etc/NetworkManager/system-connections/*.nmconnection 2>/dev/null || true
[ -s $R/etc/uz/hotspot.psk ] || tr -dc 'A-Za-z0-9' </dev/urandom | head -c 16 > $R/etc/uz/hotspot.psk
[ -s $R/etc/uz/sms.pin ] || tr -dc '0-9' </dev/urandom | head -c 6 > $R/etc/uz/sms.pin
chmod 600 $R/etc/uz/hotspot.psk $R/etc/uz/sms.pin; chown -R root:root $R/etc/uz $R/var/lib/tailscale 2>/dev/null || true
sed -i 's/^UZ_MODE=.*/UZ_MODE=home/' $R/etc/uz/uz.conf
grep -q UZ_BACKEND $R/etc/uz/uz.conf || printf 'UZ_BACKEND=auto\nUZ_USBNET=auto\n' >> $R/etc/uz/uz.conf
# The stock 'Openstick' hotspot (192.168.4.1, the image's default password) stays on so a new stick can be reached
# at http://192.168.4.1 without a cable. uz-web turns its autoconnect off once wlan0 has joined a Wi-Fi network.
echo "== services"
chroot $R systemctl enable tailscaled.service uz-probe.timer uz-sms.service uz-mode.service uz-web.service uz-led.service uz-gps.service uz-zram.service >/dev/null 2>&1
chroot $R systemctl disable dnsmasq.service getty@tty1.service hostapd.service >/dev/null 2>&1 || true
echo "== security: passwords, host keys, machine-id, hostname"
printf 'user:%s\n' "$(cat "$PWFILE")" | chroot $R chpasswd
chroot $R passwd -l root >/dev/null
rm -f $R/etc/ssh/ssh_host_*
cat > $R/etc/systemd/system/uz-ssh-hostkeys.service <<'U'
[Unit]
Description=Generate unique SSH host keys on first boot
Before=ssh.service sshd.service
ConditionPathExistsGlob=!/etc/ssh/ssh_host_*_key
[Service]
Type=oneshot
ExecStart=/usr/bin/ssh-keygen -A
[Install]
WantedBy=multi-user.target
U
chroot $R systemctl enable uz-ssh-hostkeys.service >/dev/null 2>&1
: > $R/etc/machine-id; rm -f $R/var/lib/dbus/machine-id
echo uz801 > $R/etc/hostname; sed -i 's/openstick-debian/uz801/g' $R/etc/hosts
echo "== cleanup"
rm -f $R/usr/sbin/policy-rc.d $R/etc/resolv.conf.uz; mv $R/etc/resolv.conf.orig $R/etc/resolv.conf 2>/dev/null || true
for d in dev/pts dev sys proc; do umount $R/$d; done
df -h $R | tail -1
