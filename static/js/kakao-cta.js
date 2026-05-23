/**
 * kakao-cta.js
 * Shared Kakao CTA (Call-To-Action) button infrastructure
 *
 * Usage:
 *   <script src="js/kakao-cta.js"></script>
 *   <script>initKakaoCta('landing', 'general');</script>
 */

/* ============================================================
   1. Configuration
   ============================================================ */

var KAKAO_CONFIG = {
    channelUrl: 'http://pf.kakao.com/_xhxlpxdX/chat',
    ctas: {
        kakao_intro:            { label: '카카오로 소개자료 받기',   type: 'intro'   },
        kakao_pricing:          { label: '카카오로 요금 안내 받기',  type: 'pricing'  },
        kakao_demo:             { label: '카카오로 데모 안내 받기',  type: 'demo'     },
        kakao_case:             { label: '카카오로 사례 보기',       type: 'case'     },
        kakao_manager_consult:  { label: '카카오로 상담 예약하기',   type: 'consult'  },
        kakao_manager_intro:    { label: '카카오로 도입자료 받기',   type: 'intro'    },
        kakao_manager_pricing:  { label: '카카오로 요금 안내 받기',  type: 'pricing'  },
        kakao_manager_process:  { label: '카카오로 도입 절차 보기',  type: 'process'  },
        kakao_quick:            { label: '카카오 빠른상담',          type: 'consult'  }
    }
};

/* ============================================================
   2. Deep Link URL Builder
   ============================================================ */

function buildKakaoUrl(ctaType, pageName, section) {
    var config = KAKAO_CONFIG.ctas[ctaType];
    if (!config) {
        console.warn('[kakao-cta] Unknown ctaType:', ctaType);
        return KAKAO_CONFIG.channelUrl;
    }
    var params = new URLSearchParams();
    params.set('ref', pageName || '');
    params.set('type', config.type);
    if (section) {
        params.set('page', section);
    }

    // Append UTM params if present
    var utm = getUtmParams();
    Object.keys(utm).forEach(function (key) {
        if (utm[key]) params.set(key, utm[key]);
    });

    return KAKAO_CONFIG.channelUrl + '?' + params.toString();
}

/* ============================================================
   3. Device Detection
   ============================================================ */

function getDeviceType() {
    var ua = navigator.userAgent || '';
    if (/iPad|tablet|PlayBook/i.test(ua) ||
        (navigator.maxTouchPoints > 1 && /Macintosh/i.test(ua))) {
        return 'tablet';
    }
    if (/Mobile|Android.*Mobile|iPhone|iPod|BlackBerry|IEMobile|Opera Mini/i.test(ua)) {
        return 'mobile';
    }
    return 'desktop';
}

/* ============================================================
   4. UTM Parameter Extraction
   ============================================================ */

function getUtmParams() {
    var params = new URLSearchParams(window.location.search);
    return {
        utm_source:   params.get('utm_source')   || '',
        utm_medium:   params.get('utm_medium')    || '',
        utm_campaign: params.get('utm_campaign')  || ''
    };
}

/* ============================================================
   5. Session ID Generator
   ============================================================ */

function getOrCreateSessionId() {
    var key = 'kakao_cta_session';
    var id = sessionStorage.getItem(key);
    if (id) return id;

    // Generate UUID-like random string
    id = 'xxxxxxxx-xxxx-4xxx-yxxx-xxxxxxxxxxxx'.replace(/[xy]/g, function (c) {
        var r = (Math.random() * 16) | 0;
        var v = c === 'x' ? r : (r & 0x3) | 0x8;
        return v.toString(16);
    });
    sessionStorage.setItem(key, id);
    return id;
}

/* ============================================================
   6. Click Log Function (async, non-blocking)
   ============================================================ */

var CTA_LOG_QUEUE_KEY = 'kakao_cta_failed_logs';

function logCtaClick(ctaType, pagePath, visitorType, funnelStep, sessionId) {
    var payload = {
        cta_type:     ctaType,
        page_path:    window.location.pathname || pagePath,
        visitor_type: visitorType,
        funnel_step:  funnelStep,
        session_id:   sessionId || getOrCreateSessionId(),
        device_type:  getDeviceType(),
        referrer:     document.referrer || ''
    };

    // Append UTM data
    var utm = getUtmParams();
    if (utm.utm_source)   payload.utm_source   = utm.utm_source;
    if (utm.utm_medium)   payload.utm_medium   = utm.utm_medium;
    if (utm.utm_campaign) payload.utm_campaign = utm.utm_campaign;

    // Fire-and-forget: never block navigation
    return fetch('/api/cta-logs', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload)
    }).catch(function () {
        // On failure, queue for retry in localStorage
        _enqueueFailedLog(payload);
    });
}

