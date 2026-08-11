/* Shared client runtime: API helper, formatters, toasts, Alpine components. */

/* ------------------------------------------------------------------ toasts */
function toast(title, body = '', type = 'info') {
  window.dispatchEvent(new CustomEvent('toast', { detail: { title, body, type } }));
}
const toastSuccess = (t, b) => toast(t, b, 'success');
const toastError = (t, b) => toast(t, b, 'error');

function toastHost() {
  return {
    items: [],
    seq: 0,
    push(detail) {
      const id = ++this.seq;
      this.items.push({ id, ...detail });
      setTimeout(() => this.dismiss(id), detail.type === 'error' ? 7000 : 4000);
    },
    dismiss(id) {
      this.items = this.items.filter((t) => t.id !== id);
    },
  };
}

/* --------------------------------------------------------------------- api */
async function api(path, { method = 'GET', body, params, raw = false } = {}) {
  const url = new URL(path, window.location.origin);
  if (params) {
    Object.entries(params).forEach(([k, v]) => {
      if (v !== null && v !== undefined && v !== '') url.searchParams.set(k, v);
    });
  }

  const res = await fetch(url, {
    method,
    headers: body ? { 'Content-Type': 'application/json' } : {},
    body: body ? JSON.stringify(body) : undefined,
    credentials: 'same-origin',
  });

  if (res.status === 401) {
    window.location.href = '/login?next=' + encodeURIComponent(window.location.pathname);
    throw new Error('Not authenticated');
  }
  if (raw) {
    if (!res.ok) throw new Error('Request failed');
    return res;
  }

  const isJson = (res.headers.get('content-type') || '').includes('application/json');
  const payload = isJson ? await res.json() : null;

  if (!res.ok) {
    const err = payload?.error || {};
    const error = new Error(err.message || `Request failed (${res.status})`);
    error.code = err.code;
    error.details = err.details || {};
    error.status = res.status;
    throw error;
  }
  return payload;
}

/* -------------------------------------------------------------- formatters */
const fmt = {
  money(value) {
    const n = Number(value || 0);
    return `${n.toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 })} ${window.APP.currency}`;
  },
  moneyShort(value) {
    const n = Number(value || 0);
    if (Math.abs(n) >= 1000) return `${(n / 1000).toFixed(1)}k ${window.APP.currency}`;
    return `${n.toFixed(0)} ${window.APP.currency}`;
  },
  date(iso) {
    if (!iso) return '—';
    return new Date(iso).toLocaleDateString('en-GB', { day: '2-digit', month: 'short', year: 'numeric' });
  },
  dateShort(iso) {
    if (!iso) return '—';
    return new Date(iso).toLocaleDateString('en-GB', { day: '2-digit', month: 'short' });
  },
  time(iso) {
    if (!iso) return '—';
    return new Date(iso).toLocaleTimeString('en-GB', { hour: '2-digit', minute: '2-digit' });
  },
  titleCase(text) {
    return String(text || '').replace(/_/g, ' ').replace(/\b\w/g, (c) => c.toUpperCase());
  },
  nightsBetween(a, b) {
    if (!a || !b) return 0;
    const ms = new Date(b) - new Date(a);
    return Math.max(0, Math.round(ms / 86400000));
  },
  addDays(iso, days) {
    const d = new Date(iso);
    d.setDate(d.getDate() + days);
    return d.toISOString().slice(0, 10);
  },
};

