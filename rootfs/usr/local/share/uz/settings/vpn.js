/* VPN (Travel): sing-box config for sing-box-uz (vpn.py). Secrets never come back from the server. */
(() => {
const T = {
  en: {title: 'VPN (Travel)', desc: 'In Travel mode all hotspot and stick traffic goes through sing-box (VLESS + Reality). Tailscale stays outside the tunnel.',
       notInst: 'Not installed', on: 'On', off: 'Off', ready: 'Ready', noConf: 'No config',
       engine: 'sing-box', service: 'Service', mode: 'Mode', home: 'Home', travel: 'Travel',
       instTitle: 'sing-box is not installed', instDeb: 'Debian: add the official SagerNet apt repository, then install (run over SSH):',
       instGh: 'Or download the official .deb for {arch} from github.com/SagerNet/sing-box/releases and run: sudo apt install ./sing-box_*_linux_{arch}.deb',
       instApk: 'postmarketOS / Alpine:', instBtn: 'Install sing-box {v}', instLog: 'Install log',
       unitPath: 'The service runs /usr/bin/sing-box — this binary lives elsewhere, link or reinstall it there.',
       server: 'Server', port: 'Port', sni: 'SNI', transport: 'Transport', security: 'Security', flow: 'Flow',
       placeholder: 'The config still contains CHANGE_ME placeholders.', invalid: 'The config file is not valid JSON.',
       start: 'Turn on', stop: 'Turn off', test: 'Test', testing: 'Testing…', viaVpn: 'Through VPN', direct: 'Direct', sameIp: 'Same public IP — traffic is NOT going through the VPN.',
       onlyTravel: 'Only Travel mode uses the VPN; switching to Home stops it.',
       imp: 'Import', impPh: 'Paste a vless://… share link or a full sing-box JSON config', impHint: 'The link / config is stored on the stick (root-only) and never shown again.',
       remove: 'Remove config', confirmRm: 'Really remove?', cancel: 'Cancel', notes: 'Adjusted'},
  vi: {title: 'VPN (Du lịch)', desc: 'Ở chế độ Du lịch, toàn bộ lưu lượng điểm phát và của thiết bị đi qua sing-box (VLESS + Reality). Tailscale nằm ngoài đường hầm.',
       notInst: 'Chưa cài', on: 'Bật', off: 'Tắt', ready: 'Sẵn sàng', noConf: 'Chưa có cấu hình',
       engine: 'sing-box', service: 'Dịch vụ', mode: 'Chế độ', home: 'Ở nhà', travel: 'Du lịch',
       instTitle: 'Chưa cài sing-box', instDeb: 'Debian: thêm kho apt chính thức của SagerNet rồi cài (chạy qua SSH):',
       instGh: 'Hoặc tải file .deb chính thức cho {arch} từ github.com/SagerNet/sing-box/releases rồi chạy: sudo apt install ./sing-box_*_linux_{arch}.deb',
       instApk: 'postmarketOS / Alpine:', instBtn: 'Cài sing-box {v}', instLog: 'Nhật ký cài đặt',
       unitPath: 'Dịch vụ chạy /usr/bin/sing-box — bản cài này nằm chỗ khác, hãy tạo liên kết hoặc cài lại vào đó.',
       server: 'Máy chủ', port: 'Cổng', sni: 'SNI', transport: 'Giao thức truyền', security: 'Bảo mật', flow: 'Flow',
       placeholder: 'Cấu hình vẫn còn chỗ CHANGE_ME chưa điền.', invalid: 'Tệp cấu hình không phải JSON hợp lệ.',
       start: 'Bật', stop: 'Tắt', test: 'Kiểm tra', testing: 'Đang kiểm tra…', viaVpn: 'Qua VPN', direct: 'Trực tiếp', sameIp: 'Cùng IP công khai — lưu lượng KHÔNG đi qua VPN.',
       onlyTravel: 'Chỉ chế độ Du lịch dùng VPN; chuyển sang Ở nhà sẽ tắt nó.',
       imp: 'Nhập', impPh: 'Dán liên kết vless://… hoặc toàn bộ cấu hình JSON của sing-box', impHint: 'Liên kết / cấu hình được lưu trên thiết bị (chỉ root đọc được) và không hiển thị lại.',
       remove: 'Xoá cấu hình', confirmRm: 'Chắc chắn xoá?', cancel: 'Huỷ', notes: 'Đã điều chỉnh'},
  zh: {title: 'VPN（旅行）', desc: '旅行模式下，热点和设备的全部流量经 sing-box（VLESS + Reality）转发。Tailscale 不经过隧道。',
       notInst: '未安装', on: '开', off: '关', ready: '就绪', noConf: '无配置',
       engine: 'sing-box', service: '服务', mode: '模式', home: '家庭', travel: '旅行',
       instTitle: '未安装 sing-box', instDeb: 'Debian：添加 SagerNet 官方 apt 软件源后安装（通过 SSH 运行）：',
       instGh: '或从 github.com/SagerNet/sing-box/releases 下载 {arch} 的官方 .deb，然后运行：sudo apt install ./sing-box_*_linux_{arch}.deb',
       instApk: 'postmarketOS / Alpine：', instBtn: '安装 sing-box {v}', instLog: '安装日志',
       unitPath: '服务运行 /usr/bin/sing-box——此程序位于其他位置，请链接或重新安装到该路径。',
       server: '服务器', port: '端口', sni: 'SNI', transport: '传输', security: '安全', flow: 'Flow',
       placeholder: '配置中仍有 CHANGE_ME 占位符。', invalid: '配置文件不是有效的 JSON。',
       start: '开启', stop: '关闭', test: '测试', testing: '测试中…', viaVpn: '经 VPN', direct: '直连', sameIp: '公网 IP 相同——流量没有经过 VPN。',
       onlyTravel: '只有旅行模式使用 VPN；切换到家庭模式会停止它。',
       imp: '导入', impPh: '粘贴 vless://… 分享链接或完整的 sing-box JSON 配置', impHint: '链接/配置保存在设备上（仅 root 可读），不会再次显示。',
       remove: '删除配置', confirmRm: '确定删除？', cancel: '取消', notes: '已调整'},
};
const tr = (k, v = {}) => String((T[UZ.lang] || T.en)[k] ?? T.en[k]).replace(/\{(\w+)\}/g, (_, x) => v[x] ?? '');
const e = UZ.esc;
const ICON = '<path d="M12 3l8 3v6c0 5-3.5 8-8 9-4.5-1-8-4-8-9V6z"/><rect x="9" y="11" width="6" height="5" rx="1"/><path d="M10 11V9.5a2 2 0 0 1 4 0V11"/>';
const PRE = 'style="white-space:pre-wrap;overflow-wrap:anywhere;font:13px/1.5 ui-monospace,Menlo,monospace;background:var(--glass);border-radius:14px;padding:12px 14px;margin:8px 0 12px;user-select:all"';
const DEB = `sudo mkdir -p /etc/apt/keyrings
sudo curl -fsSL https://sing-box.app/gpg.key -o /etc/apt/keyrings/sagernet.asc
sudo chmod a+r /etc/apt/keyrings/sagernet.asc
printf 'Types: deb\\nURIs: https://deb.sagernet.org/\\nSuites: *\\nComponents: *\\nEnabled: yes\\nSigned-By: /etc/apt/keyrings/sagernet.asc\\n' | sudo tee /etc/apt/sources.list.d/sagernet.sources
sudo apt-get update && sudo apt-get install sing-box`;
let D = null, notes = [], testRes = null, rmStep = false;

const dot = s => `<span class="dot ${s === 'active' ? 'ok' : s === 'failed' ? 'bad' : ''}"></span>`;

function installHtml(i) {
  const pm = /postmarket|alpine/.test(i.os || '');
  const arch = i.arch || 'arm64';
  return `<div class="stat" style="margin-bottom:14px"><div class="l">${e(tr('instTitle'))}</div>
    ${pm ? `<p>${e(tr('instApk'))}</p><pre ${PRE}>sudo apk add sing-box</pre>` : `<p>${e(tr('instDeb'))}</p><pre ${PRE}>${e(DEB)}</pre>
    <p style="color:var(--dim)">${e(tr('instGh', {arch}))}</p>`}
    ${i.candidate ? `<div class="actions" style="margin-top:8px"><button class="btn primary" data-focus id="vpn-inst">${e(tr('instBtn', {v: i.candidate}))}</button></div>` : ''}
    ${i.log?.length ? `<p style="color:var(--faint);margin-bottom:0">${e(tr('instLog'))}:</p><pre ${PRE}>${e(i.log.join('\n'))}</pre>` : ''}</div>`;
}

function summaryHtml(s) {
  const m = s?.main;
  if (!m) return '';
  const rows = [['server', m.server], ['port', m.port], ['sni', m.sni], ['transport', m.transport],
                ['security', m.reality ? 'Reality' : m.sni ? 'TLS' : '—'], ['flow', m.flow]].filter(([, v]) => v != null && v !== '');
  return `<div class="stat" style="margin-bottom:14px"><div class="l">${e(m.type || '')}${m.tag ? ' · ' + e(m.tag) : ''}</div>
    <div class="kv" style="margin-top:10px">${rows.map(([k, v]) => `<span>${e(tr(k))}</span><span style="overflow-wrap:anywhere">${e(v)}</span>`).join('')}</div>
    ${s.placeholder ? `<p style="color:#ff9f0a;margin-bottom:0">${e(tr('placeholder'))}</p>` : ''}</div>`;
}

function render() {
  const d = D, running = d.service === 'active' || d.tun;
  const status = `<div class="kv" style="margin-bottom:16px">
    <span>${e(tr('engine'))}</span><span>${d.installed ? e(d.version || '?') : e(tr('notInst'))}</span>
    <span>${e(tr('service'))}</span><span>${dot(d.service)}${e(d.service)}</span>
    <span>${e(tr('mode'))}</span><span>${e(tr(d.travel ? 'travel' : 'home'))}</span></div>`;
  const ctl = d.installed && d.configured ? `<div class="actions" style="margin-top:0">
    <button class="btn ${running ? '' : 'primary'}" data-focus id="vpn-toggle">${e(tr(running ? 'stop' : 'start'))}</button>
    <button class="btn" data-focus id="vpn-test" ${running ? '' : 'disabled'}>${e(tr('test'))}</button></div>
    ${d.travel ? '' : `<p style="color:var(--faint)">${e(tr('onlyTravel'))}</p>`}` : '';
  const tres = testRes ? `<div class="kv" style="margin-top:14px">
    <span>${e(tr('viaVpn'))}</span><span>${testRes.vpn ? e(testRes.vpn.ip + ' ' + testRes.vpn.loc) : '—'}</span>
    <span>${e(tr('direct'))}</span><span>${testRes.direct ? e(testRes.direct.ip + ' ' + testRes.direct.loc) : '—'}</span></div>
    ${testRes.same ? `<p style="color:#ff6961">${e(tr('sameIp'))}</p>` : ''}` : '';
  const nt = notes.length ? `<div class="stat" style="margin-bottom:14px"><div class="l">${e(tr('notes'))}</div>${notes.map(n => `<p style="margin:6px 0 0">${e(n)}</p>`).join('')}</div>` : '';
  const rm = d.configured ? (rmStep
    ? `<button class="btn red" data-focus id="vpn-rm-yes">${e(tr('confirmRm'))}</button><button class="btn" data-focus id="vpn-rm-no">${e(tr('cancel'))}</button>`
    : `<button class="btn red" data-focus id="vpn-rm">${e(tr('remove'))}</button>`) : '';
  UZ.openSheet('purple', 'lock', e(tr('title')), e(tr('desc')),
    `${status}${d.install ? installHtml(d.install) : ''}${d.installed && !d.unit_path_ok ? `<p style="color:#ff9f0a">${e(tr('unitPath'))}</p>` : ''}
     ${d.config_valid === false ? `<p style="color:#ff6961">${e(tr('invalid'))}</p>` : ''}${summaryHtml(d.summary)}${nt}${ctl}${tres}
     <form id="vpn-imp" autocomplete="off" style="margin-top:20px">
       <textarea class="field" id="vpn-txt" rows="4" spellcheck="false" autocapitalize="off" autocomplete="off" placeholder="${e(tr('impPh'))}" style="font:14px/1.4 ui-monospace,Menlo,monospace"></textarea>
       <small style="color:var(--faint)">${e(tr('impHint'))}</small>
       <div class="actions"><button class="btn primary" data-focus type="submit">${e(tr('imp'))}</button>${rm}${UZ.closeBtn()}</div></form>`);
  bind();
}

const later = (ms, f) => setTimeout(() => { if (UZ.$('#vpn-imp')) f(); }, ms);   // only while our sheet is open

async function refresh() {
  const d = await UZ.post('vpn-get', {});
  if (d.error) { UZ.toast(d.error); return false; }
  D = d; render(); return true;
}

function bind() {
  const $ = UZ.$;
  $('#vpn-imp').onsubmit = async ev => {
    ev.preventDefault();
    const ta = $('#vpn-txt'), v = ta.value.trim();
    if (!v) return;
    const body = /^vless:\/\//i.test(v) ? {link: v} : {config: v};
    ta.value = '';                     // never keep the secret in the page
    const r = await UZ.post('vpn-import', body);
    UZ.toast(r.error || r.out);
    if (r.error) return;
    notes = r.notes || []; testRes = null; rmStep = false;
    later(300, refresh);
  };
  const inst = $('#vpn-inst');
  if (inst) inst.onclick = async () => { inst.disabled = true; const r = await UZ.post('vpn-install', {}); UZ.toast(r.error || r.out); later(1500, refresh); };
  const tg = $('#vpn-toggle');
  if (tg) tg.onclick = async () => {
    tg.disabled = true;
    const on = !(D.service === 'active' || D.tun);
    const r = await UZ.post('vpn-enable', {on});
    UZ.toast(r.error || r.out); testRes = null;
    later(3000, async () => { await refresh(); UZ.reload(); });
  };
  const tb = $('#vpn-test');
  if (tb) tb.onclick = async () => {
    tb.disabled = true; tb.textContent = tr('testing');
    const r = await UZ.post('vpn-test', {});
    if (r.error) UZ.toast(r.error);
    testRes = r.vpn || r.direct ? r : null;
    render();
  };
  const rm = $('#vpn-rm'), yes = $('#vpn-rm-yes'), no = $('#vpn-rm-no');
  if (rm) rm.onclick = () => { rmStep = true; render(); };
  if (no) no.onclick = () => { rmStep = false; render(); };
  if (yes) yes.onclick = async () => {
    yes.disabled = true;
    const r = await UZ.post('vpn-remove', {confirm: true});
    UZ.toast(r.error || r.out); rmStep = false; notes = []; testRes = null;
    await refresh(); UZ.reload();
  };
}

UZ.register({
  id: 'vpn', order: 60, color: 'purple', iconSvg: ICON,
  title: {en: T.en.title, vi: T.vi.title, zh: T.zh.title},
  sub: S => {
    const v = S?.settings?.vpn;
    if (!v) return '';
    if (!v.installed) return tr('notInst');
    if (!v.configured) return tr('noConf');
    return v.active ? tr('on') : tr('ready');
  },
  async open() { notes = []; testRes = null; rmStep = false; await refresh(); },
});
})();