function _enqueueFailedLog(payload) {
    try {
        var queue = JSON.parse(localStorage.getItem(CTA_LOG_QUEUE_KEY) || '[]');
        queue.push(payload);
        // Cap at 50 entries to avoid storage bloat
        if (queue.length > 50) queue = queue.slice(-50);
        localStorage.setItem(CTA_LOG_QUEUE_KEY, JSON.stringify(queue));
    } catch (e) {
        // Storage full or unavailable; silently drop
    }
}

function retryFailedLogs() {
    var raw;
    try {
        raw = localStorage.getItem(CTA_LOG_QUEUE_KEY);
    } catch (e) {
        return;
    }
    if (!raw) return;

    var queue;
    try {
        queue = JSON.parse(raw);
    } catch (e) {
        localStorage.removeItem(CTA_LOG_QUEUE_KEY);
        return;
    }
    if (!Array.isArray(queue) || queue.length === 0) return;

    // Clear immediately so concurrent loads don't double-send
    localStorage.removeItem(CTA_LOG_QUEUE_KEY);

    queue.forEach(function (payload) {
        fetch('/api/cta-logs', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(payload)
        }).catch(function () {
            _enqueueFailedLog(payload);
        });
    });
}

/* ============================================================
   7. Kakao Redirect Modal (session-based, 1-time)
   ============================================================ */

function handleCtaClick(ctaType, pageName, section, visitorType) {
    var sessionId = getOrCreateSessionId();

    // Log the click (non-blocking)
    logCtaClick(ctaType, pageName, visitorType, 'click', sessionId);

    // Check if modal has already been shown this session
    if (sessionStorage.getItem('kakao_modal_shown') === 'true') {
        navigateToKakao(ctaType, pageName, section, visitorType, sessionId);
    } else {
        showKakaoModal(ctaType, pageName, section, visitorType, sessionId);
    }
}

function showKakaoModal(ctaType, pageName, section, visitorType, sessionId) {
    // Mark as shown for this session
    sessionStorage.setItem('kakao_modal_shown', 'true');

    // Log modal open
    logCtaClick(ctaType, pageName, visitorType, 'modal_open', sessionId);

    // Remove existing modal if any
    var existing = document.getElementById('kakao-modal-overlay');
    if (existing) existing.remove();

    var isMobile = getDeviceType() === 'mobile';

    // Build overlay
    var overlay = document.createElement('div');
    overlay.id = 'kakao-modal-overlay';
    overlay.setAttribute('role', 'dialog');
    overlay.setAttribute('aria-modal', 'true');
    overlay.setAttribute('aria-label', '카카오 채널 이동 안내');
    overlay.style.cssText = 'position:fixed;top:0;left:0;width:100%;height:100%;' +
        'background:rgba(0,0,0,0.5);z-index:10000;display:flex;' +
        (isMobile ? 'align-items:flex-end;' : 'align-items:center;') +
        'justify-content:center;';

    // Build dialog box
    var dialog = document.createElement('div');
    dialog.className = 'kakao-modal-dialog';
    dialog.style.cssText = 'background:#fff;padding:28px 24px 20px;max-width:400px;width:100%;' +
        'box-shadow:var(--shadow-lg, 0 8px 24px rgba(45,74,43,0.12));' +
        (isMobile
            ? 'border-radius:16px 16px 0 0;position:fixed;bottom:0;left:0;right:0;max-width:100%;'
            : 'border-radius:var(--radius-md, 8px);');

    // Icon
    var icon = document.createElement('div');
    icon.style.cssText = 'font-size:36px;text-align:center;margin-bottom:12px;';
    icon.textContent = '\uD83D\uDCAC';
    dialog.appendChild(icon);

    // Message
    var msg = document.createElement('p');
    msg.style.cssText = 'text-align:center;font-size:15px;line-height:1.6;color:#333;margin:0 0 24px;';
    msg.textContent = '카카오에서 소개자료, 도입절차, 상담 예약을 이어서 안내해드립니다.';
    dialog.appendChild(msg);

    // Button container
    var btnWrap = document.createElement('div');
    btnWrap.style.cssText = 'display:flex;gap:10px;';

    // Secondary button (닫기)
    var btnClose = document.createElement('button');
    btnClose.type = 'button';
    btnClose.textContent = '닫기';
    btnClose.setAttribute('aria-label', '모달 닫기');
    btnClose.style.cssText = 'flex:1;padding:12px 0;border:1px solid #ccc;background:#fff;' +
        'border-radius:var(--radius-md, 8px);font-size:15px;color:#555;cursor:pointer;';

    // Primary button (카카오로 이동)
    var btnGo = document.createElement('button');
    btnGo.type = 'button';
    btnGo.textContent = '카카오로 이동';
    btnGo.setAttribute('aria-label', '카카오 채널로 이동');
    btnGo.style.cssText = 'flex:1;padding:12px 0;border:none;background:#FEE500;' +
        'border-radius:var(--radius-md, 8px);font-size:15px;font-weight:600;' +
        'color:#3C1E1E;cursor:pointer;';

    btnWrap.appendChild(btnClose);
    btnWrap.appendChild(btnGo);
    dialog.appendChild(btnWrap);
    overlay.appendChild(dialog);
    document.body.appendChild(overlay);

    // --- Event handlers ---

    function closeModal() {
        overlay.remove();
        // Restore focus to previously focused element
        if (_previousFocus && _previousFocus.focus) _previousFocus.focus();
    }

    var _previousFocus = document.activeElement;

    btnClose.addEventListener('click', closeModal);
    overlay.addEventListener('click', function (e) {
        if (e.target === overlay) closeModal();
    });

    btnGo.addEventListener('click', function () {
        closeModal();
        navigateToKakao(ctaType, pageName, section, visitorType, sessionId);
    });

    // ESC to close
    function onKeydown(e) {
        if (e.key === 'Escape') {
            closeModal();
            document.removeEventListener('keydown', onKeydown);
            return;
        }
        // Focus trap
        if (e.key === 'Tab') {
            var focusable = [btnClose, btnGo];
            var first = focusable[0];
            var last = focusable[focusable.length - 1];
            if (e.shiftKey) {
                if (document.activeElement === first) {
                    e.preventDefault();
                    last.focus();
                }
            } else {
                if (document.activeElement === last) {
                    e.preventDefault();
                    first.focus();
                }
            }
        }
    }
    document.addEventListener('keydown', onKeydown);

    // Auto-focus primary button
    btnGo.focus();
}

