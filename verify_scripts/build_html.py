#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""توليد صفحة HTML بصرية ذاتية الاكتفاء من الحمولة — إثبات صحة الإحداثيات."""

HTML_TEMPLATE = r'''<!DOCTYPE html>
<html lang="ar" dir="rtl">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>ROUND34 — التحقق البصري من إحداثيات الزقزاق والفيبوناتشي</title>
<style>
  * { box-sizing: border-box; margin: 0; padding: 0; }
  body { font-family: 'Segoe UI', Tahoma, sans-serif; background: #0e1117; color: #d8dee9; padding: 16px; }
  h1 { color: #58a6ff; font-size: 20px; margin-bottom: 4px; }
  .sub { color: #8b949e; font-size: 12px; margin-bottom: 14px; }
  .tabs { display: flex; gap: 8px; margin-bottom: 10px; flex-wrap: wrap; }
  .tab { padding: 8px 16px; background: #161b22; border: 1px solid #30363d; border-radius: 6px; cursor: pointer; font-size: 13px; }
  .tab.active { background: #1f6feb33; border-color: #58a6ff; color: #58a6ff; }
  .controls { display: flex; gap: 14px; margin-bottom: 8px; flex-wrap: wrap; align-items: center; font-size: 12px; }
  .controls label { display: flex; gap: 5px; align-items: center; cursor: pointer; color: #8b949e; }
  .controls input[type=checkbox] { accent-color: #58a6ff; }
  .legend { display: flex; gap: 14px; flex-wrap: wrap; font-size: 11px; color: #8b949e; margin-bottom: 8px; }
  .legend span { display: inline-flex; align-items: center; gap: 5px; }
  .sw { display: inline-block; width: 18px; height: 3px; border-radius: 2px; }
  .sw.v { width: 3px; height: 14px; }
  canvas { background: #0d1117; border: 1px solid #30363d; border-radius: 8px; width: 100%; cursor: crosshair; }
  .info { margin-top: 10px; background: #161b22; border: 1px solid #30363d; border-radius: 8px; padding: 10px 14px; font-size: 12px; line-height: 1.9; max-height: 260px; overflow-y: auto; }
  .info b { color: #58a6ff; }
  .ok { color: #3fb950; } .bad { color: #f85149; } .warn { color: #d29922; }
  .stats { display: grid; grid-template-columns: repeat(auto-fill, minmax(190px, 1fr)); gap: 8px; margin-bottom: 10px; }
  .stat { background: #161b22; border: 1px solid #30363d; border-radius: 6px; padding: 8px 12px; font-size: 12px; }
  .stat .v { color: #58a6ff; font-size: 16px; font-weight: 600; }
  .hint { color: #8b949e; font-size: 11px; margin-top: 6px; }
</style>
</head>
<body>
<h1>ROUND34 — التحقق البصري: محرك الزقزاق والفيبوناتشي الموحد</h1>
<div class="sub">هذه الصفحة ترسم <b>الإحداثيات الفعلية</b> التي يرسلها الباك اند (نفس حمولة chart-data) — إثبات أن الرسم صحيح وغير عشوائي: الزقزاق يصل النقاط، الفيبو يبدأ من خط الولادة وينتهي بنهاية النطاق.</div>

<div class="tabs" id="tabs"></div>
<div class="controls">
  <label><input type="checkbox" id="ckZigZag" checked> الزقزاق (legs)</label>
  <label><input type="checkbox" id="ckFib" checked> الفيبوناتشي (لكل نطاق: ولادة→نهاية)</label>
  <label><input type="checkbox" id="ckAnchor" checked> خطوط ولادة النطاق</label>
  <label><input type="checkbox" id="ckRef" checked> المرجع R (أكبر حمراء)</label>
  <label><input type="checkbox" id="ckSignals" checked> الإشارات (E2E)</label>
  <label><input type="checkbox" id="ckTrend" checked> خطوط الترند (ترندية 7/15/25)</label>
  <label><input type="checkbox" id="ckTrendySig" checked> حراس الدخول (ترندية)</label>
  <label><input type="checkbox" id="ckVolume"> حجم الشموع</label>
</div>
<div class="legend">
  <span><span class="sw" style="background:#ff5d00"></span> زقزاق</span>
  <span><span class="sw" style="background:#22d3ee"></span> خط ولادة النطاق</span>
  <span><span class="sw" style="background:#95cc28"></span> 0.382 (انطلاقة 0.618 المستخدم)</span>
  <span><span class="sw" style="background:#28cc95"></span> 0.618</span>
  <span><span class="sw" style="background:#f8fc7f"></span> مرجع R</span>
  <span><span class="sw" style="background:#3fb950"></span> دخول E2E</span>
  <span><span class="sw" style="background:#d29922"></span> ممنوع بالترند</span>
  <span><span class="sw" style="background:#a371f7"></span> ترند علوي/سفلي</span>
</div>
<div class="stats" id="stats"></div>
<canvas id="chart" height="560"></canvas>
<div class="hint">اسحب بالماوس للتمرير · عجلة الماوس للتكبير/التصغير · مرّر فوق العناصر لعرض التفاصيل</div>
<div class="info" id="info">جارٍ التحميل…</div>

<script>
const DATA = __PAYLOAD__;

// ====== إعدادات ======
const FIB_COLORS = {"0":"#808080","0.236":"#a61c00","0.382":"#95cc28","0.5":"#28cc28","0.618":"#28cc95","0.786":"#2895cc","0.85415":"#7aa2f7","1":"#808080"};
let cur = 0;                       // فهرس الحالة
let view = {start: 0, count: 0};   // نافذة العرض
let hover = null;

const cvs = document.getElementById('chart');
const ctx = cvs.getContext('2d');

function caseData(){ return DATA.cases[cur]; }

function resize(){
  const w = cvs.parentElement.clientWidth - 2;
  const dpr = window.devicePixelRatio || 1;
  cvs.width = w * dpr; cvs.height = 560 * dpr;
  cvs.style.height = '560px';
  ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
}
window.addEventListener('resize', () => { resize(); draw(); });

// ====== أدوات ======
function fmtTime(ms){
  const d = new Date(ms);
  return d.toLocaleDateString('en-GB',{day:'2-digit',month:'2-digit'}) + ' ' +
         d.toLocaleTimeString('en-GB',{hour:'2-digit',minute:'2-digit'});
}
function fmtP(x){ return x >= 100 ? x.toFixed(1) : x >= 1 ? x.toFixed(3) : x.toPrecision(4); }

function computeView(){
  const c = caseData();
  if (!view.count) { view.start = Math.max(0, c.candles.length - 320); view.count = Math.min(320, c.candles.length); }
  view.count = Math.min(view.count, c.candles.length - view.start);
}

function priceBounds(){
  const c = caseData();
  let lo = Infinity, hi = -Infinity;
  const vol = document.getElementById('ckVolume').checked;
  const H = 560, volH = vol ? 90 : 0, priceH = H - volH - 46;
  for (let i = view.start; i < view.start + view.count; i++){
    const k = c.candles[i];
    lo = Math.min(lo, k.low); hi = Math.max(hi, k.high);
  }
  // وسّع ليشمل مستويات الفيبو الظاهرة والترند
  const ov = c.overlays['zzfib_e2e'] || {};
  (ov.ranges||[]).forEach(r => {
    if (r.anchor && r.anchor.bar >= view.start && r.anchor.bar < view.start + view.count){
      (r.levels||[]).forEach(lv => { if (lv.value != null){ lo = Math.min(lo, lv.value); hi = Math.max(hi, lv.value); } });
      if (r.launch_line != null){ lo = Math.min(lo, r.launch_line); hi = Math.max(hi, r.launch_line); }
    }
  });
  const pad = (hi - lo) * 0.08 || 1;
  return {lo: lo - pad, hi: hi + pad, priceH, volH, H: 560};
}

function xOf(i){ const w = cvs.clientWidth; return 40 + (i - view.start + 0.5) * (w - 60) / view.count; }
function yOf(p, b){ return 16 + (b.hi - p) / (b.hi - b.lo) * b.priceH; }

// ====== الرسم ======
function draw(){
  ctx.clearRect(0, 0, cvs.clientWidth, 560);
  if (!caseData()) return;
  computeView();
  const b = priceBounds();
  const c = caseData();
  const W = cvs.clientWidth;

  // شبكة أفقية + محور السعر
  ctx.strokeStyle = '#21262d'; ctx.fillStyle = '#484f58'; ctx.font = '10px monospace'; ctx.textAlign = 'left';
  for (let g = 0; g <= 6; g++){
    const p = b.lo + (b.hi - b.lo) * g / 6, y = yOf(p, b);
    ctx.beginPath(); ctx.moveTo(40, y); ctx.lineTo(W - 20, y); ctx.stroke();
    ctx.fillText(fmtP(p), 2, y + 3);
  }

  // الشموع
  const cw = Math.max(1.5, (W - 60) / view.count * 0.62);
  for (let i = view.start; i < view.start + view.count; i++){
    const k = c.candles[i], x = xOf(i);
    const up = k.close >= k.open;
    ctx.strokeStyle = up ? '#26a641' : '#ea4338'; ctx.fillStyle = up ? '#26a64188' : '#ea433888';
    ctx.beginPath(); ctx.moveTo(x, yOf(k.high, b)); ctx.lineTo(x, yOf(k.low, b)); ctx.stroke();
    const yo = yOf(k.open, b), yc = yOf(k.close, b);
    ctx.fillRect(x - cw/2, Math.min(yo, yc), cw, Math.max(1, Math.abs(yc - yo)));
  }

  const ov = c.overlays['zzfib_e2e'] || {};
  const tr = c.overlays['zzfib_e2e_trendy'] || {};
  const N = c.candles.length;

  // خطوط ولادة النطاق (anchor) — عمودية سماوية
  if (document.getElementById('ckAnchor').checked){
    ctx.strokeStyle = '#22d3ee'; ctx.setLineDash([4,4]); ctx.lineWidth = 1;
    (ov.ranges||[]).forEach(r => {
      if (r.anchor && r.anchor.bar >= view.start && r.anchor.bar < view.start + view.count){
        const x = xOf(r.anchor.bar);
        ctx.beginPath(); ctx.moveTo(x, 12); ctx.lineTo(x, 16 + b.priceH); ctx.stroke();
        ctx.fillStyle = '#22d3ee'; ctx.font = '9px monospace'; ctx.textAlign = 'center';
        ctx.fillText('R' + r.index, x, 10);
      }
    });
    ctx.setLineDash([]);
  }

  // الفيبو لكل نطاق (من الولادة إلى النهاية)
  if (document.getElementById('ckFib').checked){
    (ov.ranges||[]).forEach(r => {
      if (!r.levels || !r.levels.length) return;
      const x1 = xOf(Math.max(r.anchor.bar, view.start));
      const x2 = xOf(Math.min(r.levels[0].x_to, view.start + view.count - 1));
      if (x2 <= 40 || x1 > W - 20) return;
      const live = r.death && r.death.bar >= N;
      r.levels.forEach(lv => {
        if (lv.value == null) return;
        const y = yOf(lv.value, b);
        const key = String(lv.ratio);
        ctx.strokeStyle = FIB_COLORS[key] || '#666';
        ctx.globalAlpha = live ? 0.95 : 0.55;
        ctx.lineWidth = (key === '0.382' || key === '0.618') ? 1.6 : 1;
        ctx.setLineDash(live ? [] : []);
        ctx.beginPath(); ctx.moveTo(Math.max(x1, 40), y); ctx.lineTo(Math.min(x2, W-20), y); ctx.stroke();
        if (Math.abs(x2 - x1) > 55 || key === '0.382' || key === '0.618'){
          ctx.fillStyle = FIB_COLORS[key] || '#666'; ctx.font = '9px monospace'; ctx.textAlign = 'left';
          ctx.fillText(key + ' · ' + fmtP(lv.value), Math.max(x1, 40) + 3, y - 2);
        }
        ctx.globalAlpha = 1;
      });
      // خط الانطلاقة (0.618 المستخدم = price 0.382)
      if (r.launch_line != null){
        const y = yOf(r.launch_line, b);
        ctx.strokeStyle = '#95cc28'; ctx.setLineDash([6,3]); ctx.lineWidth = 1.2;
        ctx.beginPath(); ctx.moveTo(Math.max(x1, 40), y); ctx.lineTo(Math.min(x2, W-20), y); ctx.stroke();
        ctx.setLineDash([]);
      }
    });
  }

  // الزقزاق — نفس الأرجل للجميع (e2e والترندية تشتركان بنفس النطاق)
  if (document.getElementById('ckZigZag').checked){
    ctx.strokeStyle = '#ff5d00'; ctx.lineWidth = 2; ctx.lineJoin = 'round';
    const legs = (ov.legs || (tr.legs || []));
    ctx.beginPath();
    let started = false;
    legs.forEach(lg => {
      const x1 = xOf(lg.x1), y1 = yOf(lg.y1, b), x2 = xOf(lg.x2), y2 = yOf(lg.y2, b);
      if (x2 < 40 || x1 > W - 20) return;
      if (!started){ ctx.moveTo(x1, y1); started = true; } else ctx.lineTo(x1, y1);
      ctx.lineTo(x2, y2);
    });
    ctx.stroke();
    // نقاط الأطراف
    legs.forEach(lg => {
      [[lg.x1, lg.y1],[lg.x2, lg.y2]].forEach(([bx, by]) => {
        if (bx >= view.start && bx < view.start + view.count){
          ctx.fillStyle = '#ff5d00';
          ctx.beginPath(); ctx.arc(xOf(bx), yOf(by, b), 2.6, 0, 7); ctx.fill();
        }
      });
    });
  }

  // المرجع R (أكبر حمراء في عمر النطاق)
  if (document.getElementById('ckRef').checked){
    (ov.ranges||[]).forEach(r => {
      if (r.ref && r.ref.bar != null && r.ref.bar >= view.start && r.ref.bar < view.start + view.count){
        const x = xOf(r.ref.bar), y = yOf(r.ref.high, b);
        ctx.strokeStyle = '#f8fc7f'; ctx.lineWidth = 1.4;
        ctx.strokeRect(x - cw*2, y - 4, cw*4, 8);
        ctx.fillStyle = '#f8fc7f'; ctx.font = '9px monospace'; ctx.textAlign = 'center';
        ctx.fillText('R ' + fmtP(r.ref.high), x, y - 7);
      }
    });
  }

  // إشارات E2E
  if (document.getElementById('ckSignals').checked){
    ((ov.signals)||[]).forEach(s => {
      if (s.bar < view.start || s.bar >= view.start + view.count) return;
      const x = xOf(s.bar);
      if (s.side === 'buy'){
        const y = yOf(s.price != null ? s.price : 0, b) + 26;
        ctx.fillStyle = '#3fb950';
        ctx.beginPath(); ctx.moveTo(x, y - 10); ctx.lineTo(x - 6, y + 2); ctx.lineTo(x + 6, y + 2); ctx.closePath(); ctx.fill();
        ctx.fillStyle = '#3fb950'; ctx.font = 'bold 9px monospace'; ctx.textAlign = 'center';
        ctx.fillText(s.signal.replace('ZLF-E2E ',''), x, y + 12);
      }
    });
  }

  // خطوط الترند (سلاسل trf_p{n}_upper/lower من الترندية)
  if (document.getElementById('ckTrend').checked){
    const tser = (tr.series) || {};
    const periods = ((tr.trend || {}).periods) || [7,15,25];
    periods.forEach((p, pi) => {
      [['upper','#a371f7'],['lower','#4dd0e1']].forEach(([side, col]) => {
        const vals = tser['zzfet_tr_p' + p + '_' + side];
        if (!vals) return;
        ctx.strokeStyle = col; ctx.lineWidth = 1.1; ctx.globalAlpha = 0.8;
        ctx.beginPath(); let pen = false;
        for (let i = view.start; i < view.start + view.count; i++){
          const v = vals[i];
          if (v == null){ pen = false; continue; }
          const x = xOf(i), y = yOf(v, b);
          if (!pen){ ctx.moveTo(x, y); pen = true; } else ctx.lineTo(x, y);
        }
        ctx.stroke(); ctx.globalAlpha = 1;
      });
    });
  }

  // حراس الدخول للترندية: الخام والممنوع
  if (document.getElementById('ckTrendySig').checked && tr.series){
    const rawS = tr.series['zzfet_entry_raw_s1'] || [];
    const blk = [tr.series['zzfet_entry_blocked_s1'], tr.series['zzfet_entry_blocked_s2'], tr.series['zzfet_entry_blocked_s3']];
    for (let i = view.start; i < view.start + view.count; i++){
      const x = xOf(i);
      if (rawS[i]){
        ctx.fillStyle = '#3fb950';
        ctx.beginPath(); ctx.arc(x, 8, 3.2, 0, 7); ctx.fill();
      }
      for (let j = 0; j < 3; j++){
        if (blk[j] && blk[j][i]){
          ctx.fillStyle = '#d29922';
          ctx.beginPath(); ctx.moveTo(x, 4); ctx.lineTo(x - 4, 11); ctx.lineTo(x + 4, 11); ctx.closePath(); ctx.fill();
          ctx.fillStyle = '#d29922'; ctx.font = '8px monospace'; ctx.textAlign = 'center';
          ctx.fillText('blk', x, 20);
        }
      }
    }
  }

  // الحجم
  if (document.getElementById('ckVolume').checked && b.volH){
    let vmax = 0;
    for (let i = view.start; i < view.start + view.count; i++) vmax = Math.max(vmax, c.candles[i].volume || 0);
    const y0 = 16 + b.priceH + 18;
    for (let i = view.start; i < view.start + view.count; i++){
      const k = c.candles[i], x = xOf(i);
      const h = (k.volume || 0) / (vmax || 1) * (b.volH - 8);
      ctx.fillStyle = k.close >= k.open ? '#26a64155' : '#ea433855';
      ctx.fillRect(x - cw/2, y0 + (b.volH - 8 - h), cw, h);
    }
    ctx.fillStyle = '#484f58'; ctx.font = '9px monospace'; ctx.textAlign = 'left';
    ctx.fillText('VOL max ' + fmtP(vmax), 42, y0 + 10);
  }

  // محور الزمن
  ctx.fillStyle = '#484f58'; ctx.font = '9px monospace'; ctx.textAlign = 'center';
  const step = Math.max(1, Math.floor(view.count / 7));
  for (let i = view.start; i < view.start + view.count; i += step){
    ctx.fillText(fmtTime(c.candles[i].time), xOf(i), 552);
  }
}

// ====== تفاعل ======
let drag = null;
cvs.addEventListener('mousedown', e => { drag = {x: e.offsetX, start: view.start}; });
window.addEventListener('mouseup', () => drag = null);
cvs.addEventListener('mousemove', e => {
  if (drag){
    const dx = e.offsetX - drag.x;
    const c = caseData();
    const di = -dx / (cvs.clientWidth - 60) * view.count;
    view.start = Math.max(0, Math.min(c.candles.length - view.count, Math.round(drag.start + di)));
    draw(); return;
  }
  // تلميح
  const c = caseData();
  const i = view.start + Math.round((e.offsetX - 40) / (cvs.clientWidth - 60) * view.count) - 0;
  const info = document.getElementById('info');
  if (i >= 0 && i < c.candles.length){
    const k = c.candles[i];
    const ov = c.overlays['zzfib_e2e'] || {};
    let rng = null;
    (ov.ranges||[]).forEach(r => { if (r.anchor && r.anchor.bar <= i && (r.death == null || r.death.bar > i)) rng = r; });
    let lines = [];
    lines.push(`<b>${c.symbol} ${c.timeframe}</b> — شمعة #${i} · ${fmtTime(k.time)} · O:${fmtP(k.open)} H:${fmtP(k.high)} L:${fmtP(k.low)} C:${fmtP(k.close)} V:${fmtP(k.volume||0)}`);
    if (rng){
      lines.push(`<b>النطاق الحي #${rng.index}</b> — ولد ${fmtTime(rng.anchor.time)} · ساق: ${fmtP(rng.p1.price)} (${rng.p1.kind}) → ${fmtP(rng.p2.price)} (${rng.p2.kind}) · ${rng.dir > 0 ? 'صاعد' : 'هابط'} · انطلاقة: ${fmtP(rng.launch_line)}`);
      if (rng.ref) lines.push(`<span class="warn">المرجع R</span>: ${fmtTime(rng.ref.time)} · قمة ${fmtP(rng.ref.high)} · حجم ${fmtP(rng.ref.vol)}`);
      const lv382 = (rng.levels||[]).find(l => l.ratio === 0.382);
      if (lv382) lines.push(`فيبو 0.382 (انطلاقة المستخدم): <span style="color:#95cc28">${fmtP(lv382.value)}</span> — يُرسم من ${fmtTime(lv382.t_from)} إلى ${fmtTime(lv382.t_to)}`);
    } else lines.push(`<span class="bad">قبل أول نطاق — لا زقزاق ظهر بعد (كل ما قبل الظهور ليس نطاقاً)</span>`);
    const sigs = ((ov.signals)||[]).filter(s => s.bar === i);
    sigs.forEach(s => lines.push(`<span class="${s.side === 'buy' ? 'ok' : 'warn'}">◆ ${s.signal}</span> — سعر ${fmtP(s.price)} حجم ${fmtP(s.volume || 0)}`));
    info.innerHTML = lines.join('<br>');
  }
});
cvs.addEventListener('wheel', e => {
  e.preventDefault();
  const oldCount = view.count;
  const factor = e.deltaY > 0 ? 1.25 : 0.8;
  const c = caseData();
  const center = view.start + view.count / 2;
  view.count = Math.max(40, Math.min(c.candles.length, Math.round(view.count * factor)));
  view.start = Math.max(0, Math.min(c.candles.length - view.count, Math.round(center - view.count / 2)));
  draw();
}, {passive: false});

document.querySelectorAll('.controls input').forEach(el => el.addEventListener('change', draw));

// ====== تبويبات الحالات + إحصاءات ======
function initTabs(){
  const tabs = document.getElementById('tabs');
  tabs.innerHTML = '';
  DATA.cases.forEach((c, i) => {
    const t = document.createElement('div');
    t.className = 'tab' + (i === cur ? ' active' : '');
    t.textContent = c.symbol + ' · ' + c.timeframe + ' (' + c.candles.length + ' شمعة)';
    t.onclick = () => { cur = i; view = {start: 0, count: 0}; initTabs(); buildStats(); draw(); };
    tabs.appendChild(t);
  });
}
function buildStats(){
  const c = caseData();
  const ov = c.overlays['zzfib_e2e'] || {};
  const tr = c.overlays['zzfib_e2e_trendy'] || {};
  const legs = ov.legs || [];
  const timesOk = legs.every(l => l.t1 > 0 && l.t2 > 0);
  const ranges = ov.ranges || [];
  const lvOk = ranges.every(r => (r.levels || []).length > 0);
  const signals = (ov.signals || []).filter(s => s.side === 'buy');
  const tSigs = (tr.signals || []);
  const blocked = tSigs.filter(s => s.side === 'blocked').length;
  document.getElementById('stats').innerHTML = `
    <div class="stat">أرجل الزقزاق<div class="v">${legs.length}</div>${timesOk ? '<span class="ok">أزمنة كلها صحيحة ≠ 0</span>' : '<span class="bad">أزمنة صفرية!</span>'}</div>
    <div class="stat">النطاقات (ولادة→موت)<div class="v">${ranges.length}</div>${lvOk ? '<span class="ok">كلها تحمل فيبو بحدود كاملة</span>' : '<span class="bad">نطاقات بلا مستويات!</span>'}</div>
    <div class="stat">إشارات دخول E2E<div class="v">${signals.length}</div><span>${signals.map(s => 'S' + (s.state || '?')).join(' · ') || '—'}</span></div>
    <div class="stat">الترندية: خام/نافذ/ممنوع<div class="v">${tSigs.filter(s => s.side === 'buy').length}/${blocked}</div><span>بوابة majority 7/15/25</span></div>
    <div class="stat">الحجم وصل للمحرك<div class="v">${ov.volume_available ? 'نعم ✓' : 'لا ✗'}</div><span>شرط المرجع R</span></div>
    <div class="stat">النواة الموحدة<div class="v">R34</div><span>${(ov.core || {}).spec || ''}</span></div>`;
}
initTabs(); buildStats(); resize(); draw();
</script>
</body>
</html>
'''

import json

import os as _os
_HERE = _os.path.dirname(_os.path.abspath(__file__))
payload = json.load(open(_os.path.join(_HERE, "visual_full_payload.json")))
html = HTML_TEMPLATE.replace("__PAYLOAD__", json.dumps(payload, ensure_ascii=False, separators=(",", ":")))
with open(_os.path.join(_HERE, "round34_visual_check.html"), "w", encoding="utf-8") as f:
    f.write(html)
print("saved →", _os.path.join(_HERE, "round34_visual_check.html"))
print("size:", len(html) // 1024, "KB")
