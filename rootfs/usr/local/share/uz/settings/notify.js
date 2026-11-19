/* Notifications: Telegram bot + signed webhook, per-channel event routing (server: lib/uz/settings/notify.py). */
(() => {
const T = {
 en: {title: 'Notifications', notSet: 'Not set', desc: 'Choose where the stick sends SMS, uptime and LTE events.',
  tg: 'Telegram', wh: 'Webhook', bot: 'Bot', chat: 'Chat', token: 'Token', set: 'set', notset: 'not set',
  tokenPh: 'Bot token from @BotFather (123456:ABC…)', tokenKeep: 'New bot token (leave empty to keep)', save: 'Save',
  detect: 'Detect chat', detectHelp: 'Press “Detect chat”, then within 20 seconds send /start to {bot} from your Telegram account. The latest private chat becomes the destination.',
  yourBot: 'your bot', waiting: 'Listening for /start…', test: 'Send test', sending: 'Sending…', clear: 'Remove', sure: 'Tap again to remove',
  events: 'Events', url: 'URL', urlPh: 'https://example.com/hook', urlKeep: 'New URL (leave empty to keep)', secret: 'Secret',
  secretPh: 'Signing secret (optional, 8+ characters)', secretKeep: 'New secret (leave empty to keep)', noSecret: 'Remove secret',
  payload: 'Payload', sigHelp: 'Each event is POSTed as JSON (10 s timeout, 2 retries, redirects not followed). With a secret, the header X-UZ-Signature carries sha256=<hex HMAC-SHA256 of the raw request body, keyed with the secret>. Verify it before trusting the request.',
  needToken: 'Save a bot token first.', needChat: 'No chat yet — detect it.',
  ev: {sms_received: 'SMS received', sms_command: 'SMS command', sms_rejected: 'Rejected command', uptime_change: 'Uptime up/down', lte_up: 'LTE up', test: 'Test'}},
 vi: {title: 'Thông báo', notSet: 'Chưa đặt', desc: 'Chọn nơi USB gửi sự kiện SMS, giám sát và LTE.',
  tg: 'Telegram', wh: 'Webhook', bot: 'Bot', chat: 'Chat', token: 'Token', set: 'đã đặt', notset: 'chưa đặt',
  tokenPh: 'Token bot từ @BotFather (123456:ABC…)', tokenKeep: 'Token bot mới (để trống để giữ nguyên)', save: 'Lưu',
  detect: 'Dò chat', detectHelp: 'Bấm “Dò chat”, rồi trong vòng 20 giây gửi /start tới {bot} từ tài khoản Telegram của bạn. Chat riêng gần nhất sẽ là nơi nhận.',
  yourBot: 'bot của bạn', waiting: 'Đang chờ /start…', test: 'Gửi thử', sending: 'Đang gửi…', clear: 'Xoá', sure: 'Bấm lần nữa để xoá',
  events: 'Sự kiện', url: 'URL', urlPh: 'https://example.com/hook', urlKeep: 'URL mới (để trống để giữ nguyên)', secret: 'Khoá bí mật',
  secretPh: 'Khoá ký (tuỳ chọn, từ 8 ký tự)', secretKeep: 'Khoá mới (để trống để giữ nguyên)', noSecret: 'Bỏ khoá',
  payload: 'Dữ liệu gửi', sigHelp: 'Mỗi sự kiện được POST dạng JSON (timeout 10 giây, thử lại 2 lần, không theo chuyển hướng). Khi có khoá, header X-UZ-Signature chứa sha256=<hex HMAC-SHA256 của nguyên thân request, khoá là secret>. Hãy kiểm tra chữ ký trước khi tin request.',
  needToken: 'Hãy lưu token bot trước.', needChat: 'Chưa có chat — hãy dò chat.',
  ev: {sms_received: 'Nhận SMS', sms_command: 'Lệnh SMS', sms_rejected: 'Lệnh bị từ chối', uptime_change: 'Giám sát lên/xuống', lte_up: 'LTE kết nối', test: 'Thử'}},
 zh: {title: '通知', notSet: '未设置', desc: '选择设备发送短信、在线监测和 LTE 事件的位置。',
  tg: 'Telegram', wh: 'Webhook', bot: '机器人', chat: '聊天', token: '令牌', set: '已设置', notset: '未设置',
  tokenPh: '来自 @BotFather 的机器人令牌（123456:ABC…）', tokenKeep: '新令牌（留空则保留）', save: '保存',
  detect: '检测聊天', detectHelp: '点击“检测聊天”，然后在 20 秒内用你的 Telegram 账号向 {bot} 发送 /start。最近的私聊将作为接收方。',
  yourBot: '你的机器人', waiting: '正在等待 /start…', test: '发送测试', sending: '发送中…', clear: '移除', sure: '再点一次以移除',
  events: '事件', url: 'URL', urlPh: 'https://example.com/hook', urlKeep: '新 URL（留空则保留）', secret: '密钥',
  secretPh: '签名密钥（可选，至少 8 个字符）', secretKeep: '新密钥（留空则保留）', noSecret: '移除密钥',
  payload: '请求内容', sigHelp: '每个事件以 JSON 方式 POST（超时 10 秒，重试 2 次，不跟随重定向）。设置密钥后，请求头 X-UZ-Signature 为 sha256=<用密钥对原始请求体计算的 HMAC-SHA256 十六进制值>。请先校验签名再信任请求。',
  needToken: '请先保存机器人令牌。', needChat: '尚无聊天 — 请先检测。',
  ev: {sms_received: '收到短信', sms_command: '短信指令', sms_rejected: '拒绝的指令', uptime_change: '在线状态变化', lte_up: 'LTE 已连接', test: '测试'}},
};
const t = k => (T[UZ.lang] || T.en)[k] ?? T.en[k];
const E = UZ.esc;
const EXAMPLE = `POST <url>
Content-Type: application/json
X-UZ-Signature: sha256=5d41402abc4b2a76b9719d911017c592…

{"event":"sms_received","text":"✉️ SMS from +84901234567 …",
 "data":{"from":"+84901234567","ts":"…","text":"…"},
 "host":"uz801","ts":1763600000}

# verify (Python)
hmac.compare_digest(sig, "sha256=" + hmac.new(secret, body, hashlib.sha256).hexdigest())`;

const chips = (ch, c, all) => `<div class="chips" data-ch="${ch}">${all.map(e =>
  `<button type="button" class="chip ${c.events.includes(e) ? 'on' : ''}" data-focus data-ev="${E(e)}">${E(t('ev')[e] || e)}</button>`).join('')}</div>`;
const sec = s => `<h3 style="margin:26px 0 12px;font-size:15px;color:var(--dim);font-weight:700;letter-spacing:.04em;text-transform:uppercase">${s}</h3>`;

async function open() {
  const r = await UZ.post('notify-get', {});
  if (r.error) { UZ.toast(r.error); return; }
  const g = r.telegram, w = r.webhook, all = r.events || [];
  const bot = g.bot ? '@' + g.bot : t('yourBot');
  UZ.openSheet('blue', 'msg', t('title'), t('desc'), `
   ${sec(t('tg'))}
   <div class="kv"><span>${t('bot')}</span><span>${g.bot ? E('@' + g.bot) : '—'}</span>
    <span>${t('token')}</span><span>${g.token === 'set' ? t('set') + (g.token_hint ? ' (' + E(g.token_hint) + ')' : '') : t('notset')}</span>
    <span>${t('chat')}</span><span>${g.chat ? E(g.chat) : '—'}</span></div>
   <form id="ntf" autocomplete="off" style="margin-top:16px"><input class="field" id="ntok" type="password" autocomplete="off" spellcheck="false" maxlength="70"
     placeholder="${E(g.token === 'set' ? t('tokenKeep') : t('tokenPh'))}">
    <div class="actions" style="margin-top:0"><button class="btn primary sm" data-focus type="submit">${t('save')}</button>
     <button class="btn sm" data-focus type="button" id="ndet" ${g.token === 'set' ? '' : 'disabled'}>${t('detect')}</button>
     <button class="btn sm" data-focus type="button" data-test="telegram" ${g.configured ? '' : 'disabled'}>${t('test')}</button>
     ${g.token === 'set' ? `<button class="btn red sm" data-focus type="button" data-clear="notify-telegram-clear">${t('clear')}</button>` : ''}</div></form>
   <p class="desc" style="margin:12px 0 0;color:var(--dim)">${g.token !== 'set' ? t('needToken') : (g.chat ? '' : t('needChat') + ' ') + E(t('detectHelp').replace('{bot}', bot))}</p>
   <div style="margin-top:14px"><div style="color:var(--faint);font-size:13px;margin-bottom:8px">${t('events')}</div>${chips('telegram', g, all)}</div>

   ${sec(t('wh'))}
   ${w.url_set ? `<div class="kv"><span>${t('url')}</span><span style="overflow-wrap:anywhere">${E(w.url)}</span><span>${t('secret')}</span><span>${w.secret === 'set' ? t('set') : t('notset')}</span></div>` : ''}
   <form id="nwf" autocomplete="off" style="margin-top:16px"><input class="field" id="nurl" type="url" inputmode="url" autocomplete="off" spellcheck="false" maxlength="500"
     placeholder="${E(w.url_set ? t('urlKeep') : t('urlPh'))}">
    <input class="field" id="nsec" type="password" autocomplete="new-password" spellcheck="false" maxlength="256" placeholder="${E(w.secret === 'set' ? t('secretKeep') : t('secretPh'))}">
    <div class="actions" style="margin-top:0"><button class="btn primary sm" data-focus type="submit">${t('save')}</button>
     <button class="btn sm" data-focus type="button" data-test="webhook" ${w.url_set ? '' : 'disabled'}>${t('test')}</button>
     ${w.secret === 'set' ? `<button class="btn sm" data-focus type="button" id="nnosec">${t('noSecret')}</button>` : ''}
     ${w.url_set ? `<button class="btn red sm" data-focus type="button" data-clear="notify-webhook-clear">${t('clear')}</button>` : ''}</div></form>
   <div style="margin-top:14px"><div style="color:var(--faint);font-size:13px;margin-bottom:8px">${t('events')}</div>${chips('webhook', w, all)}</div>
   <p style="margin:16px 0 0;color:var(--dim);font-size:14px">${E(t('sigHelp'))}</p>
   <pre>${E(EXAMPLE)}</pre>
   <div class="actions">${UZ.closeBtn()}</div>`);

  const done = async (res, reopen = true) => { UZ.toast(res.error || res.out); if (!res.error && reopen) { await open(); UZ.reload(); } return res; };
  UZ.$('#ntf').onsubmit = async ev => {
    ev.preventDefault(); const v = UZ.$('#ntok').value.trim(); if (!v) return;
    done(await UZ.post('notify-telegram-set', {token: v}));
  };
  const det = UZ.$('#ndet');
  if (det) det.onclick = async () => {
    det.disabled = true; det.textContent = t('waiting');
    const res = await UZ.post('notify-telegram-detect', {});
    if (res.error) { det.disabled = false; det.textContent = t('detect'); }
    done(res);
  };
  UZ.$('#nwf').onsubmit = async ev => {
    ev.preventDefault(); const url = UZ.$('#nurl').value.trim(), secret = UZ.$('#nsec').value;
    if (!url && !secret) return;
    done(await UZ.post('notify-webhook-set', {url, secret}));
  };
  const ns = UZ.$('#nnosec');
  if (ns) ns.onclick = async () => done(await UZ.post('notify-webhook-set', {remove_secret: true}));
  UZ.$$('[data-test]').forEach(b => b.onclick = async () => {
    const lbl = b.textContent; b.disabled = true; b.textContent = t('sending');
    const res = await UZ.post('notify-test', {channel: b.dataset.test});
    b.disabled = false; b.textContent = lbl; UZ.toast(res.error || res.out);
  });
  UZ.$$('[data-clear]').forEach(b => b.onclick = async () => {      // confirm inside the sheet: second tap removes
    if (!b.dataset.armed) { b.dataset.armed = '1'; b.textContent = t('sure'); return; }
    done(await UZ.post(b.dataset.clear, {}));
  });
  UZ.$$('.chips[data-ch] .chip').forEach(c => c.onclick = async () => {
    c.classList.toggle('on');
    const box = c.closest('.chips'), evs = [...box.querySelectorAll('.chip.on')].map(x => x.dataset.ev);
    const res = await UZ.post('notify-events-set', {[box.dataset.ch]: evs});
    if (res.error) { c.classList.toggle('on'); UZ.toast(res.error); }
  });
}

UZ.register({
  id: 'notify', order: 10, color: 'blue',
  iconSvg: '<path d="M6 8a6 6 0 0 1 12 0c0 7 3 9 3 9H3s3-2 3-9"/><path d="M10.3 21a1.94 1.94 0 0 0 3.4 0"/>',
  title: {en: T.en.title, vi: T.vi.title, zh: T.zh.title},
  sub: S => { const n = (S.settings || {}).notify || {};
    const p = [n.telegram && 'Telegram', n.webhook && 'Webhook'].filter(Boolean);
    return p.length ? p.join(' · ') : t('notSet'); },
  open() { open().catch(e => UZ.toast(String(e))); },
});
})();
