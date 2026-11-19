/* SMS remote-control allow-list (/etc/uz/sms.allow) — actions smsallow-get / smsallow-set */
(() => {
  // uz-sms currently counts commands from non-listed numbers toward the 5-tries lockout.
  // Flip to false once uz-sms ignores them (see report / proposed uz-sms change).
  const FOREIGN_COUNTS = false;
  const NUM = /^\+?[0-9]{6,15}$/;
  const clean = s => String(s || '').replace(/[\s\-.()]/g, '');
  const T = {
    en: {title: 'SMS control', any: 'Any sender', n: n => n === 1 ? '1 number' : n + ' numbers',
      desc: 'Who may control the stick by SMS (“<PIN> command”).',
      empty: 'The list is empty: any phone that knows the PIN can send commands.',
      some: 'Only these numbers can send commands; texts from any other number are rejected and reported to Telegram. A number matches on its last 9 digits, so +84 912 345 678 and 0912 345 678 are the same.',
      lockYes: 'Rejected commands from other numbers still count toward the lockout (5 wrong tries per hour).',
      lockNo: 'Commands from other numbers are ignored and don’t count toward the lockout (5 wrong PINs per hour).',
      noPin: 'No SMS PIN is set yet, so SMS commands are off. Set one under “SMS PIN”.',
      ph: 'Phone number, e.g. +84912345678', add: 'Add number', save: 'Save', remove: 'Remove',
      bad: 'Check the highlighted numbers: optional +, then 6–15 digits.', max: 'At most 20 numbers.',
      ignored: 'Lines in the file that are not numbers (removed on save):', loading: 'Loading…'},
    vi: {title: 'Điều khiển SMS', any: 'Mọi số', n: n => n + ' số',
      desc: 'Những số được điều khiển stick bằng SMS (“<PIN> lệnh”).',
      empty: 'Danh sách trống: điện thoại nào biết PIN cũng gửi lệnh được.',
      some: 'Chỉ các số này được gửi lệnh; tin từ số khác bị từ chối và báo về Telegram. So khớp theo 9 chữ số cuối, nên +84 912 345 678 và 0912 345 678 là một.',
      lockYes: 'Lệnh bị từ chối từ số khác hiện vẫn tính vào giới hạn khoá (5 lần sai mỗi giờ).',
      lockNo: 'Lệnh từ số khác bị bỏ qua và không tính vào giới hạn khoá (5 lần sai PIN mỗi giờ).',
      noPin: 'Chưa đặt PIN SMS nên lệnh qua SMS đang tắt. Đặt PIN ở mục “PIN SMS”.',
      ph: 'Số điện thoại, vd +84912345678', add: 'Thêm số', save: 'Lưu', remove: 'Xoá',
      bad: 'Kiểm tra các số được đánh dấu: có thể có dấu +, rồi 6–15 chữ số.', max: 'Tối đa 20 số.',
      ignored: 'Các dòng trong file không phải số (sẽ bị xoá khi lưu):', loading: 'Đang tải…'},
    zh: {title: '短信控制', any: '任何号码', n: n => n + ' 个号码',
      desc: '允许通过短信（“<PIN> 命令”）控制设备的号码。',
      empty: '名单为空：任何知道 PIN 的手机都能发送命令。',
      some: '只有这些号码可以发送命令；其他号码的命令会被拒绝并通知到 Telegram。按号码最后 9 位匹配，所以 +84 912 345 678 与 0912 345 678 视为同一号码。',
      lockYes: '来自其他号码的被拒命令目前仍计入锁定次数（每小时 5 次错误）。',
      lockNo: '来自其他号码的命令会被忽略，不计入锁定次数（每小时 5 次 PIN 错误）。',
      noPin: '尚未设置短信 PIN，短信命令处于关闭状态。请在“短信 PIN”中设置。',
      ph: '电话号码，例如 +84912345678', add: '添加号码', save: '保存', remove: '删除',
      bad: '请检查标红的号码：可选 +，后接 6–15 位数字。', max: '最多 20 个号码。',
      ignored: '文件中不是号码的行（保存时删除）：', loading: '加载中…'},
  };
  const t = k => (T[UZ.lang] || T.en)[k] ?? T.en[k];
  const ICON = '<path d="M12 3l8 3v6c0 5-3.5 8-8 9-4.5-1-8-4-8-9V6z"/><path d="M9 12l2 2 4-4"/>';

  let nums = [], info = {};
  const rowsHtml = () => nums.map((n, i) => `<div style="display:flex;gap:10px;align-items:center;margin-bottom:10px">
      <input class="field" style="margin:0;flex:1" data-focus data-smsa-i="${i}" value="${UZ.esc(n)}" inputmode="tel" autocomplete="off" placeholder="${UZ.esc(t('ph'))}">
      <button class="btn sm" data-focus data-smsa-rm="${i}" aria-label="${UZ.esc(t('remove'))}" title="${UZ.esc(t('remove'))}">✕</button></div>`).join('');
  const explain = () => UZ.esc(nums.filter(n => clean(n)).length ? t('some') + ' ' + t(FOREIGN_COUNTS ? 'lockYes' : 'lockNo') : t('empty'));
  const sync = () => { nums = UZ.$$('[data-smsa-i]').map(e => e.value); };
  function paint() {
    UZ.$('#smsa-rows').innerHTML = rowsHtml();
    UZ.$('#smsa-explain').innerHTML = explain();
    UZ.$('#smsa-add').disabled = nums.length >= 20;
  }

  async function open() {
    let r;
    try { r = await UZ.post('smsallow-get', {}); } catch (e) { UZ.toast(String(e)); return; }
    if (r.error) { UZ.toast(r.error); return; }
    info = r; nums = (r.numbers || []).slice();
    const ign = (r.ignored || []).length ? `<p style="color:var(--orange);margin:0 0 12px">${UZ.esc(t('ignored'))} ${r.ignored.map(x => `<code>${UZ.esc(x)}</code>`).join(' ')}</p>` : '';
    UZ.openSheet('gray', 'lock', UZ.esc(t('title')), UZ.esc(t('desc')),
      `<div class="actions" style="margin:0 0 18px"><button class="btn primary" data-focus data-core="pin">${UZ.esc(UZ.coreT('pinBtn'))}</button></div>${r.pin_set ? '' : `<p style="color:var(--orange);margin:0 0 12px">${UZ.esc(t('noPin'))}</p>`}
       <p id="smsa-explain" style="color:var(--dim);margin:0 0 16px"></p>${ign}
       <div id="smsa-rows"></div>
       <div class="actions" style="margin-top:6px"><button class="btn sm" data-focus id="smsa-add">+ ${UZ.esc(t('add'))}</button></div>
       <div class="actions"><button class="btn primary" data-focus id="smsa-save">${UZ.esc(t('save'))}</button>${UZ.closeBtn()}</div>`);
    paint();
    const box = UZ.$('#smsa-rows');
    box.addEventListener('click', e => {
      const b = e.target.closest('[data-smsa-rm]'); if (!b) return;
      sync(); nums.splice(+b.dataset.smsaRm, 1); paint();
    });
    box.addEventListener('input', e => { if (e.target.dataset.smsaI != null) { e.target.style.boxShadow = ''; sync(); UZ.$('#smsa-explain').innerHTML = explain(); } });
    box.addEventListener('keydown', e => { if (e.key === 'Enter' && e.target.dataset.smsaI != null) { e.preventDefault(); UZ.$('#smsa-save').click(); } });
    UZ.$('#smsa-add').onclick = () => {
      sync(); if (nums.length >= 20) { UZ.toast(t('max')); return; }
      nums.push(''); paint(); const ins = UZ.$$('[data-smsa-i]'); ins[ins.length - 1]?.focus();
    };
    UZ.$('#smsa-save').onclick = async () => {
      sync();
      const ins = UZ.$$('[data-smsa-i]'); let bad = false;
      ins.forEach(e => { const v = clean(e.value); const ok = !v || NUM.test(v); e.style.boxShadow = ok ? '' : '0 0 0 2px var(--red) inset'; if (!ok) bad = true; });
      if (bad) { UZ.toast(t('bad')); return; }
      const list = nums.map(clean).filter(Boolean);
      if (list.length > 20) { UZ.toast(t('max')); return; }
      const b = UZ.$('#smsa-save'); b.disabled = true;
      try {
        const r = await UZ.post('smsallow-set', {numbers: list});
        UZ.toast(r.error || r.out);
        if (!r.error) { UZ.closeSheet(); UZ.reload(); }
      } catch (e) { UZ.toast(String(e)); }
      b.disabled = false;
    };
  }

  UZ.register({
    id: 'smsallow', order: 40, color: 'gray', iconSvg: ICON,
    title: {en: T.en.title, vi: T.vi.title, zh: T.zh.title},
    sub: S => { const n = S?.settings?.smsallow?.count; return n == null ? '' : n ? T[UZ.lang]?.n(n) ?? T.en.n(n) : t('any'); },
    open,
  });
})();
