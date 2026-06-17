/* fee-charts.js — 관리비 대시보드 시각화 */
'use strict';

const _FC_CATS = [
  { key: '일반관리', icon: '🏢', color: '#3b82f6',
    items: ['일반관리비','소독비','승강기유지비','수선유지비','법정의무점검비','제경비','건물보험료','제경비(비과세)','청소용품비','청소비'] },
  { key: '전기/에너지', icon: '⚡', color: '#f59e0b',
    items: ['세대전기료','냉난방동력전기','공동전기료','공동전력기금','세대전력기금','승강기전기','에너지캐쉬백'] },
  { key: '수도/온수', icon: '💧', color: '#06b6d4',
    items: ['세대수도료','공동수도료','세대급탕비','하수도료','물이용부담금'] },
  { key: '장기수선', icon: '🔧', color: '#8b5cf6',
    items: ['장기수선충당금'] },
  { key: '냉난방', icon: '🌡️', color: '#ec4899',
    items: ['세대난방비','기본냉난방비','공동냉난방비','세대냉방비','기본냉방비'] },
];

function _n(v) {
  const x = parseInt(String(v || '0').replace(/,/g, ''), 10);
  return isNaN(x) ? 0 : x;
}

function _animateCount(el, end, ms) {
  if (!el) return;
  const t0 = performance.now();
  function step(ts) {
    const p = Math.min((ts - t0) / ms, 1);
    const ease = 1 - Math.pow(1 - p, 3);
    el.textContent = Math.floor(ease * end).toLocaleString('ko-KR') + '원';
    if (p < 1) requestAnimationFrame(step);
  }
  requestAnimationFrame(step);
}

/* F-01 히어로 카드 */
function _heroCard(d, history) {
  const total = _n(d.total);
  const ym = d.year_month || '';
  const ymLabel = ym.length >= 6
    ? `${ym.slice(0, 4)}년 ${parseInt(ym.slice(4, 6))}월분` : '';

  let prevHtml = '';
  if (history && history.length >= 2) {
    const prev = history[history.length - 2].amount;
    if (prev > 0) {
      const diff = total - prev;
      const pct = ((diff / prev) * 100).toFixed(1);
      const up = diff >= 0;
      prevHtml = `<div style="margin-top:8px;font-size:13px;opacity:.9">전월 대비&nbsp;`
        + `<span style="font-weight:700;color:${up ? '#fca5a5' : '#86efac'}">`
        + `${up ? '+' : ''}${diff.toLocaleString()}원 (${up ? '+' : ''}${pct}%)</span></div>`;
    }
  }

  return `<div class="fc-hero">
    <div style="font-size:13px;opacity:.75;margin-bottom:6px">🏠 ${d.dong}동 ${d.ho}호 · ${ymLabel}</div>
    <div style="font-size:13px;opacity:.8;margin-bottom:2px">이번달 관리비</div>
    <div class="fc-hero-amt" id="fcHeroAmt">0원</div>
    ${prevHtml}
  </div>`;
}

/* F-02 도넛 차트 */
function _donutChart(billing) {
  const cats = [];
  const used = new Set();

  for (const cat of _FC_CATS) {
    let sum = 0;
    const items = {};
    for (const k of cat.items) {
      const v = _n(billing[k]);
      if (v > 0) { sum += v; items[k] = v; used.add(k); }
    }
    if (sum > 0) cats.push({ ...cat, total: sum, items });
  }

  let etcSum = 0;
  const etcItems = {};
  for (const [k, v] of Object.entries(billing)) {
    if (!used.has(k) && _n(v) > 0) { etcSum += _n(v); etcItems[k] = _n(v); }
  }
  if (etcSum > 0) cats.push({ key: '기타', icon: '📦', color: '#94a3b8', total: etcSum, items: etcItems });

  const grand = cats.reduce((s, c) => s + c.total, 0);
  if (!grand) return '';

  const R = 70, SW = 28, C = 95, circ = 2 * Math.PI * R;
  let cumPct = 0, slices = '', legendHtml = '';

  for (const cat of cats) {
    const pct = cat.total / grand;
    const arc = pct * circ;
    const dashOff = circ * (1 - cumPct);
    slices += `<circle cx="${C}" cy="${C}" r="${R}" fill="none" stroke="${cat.color}"
      stroke-width="${SW}" stroke-dasharray="${arc.toFixed(2)} ${(circ - arc).toFixed(2)}"
      stroke-dashoffset="${dashOff.toFixed(2)}"
      style="transform-origin:${C}px ${C}px;transform:rotate(-90deg);cursor:pointer"
      onclick="window._fcTog('${cat.key}')"/>`;

    const rows = Object.entries(cat.items)
      .map(([k, v]) => `<div class="fc-det-row"><span>${k}</span><span>${v.toLocaleString()}원</span></div>`)
      .join('');

    legendHtml += `<div class="fc-leg-row" onclick="window._fcTog('${cat.key}')">
      <span class="fc-dot" style="background:${cat.color}"></span>
      <span class="fc-leg-name">${cat.icon} ${cat.key}</span>
      <span class="fc-leg-amt">${cat.total.toLocaleString()}</span>
      <span class="fc-leg-pct">${(pct * 100).toFixed(1)}%</span>
      <span class="fc-chev" id="fc-chev-${cat.key}">▼</span>
    </div>
    <div class="fc-det" id="fc-det-${cat.key}">${rows}</div>`;
    cumPct += pct;
  }

  return `<div class="fc-card">
    <div class="fc-card-title">관리비 구성</div>
    <div class="fc-donut-wrap">
      <svg width="190" height="190" viewBox="0 0 190 190" style="flex-shrink:0">
        ${slices}
        <text x="${C}" y="${C - 6}" text-anchor="middle" font-size="12" fill="#94a3b8">합계</text>
        <text x="${C}" y="${C + 14}" text-anchor="middle" font-size="15" font-weight="700" fill="#1a1a2e">${grand.toLocaleString()}</text>
      </svg>
      <div class="fc-legend">${legendHtml}</div>
    </div>
  </div>`;
}