function navigateToKakao(ctaType, pageName, section, visitorType, sessionId) {
    // Log redirect (non-blocking), then navigate
    logCtaClick(ctaType, pageName, visitorType, 'kakao_redirect', sessionId || getOrCreateSessionId());
    var url = buildKakaoUrl(ctaType, pageName, section);
    window.open(url, '_blank');
}

/* ============================================================
   8. Mobile Floating CTA
   ============================================================ */

function initFloatingCta(pageName, visitorType) {
    // Only show on mobile (< 768px)
    if (window.innerWidth >= 768) return;

    // Prevent duplicate
    if (document.getElementById('kakao-floating-cta')) return;

    var btn = document.createElement('button');
    btn.id = 'kakao-floating-cta';
    btn.type = 'button';
    btn.setAttribute('role', 'button');
    btn.setAttribute('aria-label', '카카오 채널 빠른 상담');
    btn.textContent = '카카오 빠른상담';
    btn.style.cssText = 'position:fixed;bottom:20px;right:16px;z-index:9999;' +
        'background:#FEE500;color:#3C1E1E;border:none;border-radius:24px;' +
        'padding:14px 20px;font-size:14px;font-weight:600;' +
        'min-width:48px;min-height:48px;cursor:pointer;' +
        'box-shadow:0 4px 12px rgba(0,0,0,0.2);' +
        'display:flex;align-items:center;gap:6px;';

    // Kakao icon prefix (chat bubble emoji)
    var iconSpan = document.createElement('span');
    iconSpan.style.cssText = 'font-size:18px;line-height:1;';
    iconSpan.textContent = '\uD83D\uDCAC';
    btn.insertBefore(iconSpan, btn.firstChild);

    btn.addEventListener('click', function () {
        _showActionSheet(pageName, visitorType);
    });

    document.body.appendChild(btn);
}

