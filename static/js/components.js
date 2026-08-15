// ===== SHARED LAYOUT COMPONENTS =====
// Injects sidebar, topbar, and bottom nav into pages
// JWT-aware: shows user initials, display name, and JWT logout

function renderSidebar(activePage) {
  const initials = typeof Auth !== "undefined" ? Auth.getUserInitials() : "U";
  const displayName = typeof Auth !== "undefined" ? Auth.getUserDisplayName() : "User";
  return `
  <aside class="sidebar" id="sidebar">
    <div class="sidebar-header">
      <div class="sidebar-logo">M</div>
      <span class="sidebar-title">MoneyMatrix</span>
    </div>
    <nav class="sidebar-nav">
      <a href="/" class="nav-item ${activePage === "dashboard" ? "active" : ""}">
        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><rect x="3" y="3" width="7" height="7" rx="1"/><rect x="14" y="3" width="7" height="7" rx="1"/><rect x="3" y="14" width="7" height="7" rx="1"/><rect x="14" y="14" width="7" height="7" rx="1"/></svg>
        <span class="nav-label">Dashboard</span>
      </a>
      <a href="/expenses/" class="nav-item ${activePage === "expenses" ? "active" : ""}">
        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M12 1v22M17 5H9.5a3.5 3.5 0 000 7h5a3.5 3.5 0 010 7H6"/></svg>
        <span class="nav-label">Expenses</span>
      </a>
      <a href="/budget/" class="nav-item ${activePage === 'budget' ? 'active' : ''}">
        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><rect x="2" y="7" width="20" height="14" rx="2" ry="2"></rect><path d="M16 21V5a2 2 0 0 0-2-2h-4a2 2 0 0 0-2 2v16"></path></svg>
        <span class="nav-label">Budget</span>
      </a>
      <a href="/profile/" class="nav-item ${activePage === "profile" ? "active" : ""}">
        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M20 21v-2a4 4 0 00-4-4H8a4 4 0 00-4 4v2"/><circle cx="12" cy="7" r="4"/></svg>
        <span class="nav-label">Profile</span>
      </a>
      <a href="/settings/" class="nav-item ${activePage === "settings" ? "active" : ""}">
        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="12" cy="12" r="3"/><path d="M19.4 15a1.65 1.65 0 00.33 1.82l.06.06a2 2 0 010 2.83 2 2 0 01-2.83 0l-.06-.06a1.65 1.65 0 00-1.82-.33 1.65 1.65 0 00-1 1.51V21a2 2 0 01-4 0v-.09A1.65 1.65 0 009 19.4a1.65 1.65 0 00-1.82.33l-.06.06a2 2 0 01-2.83 0 2 2 0 010-2.83l.06-.06A1.65 1.65 0 004.68 15a1.65 1.65 0 00-1.51-1H3a2 2 0 010-4h.09A1.65 1.65 0 004.6 9a1.65 1.65 0 00-.33-1.82l-.06-.06a2 2 0 012.83-2.83l.06.06A1.65 1.65 0 009 4.68a1.65 1.65 0 001-1.51V3a2 2 0 014 0v.09a1.65 1.65 0 001 1.51 1.65 1.65 0 001.82-.33l.06-.06a2 2 0 012.83 2.83l-.06.06A1.65 1.65 0 0019.4 9a1.65 1.65 0 001.51 1H21a2 2 0 010 4h-.09a1.65 1.65 0 00-1.51 1z"/></svg>
        <span class="nav-label">Settings</span>
      </a>
    </nav>
    
    <div class="sidebar-user" style="display:flex; align-items:center; gap:12px; padding:12px 16px; margin: 0 12px 8px; border-radius:8px; background:var(--bg-user-section); border:1px solid var(--border-color); overflow:hidden;">
      <div class="sidebar-user-avatar" style="width:32px; height:32px; border-radius:50%; background:var(--accent-primary); display:flex; align-items:center; justify-content:center; font-size:12px; font-weight:600; color:#fff; flex-shrink:0;">${initials}</div>
      <div class="sidebar-user-info" style="display:flex; align-items:center; justify-content:space-between; flex:1; min-width:0;">
        <span class="sidebar-user-name" style="font-size:13px; font-weight:500; color:var(--sidebar-text); white-space:nowrap; overflow:hidden; text-overflow:ellipsis; max-width:90px;">${displayName}</span>
        <button class="sidebar-logout-btn" onclick="handleLogout()" style="background:none; border:none; color:var(--accent-danger); cursor:pointer; display:flex; align-items:center; justify-content:center;" title="Logout">
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" width="16" height="16"><path d="M9 21H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h4M16 17l5-5-5-5M21 12H9"/></svg>
        </button>
      </div>
    </div>

    <div class="sidebar-footer">
      <button class="collapse-btn" id="collapseBtn">
        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" width="20" height="20"><polyline points="11 17 6 12 11 7"/><polyline points="18 17 13 12 18 7"/></svg>
        <span class="sidebar-footer-text">Collapse</span>
      </button>
    </div>
  </aside>`;
}

