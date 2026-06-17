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

  let prevCol = '';
  if (history && history.length >= 2) {
    const prev = history[history.length - 2].amount;
    if (prev > 0) {
      const diff = total - prev;
      const pct = ((diff / prev) * 100).toFixed(1);
      const up = diff >= 0;
      prevCol = `<div>📈 지난달 대비<br>`
        + `<b style="color:${up ? '#fca5a5' : '#86efac'}">`
        + `${up ? '+' : ''}${diff.toLocaleString()}원 (${up ? '+' : ''}${pct}%)</b></div>`;
    }
  } else if (history && history.length === 1) {
    prevCol = `<div>📈 지난달 대비<br><b style="opacity:.7">비교 데이터 없음</b></div>`;
  }

  const compareHtml = prevCol
    ? `<div style="display:flex;gap:20px;margin-top:10px;font-size:12.5px;opacity:.95;line-height:1.6">${prevCol}</div>`
    : '';

  return `<div class="fc-hero">
    <div style="font-size:13px;opacity:.75;margin-bottom:6px">🏠 ${d.dong}동 ${d.ho}호 · ${ymLabel}</div>
    <div style="font-size:13px;opacity:.8;margin-bottom:2px">이번달 관리비</div>
    <div class="fc-hero-amt" id="fcHeroAmt">0원</div>
    ${compareHtml}
  </div>`;
}

/* F-02 도넛 차트 */
function _donutChart(billing, vat) {
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
  if (vat > 0) { etcSum += vat; etcItems['부가가치세'] = vat; }
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
const _FC_USAGE_AVG_KEY = { '전기': 'electricity_kwh', '수도': 'water_ton', '온수': 'hotwater_ton' };

function _usageCards(meter, avg) {
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

    // 단지 평균의 2배를 기준치로 잡아 평균=50%, 평균의 1.6배 이상=빨강이 되도록 함
    const avgKey = _FC_USAGE_AVG_KEY[cfg.key];
    const avgUsage = avgKey && avg && avg[avgKey] ? avg[avgKey].avg : null;
    const maxRef = avgUsage ? avgUsage * 2 : cfg.maxRef;

    const pct = Math.min(Math.round((usage / maxRef) * 100), 100);
    const gColor = pct > 80 ? '#ef4444' : pct > 50 ? '#f59e0b' : '#22c55e';

    return `<div class="fc-ucard">
      <div class="fc-uhead"><span>${cfg.icon}</span><span>${cfg.key}</span></div>
      <div class="fc-uval">${usage > 0 ? usage.toLocaleString() : '—'}<span class="fc-uunit"> ${cfg.unit}</span></div>
      ${fee > 0 ? `<div class="fc-ufee">${fee.toLocaleString()}원</div>` : ''}
      <div class="fc-gauge-bg"><div class="fc-gauge-fill" style="width:${pct}%;background:${gColor}"></div></div>
      <div class="fc-usub">${전월.toLocaleString()} → ${당월.toLocaleString()}</div>
      ${avgUsage ? `<div class="fc-uavg">단지 평균 ${avgUsage.toLocaleString()}${cfg.unit}</div>` : ''}
    </div>`;
  }).filter(Boolean);

  if (!cards.length) return '';
  return `<div class="fc-card">
    <div class="fc-card-title">사용량 분석</div>
    <div class="fc-ugrid">${cards.join('')}</div>
  </div>`;
}

/* F-03.5 단지 비교 분석 카드 (관리비/전기/수도/온수 — 우리집 vs 단지 평균) */
function _cmpRow2(label, icon, myVal, avgVal) {
  if (myVal == null || avgVal == null) return '';
  const ok = myVal <= avgVal;
  const color = ok ? '#22c55e' : '#ef4444';
  const maxV = Math.max(myVal, avgVal) || 1;
  const myPct = Math.max((myVal / maxV) * 100, 2);
  const avgPct = Math.max((avgVal / maxV) * 100, 2);

  return `<div class="fc-cmp2-row">
    <div class="fc-cmp2-head"><span>${ok ? '✅' : '⚠️'}</span><span class="fc-cmp2-label">${icon} ${label}</span></div>
    <div class="fc-cmp2-val">
      <span class="fc-cmp2-vlabel fc-cmp2-mine">우리집</span>
      <span class="fc-cmp2-bar-bg"><span class="fc-cmp2-bar" style="width:${myPct}%;background:${color}"></span></span>
      <span class="fc-cmp2-vamt" style="color:${color}">${Math.round(myVal).toLocaleString()}원</span>
    </div>
    <div class="fc-cmp2-val">
      <span class="fc-cmp2-vlabel">단지 평균</span>
      <span class="fc-cmp2-bar-bg"><span class="fc-cmp2-bar" style="width:${avgPct}%;background:#94a3b8"></span></span>
      <span class="fc-cmp2-vamt">${Math.round(avgVal).toLocaleString()}원</span>
    </div>
  </div>`;
}

