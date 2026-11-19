/* Calls: incoming-call policy, call triggers, missed calls, alarm ring, USSD (server: lib/uz/settings/calls.py,
   daemon: bin/uz-calls). The stick has no audio: calls are listed, rejected and placed, never heard. */
(() => {
const T = {
 en: {title: 'Calls', desc: 'Incoming-call policy, missed calls, call triggers and USSD. The stick has no audio: it can reject, hang up and ring, but never talk.',
  loading: 'Loading…', noDaemon: 'The calls service (uz-calls) is not running.', noVoice: 'Voice calls are not available — no SIM, or the modem is not enabled.',
  noSim: 'No SIM', simLocked: 'SIM locked', ready: 'Ready', unavailable: 'Unavailable', off: 'Service off',
  missedN: n => n === 1 ? '1 missed' : n + ' missed', ringingSub: n => 'Ringing: ' + n, onCall: 'Call in progress',
  now: 'Current calls', noCalls: 'No active calls.', hang: 'Hang up', hangAll: 'Hang up all', unknownNum: 'Unknown number',
  st: {'ringing-in': 'ringing', waiting: 'waiting', active: 'active', held: 'held', dialing: 'dialing', 'ringing-out': 'ringing out', terminated: 'ended'},
  recent: 'Recent calls', noLog: 'No calls yet.', clear: 'Clear log', sure: 'Tap again to clear',
  oc: {missed: 'Missed', answered: 'Answered', rejected: 'Rejected', blocked: 'Blocked', trigger: 'Trigger', unanswered: 'Rang, no answer', failed: 'Call failed'},
  outLbl: 'Outgoing', alarmSrc: 'alarm',
  policy: 'Incoming calls', mode: {notify: 'Notify only', reject_all: 'Reject all', allow_list: 'Allow list only'},
  modeHelp: {notify: 'Calls ring until the caller gives up; you get a notification and a missed call.',
   reject_all: 'Every call is rejected immediately (except call triggers).',
   allow_list: 'Calls from numbers on the allow list ring and notify; all others are rejected.'},
  notifyChip: 'Send notifications', allow: 'Allow list', block: 'Block list (always rejected)',
  listPh: 'One number per line, e.g. +84912345678', matchHelp: 'Numbers match on their last 9 digits, so +84 912 345 678 and 0912 345 678 are the same.',
  triggers: 'Call triggers', trgHelp: 'A call from a trigger number is rejected straight away — the caller pays nothing — and the stick runs the action. Optionally it replies by SMS with the result. Same number + action at most once a minute, at most 20 per hour.',
  num: 'Number', act: 'Action', reply: 'Reply SMS', addTrg: 'Add trigger', remove: 'Remove',
  starHelp: 'Number “*” = any number in the SMS allow-list (needs the switch below).', fromSms: n => `Trusted numbers from the SMS allow-list (${n})`,
  acts: {status: 'Status (IP, uptime)', lte: 'Restart LTE', wifi_on: 'Wi-Fi on', wifi_off: 'Wi-Fi off', ts: 'Restart Tailscale', reboot: 'Reboot'},
  alarm: 'Alarm call', alarmHelp: 'Ring my phone when an uptime check goes DOWN (at most once per 30 minutes). Nobody talks: the call simply rings and hangs up.',
  alarmOn: 'Ring on DOWN', ringS: 'Ring for (seconds)', test: 'Test ring', save: 'Save', saved: 'Saved',
  bad: 'Check the highlighted fields: optional +, then 3–15 digits.', badS: 'Ring time: 5–60 seconds.',
  ussd: 'USSD', ussdHelp: 'Balance and operator menus, e.g. *101#. The reply comes from the network (up to 25 s).', ussdPh: '*101#',
  send: 'Send', respond: 'Respond', cancel: 'Cancel', respPh: 'Your answer, e.g. 1', expects: 'The network is waiting for your answer.',
  badUssd: 'USSD code: 2–30 of * # 0-9.', waitNet: 'Waiting for the network…'},
 vi: {title: 'Cuộc gọi', desc: 'Chính sách cuộc gọi đến, cuộc gọi nhỡ, gọi để chạy lệnh và USSD. USB không có âm thanh: chỉ từ chối, gác máy và đổ chuông được, không nghe nói được.',
  loading: 'Đang tải…', noDaemon: 'Dịch vụ cuộc gọi (uz-calls) không chạy.', noVoice: 'Không gọi thoại được — chưa có SIM hoặc modem chưa bật.',
  noSim: 'Chưa có SIM', simLocked: 'SIM bị khoá', ready: 'Sẵn sàng', unavailable: 'Không khả dụng', off: 'Dịch vụ tắt',
  missedN: n => n + ' cuộc nhỡ', ringingSub: n => 'Đang đổ chuông: ' + n, onCall: 'Đang có cuộc gọi',
  now: 'Cuộc gọi hiện tại', noCalls: 'Không có cuộc gọi nào.', hang: 'Gác máy', hangAll: 'Gác tất cả', unknownNum: 'Số ẩn',
  st: {'ringing-in': 'đang đổ chuông', waiting: 'đang chờ', active: 'đang gọi', held: 'đang giữ', dialing: 'đang quay số', 'ringing-out': 'đang đổ chuông đi', terminated: 'đã kết thúc'},
  recent: 'Cuộc gọi gần đây', noLog: 'Chưa có cuộc gọi.', clear: 'Xoá nhật ký', sure: 'Chạm lần nữa để xoá',
  oc: {missed: 'Nhỡ', answered: 'Đã nghe', rejected: 'Từ chối', blocked: 'Đã chặn', trigger: 'Chạy lệnh', unanswered: 'Đổ chuông, không nghe', failed: 'Gọi lỗi'},
  outLbl: 'Gọi đi', alarmSrc: 'báo động',
  policy: 'Cuộc gọi đến', mode: {notify: 'Chỉ thông báo', reject_all: 'Từ chối hết', allow_list: 'Chỉ số được phép'},
  modeHelp: {notify: 'Cuộc gọi đổ chuông tới khi người gọi bỏ cuộc; bạn nhận thông báo và một cuộc gọi nhỡ.',
   reject_all: 'Mọi cuộc gọi bị từ chối ngay (trừ số chạy lệnh).',
   allow_list: 'Số trong danh sách cho phép thì đổ chuông và thông báo; số khác bị từ chối.'},
  notifyChip: 'Gửi thông báo', allow: 'Danh sách cho phép', block: 'Danh sách chặn (luôn từ chối)',
  listPh: 'Mỗi dòng một số, vd +84912345678', matchHelp: 'So khớp theo 9 chữ số cuối, nên +84 912 345 678 và 0912 345 678 là một.',
  triggers: 'Gọi để chạy lệnh', trgHelp: 'Cuộc gọi từ số chạy lệnh bị từ chối ngay — người gọi không mất tiền — và USB chạy lệnh. Có thể trả kết quả bằng SMS. Mỗi số + lệnh tối đa 1 lần/phút, tối đa 20 lần/giờ.',
  num: 'Số', act: 'Lệnh', reply: 'Trả lời SMS', addTrg: 'Thêm lệnh', remove: 'Xoá',
  starHelp: 'Số “*” = mọi số trong danh sách SMS (cần bật công tắc bên dưới).', fromSms: n => `Tin các số trong danh sách điều khiển SMS (${n})`,
  acts: {status: 'Trạng thái (IP, uptime)', lte: 'Khởi động lại LTE', wifi_on: 'Bật Wi-Fi', wifi_off: 'Tắt Wi-Fi', ts: 'Khởi động lại Tailscale', reboot: 'Khởi động lại'},
  alarm: 'Gọi báo động', alarmHelp: 'Gọi vào điện thoại của tôi khi một mục giám sát bị DOWN (tối đa 1 lần mỗi 30 phút). Không ai nói: chỉ đổ chuông rồi gác máy.',
  alarmOn: 'Gọi khi DOWN', ringS: 'Đổ chuông (giây)', test: 'Gọi thử', save: 'Lưu', saved: 'Đã lưu',
  bad: 'Kiểm tra các ô được đánh dấu: có thể có dấu +, rồi 3–15 chữ số.', badS: 'Thời gian đổ chuông: 5–60 giây.',
  ussd: 'USSD', ussdHelp: 'Tra tài khoản và menu nhà mạng, vd *101#. Phản hồi từ nhà mạng (tối đa 25 giây).', ussdPh: '*101#',
  send: 'Gửi', respond: 'Trả lời', cancel: 'Huỷ', respPh: 'Câu trả lời, vd 1', expects: 'Nhà mạng đang chờ bạn trả lời.',
  badUssd: 'Mã USSD: 2–30 ký tự * # 0-9.', waitNet: 'Đang chờ nhà mạng…'},
 zh: {title: '通话', desc: '来电策略、未接来电、来电触发和 USSD。设备没有音频：只能拒接、挂断和拨号振铃，不能通话。',
  loading: '加载中…', noDaemon: '通话服务（uz-calls）未运行。', noVoice: '语音通话不可用——没有 SIM 卡或调制解调器未启用。',
  noSim: '无 SIM 卡', simLocked: 'SIM 已锁定', ready: '就绪', unavailable: '不可用', off: '服务未运行',
  missedN: n => n + ' 个未接', ringingSub: n => '来电：' + n, onCall: '通话中',
  now: '当前通话', noCalls: '没有进行中的通话。', hang: '挂断', hangAll: '全部挂断', unknownNum: '未知号码',
  st: {'ringing-in': '响铃中', waiting: '等待中', active: '通话中', held: '保持', dialing: '拨号中', 'ringing-out': '对方响铃', terminated: '已结束'},
  recent: '最近通话', noLog: '暂无通话。', clear: '清空记录', sure: '再点一次以清空',
  oc: {missed: '未接', answered: '已接听', rejected: '已拒接', blocked: '已拦截', trigger: '触发', unanswered: '响铃无人接', failed: '呼叫失败'},
  outLbl: '呼出', alarmSrc: '告警',
  policy: '来电', mode: {notify: '仅通知', reject_all: '全部拒接', allow_list: '仅允许名单'},
  modeHelp: {notify: '来电一直响铃直到对方挂断；你会收到通知和一条未接来电。',
   reject_all: '所有来电立即拒接（来电触发号码除外）。',
   allow_list: '允许名单中的号码会响铃并通知；其他号码被拒接。'},
  notifyChip: '发送通知', allow: '允许名单', block: '黑名单（始终拒接）',
  listPh: '每行一个号码，例如 +84912345678', matchHelp: '按号码最后 9 位匹配，所以 +84 912 345 678 与 0912 345 678 视为同一号码。',
  triggers: '来电触发', trgHelp: '来自触发号码的来电会被立即拒接（对方不产生费用），设备随即执行对应操作，并可通过短信回复结果。同一号码+操作每分钟最多一次，每小时最多 20 次。',
  num: '号码', act: '操作', reply: '短信回复', addTrg: '添加触发', remove: '删除',
  starHelp: '号码“*”= 短信允许名单中的任意号码（需打开下方开关）。', fromSms: n => `信任短信控制名单中的号码（${n}）`,
  acts: {status: '状态（IP、运行时间）', lte: '重启 LTE', wifi_on: '打开 Wi-Fi', wifi_off: '关闭 Wi-Fi', ts: '重启 Tailscale', reboot: '重启设备'},
  alarm: '告警来电', alarmHelp: '在线监测出现 DOWN 时拨打我的手机（每 30 分钟最多一次）。不会通话：只响铃然后挂断。',
  alarmOn: 'DOWN 时拨打', ringS: '响铃时长（秒）', test: '测试拨打', save: '保存', saved: '已保存',
  bad: '请检查标红的字段：可选 +，后接 3–15 位数字。', badS: '响铃时长：5–60 秒。',
  ussd: 'USSD', ussdHelp: '查询余额和运营商菜单，例如 *101#。回复来自网络（最多 25 秒）。', ussdPh: '*101#',
  send: '发送', respond: '回复', cancel: '取消', respPh: '你的回答，例如 1', expects: '网络正在等待你的回答。',
  badUssd: 'USSD 代码：2–30 个 * # 0-9 字符。', waitNet: '等待网络回复…'},
};
const t = k => (T[UZ.lang] || T.en)[k] ?? T.en[k];
const E = s => UZ.esc(String(s ?? ''));
const NUM = /^\+?[0-9]{3,15}$/, USSD = /^[*#0-9]{2,30}$/;
const clean = s => String(s || '').replace(/[\s\-.()]/g, '');
const PHONE = '<path d="M22 16.9v3a2 2 0 0 1-2.2 2 19.8 19.8 0 0 1-8.6-3.1 19.5 19.5 0 0 1-6-6A19.8 19.8 0 0 1 2.1 4.2 2 2 0 0 1 4.1 2h3a2 2 0 0 1 2 1.7c.1 1 .4 1.9.7 2.8a2 2 0 0 1-.5 2.1L8 9.9a16 16 0 0 0 6 6l1.3-1.3a2 2 0 0 1 2.1-.4c.9.3 1.8.6 2.8.7a2 2 0 0 1 1.7 2z"/>';
const OIC = {missed: ['<path d="M17 7L7 17M7 9v8h8"/>', 'var(--red)'], answered: ['<path d="M5 12l5 5 9-10"/>', 'var(--green)'],
  rejected: ['<circle cx="12" cy="12" r="9"/><path d="M5.6 5.6l12.8 12.8"/>', 'var(--orange)'],
  blocked: ['<circle cx="12" cy="12" r="9"/><path d="M5.6 5.6l12.8 12.8"/>', 'var(--red)'],
  trigger: ['<path d="M13 2L4 14h7l-1 8 9-12h-7z"/>', 'var(--yellow)'], out: ['<path d="M7 17L17 7M9 7h8v8"/>', 'var(--blue)']};
const ic = (p, c) => `<div class="ic" style="color:${c}"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">${p}</svg></div>`;
const when = ts => { try { return new Date(ts * 1000).toLocaleString(UZ.lang === 'zh' ? 'zh-CN' : UZ.lang, {month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit'}); } catch (e) { return ''; } };
const label = s => `<div style="color:var(--faint);font-size:13px;margin:0 0 8px">${E(s)}</div>`;
const sec = (title, body) => `<div class="stat" style="margin-bottom:16px"><div class="l">${E(title)}</div><div style="margin-top:12px">${body}</div></div>`;
const hint = s => `<p style="color:var(--dim);margin:0 0 12px;font-size:14px">${E(s)}</p>`;

let D = null, P = null, poll = null, clearArm = false;

function nowHtml() {
  if (!D) return '';
  let warn = '';
  if (!D.daemon) warn = t('noDaemon');
  else if (!D.voice) warn = t('noVoice') + (D.sim === 'missing' ? ' (' + t('noSim') + ')' : '');
  const cs = D.calls || [];
  const rows = cs.map(c => `<div class="item">${ic(PHONE, c.dir === 'incoming' ? 'var(--green)' : 'var(--blue)')}<div><b>${E(c.number || t('unknownNum'))}</b><small>${E(c.dir === 'incoming' ? '' : t('outLbl') + ' · ')}${E((t('st') || {})[c.state] || c.state)}</small></div>
    <button class="btn sm red" data-focus data-cl-hang="${E(c.path)}">${E(t('hang'))}</button></div>`).join('');
  return (warn ? `<p style="color:var(--orange);margin:0 0 14px">${E(warn)}</p>` : '') +
    sec(t('now'), cs.length ? `<div class="list">${rows}</div>${cs.length > 1 ? `<div class="actions"><button class="btn sm red" data-focus data-cl-hang="">${E(t('hangAll'))}</button></div>` : ''}` : hint(t('noCalls')));
}

function logHtml() {
  const L = (D && D.log) || [];
  const rows = L.slice(0, 30).map(e => {
    const out = e.dir === 'out', [p, c] = OIC[out ? 'out' : e.outcome] || OIC.missed;
    const oc = (t('oc') || {})[e.outcome] || e.outcome || '';
    const extra = [out ? t('outLbl') + (e.source === 'alarm' ? ' (' + t('alarmSrc') + ')' : '') : '', oc,
      e.action ? ((t('acts') || {})[e.action] || e.action) : '', when(e.ts)].filter(Boolean).join(' · ');
    const unseen = !out && e.outcome === 'missed' && e.ts > (D.seen || 0);
    return `<div class="item">${ic(p, c)}<div><b>${E(e.number || t('unknownNum'))}</b>${unseen ? ' <span class="dot bad" style="background:var(--red)"></span>' : ''}<small>${E(extra)}</small>${e.result ? `<p>${E(e.result)}</p>` : ''}</div><span></span></div>`;
  }).join('');
  return sec(t('recent'), L.length ? `<div class="list">${rows}</div><div class="actions"><button class="btn sm" data-focus id="cl-clear">${E(clearArm ? t('sure') : t('clear'))}</button></div>` : hint(t('noLog')));
}

function trgRows() {
  const acts = (D && D.actions) || Object.keys(T.en.acts);
  return P.triggers.map((x, i) => `<div style="display:flex;gap:10px;align-items:center;flex-wrap:wrap;margin-bottom:10px">
    <input class="field" style="margin:0;flex:1;min-width:150px" data-focus data-cl-tn="${i}" value="${E(x.number)}" inputmode="tel" autocomplete="off" placeholder="${E(t('num'))}">
    <select class="field" style="margin:0;width:auto;flex:0 1 210px" data-focus data-cl-ta="${i}">${acts.map(a => `<option value="${E(a)}" ${a === x.action ? 'selected' : ''}>${E((t('acts') || {})[a] || a)}</option>`).join('')}</select>
    <button type="button" class="chip ${x.reply_sms ? 'on' : ''}" data-focus data-cl-tr="${i}">${E(t('reply'))}</button>
    <button class="btn sm" data-focus data-cl-trm="${i}" aria-label="${E(t('remove'))}" title="${E(t('remove'))}">✕</button></div>`).join('');
}

function policyHtml() {
  const chip = (attr, v, on, txt) => `<button type="button" class="chip ${on ? 'on' : ''}" data-focus ${attr}="${E(v)}">${E(txt)}</button>`;
  const modes = ['notify', 'reject_all', 'allow_list'].map(m => chip('data-cl-mode', m, P.mode === m, t('mode')[m])).join('');
  const ta = (id, v) => `<textarea class="field" id="${id}" rows="3" spellcheck="false" autocomplete="off" inputmode="tel" placeholder="${E(t('listPh'))}" style="font:15px/1.4 var(--mono)">${E(v.join('\n'))}</textarea>`;
  return sec(t('policy'), `<div class="chips" style="margin-bottom:10px">${modes}</div>${hint(t('modeHelp')[P.mode] || '')}
      <div class="chips" style="margin-bottom:16px">${chip('data-cl-flag', 'notify', P.notify, t('notifyChip'))}</div>
      <div id="cl-allow-box" ${P.mode === 'allow_list' ? '' : 'hidden'}>${label(t('allow'))}${ta('cl-allow', P.allow)}</div>
      ${label(t('block'))}${ta('cl-block', P.block)}${hint(t('matchHelp'))}`) +
    sec(t('triggers'), `${hint(t('trgHelp'))}<div id="cl-trg">${trgRows()}</div>
      <div class="actions" style="margin-top:4px"><button class="btn sm" data-focus id="cl-trg-add">+ ${E(t('addTrg'))}</button></div>
      ${hint(t('starHelp'))}<div class="chips">${chip('data-cl-flag', 'triggers_from_sms_allow', P.triggers_from_sms_allow, t('fromSms')(D.sms_allow || 0))}</div>`) +
    sec(t('alarm'), `${hint(t('alarmHelp'))}<div class="chips" style="margin-bottom:12px">${chip('data-cl-flag', 'alarm', P.alarm.enabled, t('alarmOn'))}</div>
      <div style="display:flex;gap:10px;flex-wrap:wrap;align-items:center">
       <input class="field" style="margin:0;flex:1;min-width:170px" data-focus id="cl-al-num" value="${E(P.alarm.number)}" inputmode="tel" autocomplete="off" placeholder="${E(t('num'))}">
       <label style="display:flex;gap:8px;align-items:center;color:var(--dim)">${E(t('ringS'))}<input class="field" style="margin:0;width:90px" data-focus id="cl-al-s" type="number" min="5" max="60" value="${E(P.alarm.ring_s)}"></label>
       <button class="btn sm" data-focus id="cl-test">${E(t('test'))}</button></div>`) +
    `<div class="actions" style="margin:0 0 16px"><button class="btn primary" data-focus id="cl-save">${E(t('save'))}</button></div>`;
}

function ussdHtml() {
  return sec(t('ussd'), `${hint(t('ussdHelp'))}<form id="cl-uf" style="display:flex;gap:10px;flex-wrap:wrap">
     <input class="field" style="margin:0;flex:1;min-width:150px" data-focus id="cl-ucode" inputmode="tel" autocomplete="off" placeholder="${E(t('ussdPh'))}" maxlength="30">
     <button class="btn primary sm" data-focus id="cl-usend">${E(t('send'))}</button></form>
   <pre id="cl-ureply" hidden style="margin:12px 0 0"></pre>
   <div id="cl-uresp" hidden><p style="color:var(--orange);margin:12px 0 8px">${E(t('expects'))}</p>
    <form id="cl-urf" style="display:flex;gap:10px;flex-wrap:wrap"><input class="field" style="margin:0;flex:1;min-width:150px" data-focus id="cl-utext" autocomplete="off" maxlength="160" placeholder="${E(t('respPh'))}">
     <button class="btn primary sm" data-focus>${E(t('respond'))}</button><button type="button" class="btn sm" data-focus id="cl-ucancel">${E(t('cancel'))}</button></form></div>`);
}

// read the form back into P (keeps edits across re-renders); returns false and highlights on invalid input
function sync(mark) {
  const root = UZ.$('#cl-root'); if (!root) return false;
  let ok = true;
  const flag = (el, good) => { if (mark) el.style.boxShadow = good ? '' : '0 0 0 2px var(--red) inset'; if (!good) ok = false; };
  const list = id => { const el = UZ.$('#' + id); if (!el) return []; const v = el.value.split(/[\n,;]+/).map(clean).filter(Boolean); flag(el, v.every(x => NUM.test(x))); return v; };
  P.allow = list('cl-allow'); P.block = list('cl-block');
  UZ.$$('[data-cl-tn]').forEach(el => { const i = +el.dataset.clTn, v = el.value.trim() === '*' ? '*' : clean(el.value); P.triggers[i].number = v; flag(el, v === '*' || NUM.test(v)); });
  UZ.$$('[data-cl-ta]').forEach(el => { P.triggers[+el.dataset.clTa].action = el.value; });
  const an = UZ.$('#cl-al-num'), as = UZ.$('#cl-al-s');
  if (an) { P.alarm.number = clean(an.value); flag(an, !P.alarm.number || NUM.test(P.alarm.number)); if (P.alarm.enabled && !P.alarm.number) flag(an, false); }
  if (as) { const s = parseInt(as.value, 10); P.alarm.ring_s = s; flag(as, s >= 5 && s <= 60); }
  return ok;
}

function paintLive() {
  const n = UZ.$('#cl-now'), l = UZ.$('#cl-log');
  if (n) n.innerHTML = nowHtml();
  if (l) l.innerHTML = logHtml();
}
function paintPolicy() { sync(false); const p = UZ.$('#cl-pol'); if (p) p.innerHTML = policyHtml(); }

async function refresh() {
  try { const r = await UZ.post('calls-get', {}); if (r.error) { UZ.toast(r.error); return false; } D = r; return true; }
  catch (e) { UZ.toast(String(e)); return false; }
}

function bind(root) {
  root.addEventListener('click', async e => {
    const h = e.target.closest('[data-cl-hang]');
    if (h) { h.disabled = true; const r = await UZ.post('calls-hangup', h.dataset.clHang ? {path: h.dataset.clHang} : {}); UZ.toast(r.error || r.out); if (await refresh()) paintLive(); return; }
    const m = e.target.closest('[data-cl-mode]');
    if (m) { sync(false); P.mode = m.dataset.clMode; paintPolicy(); return; }
    const f = e.target.closest('[data-cl-flag]');
    if (f) { sync(false); const k = f.dataset.clFlag; if (k === 'alarm') P.alarm.enabled = !P.alarm.enabled; else P[k] = !P[k]; paintPolicy(); return; }
    const tr = e.target.closest('[data-cl-tr]');
    if (tr) { sync(false); const x = P.triggers[+tr.dataset.clTr]; x.reply_sms = !x.reply_sms; paintPolicy(); return; }
    const rm = e.target.closest('[data-cl-trm]');
    if (rm) { sync(false); P.triggers.splice(+rm.dataset.clTrm, 1); paintPolicy(); return; }
    const id = e.target.closest('button')?.id;
    if (id === 'cl-trg-add') {
      sync(false); if (P.triggers.length >= ((D.limits || {}).triggers || 10)) return;
      P.triggers.push({number: '', action: 'status', reply_sms: false}); paintPolicy();
      const ins = UZ.$$('[data-cl-tn]'); ins[ins.length - 1]?.focus(); return;
    }
    if (id === 'cl-clear') {
      if (!clearArm) { clearArm = true; paintLive(); return; }
      clearArm = false; const r = await UZ.post('calls-log-clear', {confirm: true}); UZ.toast(r.error || r.out);
      if (await refresh()) paintLive(); UZ.reload(); return;
    }
    if (id === 'cl-save') {
      if (!sync(true)) { UZ.toast(t('bad')); return; }
      const b = e.target.closest('button'); b.disabled = true;
      try { const r = await UZ.post('calls-set', {policy: P}); UZ.toast(r.error || t('saved')); if (!r.error) { P = JSON.parse(JSON.stringify(r.policy)); D.policy = r.policy; paintPolicy(); UZ.reload(); } }
      catch (x) { UZ.toast(String(x)); }
      b.disabled = false; return;
    }
    if (id === 'cl-test') {
      sync(false);
      if (!NUM.test(P.alarm.number || '')) { UZ.toast(t('bad')); return; }
      if (!(P.alarm.ring_s >= 5 && P.alarm.ring_s <= 60)) { UZ.toast(t('badS')); return; }
      const r = await UZ.post('calls-ring', {number: P.alarm.number, seconds: P.alarm.ring_s}); UZ.toast(r.error || r.out); return;
    }
    if (id === 'cl-ucancel') { const r = await UZ.post('calls-ussd-cancel', {}); UZ.toast(r.error || r.out); UZ.$('#cl-uresp').hidden = true; return; }
  });
  root.addEventListener('submit', async e => {
    e.preventDefault();
    const respond = e.target.id === 'cl-urf';
    const inp = UZ.$(respond ? '#cl-utext' : '#cl-ucode'), v = inp.value.trim();
    if (!respond && !USSD.test(v)) { UZ.toast(t('badUssd')); return; }
    if (respond && !v) return;
    const out = UZ.$('#cl-ureply'), btns = UZ.$$('#cl-uf button, #cl-urf button');
    btns.forEach(b => b.disabled = true); out.hidden = false; out.textContent = t('waitNet');
    try {
      const r = await UZ.post(respond ? 'calls-ussd-respond' : 'calls-ussd', respond ? {text: v} : {code: v});
      out.textContent = r.error ? r.error : (r.reply || r.out || '');
      UZ.$('#cl-uresp').hidden = !r.expects_input;
      if (r.expects_input) { UZ.$('#cl-utext').value = ''; UZ.$('#cl-utext').focus(); }
    } catch (x) { out.textContent = String(x); }
    btns.forEach(b => b.disabled = false);
  });
}

async function open() {
  if (poll) { clearInterval(poll); poll = null; }
  clearArm = false; D = null;
  UZ.openSheet('green', 'phone', E(t('title')), E(t('desc')), `<div id="cl-root"><p style="color:var(--dim)">${E(t('loading'))}</p></div><div class="actions">${UZ.closeBtn()}</div>`);
  if (!(await refresh())) return;
  const root = UZ.$('#cl-root'); if (!root) return;
  P = JSON.parse(JSON.stringify(D.policy));
  root.innerHTML = `<div id="cl-now"></div><div id="cl-log"></div><div id="cl-pol">${policyHtml()}</div>${ussdHtml()}`;
  paintLive(); bind(root);
  // mark missed calls seen
  if ((D.log || []).some(e => e.outcome === 'missed' && e.ts > (D.seen || 0))) {
    UZ.post('calls-seen', {}).then(r => { if (!r.error) UZ.reload(); }).catch(() => {});
  }
  const mine = root;
  poll = setInterval(async () => {
    if (!mine.isConnected) { clearInterval(poll); poll = null; return; }
    const seen = D.seen;
    if (await refresh() && mine.isConnected) { D.seen = seen; paintLive(); }
  }, 3000);
}

if (!UZ.I.phone) UZ.I.phone = PHONE;
UZ.register({
  id: 'calls', order: 15, color: 'green', iconSvg: PHONE,
  title: {en: T.en.title, vi: T.vi.title, zh: T.zh.title},
  sub: S => {
    const c = S?.settings?.calls; if (!c) return '';
    if (c.ringing) return t('ringingSub')(c.ringing);
    if (c.active) return t('onCall');
    if (c.missed_unseen) return t('missedN')(c.missed_unseen);
    if (!c.daemon) return t('off');
    if (c.sim === 'missing') return t('noSim');
    if (c.sim === 'locked') return t('simLocked');
    return c.available ? t('ready') : t('unavailable');
  },
  open,
});
})();
