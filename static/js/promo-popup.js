/**
 * 이벤트 팝업 (공용) — 어느 페이지에서든 동작
 * 팝업 HTML이 페이지에 있으면 자동 실행, "오늘 안보기" localStorage 지원
 */
(function () {
    var STORAGE_KEY = 'promo_hide_date';

    function getToday() {
        var d = new Date();
        return d.getFullYear() + '-' +
            String(d.getMonth() + 1).padStart(2, '0') + '-' +
            String(d.getDate()).padStart(2, '0');
    }

    function init() {
        var overlay = document.getElementById('promoPopup');
        if (!overlay) return;

        var closeBtn = document.getElementById('promoPopupClose');
        var confirmBtn = document.getElementById('promoPopupConfirm');
        var todayCheck = document.getElementById('promoTodayCheck');
        var today = getToday();

        function openPopup() {
            overlay.classList.add('show');
            document.body.style.overflow = 'hidden';
        }

        function closePopup() {
            if (todayCheck && todayCheck.checked) {
                localStorage.setItem(STORAGE_KEY, today);
            }
            overlay.classList.remove('show');
            document.body.style.overflow = '';
            // 팝업 닫힘 알림 (도입글 등 대기 중인 요소에 전달)
            document.dispatchEvent(new Event('promoPopupClosed'));
        }

        // "오늘 안보기" 확인 후 자동 표시
        if (localStorage.getItem(STORAGE_KEY) !== today) {
            openPopup();
        } else {
            // 팝업 안 뜨면 즉시 알림
            document.dispatchEvent(new Event('promoPopupClosed'));
        }

        // 닫기 버튼
        if (closeBtn) closeBtn.addEventListener('click', closePopup);
        if (confirmBtn) confirmBtn.addEventListener('click', closePopup);

        // 오버레이 배경 클릭
        overlay.addEventListener('click', function (e) {
            if (e.target === overlay) closePopup();
        });

        // ESC 키
        document.addEventListener('keydown', function (e) {
            if (e.key === 'Escape' && overlay.classList.contains('show')) closePopup();
        });
    }

    // DOM 준비 후 실행
    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', init);
    } else {
        init();
    }
})();
