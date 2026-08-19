/* Shared client runtime: API helper, formatters, toasts, Alpine components. */

/* ------------------------------------------------------------------ toasts */
function toast(title, body = '', type = 'info') {
  window.dispatchEvent(new CustomEvent('toast', { detail: { title, body, type } }));
}
const toastSuccess = (t, b) => toast(t, b, 'success');
const toastError = (t, b) => toast(t, b, 'error');

// A <template x-if> nested inside an <svg> has no .content — SVG is foreign
// content to the HTML parser — so the icon is picked by binding :d instead.
const TOAST_PATHS = {
  success: 'M20 6L9 17l-5-5',
  error: 'M12 8v5m0 3h.01M10.3 3.9L2.4 18a2 2 0 001.7 3h15.8a2 2 0 001.7-3L13.7 3.9a2 2 0 00-3.4 0z',
  info: 'M12 16v-4m0-4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z',
};

function toastHost() {
  return {
    items: [],
    seq: 0,
    iconPath(type) {
      return TOAST_PATHS[type] || TOAST_PATHS.info;
    },
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
  // Whole days that a date is already in the past, 0 if it is today or later.
  // Drives the "overdue" badges: an overdue departure or an arrival that never
  // showed up used to be indistinguishable from a normal one.
  daysOverdue(iso) {
    if (!iso) return 0;
    return Math.max(0, fmt.nightsBetween(iso, window.APP.today));
  },
  overdueLabel(iso) {
    const days = fmt.daysOverdue(iso);
    if (!days) return '';
    return days === 1 ? '1 day overdue' : `${days} days overdue`;
  },
};

/* ------------------------------------------------------------ status badges
 * Tinted fill + a hairline inset ring, which keeps the pills legible on both
 * white cards and dark surfaces. Pair with the .badge component class.
 */
const TONES = {
  amber:  'bg-amber-50 text-amber-700 ring-amber-200 dark:bg-amber-500/10 dark:text-amber-300 dark:ring-amber-500/30',
  blue:   'bg-blue-50 text-blue-700 ring-blue-200 dark:bg-blue-500/10 dark:text-blue-300 dark:ring-blue-500/30',
  green:  'bg-accent-50 text-accent-700 ring-accent-200 dark:bg-accent-500/10 dark:text-accent-300 dark:ring-accent-500/30',
  slate:  'bg-slate-100 text-slate-600 ring-slate-200 dark:bg-slate-700/50 dark:text-slate-300 dark:ring-slate-600',
  red:    'bg-red-50 text-red-700 ring-red-200 dark:bg-red-500/10 dark:text-red-300 dark:ring-red-500/30',
  orange: 'bg-orange-50 text-orange-700 ring-orange-200 dark:bg-orange-500/10 dark:text-orange-300 dark:ring-orange-500/30',
  purple: 'bg-purple-50 text-purple-700 ring-purple-200 dark:bg-purple-500/10 dark:text-purple-300 dark:ring-purple-500/30',
  brand:  'bg-brand-50 text-brand-700 ring-brand-200 dark:bg-brand-500/10 dark:text-brand-200 dark:ring-brand-500/30',
};

const DOTS = {
  amber: 'bg-amber-500', blue: 'bg-blue-500', green: 'bg-accent-500', slate: 'bg-slate-400',
  red: 'bg-red-500', orange: 'bg-orange-500', purple: 'bg-purple-500', brand: 'bg-brand-500',
};

const STATUS_TONES = {
  // reservation
  pending: 'amber',
  confirmed: 'blue',
  checked_in: 'green',
  checked_out: 'slate',
  cancelled: 'red',
  no_show: 'orange',
  // room
  available: 'green',
  occupied: 'red',
  cleaning: 'amber',
  maintenance: 'slate',
  // payment
  paid: 'green',
  refunded: 'purple',
  failed: 'red',
};

const tone = (status) => STATUS_TONES[status] || 'slate';
const badgeClass = (status) => TONES[tone(status)];
const dotClass = (status) => DOTS[tone(status)];

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

/* ------------------------------------------------------------------ invoices
 * The PDF route is read-only: it renders an invoice that has been issued and
 * 404s otherwise, so that a GET (which a mailed link can trigger, cookie and
 * all) can never create a row or consume an invoice number. Issuing is this
 * explicit POST. The tab is opened first, inside the click, or the browser
 * treats the later window.open as a pop-up and blocks it.
 */
async function openInvoicePdf(reservationId) {
  const tab = window.open('', '_blank');
  try {
    await api(`/api/v1/invoices/reservation/${reservationId}`, { method: 'POST' });
    const url = `/api/v1/invoices/reservation/${reservationId}/pdf`;
    if (tab) tab.location = url;
    else window.location.href = url;
  } catch (err) {
    if (tab) tab.close();
    toastError('Could not open the invoice', err.message);
  }
}

/* --------------------------------------------------------- chart defaults */
function chartTheme() {
  const dark = document.documentElement.classList.contains('dark');

  // Charts inherit the page's typography and tooltip styling once, here, so
  // every canvas on every page reads as part of the same interface.
  if (window.Chart) {
    Chart.defaults.font.family = "'Inter', ui-sans-serif, system-ui, sans-serif";
    Chart.defaults.font.size = 11;
    Chart.defaults.color = dark ? '#94a3b8' : '#64748b';
    Chart.defaults.plugins.tooltip.backgroundColor = dark ? '#1e293b' : '#0f172a';
    Chart.defaults.plugins.tooltip.padding = 10;
    Chart.defaults.plugins.tooltip.cornerRadius = 10;
    Chart.defaults.plugins.tooltip.titleFont = { weight: '600', size: 11 };
    Chart.defaults.plugins.tooltip.boxPadding = 4;
    Chart.defaults.plugins.tooltip.borderColor = dark ? '#334155' : 'transparent';
    Chart.defaults.plugins.tooltip.borderWidth = dark ? 1 : 0;
  }

  return {
    grid: dark ? 'rgba(148,163,184,0.14)' : 'rgba(100,116,139,0.13)',
    text: dark ? '#94a3b8' : '#64748b',
    brand: dark ? '#818cf8' : '#4338ca',
    brandSoft: dark ? 'rgba(129,140,248,0.32)' : 'rgba(67,56,202,0.16)',
    accent: '#10b981',
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
window.dotClass = dotClass;
window.shell = shell;
window.confirmMixin = confirmMixin;
window.openInvoicePdf = openInvoicePdf;
window.chartTheme = chartTheme;
