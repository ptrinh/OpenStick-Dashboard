/* System settings: hostname, time zone, Debian release pin + updates, scheduled restart. Server: settings/system.py */
(() => {
const T = {
 en: {title: 'System', loading: 'Loading…', overview: 'Overview', os: 'OS', kernel: 'Kernel', uptime: 'Uptime',
  clock: 'Clock', synced: 'synced (NTP)', notSynced: 'not synced', ntpOff: 'NTP off',
  host: 'Hostname', hostPh: 'e.g. uz801', save: 'Save',
  hostWarn: 'Changes the Linux hostname only. The Tailscale name ({ts}) is pinned first, so this dashboard\'s HTTPS address and passkeys stay the same.',
  hostBad: 'Use 1–63 characters a–z, 0–9 and -, not starting or ending with -.',
  tz: 'Time zone', tzMine: 'Use this device', tzPh: 'Search, e.g. Asia/Singapore', tzBad: 'Pick a time zone from the list.',
  upd: 'Updates', pinned: 'Pinned to Debian 13 (trixie)', notPinned: 'Follows “stable”',
  pinWarn: 'Your apt sources follow “stable”. When Debian 14 is released, “stable” will point to it and a normal upgrade would pull a whole new release onto this custom kernel, which can leave the stick unbootable. Pin to “trixie” (Debian 13) to keep getting its security and bug-fix updates only. A .bak copy of each changed file is kept.',
  pinBtn: 'Pin to trixie', noDebian: 'No Debian apt sources found.', apk: 'Updates from the dashboard are not supported on postmarketOS (apk) yet.',
  noPkg: 'No package manager found on this host.',
  never: 'Not checked yet.', nUpd: n => n === 1 ? '1 update available' : `${n} updates available`, upToDate: 'Up to date',
  held: n => `${n} held back`, checked: 'checked', ago: 'ago', check: 'Check for updates', install: 'Install updates',
  needPin: 'Pin to trixie before installing updates.',
  confirmT: n => `Install ${n} update${n === 1 ? '' : 's'} now?`,
  confirmD: 'Runs apt-get upgrade (no new Debian release, nothing removed, your config files kept). It takes several minutes; the dashboard may disconnect briefly if Tailscale is updated. Do not unplug the stick.',
  yesInstall: 'Yes, install', cancel: 'Cancel',
  checking: 'Checking for updates…', installing: 'Installing updates…', upDone: 'Last install finished', upFailed: 'Last install failed',
  upInterrupted: 'Last install was interrupted (restart during upgrade)', chkFailed: 'Last check failed', log: 'Log',
  lowRes: (d, m) => `Free: ${d} MB disk, ${m} MB RAM+swap.`,
  rb: 'Scheduled restart', on: 'On', off: 'Off', time: 'Time', days: 'Days', every: 'every day',
  dn: {mon: 'Mon', tue: 'Tue', wed: 'Wed', thu: 'Thu', fri: 'Fri', sat: 'Sat', sun: 'Sun'},
  rbD: 'Restarts the stick at this local time (skipped while updates are installing).', pickDay: 'Pick at least one day.',
  updShort: n => n === 1 ? '1 update' : `${n} updates`, notPinnedShort: 'not pinned', busy: 'updating…', d: 'd', h: 'h', m: 'min'},
 vi: {title: 'Hệ thống', loading: 'Đang tải…', overview: 'Tổng quan', os: 'Hệ điều hành', kernel: 'Kernel', uptime: 'Thời gian chạy',
  clock: 'Đồng hồ', synced: 'đã đồng bộ (NTP)', notSynced: 'chưa đồng bộ', ntpOff: 'NTP tắt',
  host: 'Tên máy', hostPh: 'vd. uz801', save: 'Lưu',
  hostWarn: 'Chỉ đổi hostname của Linux. Tên Tailscale ({ts}) được chốt cố định trước, nên địa chỉ HTTPS của dashboard và passkey không đổi.',
  hostBad: 'Dùng 1–63 ký tự a–z, 0–9 và -, không bắt đầu hay kết thúc bằng -.',
  tz: 'Múi giờ', tzMine: 'Dùng múi giờ máy này', tzPh: 'Tìm, vd. Asia/Ho_Chi_Minh', tzBad: 'Hãy chọn múi giờ trong danh sách.',
  upd: 'Cập nhật', pinned: 'Đã ghim Debian 13 (trixie)', notPinned: 'Đang theo “stable”',
  pinWarn: 'Nguồn apt đang theo “stable”. Khi Debian 14 phát hành, “stable” sẽ trỏ sang bản đó và một lần nâng cấp bình thường sẽ kéo cả bản phát hành mới lên kernel tuỳ biến này, có thể khiến thiết bị không khởi động được. Ghim về “trixie” (Debian 13) để chỉ nhận bản vá bảo mật và sửa lỗi. Mỗi tệp bị sửa đều được giữ bản .bak.',
  pinBtn: 'Ghim trixie', noDebian: 'Không thấy nguồn apt Debian.', apk: 'Chưa hỗ trợ cập nhật từ bảng điều khiển trên postmarketOS (apk).',
  noPkg: 'Không tìm thấy trình quản lý gói trên máy này.',
  never: 'Chưa kiểm tra.', nUpd: n => `Có ${n} bản cập nhật`, upToDate: 'Đã mới nhất',
  held: n => `${n} gói giữ lại`, checked: 'kiểm tra', ago: 'trước', check: 'Kiểm tra cập nhật', install: 'Cài cập nhật',
  needPin: 'Hãy ghim trixie trước khi cài cập nhật.',
  confirmT: n => `Cài ${n} bản cập nhật ngay?`,
  confirmD: 'Chạy apt-get upgrade (không lên bản Debian mới, không gỡ gói, giữ tệp cấu hình của bạn). Mất vài phút; bảng điều khiển có thể mất kết nối chốc lát nếu Tailscale được cập nhật. Đừng rút thiết bị.',
  yesInstall: 'Cài ngay', cancel: 'Huỷ',
  checking: 'Đang kiểm tra cập nhật…', installing: 'Đang cài cập nhật…', upDone: 'Lần cài gần nhất đã xong', upFailed: 'Lần cài gần nhất bị lỗi',
  upInterrupted: 'Lần cài gần nhất bị ngắt (khởi động lại giữa chừng)', chkFailed: 'Lần kiểm tra gần nhất bị lỗi', log: 'Nhật ký',
  lowRes: (d, m) => `Còn trống: ${d} MB đĩa, ${m} MB RAM+swap.`,
  rb: 'Khởi động lại theo lịch', on: 'Bật', off: 'Tắt', time: 'Giờ', days: 'Ngày', every: 'mỗi ngày',
  dn: {mon: 'T2', tue: 'T3', wed: 'T4', thu: 'T5', fri: 'T6', sat: 'T7', sun: 'CN'},
  rbD: 'Khởi động lại thiết bị vào giờ địa phương này (bỏ qua khi đang cài cập nhật).', pickDay: 'Chọn ít nhất một ngày.',
  updShort: n => `${n} cập nhật`, notPinnedShort: 'chưa ghim', busy: 'đang cập nhật…', d: 'ngày', h: 'giờ', m: 'phút'},
 zh: {title: '系统', loading: '加载中…', overview: '概览', os: '系统', kernel: '内核', uptime: '运行时间',
  clock: '时钟', synced: '已同步 (NTP)', notSynced: '未同步', ntpOff: 'NTP 已关闭',
  host: '主机名', hostPh: '例如 uz801', save: '保存',
  hostWarn: '仅修改 Linux 主机名。会先固定 Tailscale 名称（{ts}），因此控制台的 HTTPS 地址和通行密钥保持不变。',
  hostBad: '使用 1–63 个字符：a–z、0–9 和 -，不能以 - 开头或结尾。',
  tz: '时区', tzMine: '使用本机时区', tzPh: '搜索，例如 Asia/Shanghai', tzBad: '请从列表中选择时区。',
  upd: '更新', pinned: '已锁定 Debian 13 (trixie)', notPinned: '跟随 “stable”',
  pinWarn: 'apt 源当前跟随 “stable”。Debian 14 发布后，“stable” 会指向它，一次普通升级就会把整个新版本装到这个定制内核上，可能导致设备无法启动。锁定到 “trixie”（Debian 13）后只接收安全和错误修复更新。每个被修改的文件都会保留 .bak 备份。',
  pinBtn: '锁定 trixie', noDebian: '未找到 Debian apt 源。', apk: '暂不支持在 postmarketOS (apk) 上从面板更新。',
  noPkg: '此设备上没有找到包管理器。',
  never: '尚未检查。', nUpd: n => `${n} 个可用更新`, upToDate: '已是最新',
  held: n => `${n} 个被保留`, checked: '检查于', ago: '前', check: '检查更新', install: '安装更新',
  needPin: '安装更新前请先锁定 trixie。',
  confirmT: n => `现在安装 ${n} 个更新？`,
  confirmD: '运行 apt-get upgrade（不升级到新的 Debian 版本，不删除软件包，保留你的配置文件）。需要几分钟；如果 Tailscale 被更新，面板可能短暂断开。请勿拔出设备。',
  yesInstall: '确认安装', cancel: '取消',
  checking: '正在检查更新…', installing: '正在安装更新…', upDone: '上次安装已完成', upFailed: '上次安装失败',
  upInterrupted: '上次安装被中断（升级中途重启）', chkFailed: '上次检查失败', log: '日志',
  lowRes: (d, m) => `可用：磁盘 ${d} MB，内存+交换 ${m} MB。`,
  rb: '定时重启', on: '开', off: '关', time: '时间', days: '日期', every: '每天',
  dn: {mon: '一', tue: '二', wed: '三', thu: '四', fri: '五', sat: '六', sun: '日'},
  rbD: '在此本地时间重启设备（正在安装更新时跳过）。', pickDay: '请至少选择一天。',
  updShort: n => `${n} 个更新`, notPinnedShort: '未锁定', busy: '更新中…', d: '天', h: '小时', m: '分钟'},
};
const t = k => { const L = T[UZ.lang] || T.en; return L[k] ?? T.en[k] ?? k; };
const E = s => UZ.esc(s == null ? '' : String(s));
const DAYS = ['mon', 'tue', 'wed', 'thu', 'fri', 'sat', 'sun'];
const HOST_RE = /^[a-z0-9]([a-z0-9-]{0,61}[a-z0-9])?$/;
let D = null, zones = null, poll = null, confirming = false, lastRun = null;

const dur = s => { s = Math.max(0, Math.floor(+s || 0)); const d = Math.floor(s / 86400), h = Math.floor(s % 86400 / 3600), m = Math.floor(s % 3600 / 60);
  return d ? `${d} ${t('d')} ${h} ${t('h')}` : h ? `${h} ${t('h')} ${m} ${t('m')}` : `${m} ${t('m')}`; };
const ago = ts => ts ? `${t('checked')} ${dur(Date.now() / 1000 - ts)} ${t('ago')}` : '';
const H3 = s => `<h3 style="margin:26px 0 10px;font-size:18px">${E(s)}</h3>`;
const P = s => `<p class="desc" style="margin:0 0 12px">${s}</p>`;    // s must already be escaped

function sub(S) {
  const x = S && S.settings && S.settings.system;
  if (!x || x.error) return '';
  const a = x.apt || {}, parts = [];
  if (x.tz) parts.push(x.tz);
  if (a.running) parts.push(t('busy'));
  else if (!a.pinned) parts.push(t('notPinnedShort'));
  else if (Number.isInteger(a.updates)) parts.push(a.updates ? t('updShort')(a.updates) : t('upToDate'));
  return parts.join(' · ');
}

function overviewHtml() {
  const ntp = D.ntp_synced === true ? `<span class="dot ok"></span>${E(t('synced'))}` : D.ntp === false ? `<span class="dot warn"></span>${E(t('ntpOff'))}`
    : D.ntp_synced === false ? `<span class="dot warn"></span>${E(t('notSynced'))}` : '—';
  return `<div class="kv"><span>${E(t('os'))}</span><span>${E(D.os || '—')}</span><span>${E(t('kernel'))}</span><span>${E(D.kernel || '—')}</span>
    <span>${E(t('uptime'))}</span><span>${D.uptime != null ? E(dur(D.uptime)) : '—'}</span><span>${E(t('clock'))}</span><span>${ntp}</span></div>`;
}

function hostHtml() {
  const ts = (UZ.S && UZ.S.ts && UZ.S.ts.dns) || '—';
  return `${H3(t('host'))}<form id="sys-hf" autocomplete="off"><input class="field" id="sys-host" value="${E(D.hostname)}" placeholder="${E(t('hostPh'))}"
    maxlength="63" spellcheck="false" autocapitalize="off"><p class="desc" style="margin:0 0 12px">${E(t('hostWarn')).replace('{ts}', `<code style="overflow-wrap:anywhere">${E(ts)}</code>`)}</p>
    <div class="actions" style="margin-top:0"><button class="btn sm primary" data-focus type="submit">${E(t('save'))}</button></div></form>`;
}

function tzHtml() {
  const mine = browserTz();
  return `${H3(t('tz'))}<form id="sys-tf" autocomplete="off"><select class="field" id="sys-tz" data-focus style="color-scheme:dark;appearance:auto"><option>${E(D.tz || '')}</option></select>
    <div class="actions" style="margin-top:0"><button class="btn sm primary" data-focus type="submit">${E(t('save'))}</button>
    ${mine && mine !== D.tz ? `<button class="btn sm" data-focus type="button" id="sys-tzme">${E(t('tzMine'))}: ${E(mine)}</button>` : ''}</div></form>`;
}

function updHtml() {
  let h = H3(t('upd'));
  if (D.pkg === 'apk') return h + P(E(t('apk')));
  if (D.pkg !== 'apt') return h + P(E(t('noPkg')));
  const pin = D.pin || {}, a = D.apt || {}, c = a.check || {}, u = a.upgrade || {}, run = a.running;
  if (!pin.debian_sources) h += P(`<span class="dot warn"></span>${E(t('noDebian'))}`);
  else if (pin.pinned) h += P(`<span class="dot ok"></span>${E(t('pinned'))}`);
  else h += P(`<span class="dot bad"></span><b>${E(t('notPinned'))}</b> (${E((pin.suites || []).join(', '))})<br>${E(t('pinWarn'))}`)
    + `<div class="actions" style="margin-top:0"><button class="btn sm primary" data-focus data-sys="pin">${E(t('pinBtn'))}</button></div>`;
  if (run === 'check') h += P(`<span class="dot warn"></span>${E(t('checking'))}`);
  else if (run === 'upgrade') h += P(`<span class="dot warn"></span>${E(t('installing'))}`);
  else {
    let line = Number.isInteger(c.count) ? (c.count ? E(t('nUpd')(c.count)) : E(t('upToDate'))) : E(t('never'));
    if (c.held) line += ' · ' + E(t('held')(c.held));
    if (c.checked) line += ' · ' + E(ago(c.checked));
    h += P(`<span class="dot ${c.count ? 'warn' : Number.isInteger(c.count) ? 'ok' : ''}"></span>${line}`);
    if (c.state === 'failed') h += P(`<span class="dot bad"></span>${E(t('chkFailed'))}: ${E(c.error || '')}`);
    if (c.count && (c.packages || []).length) h += `<p class="desc" style="margin:0 0 12px;font:13px/1.5 var(--mono);overflow-wrap:anywhere">${E(c.packages.slice(0, 60).join(' '))}${c.packages.length > 60 ? ' …' : ''}</p>`;
    if (u.state === 'done') h += P(`<span class="dot ok"></span>${E(t('upDone'))}`);
    else if (u.state === 'failed') h += P(`<span class="dot bad"></span>${E(t('upFailed'))}: ${E(u.error || '')}`);
    else if (u.state === 'interrupted') h += P(`<span class="dot bad"></span>${E(t('upInterrupted'))}`);
  }
  if (confirming && !run) {
    h += `<div class="stat" style="margin:6px 0 12px"><div style="font-weight:700;margin-bottom:6px">${E(t('confirmT')(c.count || 0))}</div>
      <div class="desc" style="margin:0">${E(t('confirmD'))}</div><div class="desc" style="margin:6px 0 0">${E(t('lowRes')(D.disk_free_mb, D.mem_free_mb))}</div>
      <div class="actions"><button class="btn sm red" data-focus data-sys="upgrade">${E(t('yesInstall'))}</button><button class="btn sm" data-focus data-sys="cancel">${E(t('cancel'))}</button></div></div>`;
  } else if (!run) {
    h += `<div class="actions" style="margin-top:0"><button class="btn sm" data-focus data-sys="check">${E(t('check'))}</button>`
      + (pin.pinned ? `<button class="btn sm primary" data-focus data-sys="confirm"${c.count === 0 ? ' disabled' : ''}>${E(t('install'))}</button>` : '') + '</div>';
    if (!pin.pinned && pin.debian_sources) h += P(E(t('needPin')));
  }
  const log = a.log || '';
  if (log) h += `<details${run ? ' open' : ''}><summary style="cursor:pointer;color:var(--dim)">${E(t('log'))}</summary><pre id="sys-log">${E(log)}</pre></details>`;
  return h;
}

function rbHtml() {
  const r = D.reboot || {}, days = r.days && r.days.length ? r.days : DAYS;
  return `${H3(t('rb'))}<p class="desc" style="margin:0 0 12px">${E(t('rbD'))}</p>
   <div class="chips" style="margin-bottom:12px"><button class="chip ${r.enabled ? 'on' : ''}" data-focus data-rb="on">${E(t('on'))}</button><button class="chip ${r.enabled ? '' : 'on'}" data-focus data-rb="off">${E(t('off'))}</button></div>
   <div id="sys-rbx"${r.enabled ? '' : ' hidden'}><input class="field" id="sys-rbt" type="time" value="${E(r.time || '04:00')}" style="max-width:200px">
   <div class="chips" id="sys-days" style="margin-bottom:12px">${DAYS.map(d => `<button class="chip ${days.includes(d) ? 'on' : ''}" data-focus data-day="${d}">${E(t('dn')[d])}</button>`).join('')}</div></div>
   <div class="actions" style="margin-top:0"><button class="btn sm primary" data-focus data-sys="rb-save">${E(t('save'))}</button></div>`;
}

function renderUpd() { const el = UZ.$('#sys-upd'); if (el) el.innerHTML = updHtml(); }

async function refresh() {
  const r = await UZ.post('sys-get', {});
  if (r.error) { UZ.toast(r.error); return false; }
  D = r; return true;
}

async function tick() {
  if (!UZ.$('#sysx')) { clearInterval(poll); poll = null; return; }   // sheet closed or replaced
  let a; try { a = await UZ.post('sys-apt-status', {}); } catch (e) { return; }   // e.g. Tailscale restarting
  if (!a || a.error || !D || !UZ.$('#sysx')) return;
  const was = lastRun; lastRun = a.running;
  D.apt = a;
  if (was && !a.running) { await refresh(); UZ.reload(); renderUpd(); return; }   // job just finished
  if (a.running) {
    const pre = UZ.$('#sys-log');
    if (pre && UZ.$('#sys-upd').dataset.run === a.running) { const stick = pre.scrollTop + pre.clientHeight >= pre.scrollHeight - 8; pre.textContent = a.log || ''; if (stick) pre.scrollTop = pre.scrollHeight; }
    else { renderUpd(); UZ.$('#sys-upd').dataset.run = a.running; const p = UZ.$('#sys-log'); if (p) p.scrollTop = p.scrollHeight; }
  }
}

function browserTz() { try { return Intl.DateTimeFormat().resolvedOptions().timeZone || ''; } catch (e) { return ''; } }

async function loadZones() {
  if (!zones) { const r = await UZ.post('sys-timezones', {}); zones = r.zones || []; }
  const sel = UZ.$('#sys-tz'); if (!sel || !zones.length) return;
  const cur = D.tz || 'Etc/UTC', groups = {};
  zones.forEach(z => { const g = z.includes('/') ? z.split('/')[0] : 'Other'; (groups[g] = groups[g] || []).push(z); });
  sel.innerHTML = (zones.includes(cur) ? '' : `<option value="${E(cur)}" selected>${E(cur)}</option>`) +
    Object.keys(groups).sort().map(g => `<optgroup label="${E(g)}">${groups[g].map(z =>
      `<option value="${E(z)}"${z === cur ? ' selected' : ''}>${E(z.includes('/') ? z.slice(g.length + 1).replace(/_/g, ' ') : z)}</option>`).join('')}</optgroup>`).join('');
}

async function act(name, body) {
  const r = await UZ.post(name, body);
  UZ.toast(r.error || r.out || 'OK');
  return r;
}

function bind() {
  const root = UZ.$('#sysx');
  UZ.$('#sys-hf').onsubmit = async e => {
    e.preventDefault(); const v = UZ.$('#sys-host').value.trim().toLowerCase();
    if (!HOST_RE.test(v)) { UZ.toast(t('hostBad')); return; }
    const r = await act('sys-hostname-set', {hostname: v}); if (!r.error) { D.hostname = r.hostname; UZ.reload(); }
  };
  UZ.$('#sys-tf').onsubmit = async e => {
    e.preventDefault(); const v = UZ.$('#sys-tz').value.trim();
    if (zones && zones.length && !zones.includes(v)) { UZ.toast(t('tzBad')); return; }
    const r = await act('sys-timezone-set', {tz: v}); if (!r.error) { D.tz = r.tz; UZ.reload(); }
  };
  const me = UZ.$('#sys-tzme');
  if (me) me.onclick = () => { const z = browserTz(), sel = UZ.$('#sys-tz');
    if (zones && zones.includes(z)) { sel.value = z; UZ.$('#sys-tf').requestSubmit(); } else UZ.toast(t('tzBad')); };
  root.onclick = async e => {
    const rb = e.target.closest('[data-rb]'), day = e.target.closest('[data-day]'), b = e.target.closest('[data-sys]');
    if (rb) { UZ.$$('[data-rb]').forEach(x => x.classList.toggle('on', x === rb)); UZ.$('#sys-rbx').hidden = rb.dataset.rb !== 'on'; return; }
    if (day) { day.classList.toggle('on'); return; }
    if (!b || b.disabled) return;
    const k = b.dataset.sys;
    if (k === 'confirm') { confirming = true; renderUpd(); UZ.$('[data-sys="cancel"]')?.focus(); return; }
    if (k === 'cancel') { confirming = false; renderUpd(); return; }
    if (k === 'rb-save') {
      const enabled = UZ.$('[data-rb="on"]').classList.contains('on');
      const days = UZ.$$('[data-day].on').map(x => x.dataset.day), time = UZ.$('#sys-rbt').value;
      if (enabled && !days.length) { UZ.toast(t('pickDay')); return; }
      const r = await act('sys-reboot-schedule', enabled ? {enabled, time, days} : {enabled});
      if (!r.error && r.reboot) { D.reboot = r.reboot; UZ.reload(); }
      return;
    }
    b.disabled = true;
    try {
      if (k === 'pin') await act('sys-apt-pin', {suite: 'trixie'});
      else if (k === 'check') await act('sys-apt-check', {});
      else if (k === 'upgrade') { confirming = false; await act('sys-apt-upgrade', {confirm: true}); }
      if (await refresh()) { lastRun = D.apt && D.apt.running; renderUpd(); UZ.reload(); }
    } finally { b.disabled = false; }
  };
}

UZ.register({
  id: 'system', order: 70, color: 'gray', icon: 'chip',
  title: {en: T.en.title, vi: T.vi.title, zh: T.zh.title},
  sub,
  async open(S) {
    confirming = false; D = null;
    UZ.openSheet('gray', 'chip', E(t('title')), E(t('loading')), `<div id="sysx"></div><div class="actions">${UZ.closeBtn()}</div>`);
    if (!(await refresh())) return;
    const root = UZ.$('#sysx'); if (!root) return;
    const desc = UZ.card().querySelector('.desc'); if (desc) desc.textContent = `${D.hostname || ''}${D.os ? ' · ' + D.os : ''}`;
    root.innerHTML = overviewHtml() + hostHtml() + tzHtml() + `<div id="sys-upd">${updHtml()}</div>` + rbHtml();
    lastRun = D.apt && D.apt.running;
    bind(); loadZones();
    if (poll) clearInterval(poll);
    poll = setInterval(tick, 3000);
  },
});
})();