/* ------------------------------------------------------------ status badges */
const STATUS_STYLES = {
  // reservation
  pending: 'bg-amber-100 text-amber-800 dark:bg-amber-500/15 dark:text-amber-300',
  confirmed: 'bg-blue-100 text-blue-800 dark:bg-blue-500/15 dark:text-blue-300',
  checked_in: 'bg-accent-100 text-accent-700 dark:bg-accent-500/15 dark:text-accent-300',
  checked_out: 'bg-slate-200 text-slate-700 dark:bg-slate-700 dark:text-slate-300',
  cancelled: 'bg-red-100 text-red-700 dark:bg-red-500/15 dark:text-red-300',
  no_show: 'bg-orange-100 text-orange-800 dark:bg-orange-500/15 dark:text-orange-300',
  // room
  available: 'bg-accent-100 text-accent-700 dark:bg-accent-500/15 dark:text-accent-300',
  occupied: 'bg-red-100 text-red-700 dark:bg-red-500/15 dark:text-red-300',
  cleaning: 'bg-amber-100 text-amber-800 dark:bg-amber-500/15 dark:text-amber-300',
  maintenance: 'bg-slate-200 text-slate-600 dark:bg-slate-700 dark:text-slate-400',
  // payment
  paid: 'bg-accent-100 text-accent-700 dark:bg-accent-500/15 dark:text-accent-300',
  refunded: 'bg-purple-100 text-purple-700 dark:bg-purple-500/15 dark:text-purple-300',
  failed: 'bg-red-100 text-red-700 dark:bg-red-500/15 dark:text-red-300',
};
const badgeClass = (status) => STATUS_STYLES[status] || STATUS_STYLES.checked_out;

/* --------------------------------------------------------- app shell (nav) */
function shell() {
  return {
    collapsed: localStorage.getItem('sidebar') === 'collapsed',
    mobileOpen: false,
    dark: document.documentElement.classList.contains('dark'),

    init() {
      this.$watch('collapsed', (v) => localStorage.setItem('sidebar', v ? 'collapsed' : 'open'));
    },
    toggleTheme() {
      this.dark = !this.dark;
      document.documentElement.classList.toggle('dark', this.dark);
      localStorage.setItem('theme', this.dark ? 'dark' : 'light');
      window.dispatchEvent(new CustomEvent('theme-changed', { detail: { dark: this.dark } }));
    },
    async logout() {
      try {
        await api('/api/v1/auth/logout', { method: 'POST' });
      } finally {
        window.location.href = '/login';
      }
    },
  };
}

/* ------------------------------------------------- confirmation dialog mixin
 * Spread into any page component: `return { ...confirmMixin(), ... }`.
 * Pair it with the confirm_dialog() Jinja macro, which binds to this state.
 * askConfirm() resolves true/false, so callers can `await` a decision.
 */
function confirmMixin() {
  return {
    confirm: {
      open: false,
      title: '',
      message: '',
      confirmLabel: 'Confirm',
      danger: true,
      _resolve: null,
    },

    askConfirm(title, message, { confirmLabel = 'Confirm', danger = true } = {}) {
      Object.assign(this.confirm, { title, message, confirmLabel, danger, open: true });
      return new Promise((resolve) => (this.confirm._resolve = resolve));
    },

    settleConfirm(value) {
      this.confirm.open = false;
      const resolve = this.confirm._resolve;
      this.confirm._resolve = null;
      if (resolve) resolve(value);
    },
  };
}

/* --------------------------------------------------------- chart defaults */
function chartTheme() {
  const dark = document.documentElement.classList.contains('dark');
  return {
    grid: dark ? 'rgba(148,163,184,0.15)' : 'rgba(100,116,139,0.15)',
    text: dark ? '#94a3b8' : '#64748b',
    brand: '#1E3A8A',
    brandSoft: dark ? 'rgba(99,102,241,0.35)' : 'rgba(30,58,138,0.12)',
    accent: '#10B981',
    accentSoft: dark ? 'rgba(16,185,129,0.3)' : 'rgba(16,185,129,0.15)',
  };
}

window.toast = toast;
window.toastSuccess = toastSuccess;
window.toastError = toastError;
window.toastHost = toastHost;
window.api = api;
window.fmt = fmt;
window.badgeClass = badgeClass;
window.shell = shell;
window.confirmMixin = confirmMixin;
window.chartTheme = chartTheme;
