/* Hotspot (advanced): channel, hidden SSID, connected clients — actions hotspot-adv-get / hotspot-adv-set */
(() => {
  const T = {
    en: {title: 'Hotspot', desc: 'Travel-mode hotspot: network name, password and join QR, plus 2.4 GHz channel and visibility.',
      channel: 'Channel', auto: 'Auto', chHelp: '1, 6 and 11 don’t overlap. 12–13 are not allowed in some countries (e.g. the US) — the hotspot may fail to start there.',
      hidden: 'Hide network name', hiddenD: 'Phones won’t list it; join by typing the name. The QR code may not work for hidden networks on every phone.',
      on: 'On', off: 'Off', security: 'Security', band: 'Band', clients: 'Connected devices', noClients: 'No devices connected.',
      notActive: 'The hotspot is off (Home mode) — devices appear here in Travel mode.',
      noProfile: 'The hotspot hasn’t been created yet. Your choice is saved and applies when Travel mode first creates it.',
      restart: 'Saving restarts the hotspot: devices (maybe this one) disconnect for a few seconds.',
      save: 'Save', online: 'online', stale: 'idle', unknown: 'name unknown',
      sub: n => n === 1 ? '1 device' : n + ' devices', subOff: 'Off', subCh: 'channel'},
    vi: {title: 'Hotspot', desc: 'Hotspot ở chế độ Travel: tên mạng, mật khẩu, mã QR, kênh 2.4 GHz và chế độ ẩn.',
      channel: 'Kênh', auto: 'Tự động', chHelp: 'Kênh 1, 6 và 11 không chồng lấn nhau. Kênh 12–13 bị cấm ở một số nước (vd Mỹ) — ở đó hotspot có thể không lên.',
      hidden: 'Ẩn tên mạng', hiddenD: 'Điện thoại sẽ không thấy mạng trong danh sách; phải gõ tên để kết nối. Mã QR có thể không dùng được với mạng ẩn trên một số máy.',
      on: 'Bật', off: 'Tắt', security: 'Bảo mật', band: 'Băng tần', clients: 'Thiết bị đang kết nối', noClients: 'Chưa có thiết bị nào kết nối.',
      notActive: 'Hotspot đang tắt (chế độ Home) — thiết bị sẽ hiện ở đây khi ở chế độ Travel.',
      noProfile: 'Hotspot chưa được tạo. Lựa chọn được lưu lại và áp dụng khi chế độ Travel tạo hotspot lần đầu.',
      restart: 'Lưu sẽ khởi động lại hotspot: các thiết bị (có thể cả máy này) mất kết nối vài giây.',
      save: 'Lưu', online: 'đang online', stale: 'đang nghỉ', unknown: 'không rõ tên',
      sub: n => n + ' thiết bị', subOff: 'Tắt', subCh: 'kênh'},
    zh: {title: '热点', desc: 'Travel 模式热点：网络名称、密码和加入二维码，以及 2.4 GHz 信道和可见性。',
      channel: '信道', auto: '自动', chHelp: '1、6、11 信道互不重叠。12–13 信道在部分国家（如美国）不允许使用——在那里热点可能无法启动。',
      hidden: '隐藏网络名称', hiddenD: '手机不会在列表中显示此网络，需要手动输入名称连接。部分手机扫码可能无法连接隐藏网络。',
      on: '开启', off: '关闭', security: '安全', band: '频段', clients: '已连接设备', noClients: '暂无设备连接。',
      notActive: '热点已关闭（Home 模式）——切换到 Travel 模式后设备会显示在这里。',
      noProfile: '热点尚未创建。你的选择已保存，将在 Travel 模式首次创建热点时生效。',
      restart: '保存会重启热点：设备（可能包括本设备）会断开几秒钟。',
      save: '保存', online: '在线', stale: '空闲', unknown: '名称未知',
      sub: n => n + ' 台设备', subOff: '关闭', subCh: '信道'},
  };
  const L = () => T[UZ.lang] || T.en;
  const t = k => L()[k] ?? T.en[k];
  const ICON = '<circle cx="12" cy="12" r="2"/><path d="M8.5 15.5a5 5 0 0 1 0-7M15.5 8.5a5 5 0 0 1 0 7M5.6 18.4a9 9 0 0 1 0-12.8M18.4 5.6a9 9 0 0 1 0 12.8"/>';
  const DEV = '<rect x="7" y="3" width="10" height="18" rx="2"/><path d="M11 18h2"/>';
  const KM = {'wpa-psk': 'WPA2-Personal', sae: 'WPA3-Personal', none: 'Open', '': 'WPA2-Personal'};

  let ch = 0, hid = false;
  function paint() {
    UZ.$('#hs-ch').innerHTML = Array.from({length: 14}, (_, n) =>
      `<button class="chip ${n === ch ? 'on' : ''}" data-focus data-hs-ch="${n}" style="${n >= 12 ? 'opacity:.7' : ''}">${n ? n : UZ.esc(t('auto'))}</button>`).join('');
    UZ.$('#hs-hid').innerHTML = [[false, 'off'], [true, 'on']].map(([v, k]) =>
      `<button class="chip ${v === hid ? 'on' : ''}" data-focus data-hs-hid="${v ? 1 : 0}">${UZ.esc(t(k))}</button>`).join('');
  }
  function clientsHtml(r) {
    if (!r.active) return `<p style="color:var(--faint);margin:0">${UZ.esc(t('notActive'))}</p>`;
    const cs = r.clients || [];
    if (!cs.length) return `<p style="color:var(--faint);margin:0">${UZ.esc(t('noClients'))}</p>`;
    return `<div class="list">${cs.map(c => `<div class="item"><div class="ic"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">${DEV}</svg></div>
      <div><b>${UZ.esc(c.hostname || t('unknown'))}</b><small>${UZ.esc(c.ip)} · ${UZ.esc(c.mac)}</small></div>
      <span style="font-size:14px;white-space:nowrap"><span class="dot ${c.online ? 'ok' : c.state === 'STALE' ? 'warn' : ''}"></span>${UZ.esc(c.online ? t('online') : c.state === 'STALE' ? t('stale') : '—')}</span></div>`).join('')}</div>`;
  }

  async function open() {
    let r;
    try { r = await UZ.post('hotspot-adv-get', {}); } catch (e) { UZ.toast(String(e)); return; }
    if (r.error) UZ.toast(r.error);
    const p = r.prefs || {};
    ch = r.profile ? (r.channel | 0) : (p.channel | 0); hid = r.profile ? !!r.hidden : !!p.hidden;
    const note = !r.profile && !r.error ? t('noProfile') : r.active ? t('restart') : '';
    UZ.openSheet('green', 'wifi', UZ.esc(t('title')), UZ.esc(t('desc')),
      `<div id="hs-root">
       <div class="actions" style="margin:0 0 18px"><button class="btn primary" data-focus data-core="psk">${UZ.esc(UZ.coreT('pskBtn'))}</button></div>
       <div class="kv" style="margin-bottom:18px"><span>${UZ.esc(t('band'))}</span><span>2.4 GHz</span>
         <span>${UZ.esc(t('security'))}</span><span>${UZ.esc(KM[r.key_mgmt || ''] || r.key_mgmt)}</span></div>
       <div class="stat" style="margin-bottom:12px"><div class="l">${UZ.esc(t('channel'))}</div><div class="chips" id="hs-ch" style="margin-top:10px"></div>
         <p style="color:var(--faint);font-size:13px;margin:10px 0 0">${UZ.esc(t('chHelp'))}</p></div>
       <div class="stat" style="margin-bottom:12px"><div class="l">${UZ.esc(t('hidden'))}</div><div class="chips" id="hs-hid" style="margin-top:10px"></div>
         <p style="color:var(--faint);font-size:13px;margin:10px 0 0">${UZ.esc(t('hiddenD'))}</p></div>
       ${note ? `<p style="color:var(--orange);margin:6px 0 0">${UZ.esc(note)}</p>` : ''}
       <div class="actions"><button class="btn primary" data-focus id="hs-save" ${r.error ? 'disabled' : ''}>${UZ.esc(t('save'))}</button>${UZ.closeBtn()}</div>
       <h3 style="margin:28px 0 12px;font-size:15px;color:var(--faint);text-transform:uppercase;letter-spacing:.04em">${UZ.esc(t('clients'))}${r.active ? ` · ${(r.clients || []).length}` : ''}</h3>
       ${clientsHtml(r)}</div>`);
    paint();
    UZ.$('#hs-root').addEventListener('click', e => {
      const c = e.target.closest('[data-hs-ch]'); if (c) { ch = +c.dataset.hsCh; paint(); return; }
      const h = e.target.closest('[data-hs-hid]'); if (h) { hid = h.dataset.hsHid === '1'; paint(); }
    });
    UZ.$('#hs-save').onclick = async () => {
      const b = UZ.$('#hs-save'); b.disabled = true;
      try {
        const x = await UZ.post('hotspot-adv-set', {channel: ch, hidden: hid, security: 'wpa2'});
        UZ.toast(x.error || x.out);
        if (!x.error) { UZ.closeSheet(); setTimeout(UZ.reload, x.restarting ? 6000 : 300); }
      } catch (e) { UZ.toast(String(e)); }
      b.disabled = false;
    };
  }

  UZ.register({
    id: 'hotspot', order: 25, color: 'green', iconSvg: ICON,
    title: {en: T.en.title, vi: T.vi.title, zh: T.zh.title},
    sub: S => {
      const s = S?.settings?.hotspot; if (!s) return '';
      if (S.hotspot) return L().sub(s.leases | 0);
      return `${t('subOff')} · ${t('subCh')} ${s.channel ? s.channel : t('auto')}`;
    },
    open,
  });
})();
