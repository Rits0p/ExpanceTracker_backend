// ===== EXPENSE TRACKER - SHARED APP JS =====

// --- Theme ---
// --- Theme ---
function initTheme() {
  const theme = Settings.get("theme") || "dark";
  if (theme === "light") {
    document.body.classList.add("light-mode");
  } else {
    document.body.classList.remove("light-mode");
  }
  updateThemeIcon();
}
function toggleTheme() {
  document.body.classList.toggle("light-mode");
  const isLight = document.body.classList.contains("light-mode");
  const newTheme = isLight ? "light" : "dark";
  Settings.set("theme", newTheme);
  updateThemeIcon();
  if (typeof updateChartsTheme === "function") updateChartsTheme();
}
function updateThemeIcon() {
  const btn = document.getElementById("themeToggle");
  if (!btn) return;
  const isLight = document.body.classList.contains("light-mode");
  btn.innerHTML = isLight
    ? '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" width="20" height="20"><path d="M21 12.79A9 9 0 1111.21 3a7 7 0 009.79 9.79z"/></svg>'
    : '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" width="20" height="20"><circle cx="12" cy="12" r="5"/><path d="M12 1v2M12 21v2M4.22 4.22l1.42 1.42M18.36 18.36l1.42 1.42M1 12h2M21 12h2M4.22 19.78l1.42-1.42M18.36 5.64l1.42-1.42"/></svg>';
}

// --- Sidebar ---
function applySidebarState() {
  const sidebar = document.getElementById("sidebar");
  if (!sidebar) return;
  const collapsed = Settings.get("sidebarCollapsed") === true;
  if (collapsed && window.innerWidth > 1024) {
    sidebar.classList.add("collapsed");
  } else {
    sidebar.classList.remove("collapsed");
  }
}

function initSidebar() {
  const sidebar = document.getElementById("sidebar");
  const collapseBtn = document.getElementById("collapseBtn");
  const menuBtn = document.getElementById("menuBtn");
  if (!sidebar) return;
  if (collapseBtn) {
    collapseBtn.addEventListener("click", () => {
      sidebar.classList.toggle("collapsed");
      Settings.set(
        "sidebarCollapsed",
        sidebar.classList.contains("collapsed")
      );
      // Trigger instant and delayed window resize to adjust layout and charts
      window.dispatchEvent(new Event("resize"));
      setTimeout(() => {
        window.dispatchEvent(new Event("resize"));
      }, 260);
    });
  }
  if (menuBtn) {
    menuBtn.addEventListener("click", () => sidebar.classList.toggle("open"));
  }
  // Close sidebar on mobile when clicking outside
  document.addEventListener("click", (e) => {
    if (
      window.innerWidth <= 1024 &&
      sidebar.classList.contains("open") &&
      !sidebar.contains(e.target) &&
      e.target !== menuBtn
    ) {
      sidebar.classList.remove("open");
    }
  });
  // Restore state
  applySidebarState();
  // Set active nav based on current URL path
  const currentPath = location.pathname;
  document.querySelectorAll(".nav-item").forEach((item) => {
    const href = item.getAttribute("href");
    if (href === currentPath || (href === "/" && currentPath === "/")) {
      item.classList.add("active");
    }
  });
  document.querySelectorAll(".bottom-nav-item").forEach((item) => {
    const href = item.getAttribute("href");
    if (href === currentPath || (href === "/" && currentPath === "/")) {
      item.classList.add("active");
    }
  });
}

// --- Animated Counter ---
function animateCounter(el, target, prefix = "", suffix = "", duration = 1200) {
  if (!el) return;
  let start = 0;
  const step = (timestamp) => {
    if (!start) start = timestamp;
    const progress = Math.min((timestamp - start) / duration, 1);
    const eased = 1 - Math.pow(1 - progress, 3);
    el.textContent =
      prefix + Math.floor(target * eased).toLocaleString() + suffix;
    if (progress < 1) requestAnimationFrame(step);
  };
  requestAnimationFrame(step);
}

