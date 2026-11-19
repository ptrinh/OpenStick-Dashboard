/* LED mapping: choose what red / green / blue show in `auto` mode (leds.py, /etc/uz/led-map.conf). */
(() => {
const T = {
  en: {title: 'LED mapping', desc: 'What each LED shows when it is set to Auto. Manual modes (on, off, blink…) on the main page still override this.',
       red: 'Red', green: 'Green', blue: 'Blue', now: 'now', manual: 'manual',
       src: {internet: 'Internet', wifi: 'Wi-Fi', lte: '4G', tailscale: 'Tailscale', usb: 'USB host', sms: 'Unread SMS', heartbeat: 'Heartbeat', off: 'Off'},
       hint: {internet: 'on when online, fast blink offline', wifi: 'link + traffic on wlan0', lte: 'link + traffic on 4G, slow blink while searching',
              tailscale: 'on while Tailscale is connected', usb: 'on while a computer is plugged in', sms: 'blinks until new SMS are marked seen',
              heartbeat: 'steady double pulse', off: 'always dark'},
       save: 'Save', reset: 'Defaults', seen: 'Mark SMS seen', unavailable: 'LED daemon not available on this host — the map can still be saved.'},
  vi: {title: 'Gán đèn LED', desc: 'Mỗi đèn hiển thị gì khi đặt ở chế độ Tự động. Chế độ thủ công (bật, tắt, nháy…) ở trang chính vẫn được ưu tiên.',
       red: 'Đỏ', green: 'Xanh lá', blue: 'Xanh dương', now: 'hiện tại', manual: 'thủ công',
       src: {internet: 'Internet', wifi: 'Wi-Fi', lte: '4G', tailscale: 'Tailscale', usb: 'Máy tính USB', sms: 'SMS chưa đọc', heartbeat: 'Nhịp tim', off: 'Tắt'},
       hint: {internet: 'sáng khi có mạng, nháy nhanh khi mất mạng', wifi: 'kết nối + lưu lượng wlan0', lte: 'kết nối + lưu lượng 4G, nháy chậm khi đang tìm sóng',
              tailscale: 'sáng khi Tailscale đã kết nối', usb: 'sáng khi đang cắm vào máy tính', sms: 'nháy tới khi SMS mới được đánh dấu đã xem',
              heartbeat: 'nhịp đập đôi đều đặn', off: 'luôn tắt'},
       save: 'Lưu', reset: 'Mặc định', seen: 'Đánh dấu SMS đã xem', unavailable: 'Không có dịch vụ LED trên máy này — vẫn lưu được cấu hình.'},
  zh: {title: 'LED 映射', desc: '设为“自动”时每个 LED 显示的内容。主页上的手动模式（亮、灭、闪烁…）仍然优先。',
       red: '红', green: '绿', blue: '蓝', now: '当前', manual: '手动',
       src: {internet: '互联网', wifi: 'Wi-Fi', lte: '4G', tailscale: 'Tailscale', usb: 'USB 主机', sms: '未读短信', heartbeat: '心跳', off: '关闭'},
       hint: {internet: '在线时常亮，离线时快闪', wifi: 'wlan0 连接 + 流量', lte: '4G 连接 + 流量，搜索信号时慢闪',
              tailscale: 'Tailscale 已连接时常亮', usb: '插入电脑时常亮', sms: '闪烁直到新短信标记为已读',
              heartbeat: '稳定的双脉冲', off: '始终熄灭'},
       save: '保存', reset: '默认', seen: '短信标为已读', unavailable: '此主机上没有 LED 服务——仍可保存映射。'},
};
const tr = k => (T[UZ.lang] || T.en)[k] ?? T.en[k];
const LEDS = ['red', 'green', 'blue'];
const SW = {red: '#ff453a', green: '#30d158', blue: '#0a84ff'};
let draft = null;

function render(d) {
  const src = tr('src'), hint = tr('hint');
  const rows = LEDS.map(l => {
    const st = d.state?.[l] || {};
    const now = st.mode && st.mode !== 'auto' ? `${tr('manual')}: ${UZ.esc(st.mode)}` : st.trigger ? `${tr('now')}: ${UZ.esc(st.trigger)}${st.on === '1' ? ' · on' : ''}` : '';
    return `<div style="margin-bottom:18px"><div style="display:flex;align-items:center;gap:10px;margin-bottom:10px">
      <span style="width:14px;height:14px;border-radius:50%;background:${SW[l]};box-shadow:0 0 10px ${SW[l]}"></span>
      <b>${UZ.esc(tr(l))}</b><small style="color:var(--faint)">${UZ.esc(hint[draft[l]] || '')}</small>
      <small style="margin-left:auto;color:var(--faint)">${now}</small></div>
      <div class="chips">${(d.sources || []).map(s => `<button class="chip ${draft[l] === s ? 'on' : ''}" data-focus data-led-src="${l}" data-v="${UZ.esc(s)}">${UZ.esc(src[s] || s)}</button>`).join('')}</div></div>`;
  }).join('');
  const sms = LEDS.some(l => draft[l] === 'sms') && d.sms_log;
  UZ.openSheet('yellow', 'bulb', UZ.esc(tr('title')), UZ.esc(tr('desc')) + (d.available ? '' : '<br><small>' + UZ.esc(tr('unavailable')) + '</small>'),
    `${rows}<div class="actions"><button class="btn primary" data-focus id="led-map-save">${UZ.esc(tr('save'))}</button>
     <button class="btn" data-focus id="led-map-reset">${UZ.esc(tr('reset'))}</button>
     ${sms ? `<button class="btn" data-focus id="led-sms-seen">${UZ.esc(tr('seen'))}</button>` : ''}${UZ.closeBtn()}</div>`);
  UZ.$$('[data-led-src]').forEach(b => b.onclick = () => { draft[b.dataset.ledSrc] = b.dataset.v; render(d); });
  UZ.$('#led-map-reset').onclick = () => { draft = {...(d.defaults || {red: 'internet', green: 'wifi', blue: 'lte'})}; render(d); };
  UZ.$('#led-map-save').onclick = async e => {
    e.target.disabled = true;
    const r = await UZ.post('leds-map-set', {red: draft.red, green: draft.green, blue: draft.blue});
    UZ.toast(r.error || r.out);
    if (r.error) { e.target.disabled = false; return; }
    UZ.closeSheet(); UZ.reload();
  };
  const sb = UZ.$('#led-sms-seen');
  if (sb) sb.onclick = async () => { const r = await UZ.post('leds-sms-seen', {}); UZ.toast(r.error || r.out); };
}

UZ.register({
  id: 'leds', order: 80, color: 'yellow', icon: 'bulb',
  title: {en: T.en.title, vi: T.vi.title, zh: T.zh.title},
  sub: S => { const m = S?.settings?.leds?.map; if (!m) return ''; const s = tr('src'); return LEDS.map(l => s[m[l]] || m[l]).join(' · '); },
  async open() {
    const d = await UZ.post('leds-get', {});
    if (d.error) return UZ.toast(d.error);
    draft = {...d.map};
    render(d);
  },
});
})();
