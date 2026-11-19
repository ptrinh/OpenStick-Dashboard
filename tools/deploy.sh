#!/bin/zsh
# deploy.sh [setup|ssh <cmd>|root <cmd>|push <local> <remote>] — talk to the stick over USB NCM.
mkdir -p $HOME/.config/uz801; D=${0:A:h}; H=${UZ_HOST:-}
if [[ -z $H ]]; then for c in 192.168.5.1 172.16.42.1; do ping -c1 -t1 $c >/dev/null 2>&1 && { H=$c; break; }; done; H=${H:-192.168.5.1}; fi; PW=${UZ_PASSWORD_FILE:-$HOME/.config/uz801/password}
O=(-o StrictHostKeyChecking=accept-new -o UserKnownHostsFile=${UZ_KNOWN_HOSTS:-$HOME/.config/uz801/known_hosts} -o PreferredAuthentications=password,keyboard-interactive -o PubkeyAuthentication=no -o ConnectTimeout=10)
pa(){ python3 -I $D/pty-auth.py $PW "$@"; }
SU='$(command -v doas || echo sudo)'
# Prefer Tailscale SSH as root (no password); UZ_VIA=usb forces the USB/password path.
TS=${UZ_TS_HOST:-uz801}
if [[ ${UZ_VIA:-} != usb ]] && tailscale status 2>/dev/null | grep -q " $TS .*linux *[-a-z]" && ! tailscale status | grep " $TS " | grep -q offline; then
  case ${1:-} in
    setup)  tar -C $D/.. -cf - rootfs -C $D stick-setup.sh  | tailscale ssh root@$TS 'rm -rf /tmp/uz && mkdir -p /tmp/uz && tar -xf - -C /tmp/uz && sh /tmp/uz/stick-setup.sh'; exit ;;
    ssh)    shift; tailscale ssh user@$TS "$*"; exit ;;
    root)   shift; tailscale ssh root@$TS "$*"; exit ;;
    push)   tailscale ssh root@$TS "cat > $3" < $2; exit ;;
  esac
fi
case ${1:-} in
  setup)
    pa ssh $O user@$H 'rm -rf /tmp/uz && mkdir -p /tmp/uz' &&
    pa scp -q $O -r $D/../rootfs $D/stick-setup.sh $([[ -d $D/../pkgs ]] && echo $D/../pkgs) user@$H:/tmp/uz/ &&
    pa ssh -tt $O user@$H "$SU sh /tmp/uz/stick-setup.sh" ;;
  ssh)  shift; pa ssh -tt $O user@$H "$*" ;;
  root) shift; pa ssh -tt $O user@$H "$SU sh -c '$*'" ;;
  push) pa scp -q $O $2 user@$H:$3 ;;
  *) echo "usage: $0 setup | ssh <cmd> | root <cmd> | push <local> <remote>" ;;
esac