// --- Toast ---
function showToast(message, type = "success") {
  let container = document.querySelector(".toast-container");
  if (!container) {
    container = document.createElement("div");
    container.className = "toast-container";
    document.body.appendChild(container);
  }
  const icons = {
    success:
      '<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="#10b981" stroke-width="2"><path d="M20 6L9 17l-5-5"/></svg>',
    error:
      '<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="#ef4444" stroke-width="2"><circle cx="12" cy="12" r="10"/><path d="M15 9l-6 6M9 9l6 6"/></svg>',
    warning:
      '<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="#f59e0b" stroke-width="2"><path d="M10.29 3.86L1.82 18a2 2 0 001.71 3h16.94a2 2 0 001.71-3L13.71 3.86a2 2 0 00-3.42 0zM12 9v4M12 17h.01"/></svg>',
  };
  const toast = document.createElement("div");
  toast.className = "toast";
  toast.innerHTML = (icons[type] || icons.success) + `<span>${message}</span>`;
  container.appendChild(toast);
  setTimeout(() => {
    toast.style.opacity = "0";
    toast.style.transform = "translateX(100%)";
    setTimeout(() => toast.remove(), 300);
  }, 3500);
}

// --- Modal ---
function openModal(id) {
  const m = document.getElementById(id);
  if (m) m.classList.add("active");
}
function closeModal(id) {
  const m = document.getElementById(id);
  if (m) m.classList.remove("active");
}

// --- Toggle ---
function initToggles() {
  document.querySelectorAll(".toggle").forEach((t) => {
    // If an element has an inline `onclick`, skip adding an automatic
    // toggle handler to avoid double-inverting the state (click ->
    // inline onclick toggles -> this handler toggles again).
    if (t.getAttribute('onclick')) return;

    // For toggles without inline handlers, toggle the class and
    // persist the setting if a `data-setting` attribute is provided.
    t.addEventListener("click", function () {
      const newState = t.classList.toggle("active");
      const setting = t.dataset.setting;
      if (setting) {
        Settings.set(setting, newState);
      }
    });
  });
}

// --- User Settings Manager ---
const Settings = {
  defaults: {
    theme: "dark",
    sidebarCollapsed: false,
    currency: "USD",
    currencySymbol: "$",
    dateFormat: "YYYY-MM-DD",
    numberFormat: "1,000.00",
    compactMode: false,
    animations: true,
    budgetAlerts: true,
    weeklyReport: true,
    recurringReminders: false,
    autoBackup: true,
  },
  _data: null,

  load() {
    if (!this._data) {
      if (typeof Auth !== "undefined" && Auth.getUser()) {
        const user = Auth.getUser();
        if (user && user.settings) {
          this._data = { ...this.defaults, ...user.settings };
        }
      }
      if (!this._data) {
        this._data = { ...this.defaults };
      }
    }
    this.apply();
    return this._data;
  },

  loadFromUser(data) {
    this._data = { ...this.defaults, ...data };
    this.apply();
    initTheme();
    applySidebarState();
    if (typeof updateChartsTheme === "function") updateChartsTheme();
  },

  get(key) {
    if (!this._data) this.load();
    return this._data[key];
  },

  async set(key, value) {
    if (!this._data) this.load();
    this._data[key] = value;
    this.apply();

    if (key === "theme") {
      updateThemeIcon();
      if (typeof updateChartsTheme === "function") updateChartsTheme();
    } else if (key === "currencySymbol" || key === "currency") {
      if (typeof updateChartsTheme === "function") updateChartsTheme();
    } else if (key === "sidebarCollapsed") {
      const sidebar = document.getElementById("sidebar");
      if (sidebar) {
        if (value) sidebar.classList.add("collapsed");
        else sidebar.classList.remove("collapsed");
        window.dispatchEvent(new Event("resize"));
        setTimeout(() => window.dispatchEvent(new Event("resize")), 260);
      }
    }

    // Persist to DB
    if (typeof Auth !== "undefined" && Auth.isLoggedIn()) {
      try {
        const payload = {};
        payload[key] = value;
        await Auth.apiFetch("/api/v1/settings", {
          method: "PUT",
          body: JSON.stringify(payload),
        });
      } catch (e) {
        console.error("Failed to save settings to DB:", e);
      }
    }
  },

  getAll() {
    if (!this._data) this.load();
    return { ...this._data };
  },

  apply() {
    if (!this._data) return;
    if (this._data.compactMode) document.body.classList.add("compact-mode");
    else document.body.classList.remove("compact-mode");
    if (!this._data.animations) document.body.classList.add("no-animations");
    else document.body.classList.remove("no-animations");
    const sidebarSign = document.getElementById("sidebarCurrencySign");
    if (sidebarSign) {
      sidebarSign.textContent = this._data.currencySymbol || "$";
    }
  },

  formatCurrency(n) {
    if (!this._data) this.load();
    const num = Number(n);
    const sym = this._data.currencySymbol || "$";
    const fmt = this._data.numberFormat || "1,000.00";
    if (fmt === "1.000,00")
      return sym + num.toLocaleString("de-DE", { minimumFractionDigits: 0 });
    if (fmt === "1 000.00")
      return sym + num.toLocaleString("fr-FR", { minimumFractionDigits: 0 });
    return sym + num.toLocaleString("en-US", { minimumFractionDigits: 0 });
  },

  formatDate(dateStr) {
    if (!this._data) this.load();
    const d = new Date(dateStr);
    if (isNaN(d)) return dateStr;
    const yyyy = d.getFullYear(),
      mm = String(d.getMonth() + 1).padStart(2, "0"),
      dd = String(d.getDate()).padStart(2, "0");
    const fmt = this._data.dateFormat || "YYYY-MM-DD";
    if (fmt === "MM/DD/YYYY") return `${mm}/${dd}/${yyyy}`;
    if (fmt === "DD/MM/YYYY") return `${dd}/${mm}/${yyyy}`;
    return `${yyyy}-${mm}-${dd}`;
  },
};

