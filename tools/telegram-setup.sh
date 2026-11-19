#!/bin/zsh
# Run via: touchenv run --intent "UZ801 telegram" UZ801_TG_TOKEN -- ./telegram-setup.sh
# Finds the chat id from the latest message sent to the bot, installs /etc/uz/telegram.env on the stick.
set -eu
D=${0:A:h}
[[ -n ${UZ801_TG_TOKEN:-} ]] || { echo "UZ801_TG_TOKEN missing"; exit 1; }
CHAT=$(python3 -I -c '
import json,os,urllib.request
r=json.load(urllib.request.urlopen("https://api.telegram.org/bot%s/getUpdates" % os.environ["UZ801_TG_TOKEN"], timeout=20))
ids=[u["message"]["chat"]["id"] for u in r.get("result",[]) if "message" in u]
print(ids[-1] if ids else "")')
[[ -n $CHAT ]] || { echo "no message found — send /start to the bot first"; exit 1; }
T=$(mktemp); chmod 600 $T; trap 'rm -f $T' EXIT
printf 'TG_TOKEN=%s\nTG_CHAT=%s\n' "$UZ801_TG_TOKEN" "$CHAT" > $T
$D/deploy.sh push $T /tmp/uz-tg.env >/dev/null
$D/deploy.sh root "install -m600 /tmp/uz-tg.env /etc/uz/telegram.env && rm -f /tmp/uz-tg.env && systemctl restart uz-sms && uz-notify ✅ UZ801 connected to Telegram" >/dev/null
echo "telegram configured (chat id found)"
