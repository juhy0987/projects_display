// ── Sidebar toggle ────────────────────────────────────────────────────────────

const SIDEBAR_KEY = 'sidebar-collapsed';

/**
 * @param {HTMLElement} sidebarTab
 * @param {HTMLElement|null} sidebarPanel
 * @param {boolean} collapsed
 */
function applySidebarState(sidebarTab, sidebarPanel, collapsed) {
  document.body.classList.toggle('sidebar-collapsed', collapsed);
  sidebarTab.setAttribute('aria-expanded', String(!collapsed));

  if (sidebarPanel) {
    sidebarPanel.setAttribute('aria-hidden', String(collapsed));
    sidebarPanel.inert = collapsed;

    // 접힘 시 포커스가 사이드바 안에 있으면 탭으로 이동
    if (collapsed && sidebarPanel.contains(document.activeElement)) {
      sidebarTab.focus();
    }
  }
}

/**
 * Initialise sidebar toggle behaviour.
 * @param {HTMLElement} sidebarTab
 * @param {HTMLElement|null} sidebarPanel
 */
export function initSidebar(sidebarTab, sidebarPanel) {
  applySidebarState(sidebarTab, sidebarPanel, localStorage.getItem(SIDEBAR_KEY) === 'true');

  function toggleSidebar() {
    const collapsed = !document.body.classList.contains('sidebar-collapsed');
    applySidebarState(sidebarTab, sidebarPanel, collapsed);
    localStorage.setItem(SIDEBAR_KEY, String(collapsed));
  }

  sidebarTab.addEventListener('click', toggleSidebar);
  sidebarTab.addEventListener('keydown', (e) => {
    if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); toggleSidebar(); }
  });
}