// Legacy helper
function formatCurrency(n) {
  return Settings.formatCurrency(n);
}

// --- Sample Data Store (Replaced by real API data) ---
const AppData = {
  expenses: [],
  income: [],
  categories: [],
  kpis: {},
};

// --- In-Memory API Cache ---
// TTL-based cache that wraps Auth.apiFetch to avoid redundant network calls.
// Cache is per page-load (not persisted to localStorage).
const AppCache = {
  _store: {},

  // Default TTLs in milliseconds per URL prefix
  _ttls: {
    '/api/v1/auth/me':               15 * 60 * 1000, // 15 min (lifetime of access token)
    '/api/v1/categories':             5 * 60 * 1000, // 5 min
    '/api/v1/analytics':              2 * 60 * 1000, // 2 min
    '/api/v1/budget':                 2 * 60 * 1000, // 2 min
    '/api/v1/expenses':               60 * 1000,     // 60 s
    '/api/v1/recurring-expenses':     60 * 1000,     // 60 s
    '/api/v1/notifications/alerts':   90 * 1000,     // 90 s (matches poll interval)
    '/api/v1/settings':               5 * 60 * 1000, // 5 min
  },

  // Tags allow bulk-invalidating related cache entries.
  // Key → Set of tag strings
  _tags: {},

  _getTTL(url) {
    const path = url.split('?')[0];
    for (const prefix of Object.keys(this._ttls)) {
      if (path.startsWith(prefix)) return this._ttls[prefix];
    }
    return 30 * 1000; // default 30s for unknown endpoints
  },

  /**
   * Fetch with caching. If a valid (non-expired) cache entry exists, return it.
   * Otherwise call Auth.apiFetch, store the result, and return it.
   *
   * @param {string} url
   * @param {string[]} [tags]  - tag names to associate with this cache entry
   * @returns {Promise<any>}
   */
  async get(url, tags = []) {
    const now = Date.now();
    const entry = this._store[url];
    if (entry && now < entry.expiresAt) {
      return entry.data;
    }
    if (typeof Auth === 'undefined') return null;
    const data = await Auth.apiFetch(url);
    if (data !== null) {
      this._store[url] = { data, expiresAt: now + this._getTTL(url) };
      tags.forEach(tag => {
        if (!this._tags[tag]) this._tags[tag] = new Set();
        this._tags[tag].add(url);
      });
    }
    return data;
  },

  /**
   * Invalidate a specific URL's cache entry.
   * @param {string} url
   */
  invalidate(url) {
    delete this._store[url];
  },

  /**
   * Invalidate all cache entries matching a URL prefix.
   * @param {string} prefix
   */
  invalidatePrefix(prefix) {
    Object.keys(this._store).forEach(key => {
      if (key.startsWith(prefix)) delete this._store[key];
    });
  },

  /**
   * Invalidate all cache entries associated with a tag.
   * @param {string} tag
   */
  invalidateTag(tag) {
    const urls = this._tags[tag];
    if (urls) {
      urls.forEach(url => delete this._store[url]);
      delete this._tags[tag];
    }
  },

  /**
   * Clear all cached data (e.g., on logout or full refresh).
   */
  clear() {
    this._store = {};
    this._tags = {};
  },
};

