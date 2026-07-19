// ===== JWT AUTHENTICATION MODULE =====
// Handles JWT auth via HTTP-only cookies (set by backend)

const Auth = {
  user: null,
  _initPromise: null, // ensures only one /api/v1/auth/me call per page load

  // ── Login ──
  async login(identifier, password) {
    try {
      const res = await fetch("/api/v1/auth/login", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        credentials: "same-origin",
        body: JSON.stringify({ identifier, password }),
      });
      const data = await res.json();
      if (data.success) {
        this.user = data.data.user;
        return { success: true, user: this.user, message: data.message };
      }
      return {
        success: false,
        message: data.message || "Login failed",
        errors: data.errors,
      };
    } catch (err) {
      return { success: false, message: "Network error. Please try again." };
    }
  },

  // ── Register ──
  async register(username, email, password, confirmPassword) {
    try {
      const res = await fetch("/api/v1/auth/register", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        credentials: "same-origin",
        body: JSON.stringify({ username, email, password, confirmPassword }),
      });
      const data = await res.json();
      if (data.success) {
        this.user = data.data.user;
        return { success: true, user: this.user, message: data.message };
      }
      return {
        success: false,
        message: data.message || "Registration failed",
        errors: data.errors,
      };
    } catch (err) {
      return { success: false, message: "Network error. Please try again." };
    }
  },

  // ── Logout ──
  async logout() {
    try {
      await fetch("/api/v1/auth/logout", {
        method: "POST",
        credentials: "same-origin",
      });
    } catch (e) {
      // Ignore — we clear local state regardless
    }
    this.user = null;
    this._initPromise = null;
    if (typeof AppCache !== 'undefined') AppCache.clear();
    window.location.href = "/login/";
  },


  // ── Refresh tokens ──
  async refresh() {
    try {
      const res = await fetch("/api/v1/auth/refresh", {
        method: "POST",
        credentials: "same-origin",
      });
      if (!res.ok) {
        // Refresh failed — session expired
        this.user = null;
        return false;
      }
      return true;
    } catch (e) {
      return false;
    }
  },

  // ── Get current user from API ──
  async fetchUser() {
    try {
      // Use apiFetch so it automatically handles 401 and refresh token logic
      const data = await this.apiFetch("/api/v1/auth/me");
      if (data && data.success) {
        this.user = data.data;
        return this.user;
      }
      return null;
    } catch (e) {
      return null;
    }
  },

  // ── Get user from memory ──
  getUser() {
    return this.user;
  },

  // ── User display helpers ──
  getUserInitials() {
    const user = this.getUser();
    if (!user) return "U";
    if (user.firstName && user.lastName) {
      return (user.firstName[0] + user.lastName[0]).toUpperCase();
    }
    return user.username ? user.username[0].toUpperCase() : "U";
  },

  getUserDisplayName() {
    const user = this.getUser();
    if (!user) return "User";
    if (user.firstName) return user.firstName;
    return user.username || "User";
  },

  isLoggedIn() {
    return !!this.getUser();
  },

  // ── Change password ──
  async changePassword(currentPassword, newPassword, confirmPassword) {
    try {
      const res = await fetch("/api/v1/auth/change-password", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        credentials: "same-origin",
        body: JSON.stringify({ currentPassword, newPassword, confirmPassword }),
      });
      const data = await res.json();
      return {
        success: data.success,
        message: data.message,
        errors: data.errors,
      };
    } catch (err) {
      return { success: false, message: "Network error. Please try again." };
    }
  },

  // ── Auto-refresh (every 12 min for 15-min access tokens) ──
  startAutoRefresh() {
    this._refreshInterval = setInterval(() => this.refresh(), 12 * 60 * 1000);
  },

  stopAutoRefresh() {
    if (this._refreshInterval) clearInterval(this._refreshInterval);
  },

  // ── Initialize on protected pages ──
  async init() {
    // If user is already loaded, skip the network call entirely.
    if (this.user) return this.user;
    // If a fetch is already in-flight (e.g., multiple page init functions called concurrently),
    // return the same promise instead of firing a second /api/v1/auth/me request.
    if (this._initPromise) return this._initPromise;
    this._initPromise = this._doInit();
    return this._initPromise;
  },

  async _doInit() {
    // With HttpOnly cookies, user state is null on reload.
    // Must fetch from API to determine login status.
    const user = await this.fetchUser();
    if (user) {
      this.startAutoRefresh();
      if (user.settings && typeof Settings !== 'undefined') {
        Settings.loadFromUser(user.settings);
      }
      if (typeof updateProfileUI === 'function') {
        updateProfileUI();
      }
    } else {
      // Not logged in, but on a protected page?
      // window.location.href = '/login/';
    }
    return user;
  },


  // ── CSRF token reader ──
  getCSRFToken() {
    const name = "csrftoken";
    const cookies = document.cookie.split(";");
    for (let c of cookies) {
      c = c.trim();
      if (c.startsWith(name + "=")) {
        return decodeURIComponent(c.substring(name.length + 1));
      }
    }
    // Fallback: read from hidden input if present
    const el = document.querySelector("[name=csrfmiddlewaretoken]");
    return el ? el.value : "";
  },

  // ── General API Fetch helper ──
  async apiFetch(url, options = {}) {
    try {
      const csrfToken = this.getCSRFToken();
      const headers = {
        "Content-Type": "application/json",
        ...(csrfToken ? { "X-CSRFToken": csrfToken } : {}),
        ...(options.headers || {}),
      };
      const res = await fetch(url, {
        ...options,
        credentials: "same-origin",
        headers,
      });
      if (res.status === 401) {
        // If unauthorized, attempt to refresh and retry
        const refreshed = await this.refresh();
        if (refreshed) {
          const retryRes = await fetch(url, {
            ...options,
            credentials: "same-origin",
            headers,
          });
          return await retryRes.json();
        } else {
          this.logout();
          return null;
        }
      }
      return await res.json();
    } catch (e) {
      console.error("API Fetch error:", e);
      return null;
    }
  },
};
