/* 우리아파트 당근 — 공통 JS */

const API = '/api/market';

// ── 토큰 관리 ─────────────────────────────────────────────────────────────────

const MarketAuth = {
  getToken: () => sessionStorage.getItem('market_token'),
  getUser:  () => { try { return JSON.parse(sessionStorage.getItem('market_user') || 'null'); } catch { return null; } },
  save(token, user) {
    sessionStorage.setItem('market_token', token);
    sessionStorage.setItem('market_user', JSON.stringify(user));
  },
  clear() {
    sessionStorage.removeItem('market_token');
    sessionStorage.removeItem('market_user');
  },
  required() {
    if (!this.getToken()) {
      location.href = '/market-login.html';
      throw new Error('not logged in');
    }
    return this.getToken();
  },
};

// ── fetch helper ─────────────────────────────────────────────────────────────

async function mktFetch(path, opts = {}) {
  const token = MarketAuth.getToken();
  const headers = { ...(opts.headers || {}) };
  if (token) headers['Authorization'] = `Bearer ${token}`;
  if (opts.body && typeof opts.body === 'object' && !(opts.body instanceof FormData)) {
    headers['Content-Type'] = 'application/json';
    opts.body = JSON.stringify(opts.body);
  }
  const res = await fetch(API + path, { ...opts, headers });
  if (res.status === 401) { MarketAuth.clear(); location.href = '/market-login.html'; throw new Error('401'); }
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: '오류가 발생했습니다.' }));
    throw new Error(err.detail || '오류가 발생했습니다.');
  }
  return res.json();
}

// ── toast ─────────────────────────────────────────────────────────────────────

function showToast(msg) {
  let t = document.querySelector('.mkt-toast');
  if (!t) {
    t = document.createElement('div');
    t.className = 'mkt-toast';
    document.body.appendChild(t);
  }
  t.textContent = msg;
  t.classList.add('show');
  setTimeout(() => t.classList.remove('show'), 2500);
}

// ── 시간 표시 ─────────────────────────────────────────────────────────────────

function timeAgo(iso) {
  const diff = (Date.now() - new Date(iso)) / 1000;
  if (diff < 60) return '방금 전';
  if (diff < 3600) return `${Math.floor(diff / 60)}분 전`;
  if (diff < 86400) return `${Math.floor(diff / 3600)}시간 전`;
  return `${Math.floor(diff / 86400)}일 전`;
}

// ── 가격 표시 ─────────────────────────────────────────────────────────────────

function formatPrice(price, category) {
  if (category === '무료나눔' || price === 0) return '무료나눔';
  return price.toLocaleString() + '원';
}

// ── 상태 배지 ─────────────────────────────────────────────────────────────────

function statusBadge(status) {
  const map = {
    '판매중':  ['badge-sell',    '판매중'],
    '예약중':  ['badge-reserve', '예약중'],
    '거래완료': ['badge-done',    '거래완료'],
  };
  const [cls, label] = map[status] || ['badge-sell', status];
  return `<span class="badge ${cls}">${label}</span>`;
}

// ── 카테고리 이모지 ───────────────────────────────────────────────────────────

function categoryEmoji(cat) {
  return { '중고거래': '🛍', '무료나눔': '🎁', '공동구매': '🤝', '분실물': '🔍' }[cat] || '📦';
}