function _showActionSheet(pageName, visitorType) {
    // Remove existing sheet if any
    var existing = document.getElementById('kakao-action-sheet-overlay');
    if (existing) existing.remove();

    // Determine options based on visitor type
    var options;
    if (visitorType === 'manager') {
        options = [
            { ctaType: 'kakao_manager_intro',   label: '도입자료 받기'   },
            { ctaType: 'kakao_manager_pricing',  label: '요금 안내 받기'  },
            { ctaType: 'kakao_manager_consult',  label: '상담 예약'       }
        ];
    } else {
        options = [
            { ctaType: 'kakao_intro', label: '소개자료 받기' },
            { ctaType: 'kakao_demo',  label: '데모 안내 받기' },
            { ctaType: 'kakao_quick', label: '빠른 문의'      }
        ];
    }

    // Overlay
    var overlay = document.createElement('div');
    overlay.id = 'kakao-action-sheet-overlay';
    overlay.setAttribute('role', 'dialog');
    overlay.setAttribute('aria-modal', 'true');
    overlay.setAttribute('aria-label', '카카오 상담 옵션 선택');
    overlay.style.cssText = 'position:fixed;top:0;left:0;width:100%;height:100%;' +
        'background:rgba(0,0,0,0.4);z-index:10001;display:flex;' +
        'align-items:flex-end;justify-content:center;';

    // Sheet
    var sheet = document.createElement('div');
    sheet.className = 'kakao-action-sheet';
    sheet.style.cssText = 'background:#fff;width:100%;max-width:100%;' +
        'border-radius:16px 16px 0 0;padding:16px 16px 24px;' +
        'box-shadow:var(--shadow-lg, 0 8px 24px rgba(45,74,43,0.12));';

    // Title
    var title = document.createElement('div');
    title.style.cssText = 'font-size:15px;font-weight:600;color:#333;text-align:center;' +
        'padding-bottom:12px;margin-bottom:8px;border-bottom:1px solid #eee;';
    title.textContent = '카카오 빠른상담';
    sheet.appendChild(title);

    // Option buttons
    var firstBtn = null;
    options.forEach(function (opt, idx) {
        var optBtn = document.createElement('button');
        optBtn.type = 'button';
        optBtn.textContent = opt.label;
        optBtn.setAttribute('aria-label', opt.label);
        optBtn.style.cssText = 'display:block;width:100%;padding:14px 16px;' +
            'border:none;background:transparent;font-size:15px;color:#333;' +
            'text-align:left;cursor:pointer;border-radius:8px;' +
            'min-height:48px;';
        optBtn.addEventListener('mouseenter', function () {
            optBtn.style.background = '#f5f5f5';
        });
        optBtn.addEventListener('mouseleave', function () {
            optBtn.style.background = 'transparent';
        });
        optBtn.addEventListener('click', function () {
            closeSheet();
            handleCtaClick(opt.ctaType, pageName, 'floating_cta', visitorType);
        });
        sheet.appendChild(optBtn);
        if (idx === 0) firstBtn = optBtn;
    });

    // Cancel button
    var cancelBtn = document.createElement('button');
    cancelBtn.type = 'button';
    cancelBtn.textContent = '닫기';
    cancelBtn.setAttribute('aria-label', '액션 시트 닫기');
    cancelBtn.style.cssText = 'display:block;width:100%;padding:14px 16px;margin-top:8px;' +
        'border:1px solid #eee;background:#f9f9f9;font-size:15px;color:#888;' +
        'text-align:center;cursor:pointer;border-radius:8px;min-height:48px;';
    sheet.appendChild(cancelBtn);

    overlay.appendChild(sheet);
    document.body.appendChild(overlay);

    var _prevFocus = document.activeElement;

    function closeSheet() {
        overlay.remove();
        if (_prevFocus && _prevFocus.focus) _prevFocus.focus();
    }

    cancelBtn.addEventListener('click', closeSheet);
    overlay.addEventListener('click', function (e) {
        if (e.target === overlay) closeSheet();
    });

    // ESC to close
    function onKey(e) {
        if (e.key === 'Escape') {
            closeSheet();
            document.removeEventListener('keydown', onKey);
        }
    }
    document.addEventListener('keydown', onKey);

    // Focus first option
    if (firstBtn) firstBtn.focus();
}

/* ============================================================
   9. Impression Tracking (IntersectionObserver)
   ============================================================ */

function initImpressionTracking(pageName, visitorType) {
    if (typeof IntersectionObserver === 'undefined') return;

    var observed = new Set();
    var observer = new IntersectionObserver(function (entries) {
        entries.forEach(function (entry) {
            if (!entry.isIntersecting) return;
            var btn = entry.target;
            var ctaType = btn.getAttribute('data-cta');
            if (!ctaType) return;

            // Log impression only once per CTA per session
            var key = 'imp_' + ctaType + '_' + pageName;
            if (observed.has(key)) return;
            observed.add(key);

            logCtaClick(ctaType, pageName, visitorType, 'impression', getOrCreateSessionId());
        });
    }, { threshold: 0.5 });

    // Observe all CTA buttons with data-cta attribute
    document.querySelectorAll('[data-cta]').forEach(function (btn) {
        observer.observe(btn);
    });
}

/* ============================================================
   10. Initialize on page load
   ============================================================ */

function initKakaoCta(pageName, visitorType) {
    retryFailedLogs();
    initFloatingCta(pageName, visitorType);
    initImpressionTracking(pageName, visitorType);
}