function renderTopbar(title, subtitle) {
  const initials = typeof Auth !== "undefined" ? Auth.getUserInitials() : "U";

  return `
  <header class="topbar">
    <div class="topbar-left">
      <button class="topbar-btn" id="menuBtn" style="display:none" onclick="document.getElementById('sidebar').classList.toggle('open')">
        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" width="20" height="20"><line x1="3" y1="6" x2="21" y2="6"/><line x1="3" y1="12" x2="21" y2="12"/><line x1="3" y1="18" x2="21" y2="18"/></svg>
      </button>
      <div>
        <h1 class="page-title">${title}</h1>
        <p class="page-subtitle">${subtitle}</p>
      </div>
    </div>
    <div class="topbar-right">
      <button class="topbar-btn" id="themeToggle" onclick="toggleTheme()"></button>
      <button class="topbar-btn" id="notifBtn">
        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" width="20" height="20"><path d="M18 8A6 6 0 006 8c0 7-3 9-3 9h18s-3-2-3-9"/><path d="M13.73 21a2 2 0 01-3.46 0"/></svg>
      </button>
      <div class="topbar-user" id="topbarUser">
        <a href="/profile/" style="text-decoration:none">
          <div class="avatar" id="topbarAvatar">${initials}</div>
        </a>
      </div>
    </div>
  </header>`;
}

function renderBottomNav(activePage) {
  return `
  <nav class="bottom-nav">
    <div class="bottom-nav-inner">
      <a href="/" class="bottom-nav-item ${activePage === "dashboard" ? "active" : ""}">
        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><rect x="3" y="3" width="7" height="7" rx="1"/><rect x="14" y="3" width="7" height="7" rx="1"/><rect x="3" y="14" width="7" height="7" rx="1"/><rect x="14" y="14" width="7" height="7" rx="1"/></svg>
        <span>Home</span>
      </a>
      <a href="/expenses/" class="bottom-nav-item ${activePage === "expenses" ? "active" : ""}">
        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M12 1v22M17 5H9.5a3.5 3.5 0 000 7h5a3.5 3.5 0 010 7H6"/></svg>
        <span>Expenses</span>
      </a>
      <a href="/budget/" class="bottom-nav-item ${activePage === 'budget' ? 'active' : ''}">
        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><rect x="2" y="7" width="20" height="14" rx="2" ry="2"></rect><path d="M16 21V5a2 2 0 0 0-2-2h-4a2 2 0 0 0-2 2v16"></path></svg>
        <span>Budget</span>
      </a>
      <a href="/profile/" class="bottom-nav-item ${activePage === "profile" ? "active" : ""}">
        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M20 21v-2a4 4 0 00-4-4H8a4 4 0 00-4 4v2"/><circle cx="12" cy="7" r="4"/></svg>
        <span>Profile</span>
      </a>
      <a href="/settings/" class="bottom-nav-item ${activePage === "settings" ? "active" : ""}">
        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="12" cy="12" r="3"/><path d="M19.4 15a1.65 1.65 0 00.33 1.82l.06.06a2 2 0 010 2.83 2 2 0 01-2.83 0l-.06-.06a1.65 1.65 0 00-1.82-.33 1.65 1.65 0 00-1 1.51V21a2 2 0 01-4 0v-.09A1.65 1.65 0 009 19.4a1.65 1.65 0 00-1.82.33l-.06.06a2 2 0 01-2.83 0 2 2 0 010-2.83l.06-.06A1.65 1.65 0 004.68 15a1.65 1.65 0 00-1.51-1H3a2 2 0 010-4h.09A1.65 1.65 0 004.6 9a1.65 1.65 0 00-.33-1.82l-.06-.06a2 2 0 012.83-2.83l.06.06A1.65 1.65 0 009 4.68a1.65 1.65 0 001-1.51V3a2 2 0 014 0v.09a1.65 1.65 0 001 1.51 1.65 1.65 0 001.82-.33l.06-.06a2 2 0 012.83 2.83l-.06.06A1.65 1.65 0 0019.4 9a1.65 1.65 0 001.51 1H21a2 2 0 010 4h-.09a1.65 1.65 0 00-1.51 1z"/></svg>
        <span>Settings</span>
      </a>
    </div>
  </nav>`;
}

function injectLayout(activePage, title, subtitle) {
  // Show menu btn on mobile
  const style = document.createElement("style");
  style.textContent =
    "@media(max-width:1024px){#menuBtn{display:flex!important}}";
  document.head.appendChild(style);
}

// ── JWT Logout handler ──
function handleLogout() {
  if (typeof Auth !== "undefined") {
    Auth.logout();
  } else {
    window.location.href = "/logout/";
  }
}

// ── Profile UI Updater ──
function updateProfileUI() {
  if (typeof Auth === "undefined") return;
  const initials = Auth.getUserInitials();
  const displayName = Auth.getUserDisplayName();

  // Update sidebar
  const sidebarAvatar = document.querySelector(".sidebar-user-avatar");
  if (sidebarAvatar) sidebarAvatar.textContent = initials;
  const sidebarName = document.querySelector(".sidebar-user-name");
  if (sidebarName) sidebarName.textContent = displayName;

  // Update topbar
  const topbarAvatar = document.getElementById("topbarAvatar");
  if (topbarAvatar) topbarAvatar.textContent = initials;
}