window._fcTog = function(key) {
  const det = document.getElementById('fc-det-' + key);
  const chev = document.getElementById('fc-chev-' + key);
  if (!det) return;
  const hidden = getComputedStyle(det).display === 'none';
  det.style.display = hidden ? 'block' : 'none';
  if (chev) chev.textContent = hidden ? '▲' : '▼';
};

/* F-03 사용량 카드 */
function _usageCards(meter) {
  const CFGS = [
    { key: '전기', icon: '⚡', unit: 'kWh', maxRef: 300 },
    { key: '수도', icon: '💧', unit: '톤',  maxRef: 20 },
    { key: '온수', icon: '🔥', unit: '톤',  maxRef: 10 },
    { key: '난방', icon: '🌡️', unit: 'Mcal', maxRef: 500 },
    { key: '냉방', icon: '❄️', unit: 'Mcal', maxRef: 500 },
  ];

  const cards = CFGS.map(cfg => {
    const m = meter[cfg.key];
    if (!m) return null;
    const 당월 = parseFloat(String(m['당월'] || m['당월지침'] || '0').replace(/,/g, '')) || 0;
    const 전월 = parseFloat(String(m['전월'] || m['전월지침'] || '0').replace(/,/g, '')) || 0;
    const usage = Math.max(당월 - 전월, 0);
    const fee = _n(m['요금']);
    if (usage === 0 && fee === 0) return null;

    const pct = Math.min(Math.round((usage / cfg.maxRef) * 100), 100);
    const gColor = pct > 80 ? '#ef4444' : pct > 50 ? '#f59e0b' : '#22c55e';

    return `<div class="fc-ucard">
      <div class="fc-uhead"><span>${cfg.icon}</span><span>${cfg.key}</span></div>
      <div class="fc-uval">${usage > 0 ? usage.toLocaleString() : '—'}<span class="fc-uunit"> ${cfg.unit}</span></div>
      ${fee > 0 ? `<div class="fc-ufee">${fee.toLocaleString()}원</div>` : ''}
      <div class="fc-gauge-bg"><div class="fc-gauge-fill" style="width:${pct}%;background:${gColor}"></div></div>
      <div class="fc-usub">${전월.toLocaleString()} → ${당월.toLocaleString()}</div>
    </div>`;
  }).filter(Boolean);

  if (!cards.length) return '';
  return `<div class="fc-card">
    <div class="fc-card-title">사용량 분석</div>
    <div class="fc-ugrid">${cards.join('')}</div>
  </div>`;
}

/* F-04 월별 추이 (Chart.js) */
function _historyChart() {
  return `<div class="fc-card">
    <div class="fc-card-title">월별 관리비 추이</div>
    <div style="position:relative;height:180px"><canvas id="fcHistChart"></canvas></div>
  </div>`;
}

