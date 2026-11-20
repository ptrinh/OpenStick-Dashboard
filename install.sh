#!/bin/sh
# Install or update OpenStick Dashboard ON the stick (OpenStick Debian; also postmarketOS via tools/deploy.sh).
#   curl -fsSL https://github.com/ptrinh/OpenStick-Dashboard/archive/refs/heads/main.tar.gz | tar -xz
#   cd OpenStick-Dashboard-main && sudo sh install.sh
# Idempotent: re-run it to update. Keeps /etc/uz (settings, secrets) across updates.
set -e
[ "$(id -u)" = 0 ] || { echo "run as root: sudo sh install.sh"; exit 1; }
HERE=$(cd "$(dirname "$0")" && pwd)
[ -d "$HERE/rootfs" ] && [ -f "$HERE/tools/stick-setup.sh" ] || { echo "run from the repository folder"; exit 1; }

if command -v apt-get >/dev/null; then
  echo "== Debian packages"
  export DEBIAN_FRONTEND=noninteractive
  APT="apt-get -o DPkg::Lock::Timeout=900"   # wait if an update is already running
  $APT update -qq
  $APT install -y -qq --no-install-recommends python3 python3-cryptography jq curl ca-certificates busybox dosfstools gnupg qrencode >/dev/null
  if ! command -v tailscale >/dev/null; then
    echo "== Tailscale (pkgs.tailscale.com)"
    . /etc/os-release
    curl -fsSL "https://pkgs.tailscale.com/stable/debian/${VERSION_CODENAME}.noarmor.gpg" -o /usr/share/keyrings/tailscale-archive-keyring.gpg
    curl -fsSL "https://pkgs.tailscale.com/stable/debian/${VERSION_CODENAME}.tailscale-keyring.list" -o /etc/apt/sources.list.d/tailscale.list
    $APT update -qq && $APT install -y -qq tailscale >/dev/null
  fi
  # NetworkManager runs its own dnsmasq for the hotspot / USB sharing; the system one only gets in the way.
  systemctl disable --now dnsmasq.service >/dev/null 2>&1 || true
fi

echo "== dashboard"
rm -rf /tmp/uz && mkdir -p /tmp/uz
cp -r "$HERE/rootfs" "$HERE/tools/stick-setup.sh" /tmp/uz/
sh /tmp/uz/stick-setup.sh
IP=$(ip -4 -o addr show 2>/dev/null | awk '$2 ~ /^(wlan0|usb0)$/ {split($4,a,"/"); print a[1]}' | head -3 | tr '\n' ' ')
echo
echo "Open the dashboard: $(for i in $IP; do printf 'http://%s  ' "$i"; done)"
echo "Then use Tailscale → Sign in on the dashboard to pair the stick with your tailnet."
