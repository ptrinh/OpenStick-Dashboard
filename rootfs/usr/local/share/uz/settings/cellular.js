/* Cellular (4G) settings: SIM / PIN, APN, roaming, network mode, reconnect. ModemManager backend only. */
(() => {
const T = {
 en: {title: 'Cellular', desc: 'SIM, APN, roaming and network mode (ModemManager).', loading: 'Loading…',
  noSim: 'No SIM', pinReq: 'SIM PIN required', pukReq: 'SIM PUK required', apnAuto: 'APN automatic', apn: 'APN', roamingOn: 'Roaming',
  unsupported: 'Not available on this system', unsupportedD: 'These settings need ModemManager + NetworkManager (Debian image). On postmarketOS LTE is driven by uz-lte and is configured in /etc/uz/uz.conf.',
  noProfile: 'NetworkManager profile "lte" not found.',
  sim: 'SIM card', state: 'State', iccid: 'ICCID', imsi: 'IMSI', operator: 'Operator', number: 'Number', network: 'Network',
  sReady: 'Ready', sLocked: 'Locked', sMissing: 'No SIM inserted', sUnknown: 'Unknown',
  pin: 'SIM PIN', unlock: 'Unlock', left: n => `${n} attempts left. If they run out the SIM is blocked and needs the PUK from your carrier.`,
  lastTry: 'Last attempt! A wrong PIN now blocks the SIM.',
  puk: 'The SIM is blocked (PUK required). Unlock it in a phone, then reinsert it.',
  pinLock: 'PIN lock', on: 'On', off: 'Off', turnOn: 'Turn on', turnOff: 'Turn off', changePin: 'Change PIN',
  curPin: 'Current PIN', newPin: 'New PIN (4–8 digits)', confirmPin: 'I understand a wrong PIN uses up an attempt', apply: 'Apply',
  apnH: 'Access point (APN)', apnPh: 'APN — empty = automatic', user: 'Username (optional)', pw: 'Password — leave empty to keep',
  clearPw: 'Clear saved password', ipType: 'IP type', save: 'Save & reconnect',
  roaming: 'Data roaming', roamingD: 'Abroad, data roaming can be very expensive. Check your plan before turning it on.',
  roamingNow: 'Currently roaming', allowed: 'Allowed', blocked: 'Blocked',
  mode: 'Network mode', modeNone: 'The modem reports no selectable modes.', prefer: 'prefer', any: 'Any',
  reconnect: 'Reconnect', err: 'Error'},
 vi: {title: 'Di động', desc: 'SIM, APN, chuyển vùng và chế độ mạng (ModemManager).', loading: 'Đang tải…',
  noSim: 'Không có SIM', pinReq: 'Cần mã PIN SIM', pukReq: 'Cần mã PUK SIM', apnAuto: 'APN tự động', apn: 'APN', roamingOn: 'Chuyển vùng',
  unsupported: 'Không khả dụng trên hệ thống này', unsupportedD: 'Phần này cần ModemManager + NetworkManager (bản Debian). Trên postmarketOS, LTE do uz-lte điều khiển và cấu hình trong /etc/uz/uz.conf.',
  noProfile: 'Không tìm thấy hồ sơ NetworkManager "lte".',
  sim: 'Thẻ SIM', state: 'Trạng thái', iccid: 'ICCID', imsi: 'IMSI', operator: 'Nhà mạng', number: 'Số thuê bao', network: 'Mạng',
  sReady: 'Sẵn sàng', sLocked: 'Đang khoá', sMissing: 'Chưa lắp SIM', sUnknown: 'Không rõ',
  pin: 'Mã PIN SIM', unlock: 'Mở khoá', left: n => `Còn ${n} lần thử. Hết lượt, SIM sẽ bị khoá và cần mã PUK từ nhà mạng.`,
  lastTry: 'Lần thử cuối! Nhập sai PIN lúc này sẽ khoá SIM.',
  puk: 'SIM đã bị khoá (cần PUK). Hãy mở khoá bằng điện thoại rồi lắp lại.',
  pinLock: 'Khoá PIN', on: 'Bật', off: 'Tắt', turnOn: 'Bật', turnOff: 'Tắt', changePin: 'Đổi PIN',
  curPin: 'PIN hiện tại', newPin: 'PIN mới (4–8 số)', confirmPin: 'Tôi hiểu nhập sai PIN sẽ mất một lần thử', apply: 'Áp dụng',
  apnH: 'Điểm truy cập (APN)', apnPh: 'APN — để trống = tự động', user: 'Tên đăng nhập (tuỳ chọn)', pw: 'Mật khẩu — để trống để giữ nguyên',
  clearPw: 'Xoá mật khẩu đã lưu', ipType: 'Loại IP', save: 'Lưu & kết nối lại',
  roaming: 'Chuyển vùng dữ liệu', roamingD: 'Ở nước ngoài, chuyển vùng dữ liệu có thể rất đắt. Kiểm tra gói cước trước khi bật.',
  roamingNow: 'Đang chuyển vùng', allowed: 'Cho phép', blocked: 'Chặn',
  mode: 'Chế độ mạng', modeNone: 'Modem không báo chế độ nào để chọn.', prefer: 'ưu tiên', any: 'Bất kỳ',
  reconnect: 'Kết nối lại', err: 'Lỗi'},
 zh: {title: '蜂窝网络', desc: 'SIM、APN、漫游和网络模式（ModemManager）。', loading: '加载中…',
  noSim: '无 SIM 卡', pinReq: '需要 SIM PIN', pukReq: '需要 SIM PUK', apnAuto: 'APN 自动', apn: 'APN', roamingOn: '漫游中',
  unsupported: '此系统不支持', unsupportedD: '这些设置需要 ModemManager + NetworkManager（Debian 镜像）。在 postmarketOS 上 LTE 由 uz-lte 驱动，请在 /etc/uz/uz.conf 中配置。',
  noProfile: '未找到 NetworkManager 配置 "lte"。',
  sim: 'SIM 卡', state: '状态', iccid: 'ICCID', imsi: 'IMSI', operator: '运营商', number: '号码', network: '网络',
  sReady: '就绪', sLocked: '已锁定', sMissing: '未插入 SIM 卡', sUnknown: '未知',
  pin: 'SIM PIN', unlock: '解锁', left: n => `剩余 ${n} 次尝试。用完后 SIM 卡将被锁，需要运营商提供的 PUK 码。`,
  lastTry: '最后一次尝试！PIN 错误将锁定 SIM 卡。',
  puk: 'SIM 卡已被锁定（需要 PUK）。请在手机上解锁后重新插入。',
  pinLock: 'PIN 锁', on: '开', off: '关', turnOn: '开启', turnOff: '关闭', changePin: '更改 PIN',
  curPin: '当前 PIN', newPin: '新 PIN（4–8 位数字）', confirmPin: '我了解输错 PIN 会消耗一次尝试机会', apply: '应用',
  apnH: '接入点（APN）', apnPh: 'APN — 留空 = 自动', user: '用户名（可选）', pw: '密码 — 留空则保持不变',
  clearPw: '清除已保存的密码', ipType: 'IP 类型', save: '保存并重连',
  roaming: '数据漫游', roamingD: '在国外，数据漫游费用可能很高。开启前请确认您的套餐。',
  roamingNow: '当前处于漫游', allowed: '允许', blocked: '禁止',
  mode: '网络模式', modeNone: '调制解调器未报告可选模式。', prefer: '优先', any: '任意',
  reconnect: '重新连接', err: '错误'},
};
const t = k => (T[UZ.lang] || T.en)[k] ?? T.en[k];
const e = s => UZ.esc(s);
const st = S => (S && S.settings && S.settings.cellular) || {};

function modeLabel(m) {
  const x = /^allowed: ([a-z0-9, ]+); preferred: ([a-z0-9]+)$/.exec(m || '');
  if (!x) return m || '';
  const up = s => s === 'any' ? t('any') : s.toUpperCase();
  const a = x[1].split(',').map(s => up(s.trim())).join(' + ');
  return x[2] === 'none' ? a : `${a} (${t('prefer')} ${up(x[2])})`;
}

function sub(S) {
  const c = st(S);
  if (c.backend === 'none') return t('unsupported');
  if (c.sim === 'missing') return t('noSim');
  if (c.sim === 'locked') return c.unlock === 'sim-puk' ? t('pukReq') : t('pinReq');
  if (c.sim === 'ready') return (c.apn ? `${t('apn')} ${c.apn}` : t('apnAuto')) + (c.roaming ? ' · ' + t('roamingOn') : '');
  return '';
}

const row = (l, v) => `<span>${e(l)}</span><span style="overflow-wrap:anywhere">${v}</span>`;
const note = s => `<p style="color:var(--faint);font-size:13px;margin:6px 0 0">${e(s)}</p>`;
const h3 = s => `<h3 style="margin:24px 0 10px;font-size:15px;color:var(--dim);font-weight:700;letter-spacing:.04em;text-transform:uppercase">${e(s)}</h3>`;

function simHtml(d) {
  const s = d.sim, r = s.unlock_retries || {};
  const lbl = {ready: t('sReady'), locked: t('sLocked'), missing: t('sMissing')}[s.state] || t('sUnknown');
  const dot = s.state === 'ready' ? 'ok' : s.state === 'locked' ? 'warn' : 'bad';
  let h = `<div class="kv">${row(t('state'), `<span class="dot ${dot}"></span>${e(lbl)}`)}`;
  if (s.iccid) h += row(t('iccid'), `<code>${e(s.iccid)}</code>`);
  if (s.imsi) h += row(t('imsi'), `<code>${e(s.imsi)}</code>`);
  if (s.operator || d.network.operator) h += row(t('operator'), e(d.network.operator || s.operator));
  if ((s.own_numbers || []).length) h += row(t('number'), e(s.own_numbers.join(', ')));
  if (d.network.registration) h += row(t('network'), e([d.network.registration, ...(d.network.access_tech || [])].join(' · ')));
  h += '</div>';
  if (s.unlock_required === 'sim-pin') {
    const n = r['sim-pin'];
    h += `<form id="cell-pinf" autocomplete="off" style="margin-top:16px"><input class="field" id="cell-pin" type="password" inputmode="numeric" maxlength="8" placeholder="${e(t('pin'))}" autocomplete="off">
      ${n != null ? `<p style="color:${n <= 1 ? 'var(--red)' : 'var(--orange)'};font-size:14px;margin:0 0 10px">${e(n <= 1 ? t('lastTry') : t('left')(n))}</p>` : ''}
      <button class="btn primary sm" data-focus type="submit">${e(t('unlock'))}</button></form>`;
  } else if (s.unlock_required === 'sim-puk') {
    h += `<p style="color:var(--red);margin:14px 0 0">${e(t('puk'))}</p>`;
  } else if (s.state === 'ready') {
    h += `<details style="margin-top:14px"><summary style="cursor:pointer;color:var(--dim)">${e(t('pinLock'))}: ${e(s.pin_lock ? t('on') : t('off'))}</summary>
      <form id="cell-lockf" autocomplete="off" style="margin-top:12px"><input class="field" id="cell-lpin" type="password" inputmode="numeric" maxlength="8" placeholder="${e(t('curPin'))}" autocomplete="off">
      ${s.pin_lock ? `<input class="field" id="cell-npin" type="password" inputmode="numeric" maxlength="8" placeholder="${e(t('newPin'))}" autocomplete="off">` : ''}
      <label style="display:flex;gap:10px;align-items:center;font-size:14px;color:var(--dim);margin-bottom:12px"><input type="checkbox" id="cell-lconf"> ${e(t('confirmPin'))}</label>
      ${r['sim-pin'] != null ? note(t('left')(r['sim-pin'])) : ''}
      <div class="chips" style="margin-top:10px"><button class="btn sm" data-focus type="button" id="cell-lock-tog">${e(s.pin_lock ? t('turnOff') : t('turnOn'))}</button>
      ${s.pin_lock ? `<button class="btn sm" data-focus type="button" id="cell-pin-chg">${e(t('changePin'))}</button>` : ''}</div></form></details>`;
  }
  return h;
}

function apnHtml(p) {
  return `<form id="cell-apnf" autocomplete="off">
    <input class="field" id="cell-apn" maxlength="63" placeholder="${e(t('apnPh'))}" value="${e(p.apn)}" autocomplete="off" spellcheck="false">
    <input class="field" id="cell-user" maxlength="64" placeholder="${e(t('user'))}" value="${e(p.username)}" autocomplete="off" spellcheck="false">
    <input class="field" id="cell-pw" type="password" maxlength="64" placeholder="${e(t('pw'))}" autocomplete="new-password">
    <label style="display:flex;gap:10px;align-items:center;font-size:14px;color:var(--dim);margin-bottom:12px"><input type="checkbox" id="cell-clrpw"> ${e(t('clearPw'))}</label>
    <div style="color:var(--faint);font-size:13px;margin-bottom:8px">${e(t('ipType'))}</div>
    <div class="chips">${['ipv4', 'ipv6', 'ipv4v6'].map(x => `<button type="button" class="chip ${p.ip_type === x ? 'on' : ''}" data-focus data-cip="${x}">${x === 'ipv4v6' ? 'IPv4 + IPv6' : x === 'ipv4' ? 'IPv4' : 'IPv6'}</button>`).join('')}</div>
    <div class="actions" style="margin-top:14px"><button class="btn primary sm" data-focus type="submit">${e(t('save'))}</button></div></form>`;
}

function roamHtml(d) {
  const allow = d.profile.roaming_allowed;
  return `<div class="stat" style="display:flex;align-items:center;gap:16px;flex-wrap:wrap"><div style="flex:1;min-width:200px">
    <div class="n"><span class="dot ${allow ? 'warn' : ''}"></span>${e(allow ? t('allowed') : t('blocked'))}${d.network.roaming ? `<small>${e(t('roamingNow'))}</small>` : ''}</div>
    ${note(t('roamingD'))}</div>
    <button class="btn sm ${allow ? '' : 'primary'}" data-focus type="button" id="cell-roam" data-allow="${allow ? '' : '1'}">${e(allow ? t('turnOff') : t('turnOn'))}</button></div>`;
}

function modeHtml(d) {
  const L = d.modes.supported || [];
  if (!L.length) return note(t('modeNone'));
  return `<div class="chips">${L.map((m, i) => `<button type="button" class="chip ${m === d.modes.current ? 'on' : ''}" data-focus data-cmode="${i}">${e(modeLabel(m))}</button>`).join('')}</div>`;
}

async function run(action, body, btn) {
  if (btn) btn.disabled = true;
  let r;
  try { r = await UZ.post(action, body); } catch (x) { r = {error: t('err') + ': ' + x}; }
  UZ.toast(r.error || r.out || 'ok');
  if (btn) btn.disabled = false;
  if (!r.error) { setTimeout(() => { UZ.reload(); if (document.getElementById('cell-root')) open(UZ.S); }, 1200); }
  return r;
}

async function open(S) {
  const shell = body => UZ.openSheet('blue', 'signal', e(t('title')), e(t('desc')), `<div id="cell-root">${body}</div><div class="actions">${UZ.closeBtn()}</div>`);
  if (st(S).backend === 'none') {
    shell(`<div class="empty">${e(t('unsupported'))}</div>${note(t('unsupportedD'))}`); return;
  }
  if (!document.getElementById('cell-root')) shell(`<div class="empty">${e(t('loading'))}</div>`);
  let d;
  try { d = await UZ.post('cell-get', {}); } catch (x) { d = {error: String(x)}; }
  if (!document.getElementById('cell-root')) return;            // sheet closed meanwhile
  if (d.error) {
    shell(`<div class="empty">${e(d.error)}</div>${d.error.includes('backend') ? note(t('unsupportedD')) : ''}`); return;
  }
  let h = h3(t('sim')) + simHtml(d);
  if (d.profile) {
    h += h3(t('apnH')) + apnHtml(d.profile) + h3(t('roaming')) + roamHtml(d);
  } else {
    h += `<div class="empty" style="margin-top:20px">${e(t('noProfile'))}</div>`;
  }
  h += h3(t('mode')) + modeHtml(d);
  UZ.openSheet('blue', 'signal', e(t('title')), e(t('desc')),
    `<div id="cell-root">${h}</div><div class="actions"><button class="btn primary" data-focus type="button" id="cell-rec">${e(t('reconnect'))}</button>${UZ.closeBtn()}</div>`);
  wire(d);
}

function wire(d) {
  const $ = UZ.$, $$ = UZ.$$;
  let ip = d.profile ? d.profile.ip_type : 'ipv4v6';
  const pf = $('#cell-pinf');
  if (pf) pf.onsubmit = ev => { ev.preventDefault(); const p = $('#cell-pin'); const v = p.value; p.value = ''; run('cell-pin-unlock', {pin: v}, pf.querySelector('button')); };
  const tog = $('#cell-lock-tog');
  if (tog) tog.onclick = () => {
    const v = $('#cell-lpin').value; $('#cell-lpin').value = '';
    run('cell-pin-lock', {pin: v, enable: !d.sim.pin_lock, confirm: $('#cell-lconf').checked}, tog);
  };
  const chg = $('#cell-pin-chg');
  if (chg) chg.onclick = () => {
    const v = $('#cell-lpin').value, n = $('#cell-npin').value; $('#cell-lpin').value = ''; $('#cell-npin').value = '';
    run('cell-pin-change', {pin: v, new_pin: n, confirm: $('#cell-lconf').checked}, chg);
  };
  $$('[data-cip]').forEach(b => b.onclick = () => { ip = b.dataset.cip; $$('[data-cip]').forEach(x => x.classList.toggle('on', x === b)); });
  const af = $('#cell-apnf');
  if (af) af.onsubmit = ev => {
    ev.preventDefault();
    const body = {apn: $('#cell-apn').value.trim(), username: $('#cell-user').value, ip_type: ip};
    const pw = $('#cell-pw').value; $('#cell-pw').value = '';
    if (pw) body.password = pw; else if ($('#cell-clrpw').checked) body.password = '';
    run('cell-apn-set', body, af.querySelector('button[type=submit]'));
  };
  const rb = $('#cell-roam');
  if (rb) rb.onclick = () => run('cell-roaming-set', {allow: rb.dataset.allow === '1'}, rb);
  $$('[data-cmode]').forEach(b => b.onclick = () => run('cell-mode-set', {mode: d.modes.supported[+b.dataset.cmode]}, b));
  const rc = $('#cell-rec');
  if (rc) rc.onclick = () => run('cell-reconnect', {}, rc);
}

UZ.register({
  id: 'cellular', order: 30, color: 'blue', icon: 'signal',
  title: {en: T.en.title, vi: T.vi.title, zh: T.zh.title},
  sub, open,
});
})();