function _drawHistChart(history) {
  const ctx = document.getElementById('fcHistChart');
  if (!ctx || !window.Chart) return;
  const labels = history.map(h => {
    const ym = String(h.year_month || '');
    return ym.length >= 6 ? `${parseInt(ym.slice(4, 6))}월` : '';
  });
  const amounts = history.map(h => h.amount);
  const lastI = amounts.length - 1;
  new window.Chart(ctx, {
    type: 'line',
    data: {
      labels,
      datasets: [{
        data: amounts,
        borderColor: '#1a56db',
        backgroundColor: 'rgba(26,86,219,0.07)',
        fill: true, tension: 0.35,
        pointBackgroundColor: amounts.map((_, i) => i === lastI ? '#1a56db' : 'rgba(26,86,219,0.45)'),
        pointRadius: amounts.map((_, i) => i === lastI ? 6 : 4),
        pointHoverRadius: 8,
      }],
    },
    options: {
      responsive: true, maintainAspectRatio: false,
      plugins: {
        legend: { display: false },
        tooltip: { callbacks: { label: c => c.parsed.y.toLocaleString('ko-KR') + '원' } },
      },
      scales: {
        y: {
          ticks: { callback: v => (v / 10000).toFixed(0) + '만', font: { size: 11 } },
          grid: { color: 'rgba(0,0,0,0.05)' },
        },
        x: { ticks: { font: { size: 11 } }, grid: { display: false } },
      },
    },
  });
}

/* F-05 AI 분석 카드 (규칙 기반) */
function _aiCard(d, history) {
  const msgs = [];
  const tips = [];
  const total = _n(d.total);

  if (history && history.length >= 2) {
    const prev = history[history.length - 2].amount;
    if (prev > 0) {
      const diff = total - prev;
      const pct = (diff / prev) * 100;
      if (pct > 10) {
        msgs.push(`이번 달 관리비가 지난달보다 <b>${pct.toFixed(1)}% 증가</b>했습니다.`);
      } else if (pct < -5) {
        msgs.push(`이번 달 관리비가 지난달보다 <b>${Math.abs(pct).toFixed(1)}% 감소</b>했습니다. 👍`);
      } else {
        msgs.push(`이번 달 관리비는 지난달과 비슷한 수준입니다.`);
      }
    }
  }

  const elec = d.meter && d.meter['전기'];
  if (elec) {
    const 당 = parseFloat(String(elec['당월'] || '0').replace(/,/g, '')) || 0;
    const 전 = parseFloat(String(elec['전월'] || '0').replace(/,/g, '')) || 0;
    const use = 당 - 전;
    if (use > 200) {
      msgs.push(`전기 사용량(${use.toFixed(0)}kWh)이 많은 편입니다.`);
      tips.push('💡 에어컨 설정온도를 1°C 높이면 약 7% 전기료가 절감됩니다.');
    } else if (use > 0 && use < 100) {
      msgs.push(`전기를 효율적으로 사용하고 있습니다. (${use.toFixed(0)}kWh) ⚡`);
    }
  }

  const 장기 = _n((d.billing_items || {})['장기수선충당금']);
  if (장기 > 0) {
    tips.push(`🔧 장기수선충당금(${장기.toLocaleString()}원)은 퇴거 시 돌려받을 수 있습니다.`);
  }

  if (!msgs.length && !tips.length) return '';

  return `<div class="fc-card">
    <div class="fc-card-title">🤖 AI 분석</div>
    <div style="font-size:13.5px;color:#374151;line-height:1.8">
      ${msgs.map(m => `<p style="margin:0 0 6px">• ${m}</p>`).join('')}
    </div>
    ${tips.length ? `<hr style="border:none;border-top:1px solid #f1f5f9;margin:12px 0">
    <div style="font-size:12.5px;color:#64748b;line-height:1.8">
      ${tips.map(t => `<p style="margin:0 0 4px">${t}</p>`).join('')}
    </div>` : ''}
  </div>`;
}

/* 메인 대시보드 렌더러 */
window.renderDashboard = async function(d, token, companyId) {
  const container = document.getElementById('dashContainer');
  if (!container) return;

  function _render(hist) {
    let html = _heroCard(d, hist);
    html += _donutChart(d.billing_items || {});
    html += _usageCards(d.meter || {});
    if (hist && hist.length >= 2) html += _historyChart();
    html += _aiCard(d, hist);
    container.innerHTML = html;
    container.style.display = '';
    _animateCount(document.getElementById('fcHeroAmt'), _n(d.total), 1200);

    if (hist && hist.length >= 2) {
      const draw = () => _drawHistChart(hist);
      if (window.Chart) {
        draw();
      } else {
        const s = document.createElement('script');
        s.src = 'https://cdn.jsdelivr.net/npm/chart.js@4/dist/chart.umd.min.js';
        s.onload = draw;
        document.head.appendChild(s);
      }
    }
  }

  _render(null); // Phase 1: 즉시 표시

  // Phase 2: 히스토리 비동기 로드
  try {
    const params = new URLSearchParams({ dong: d.dong, ho: d.ho, company_id: String(companyId) });
    const res = await fetch(`/api/fee/history?${params}`, {
      headers: { Authorization: `Bearer ${token}` },
    });
    if (res.ok) {
      const { history } = await res.json();
      if (history && history.length >= 1) _render(history);
    }
  } catch (_) {}
};
