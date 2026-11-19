/* Wi-Fi networks (client): scan, join, saved profiles. Server side: /usr/local/lib/uz/settings/wifi.py */
(() => {
const T = {
 en: {title: 'Wi-Fi networks', notConn: 'Not connected', hsMode: 'Hotspot mode', switching: 'Switching to',
  desc: 'Networks the stick joins as a client. Remote access (Tailscale) often runs over this Wi-Fi.',
  current: 'Current network', signal: 'signal', scan: 'Scan', scanning: 'Scanning…', other: 'Join other network',
  nets: 'Nearby networks', hiddenN: n => `${n} hidden network${n === 1 ? '' : 's'} — use “Join other network”`,
  none: 'No networks found', saved: 'Saved networks', noSaved: 'No saved networks', connected: 'Connected', savedTag: 'Saved',
  open: 'Open', ent: 'Enterprise — not supported', aps: 'access points', ch: 'ch',
  connect: 'Connect', cancel: 'Cancel', pw: 'Password', pwSaved: 'Password (leave empty to use the saved one)',
  ssid: 'Network name (SSID)', hidden: 'Hidden network', pwOpen: 'Password (empty for an open network)',
  warn: 'Switching networks may disconnect this dashboard for up to a minute. If the new network has no Internet after 60 s, the stick goes back to the current one automatically.',
  hsWarn: 'Wi-Fi is running the stick’s hotspot (Travel mode). Switch to Home mode to scan or join networks.',
  prio: 'Priority', auto: 'Auto-connect', on: 'on', off: 'off', edit: 'Edit', save: 'Save', forget: 'Forget',
  forgetQ: 'Forget this network? The saved password is deleted.',
  forgetActive: 'This is the network in use. Forgetting it disconnects Wi-Fi; allowed only while 4G or USB provides Internet.',
  confirmForget: 'Yes, forget', last: 'last used', never: 'never', active: 'in use',
  prioHint: 'Higher priority is preferred when several saved networks are in range (−999…999).',
  sw: {connecting: 'Connecting…', checking: 'Checking Internet…', ok: 'Connected', 'rolled-back': 'Rolled back'},
  unavailable: 'Wi-Fi control is not available on this host.'},
 vi: {title: 'Mạng Wi-Fi', notConn: 'Chưa kết nối', hsMode: 'Đang phát hotspot', switching: 'Đang chuyển sang',
  desc: 'Các mạng stick kết nối vào (chế độ client). Truy cập từ xa (Tailscale) thường đi qua Wi-Fi này.',
  current: 'Mạng hiện tại', signal: 'sóng', scan: 'Quét', scanning: 'Đang quét…', other: 'Kết nối mạng khác',
  nets: 'Mạng xung quanh', hiddenN: n => `${n} mạng ẩn — dùng “Kết nối mạng khác”`,
  none: 'Không tìm thấy mạng nào', saved: 'Mạng đã lưu', noSaved: 'Chưa lưu mạng nào', connected: 'Đang kết nối', savedTag: 'Đã lưu',
  open: 'Mở', ent: 'Enterprise — không hỗ trợ', aps: 'điểm phát', ch: 'kênh',
  connect: 'Kết nối', cancel: 'Huỷ', pw: 'Mật khẩu', pwSaved: 'Mật khẩu (để trống để dùng mật khẩu đã lưu)',
  ssid: 'Tên mạng (SSID)', hidden: 'Mạng ẩn', pwOpen: 'Mật khẩu (để trống nếu mạng mở)',
  warn: 'Chuyển mạng có thể làm mất kết nối dashboard tối đa một phút. Nếu sau 60 giây mạng mới không có Internet, stick sẽ tự quay lại mạng hiện tại.',
  hsWarn: 'Wi-Fi đang phát hotspot của stick (chế độ Travel). Chuyển sang chế độ Home để quét hoặc kết nối mạng.',
  prio: 'Ưu tiên', auto: 'Tự kết nối', on: 'bật', off: 'tắt', edit: 'Sửa', save: 'Lưu', forget: 'Quên',
  forgetQ: 'Quên mạng này? Mật khẩu đã lưu sẽ bị xoá.',
  forgetActive: 'Đây là mạng đang dùng. Quên mạng sẽ ngắt Wi-Fi; chỉ được phép khi 4G hoặc USB đang cấp Internet.',
  confirmForget: 'Đồng ý quên', last: 'dùng lần cuối', never: 'chưa bao giờ', active: 'đang dùng',
  prioHint: 'Mạng ưu tiên cao hơn được chọn khi có nhiều mạng đã lưu trong vùng phủ (−999…999).',
  sw: {connecting: 'Đang kết nối…', checking: 'Đang kiểm tra Internet…', ok: 'Đã kết nối', 'rolled-back': 'Đã quay lại mạng cũ'},
  unavailable: 'Máy này không điều khiển được Wi-Fi.'},
 zh: {title: 'Wi-Fi 网络', notConn: '未连接', hsMode: '热点模式', switching: '正在切换到',
  desc: '设备作为客户端加入的网络。远程访问（Tailscale）通常经由此 Wi-Fi。',
  current: '当前网络', signal: '信号', scan: '扫描', scanning: '正在扫描…', other: '加入其他网络',
  nets: '附近的网络', hiddenN: n => `${n} 个隐藏网络 — 请用“加入其他网络”`,
  none: '未找到网络', saved: '已保存的网络', noSaved: '没有已保存的网络', connected: '已连接', savedTag: '已保存',
  open: '开放', ent: '企业级 — 不支持', aps: '个接入点', ch: '信道',
  connect: '连接', cancel: '取消', pw: '密码', pwSaved: '密码（留空则使用已保存的密码）',
  ssid: '网络名称（SSID）', hidden: '隐藏网络', pwOpen: '密码（开放网络留空）',
  warn: '切换网络可能使本控制台断开最多一分钟。如果 60 秒后新网络无法上网，设备会自动切回当前网络。',
  hsWarn: 'Wi-Fi 正在运行设备热点（Travel 模式）。请切换到 Home 模式后再扫描或加入网络。',
  prio: '优先级', auto: '自动连接', on: '开', off: '关', edit: '编辑', save: '保存', forget: '忘记',
  forgetQ: '忘记此网络？已保存的密码将被删除。',
  forgetActive: '这是正在使用的网络。忘记后 Wi-Fi 将断开；仅在 4G 或 USB 提供网络时允许。',
  confirmForget: '确认忘记', last: '上次使用', never: '从未', active: '使用中',
  prioHint: '多个已保存网络都在范围内时，优先级高者优先（−999…999）。',
  sw: {connecting: '正在连接…', checking: '正在检测网络…', ok: '已连接', 'rolled-back': '已回退'},
  unavailable: '此主机无法控制 Wi-Fi。'},
};
const tx = k => (T[UZ.lang] || T.en)[k] ?? T.en[k];
const E = s => UZ.esc(String(s ?? ''));
const W = S => (S && S.settings && S.settings.wifi) || {};

function bars(sig) {
  const lv = sig >= 75 ? 4 : sig >= 50 ? 3 : sig >= 30 ? 2 : sig > 0 ? 1 : 0;
  return `<svg viewBox="0 0 24 24" width="20" height="20" fill="currentColor" aria-label="${E(sig)}%">${[0, 1, 2, 3].map(i =>
    `<rect x="${3 + i * 5}" y="${17 - i * 4}" width="3.5" height="${4 + i * 4}" rx="1" opacity="${i < lv ? 1 : .25}"/>`).join('')}</svg>`;
}
const lock = () => UZ.svg('lock').replace('<svg', '<svg width="13" height="13" style="vertical-align:-1px;margin-right:3px"');
const date = ts => ts ? new Date(ts * 1000).toLocaleDateString(UZ.lang === 'zh' ? 'zh-CN' : UZ.lang) : tx('never');
const warnBox = txt => `<p class="desc" style="margin:4px 0 12px;color:var(--orange)">${E(txt)}</p>`;

UZ.register({
  id: 'wifi', order: 20, color: 'green', icon: 'wifi',
  title: {en: T.en.title, vi: T.vi.title, zh: T.zh.title},
  sub: S => {
    const w = W(S), n = (S && S.net) || {};
    if (w.switch && (w.switch.state === 'connecting' || w.switch.state === 'checking')) return `${tx('switching')} ${w.switch.ssid}`;
    if (w.mode === 'hotspot' || n.wifi_mode === 'ap') return tx('hsMode');
    return w.ssid || n.ssid || tx('notConn');
  },
  open(S) {
    const st = {nets: null, hidden: 0, saved: [], openNet: -1, edit: -1, forget: -1, scanning: false};
    const w = W(S), n = (S && S.net) || {};
    const hs = w.mode === 'hotspot' || n.wifi_mode === 'ap';
    const ssid = w.ssid || n.ssid || '', sigl = w.signal || n.wifi_signal || '';

    function currentCard() {
      const sw = w.switch, swl = sw ? (tx('sw')[sw.state] || sw.state) : '';
      return `<div class="stat"><div class="l">${E(tx('current'))}</div><div class="n">${hs
        ? `<span class="dot warn"></span>${E(tx('hsMode'))}${ssid ? `<small>${E(ssid)}</small>` : ''}`
        : ssid ? `<span class="dot ok"></span>${E(ssid)}${sigl ? `<small>${E(tx('signal'))} ${E(sigl)}%</small>` : ''}`
        : `<span class="dot"></span>${E(tx('notConn'))}`}</div>${sw ? `<div style="margin-top:6px;color:var(--dim);font-size:14px">${E(swl)} · ${E(sw.ssid)}${sw.msg ? ' — ' + E(sw.msg) : ''}</div>` : ''}</div>`;
    }

    function netItem(x, i) {
      const tags = [x.connected ? tx('connected') : x.saved ? tx('savedTag') : '',
        x.kind === 'open' || x.kind === 'owe' ? tx('open') : x.kind === 'enterprise' ? tx('ent') : x.security,
        `${tx('ch')} ${x.chan}`, x.aps > 1 ? `${x.aps} ${tx('aps')}` : ''].filter(Boolean);
      const secured = x.kind !== 'open' && x.kind !== 'owe';
      const btn = x.connected || x.kind === 'enterprise' ? '<span></span>'
        : `<button class="btn sm" data-focus data-w="pick" data-i="${i}">${E(tx('connect'))}</button>`;
      let form = '';
      if (st.openNet === i) {
        const needPw = secured && !x.saved;
        form = `<form class="wf-join" data-i="${i}" autocomplete="off" style="grid-column:1/-1">
          ${secured ? `<input class="field" name="pw" type="password" autocomplete="new-password" placeholder="${E(x.saved ? tx('pwSaved') : tx('pw'))}" ${needPw ? 'required minlength="8"' : ''} maxlength="64">` : ''}
          ${warnBox(tx('warn'))}
          <div class="actions" style="margin-top:0"><button class="btn primary sm" data-focus type="submit">${E(tx('connect'))}</button><button class="btn sm" data-focus type="button" data-w="unpick">${E(tx('cancel'))}</button></div></form>`;
      }
      return `<div class="item"><div class="ic">${bars(x.signal)}</div><div><b>${secured ? lock() : ''}${E(x.ssid)}</b><small>${tags.map(E).join(' · ')} · ${E(x.signal)}%</small></div>${btn}${form}</div>`;
    }

    function savedItem(p, i) {
      const meta = [p.active ? tx('active') : '', `${tx('prio')} ${p.priority}`, `${tx('auto')} ${p.autoconnect ? tx('on') : tx('off')}`,
        `${tx('last')} ${date(p.last)}`].filter(Boolean);
      let extra = '';
      if (st.edit === i) {
        extra = `<form class="wf-prio" data-i="${i}" style="grid-column:1/-1">
          <input class="field" name="prio" type="number" min="-999" max="999" step="1" value="${E(p.priority)}" aria-label="${E(tx('prio'))}">
          <label style="display:flex;gap:10px;align-items:center;margin-bottom:8px"><input type="checkbox" name="auto" data-focus ${p.autoconnect ? 'checked' : ''}> ${E(tx('auto'))}</label>
          <p class="desc" style="margin:0 0 8px">${E(tx('prioHint'))}</p>
          <div class="actions" style="margin-top:0"><button class="btn primary sm" data-focus type="submit">${E(tx('save'))}</button><button class="btn sm" data-focus type="button" data-w="noedit">${E(tx('cancel'))}</button></div></form>`;
      } else if (st.forget === i) {
        extra = `<div style="grid-column:1/-1">${warnBox(p.active ? tx('forgetActive') : tx('forgetQ'))}
          <div class="actions" style="margin-top:0"><button class="btn red sm" data-focus data-w="forget-yes" data-i="${i}">${E(tx('confirmForget'))}</button><button class="btn sm" data-focus data-w="noforget">${E(tx('cancel'))}</button></div></div>`;
      }
      return `<div class="item"><div class="ic">${UZ.svg(p.active ? 'check' : 'wifi')}</div><div><b>${p.secured ? lock() : ''}${E(p.name)}</b>${p.ssid && p.ssid !== p.name ? `<small>SSID ${E(p.ssid)}</small>` : ''}<small>${meta.map(E).join(' · ')}</small></div>
        <div style="display:flex;gap:8px"><button class="btn sm" data-focus data-w="edit" data-i="${i}">${E(tx('edit'))}</button><button class="btn sm red" data-focus data-w="forget" data-i="${i}">${E(tx('forget'))}</button></div>${extra}</div>`;
    }

    function otherForm() {
      return `<form id="wf-other" autocomplete="off" hidden style="margin-top:14px">
        <input class="field" name="ssid" placeholder="${E(tx('ssid'))}" maxlength="32" required autocomplete="off">
        <input class="field" name="pw" type="password" placeholder="${E(tx('pwOpen'))}" maxlength="64" autocomplete="new-password">
        <label style="display:flex;gap:10px;align-items:center;margin-bottom:8px"><input type="checkbox" name="hid" data-focus checked> ${E(tx('hidden'))}</label>
        ${warnBox(tx('warn'))}
        <div class="actions" style="margin-top:0"><button class="btn primary sm" data-focus type="submit">${E(tx('connect'))}</button><button class="btn sm" data-focus type="button" data-w="noother">${E(tx('cancel'))}</button></div></form>`;
    }

    function draw() {
      const sc = UZ.$('#wf-scan'), sv = UZ.$('#wf-saved');
      if (sc) sc.innerHTML = st.nets === null ? '' : `<h3 style="margin:22px 0 10px">${E(tx('nets'))}</h3><div class="list">${
        st.nets.map(netItem).join('') || `<div class="empty">${E(tx('none'))}</div>`}</div>${st.hidden ? `<p class="desc" style="margin-top:10px">${E(tx('hiddenN')(st.hidden))}</p>` : ''}`;
      if (sv) sv.innerHTML = `<h3 style="margin:22px 0 10px">${E(tx('saved'))}</h3><div class="list">${
        st.saved.map(savedItem).join('') || `<div class="empty">${E(tx('noSaved'))}</div>`}</div>`;
    }

    async function loadSaved() {
      const r = await UZ.post('wifi-saved', {});
      if (r.error) { UZ.toast(r.error); return; }
      st.saved = r.saved || []; draw();
    }

    async function doConnect(body, btn) {
      if (btn) btn.disabled = true;
      const r = await UZ.post('wifi-connect', body).catch(e => ({error: String(e)}));
      UZ.toast(r.error || r.out);
      if (btn) btn.disabled = false;
      if (!r.error) { UZ.closeSheet(); setTimeout(UZ.reload, 1500); }
    }

    const avail = w.available !== false;
    UZ.openSheet('green', 'wifi', E(tx('title')), E(tx('desc')), `<div id="wf-root">${currentCard()}
      ${!avail ? warnBox(tx('unavailable')) : hs ? warnBox(tx('hsWarn')) : ''}
      <div class="actions"><button class="btn primary" data-focus data-w="scan" ${hs ? 'disabled' : ''}>${E(tx('scan'))}</button><button class="btn" data-focus data-w="other" ${hs ? 'disabled' : ''}>${E(tx('other'))}</button>${UZ.closeBtn()}</div>
      ${otherForm()}<div id="wf-scan"></div><div id="wf-saved"></div></div>`);
    const root = UZ.$('#wf-root');

    root.addEventListener('click', async e => {
      const b = e.target.closest('[data-w]'); if (!b) return;
      const i = +b.dataset.i, a = b.dataset.w;
      if (a === 'scan') {
        if (st.scanning) return; st.scanning = true; b.disabled = true; b.textContent = tx('scanning');
        const r = await UZ.post('wifi-scan', {}).catch(x => ({error: String(x)}));
        st.scanning = false; b.disabled = false; b.textContent = tx('scan');
        if (r.error) { UZ.toast(r.error); return; }
        st.nets = r.networks || []; st.hidden = r.hidden || 0; st.openNet = -1; draw();
      } else if (a === 'other') { const f = UZ.$('#wf-other'); f.hidden = false; f.querySelector('[name=ssid]').focus(); }
      else if (a === 'noother') UZ.$('#wf-other').hidden = true;
      else if (a === 'pick') { st.openNet = i; draw(); UZ.$(`.wf-join[data-i="${i}"] input,.wf-join[data-i="${i}"] button`)?.focus(); }
      else if (a === 'unpick') { st.openNet = -1; draw(); }
      else if (a === 'edit') { st.edit = i; st.forget = -1; draw(); }
      else if (a === 'noedit') { st.edit = -1; draw(); }
      else if (a === 'forget') { st.forget = i; st.edit = -1; draw(); }
      else if (a === 'noforget') { st.forget = -1; draw(); }
      else if (a === 'forget-yes') {
        const p = st.saved[i]; if (!p) return; b.disabled = true;
        const r = await UZ.post('wifi-forget', {name: p.uuid, force: !!p.active}).catch(x => ({error: String(x)}));
        UZ.toast(r.error || r.out); st.forget = -1;
        if (!r.error) await loadSaved(); else draw();
      }
    });

    root.addEventListener('submit', async e => {
      e.preventDefault();
      const f = e.target, btn = f.querySelector('[type=submit]');
      if (f.id === 'wf-other') {
        const body = {ssid: f.ssid.value, hidden: f.hid.checked};
        if (f.pw.value) body.password = f.pw.value;
        await doConnect(body, btn);
      } else if (f.classList.contains('wf-join')) {
        const x = st.nets[+f.dataset.i]; if (!x) return;
        const body = {ssid: x.ssid}; const pw = f.querySelector('[name=pw]');
        if (pw && pw.value) body.password = pw.value;
        await doConnect(body, btn);
      } else if (f.classList.contains('wf-prio')) {
        const p = st.saved[+f.dataset.i]; if (!p) return;
        const prio = parseInt(f.prio.value, 10);
        btn.disabled = true;
        const r = await UZ.post('wifi-priority', {name: p.uuid, priority: Number.isFinite(prio) ? prio : 0, autoconnect: f.auto.checked})
          .catch(x => ({error: String(x)}));
        btn.disabled = false; UZ.toast(r.error || r.out);
        if (!r.error) { st.edit = -1; await loadSaved(); }
      }
    });

    draw();
    if (avail) loadSaved();
  },
});
})();
