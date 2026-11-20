/* Data plan: billing-cycle start day + monthly cap for the 4G usage counter (usage.py, /etc/uz/usage.json).
   The usage chart itself lives on the Statistics tab (index.html). */
(() => {
const T = {
  en: {title: 'Data plan', desc: 'Billing cycle and monthly cap for the 4G usage counter. Notifications are sent at 80 % and 100 % of the cap (event “Data cap”).',
       day: 'Cycle starts on day', cap: 'Monthly cap (MB, 0 = none)', save: 'Save', reset: 'Clear history', sure: 'Clear all usage history?', yes: 'Yes, clear',
       none: 'no cap', used: 'used', unavailable: 'No ModemManager on this host — usage is not counted.'},
  vi: {title: 'Gói cước', desc: 'Chu kỳ tính cước và hạn mức tháng cho bộ đếm lưu lượng 4G. Thông báo được gửi khi dùng 80 % và 100 % hạn mức (sự kiện “Hạn mức dữ liệu”).',
       day: 'Chu kỳ bắt đầu ngày', cap: 'Hạn mức tháng (MB, 0 = không giới hạn)', save: 'Lưu', reset: 'Xoá lịch sử', sure: 'Xoá toàn bộ lịch sử lưu lượng?', yes: 'Xoá',
       none: 'không giới hạn', used: 'đã dùng', unavailable: 'Máy này không có ModemManager — không đếm lưu lượng.'},
  zh: {title: '流量套餐', desc: '4G 流量计数的计费周期和每月上限。达到上限的 80 % 和 100 % 时发送通知（事件“流量上限”）。',
       day: '周期开始日', cap: '每月上限（MB，0 = 无）', save: '保存', reset: '清除记录', sure: '清除全部流量记录？', yes: '确认清除',
       none: '无上限', used: '已用', unavailable: '此主机没有 ModemManager——不统计流量。'},
};
const tr = k => (T[UZ.lang] || T.en)[k] ?? T.en[k];
const fmt = b => b >= 1e9 ? (b / 1e9).toFixed(2) + ' GB' : (b / 1e6).toFixed(0) + ' MB';

async function open() {
  const d = await UZ.post('usage-get', {range: 'month'});
  if (d.error) { UZ.toast(d.error); return; }
  UZ.openSheet('teal', 'signal', UZ.esc(tr('title')), UZ.esc(tr('desc')) + (d.available ? '' : '<br><small>' + UZ.esc(tr('unavailable')) + '</small>'),
    `<form id="up-f" autocomplete="off">
      <label class="s">${UZ.esc(tr('day'))}</label><input class="field" id="up-day" type="number" min="1" max="28" step="1" value="${d.cycle_day}">
      <label class="s">${UZ.esc(tr('cap'))}</label><input class="field" id="up-cap" type="number" min="0" max="10000000" step="1" value="${d.cap_mb}">
      <div class="actions"><button class="btn primary" data-focus type="submit">${UZ.esc(tr('save'))}</button>
      <button class="btn" data-focus type="button" id="up-reset">${UZ.esc(tr('reset'))}</button>${UZ.closeBtn()}</div></form>
     <div id="up-confirm"></div>`);
  UZ.$('#up-f').onsubmit = async e => {
    e.preventDefault();
    const r = await UZ.post('usage-set', {cycle_day: parseInt(UZ.$('#up-day').value, 10), cap_mb: parseInt(UZ.$('#up-cap').value || '0', 10)});
    UZ.toast(r.error || r.out);
    if (!r.error) { UZ.closeSheet(); UZ.reload(); }
  };
  UZ.$('#up-reset').onclick = () => {
    UZ.$('#up-confirm').innerHTML = `<p>${UZ.esc(tr('sure'))}</p><div class="actions"><button class="btn red" data-focus id="up-yes">${UZ.esc(tr('yes'))}</button></div>`;
    UZ.$('#up-yes').onclick = async () => { const r = await UZ.post('usage-reset', {confirm: true}); UZ.toast(r.error || r.out); if (!r.error) { UZ.closeSheet(); UZ.reload(); } };
  };
}

UZ.register({
  id: 'usage', order: 25, color: 'teal', icon: 'signal',
  title: {en: 'Data plan', vi: 'Gói cước', zh: '流量套餐'},
  sub: S => {
    const u = S.settings?.usage || {};
    if (u.month_bytes == null) return '';
    return u.cap_mb ? `${fmt(u.month_bytes)} / ${fmt(u.cap_mb * 1e6)}` : `${fmt(u.month_bytes)} · ${tr('none')}`;
  },
  open,
});
})();