/* 백엔드 average 집계와 동일한 항목 그룹 (검침 '요금'은 단가라 총비용 비교에 부적합) */
const _FC_ELEC_FEE_ITEMS = ['세대전기료', '냉난방동력전기', '공동전기료', '공동전력기금', '세대전력기금', '승강기전기'];
const _FC_WATER_FEE_ITEMS = ['세대수도료', '공동수도료', '하수도료', '물이용부담금'];
const _FC_HOTWATER_FEE_ITEMS = ['세대급탕비'];

function _sumItems(billing, keys) {
  return keys.reduce((s, k) => s + _n(billing[k]), 0);
}

function _compareCard(d, avg) {
  if (!avg) return '';
  const billing = d.billing_items || {};
  const elecFee = _sumItems(billing, _FC_ELEC_FEE_ITEMS) || null;
  const waterFee = _sumItems(billing, _FC_WATER_FEE_ITEMS) || null;
  const hotFee = _sumItems(billing, _FC_HOTWATER_FEE_ITEMS) || null;

  const rows = [
    _cmpRow2('관리비', '🏢', _n(d.total) || null, avg.amount && avg.amount.avg),
    _cmpRow2('전기', '⚡', elecFee, avg.electricity_fee && avg.electricity_fee.avg),
    _cmpRow2('수도', '💧', waterFee, avg.water_fee && avg.water_fee.avg),
    _cmpRow2('온수', '🔥', hotFee, avg.hotwater_fee && avg.hotwater_fee.avg),
  ].filter(Boolean);

  if (!rows.length) return '';
  return `<div class="fc-card">
    <div class="fc-card-title">단지 비교 분석</div>
    ${rows.join('')}
  </div>`;
}

/* F-04 월별 추이 (Chart.js) */
function _historyChart(history) {
  if (!history || !history.length) return '';

  if (history.length < 3) {
    return `<div class="fc-card">
      <div class="fc-card-title">월별 관리비 추이</div>
      <div style="text-align:center;color:#94a3b8;font-size:13px;padding:20px 0;line-height:1.7">
        📊 데이터 누적 중입니다 (현재 ${history.length}개월)<br>
        <span style="font-size:11.5px">3개월 이상 쌓이면 추이 그래프가 표시됩니다.</span>
      </div>
    </div>`;
  }

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
function _aiCard(d, history, avg) {
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
    if (use > 0 && avg && avg.electricity_kwh) {
      const ratio = use / avg.electricity_kwh.avg;
      if (ratio > 1.1) {
        msgs.push(`전기 사용량이 단지 평균보다 <b>${Math.round((ratio - 1) * 100)}% 높습니다</b>.`);
        tips.push('💡 에어컨 설정온도를 1°C 높이면 약 7% 전기료가 절감됩니다.');
      } else if (ratio < 0.9) {
        msgs.push(`전기 절약을 잘 실천하고 계세요! 평균보다 <b>${Math.round((1 - ratio) * 100)}% 적게</b> 사용했습니다. 👍`);
      }
    } else if (use > 200) {
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

  function _render(hist, avg) {
    const vat = _n((d.summary || {})['부가가치세']);
    let html = _heroCard(d, hist);
    html += _donutChart(d.billing_items || {}, vat);
    html += _usageCards(d.meter || {}, avg);
    html += _compareCard(d, avg);
    html += _historyChart(hist);
    html += _aiCard(d, hist, avg);
    container.innerHTML = html;
    container.style.display = '';
    _animateCount(document.getElementById('fcHeroAmt'), _n(d.total), 1200);

    if (hist && hist.length >= 3) {
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

  _render(null, null); // Phase 1: 즉시 표시

  // Phase 2: 히스토리/단지평균 비동기 로드
  try {
    const histParams = new URLSearchParams({ dong: d.dong, ho: d.ho, company_id: String(companyId) });
    const avgParams = new URLSearchParams({ dong: d.dong, ho: d.ho, company_id: String(companyId), year_month: d.year_month || '' });
    const authHeader = { Authorization: `Bearer ${token}` };

    const [histRes, avgRes] = await Promise.all([
      fetch(`/api/fee/history?${histParams}`, { headers: authHeader }),
      fetch(`/api/fee/average?${avgParams}`, { headers: authHeader }),
    ]);

    const hist = histRes.ok ? (await histRes.json()).history : null;
    const avg = avgRes.ok ? await avgRes.json() : null;

    if ((hist && hist.length >= 1) || (avg && avg.amount)) _render(hist, avg);
  } catch (_) {}
};
