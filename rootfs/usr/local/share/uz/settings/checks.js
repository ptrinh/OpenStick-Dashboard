/* Uptime checks: /etc/uz/probe.list targets + uz-probe.timer interval — actions checks-get / checks-set / checks-run */
(() => {
  const T = {
    en: {title: 'Uptime checks', desc: 'The stick checks these targets over its current uplink and sends a Telegram alert when one goes down or comes back.',
      none: 'No targets', n: n => n === 1 ? '1 target' : n + ' targets', every: 'every', min: 'min',
      interval: 'Check every', add: 'Add', save: 'Save', run: 'Run now', remove: 'Remove',
      lastRun: 'Last run', via: 'via', ago: 'min ago', never: 'not run yet', noResult: 'no result yet',
      empty: 'No targets yet — add a website, a TCP port or a host to ping.',
      bad: 'Check the highlighted targets.', max: 'At most 20 targets.',
      help: 'https://example.com · tcp:host:port (e.g. tcp:1.1.1.1:53) · ping:host',
      phU: 'https://example.com', phT: 'tcp:example.com:443', phP: 'ping:1.1.1.1', bad1: 'invalid target'},
    vi: {title: 'Kiểm tra dịch vụ', desc: 'Stick kiểm tra các mục này qua đường Internet hiện tại và báo Telegram khi một mục bị sập hoặc hoạt động lại.',
      none: 'Chưa có mục', n: n => n + ' mục', every: 'mỗi', min: 'phút',
      interval: 'Kiểm tra mỗi', add: 'Thêm', save: 'Lưu', run: 'Chạy ngay', remove: 'Xoá',
      lastRun: 'Lần chạy cuối', via: 'qua', ago: 'phút trước', never: 'chưa chạy', noResult: 'chưa có kết quả',
      empty: 'Chưa có mục nào — thêm một website, một cổng TCP hoặc một máy để ping.',
      bad: 'Kiểm tra lại các mục được đánh dấu.', max: 'Tối đa 20 mục.',
      help: 'https://example.com · tcp:máy:cổng (vd tcp:1.1.1.1:53) · ping:máy',
      phU: 'https://example.com', phT: 'tcp:example.com:443', phP: 'ping:1.1.1.1', bad1: 'mục không hợp lệ'},
    zh: {title: '服务可用性检测', desc: '设备通过当前上行网络检测这些目标，目标宕机或恢复时发送 Telegram 通知。',
      none: '无目标', n: n => n + ' 个目标', every: '每', min: '分钟',
      interval: '检测间隔', add: '添加', save: '保存', run: '立即检测', remove: '删除',
      lastRun: '上次检测', via: '经由', ago: '分钟前', never: '尚未运行', noResult: '暂无结果',
      empty: '还没有目标——添加网站、TCP 端口或要 ping 的主机。',
      bad: '请检查标红的目标。', max: '最多 20 个目标。',
      help: 'https://example.com · tcp:主机:端口（例如 tcp:1.1.1.1:53）· ping:主机',
      phU: 'https://example.com', phT: 'tcp:example.com:443', phP: 'ping:1.1.1.1', bad1: '目标无效'},
  };
  const t = k => (T[UZ.lang] || T.en)[k] ?? T.en[k];
  const tn = n => ((T[UZ.lang] || T.en).n || T.en.n)(n);
  const INTERVALS = [1, 2, 5, 10, 15, 30, 60];
  const VIA = {wwan0: '4G', wlan0: 'Wi-Fi', usb0: 'USB'};
  const LABEL = '[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?';
  const HOST = new RegExp(`^(?:${LABEL})(?:\\.${LABEL})*\\.?$`);
  const hostOk = h => h.length <= 253 && HOST.test(h) && (!/^[0-9.]+$/.test(h) || /^((25[0-5]|2[0-4]\d|1?\d?\d)\.){3}(25[0-5]|2[0-4]\d|1?\d?\d)$/.test(h));
  const norm = s => { s = String(s || '').trim(); const m = s.match(/^(https?:\/\/|tcp:|ping:)/i); return m ? m[1].toLowerCase() + s.slice(m[1].length) : s; };
  const kind = s => /^https:\/\//.test(s) ? 'https' : /^http:\/\//.test(s) ? 'http' : /^tcp:/.test(s) ? 'tcp' : /^ping:/.test(s) ? 'ping' : '';
  function valid(s) {
    const k = kind(s);
    if (k === 'https' || k === 'http') return s.length <= 200 && /^https?:\/\/[\x21-\x7e]+$/.test(s) && /^https?:\/\/[^/?#]+/.test(s);
    if (k === 'tcp') { const p = s.split(':'); return p.length === 3 && hostOk(p[1]) && /^\d{1,5}$/.test(p[2]) && +p[2] >= 1 && +p[2] <= 65535; }
    if (k === 'ping') return hostOk(s.slice(5));
    return false;
  }
  const PREFIXES = ['https://', 'http://', 'tcp:', 'ping:'];
  const CHIP = {https: 'HTTPS', http: 'HTTP', tcp: 'TCP', ping: 'Ping', '': '?'};
  const ICON_STYLE = 'min-width:62px;padding:8px 10px;font-size:13px;cursor:default;text-align:center';

  let rows = [], interval = 5;
  function result(target) {
    const v = (UZ.S?.probe || {})[target];
    if (v == null) return `<span style="color:var(--faint);font-size:14px">${UZ.esc(t('noResult'))}</span>`;
    const o = typeof v === 'object' ? v : {ok: !!v};
    const c = !o.ok ? 'bad' : o.ms != null && o.ms > 1000 ? 'warn' : 'ok';
    const txt = (o.ok ? 'UP' : 'DOWN') + (o.ms != null ? ` · ${+o.ms} ms` : '') + (o.info ? ` · ${o.info}` : '');
    return `<span style="font-size:14px;white-space:nowrap;font-variant-numeric:tabular-nums"><span class="dot ${c}"></span>${UZ.esc(txt)}</span>`;
  }
  function rowHtml(r, i) {
    const k = kind(norm(r));
    return `<div style="display:grid;grid-template-columns:auto 1fr auto;gap:8px 10px;align-items:center;margin-bottom:14px">
      <span class="chip ${k ? 'on' : ''}" style="${ICON_STYLE}">${UZ.esc(CHIP[k])}</span>
      <input class="field" style="margin:0" data-focus data-chk-i="${i}" value="${UZ.esc(r)}" autocomplete="off" autocapitalize="off" spellcheck="false" maxlength="210">
      <button class="btn sm" data-focus data-chk-rm="${i}" aria-label="${UZ.esc(t('remove'))}" title="${UZ.esc(t('remove'))}">✕</button>
      <span></span><span data-chk-res="${i}">${result(norm(r))}</span><span></span></div>`;
  }
  const sync = () => { rows = UZ.$$('[data-chk-i]').map(e => e.value); };
  function paintRows() {
    UZ.$('#chk-rows').innerHTML = rows.length ? rows.map(rowHtml).join('') : `<p style="color:var(--faint);margin:0 0 12px">${UZ.esc(t('empty'))}</p>`;
    UZ.$$('[data-chk-add]').forEach(b => { b.disabled = rows.length >= 20; });
  }
  function paintInterval() {
    const list = INTERVALS.includes(interval) ? INTERVALS : [...INTERVALS, interval].sort((a, b) => a - b);
    UZ.$('#chk-int').innerHTML = list.map(n => `<button class="chip ${n === interval ? 'on' : ''}" data-focus data-chk-int="${n}">${n} ${UZ.esc(t('min'))}</button>`).join('');
  }
  function lastRun() {
    const P = UZ.S?.probe || {};
    if (!P._at) return UZ.esc(t('never'));
    const m = Math.max(0, Math.round((Date.now() / 1000 - P._at) / 60));
    const via = VIA[P._via] || P._via || '';
    return `${UZ.esc(t('lastRun'))}: ${m} ${UZ.esc(t('ago'))}${via ? ` · ${UZ.esc(t('via'))} ${UZ.esc(via)}` : ''}`;
  }

  async function open() {
    let r;
    try { r = await UZ.post('checks-get', {}); } catch (e) { UZ.toast(String(e)); return; }
    if (r.error) { UZ.toast(r.error); return; }
    rows = (r.targets || []).map(x => x.target);
    interval = Number.isInteger(r.interval_min) && r.interval_min >= 1 && r.interval_min <= 60 ? r.interval_min : 5;
    UZ.openSheet('teal', 'check', UZ.esc(t('title')), UZ.esc(t('desc')),
      `<div id="chk-root"><p style="color:var(--faint);margin:0 0 16px;font-size:14px">${lastRun()}${r.warn ? ` · ${UZ.esc(r.warn)}` : ''}</p>
       <div id="chk-rows"></div>
       <div class="chips" style="margin:4px 0 6px">
         <button class="chip" data-focus data-chk-add="https://">+ HTTPS</button>
         <button class="chip" data-focus data-chk-add="tcp:">+ TCP</button>
         <button class="chip" data-focus data-chk-add="ping:">+ Ping</button></div>
       <p style="color:var(--faint);font-size:13px;margin:6px 0 20px;overflow-wrap:anywhere">${UZ.esc(t('help'))}</p>
       <div class="stat" style="margin-bottom:4px"><div class="l">${UZ.esc(t('interval'))}</div><div class="chips" id="chk-int" style="margin-top:10px"></div></div>
       <div class="actions"><button class="btn primary" data-focus id="chk-save">${UZ.esc(t('save'))}</button>
         <button class="btn" data-focus id="chk-run">${UZ.esc(t('run'))}</button>${UZ.closeBtn()}</div></div>`);
    paintRows(); paintInterval();
    UZ.$('#chk-root').addEventListener('click', e => {
      const rm = e.target.closest('[data-chk-rm]');
      if (rm) { sync(); rows.splice(+rm.dataset.chkRm, 1); paintRows(); return; }
      const add = e.target.closest('[data-chk-add]');
      if (add) {
        sync(); if (rows.length >= 20) { UZ.toast(t('max')); return; }
        rows.push(add.dataset.chkAdd); paintRows();
        const ins = UZ.$$('[data-chk-i]'), el = ins[ins.length - 1]; if (el) { el.focus(); el.setSelectionRange(el.value.length, el.value.length); }
        return;
      }
      const iv = e.target.closest('[data-chk-int]');
      if (iv) { interval = +iv.dataset.chkInt; paintInterval(); }
    });
    UZ.$('#chk-rows').addEventListener('input', e => {
      const i = e.target.dataset.chkI; if (i == null) return;
      e.target.style.boxShadow = '';
      const v = norm(e.target.value), chip = e.target.previousElementSibling, k = kind(v);
      chip.textContent = CHIP[k]; chip.classList.toggle('on', !!k);
      const res = UZ.$(`[data-chk-res="${+i}"]`); if (res) res.innerHTML = result(v);
    });
    UZ.$('#chk-save').onclick = async () => {
      sync();
      const ins = UZ.$$('[data-chk-i]'); let bad = false;
      ins.forEach(e => { const v = norm(e.value); const ok = !v || PREFIXES.includes(v) || valid(v); e.style.boxShadow = ok ? '' : '0 0 0 2px var(--red) inset'; if (!ok) bad = true; });
      if (bad) { UZ.toast(t('bad')); return; }
      const list = [...new Set(rows.map(norm).filter(v => v && !PREFIXES.includes(v)))];
      if (list.length > 20) { UZ.toast(t('max')); return; }
      const b = UZ.$('#chk-save'); b.disabled = true;
      try {
        const r = await UZ.post('checks-set', {targets: list, interval_min: interval});
        UZ.toast(r.error || r.out);
        if (!r.error) { UZ.closeSheet(); UZ.reload(); }
      } catch (e) { UZ.toast(String(e)); }
      b.disabled = false;
    };
    UZ.$('#chk-run').onclick = async () => {
      const b = UZ.$('#chk-run'); b.disabled = true;
      try { const r = await UZ.post('checks-run', {}); UZ.toast(r.error || r.out); } catch (e) { UZ.toast(String(e)); }
      b.disabled = false;
    };
  }

  UZ.register({
    id: 'checks', order: 50, color: 'teal', icon: 'check',
    title: {en: T.en.title, vi: T.vi.title, zh: T.zh.title},
    sub: S => {
      const s = S?.settings?.checks; if (!s) return '';
      if (!s.count) return t('none');
      const down = Object.entries(S.probe || {}).filter(([k, v]) => !k.startsWith('_') && v && typeof v === 'object' && v.ok === false).length;
      return tn(s.count) + (s.interval_min ? ` · ${t('every')} ${s.interval_min} ${t('min')}` : '') + (down ? ` · ${down} DOWN` : '');
    },
    open,
  });
})();