// --- API Service Wrapper ---
const API = {
  async getDashboardData({ startDate, endDate } = {}) {
    if (typeof Auth === 'undefined') return false;

    let queryParams = '';
    if (startDate && endDate) {
      queryParams = `?startDate=${encodeURIComponent(startDate)}&endDate=${encodeURIComponent(endDate)}`;
    }

    let m = new Date().getMonth() + 1;
    let y = new Date().getFullYear();
    if (startDate) {
      const parsed = new Date(startDate);
      if (!isNaN(parsed)) {
        m = parsed.getMonth() + 1;
        y = parsed.getFullYear();
      }
    }

    // Fetch multiple endpoints simultaneously — analytics/kpis are date-range-specific so no cache hit
    // for different ranges; categories and budget are cached independently.
    const [kpisRes, expensesRes, categoriesRes, budgetRes, budgetDetailRes] = await Promise.all([
      AppCache.get(`/api/v1/analytics/kpis${queryParams}`, ['analytics']),
      AppCache.get(`/api/v1/expenses/?limit=10${startDate ? `&startDate=${startDate}&endDate=${endDate}` : ''}`, ['expenses']),
      AppCache.get(`/api/v1/analytics/categories${queryParams}`, ['analytics']),
      AppCache.get('/api/v1/budget/warnings', ['budget']),
      AppCache.get(`/api/v1/budget?month=${m}&year=${y}`, ['budget']).catch(() => null),
    ]);

    if (kpisRes && kpisRes.success) {
      AppData.kpis = kpisRes.data;
    }
    if (expensesRes && expensesRes.success) {
      AppData.expenses = expensesRes.data.results || expensesRes.data;
    }
    if (categoriesRes && categoriesRes.success) {
      AppData.categories = categoriesRes.data;
    }
    if (budgetRes && budgetRes.success) {
      AppData.budget = budgetRes.data;
    }
    if (budgetDetailRes && budgetDetailRes.success) {
      AppData.budgetDetail = budgetDetailRes.data;
    } else {
      AppData.budgetDetail = null;
    }

    return true;
  },

  async getChartData() {
    if (typeof Auth === 'undefined') return null;
    // Chart data changes slowly — cache for 2 min to avoid re-fetching on filter tab clicks
    const [monthlyBar, weeklyLine, incExp] = await Promise.all([
      AppCache.get('/api/v1/analytics/charts/monthly-bar', ['analytics']),
      AppCache.get('/api/v1/analytics/charts/weekly-line', ['analytics']),
      AppCache.get('/api/v1/analytics/charts/budget-expense', ['analytics']),
    ]);
    return {
      monthlyBar: monthlyBar?.data || [],
      weeklyLine: weeklyLine?.data || [],
      incExp: incExp?.data || [],
    };
  },
};

// --- Init ---
document.addEventListener("DOMContentLoaded", () => {
  Settings.load();
  initTheme();
  initSidebar();
  initToggles();

  // Initialize JWT auth on protected pages
  if (typeof Auth !== "undefined") {
    Auth.init();
  }
});

// Debounce helper
function debounce(fn, wait) {
  let t = null;
  return function (...args) {
    if (t) clearTimeout(t);
    t = setTimeout(() => fn.apply(this, args), wait);
  };
}

// Add BroadcastChannel for global sync across tabs/pages
if (typeof window !== 'undefined' && window.BroadcastChannel) {
  const financeSyncChannel = new BroadcastChannel('finance_sync');

  financeSyncChannel.onmessage = (event) => {
    if (event.data && event.data.type === 'REFRESH') {
      window.dispatchEvent(new CustomEvent('ai:finance:changed', { detail: event.data.detail }));
    }
  };

  window.addEventListener('ai:finance:changed', (e) => {
    if (e.detail && !e.detail.internal) {
      financeSyncChannel.postMessage({ type: 'REFRESH', detail: { ...e.detail, internal: true } });
    }
  });
}

