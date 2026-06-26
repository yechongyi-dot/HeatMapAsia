// ─── Formatting + small helpers ───────────────────────

export function fmtN(n) {
  n = Number(n) || 0;
  if (n >= 1e8) return (n / 1e8).toFixed(1) + '亿';
  if (n >= 1e4) return (n / 1e4).toFixed(1) + '万';
  if (n >= 1e3) return (n / 1e3).toFixed(1) + 'K';
  return String(n);
}

export function fmtDur(s) {
  s = Number(s) || 0;
  if (!s) return '';
  const h = Math.floor(s / 3600);
  const m = Math.floor((s % 3600) / 60);
  const sec = s % 60;
  if (h) return `${h}:${String(m).padStart(2, '0')}:${String(sec).padStart(2, '0')}`;
  return `${m}:${String(sec).padStart(2, '0')}`;
}

export function fmtDate(ts) {
  return new Date(ts * 1000).toLocaleDateString('zh-CN', { month: 'short', day: 'numeric' });
}

export function fmtDateFull(ts) {
  return new Date(ts * 1000).toLocaleDateString('zh-CN');
}

// Conditional class names: cls('a', cond && 'b', {c: cond2})
export function cls(...parts) {
  const out = [];
  for (const p of parts) {
    if (!p) continue;
    if (typeof p === 'string') out.push(p);
    else if (typeof p === 'object') {
      for (const k in p) if (p[k]) out.push(k);
    }
  }
  return out.join(' ');
}

export function debounce(fn, ms) {
  let t;
  return (...args) => { clearTimeout(t); t = setTimeout(() => fn(...args), ms); };
}

// Deterministic avatar color from a string
const AVATAR_COLORS = [
  '#3d7ef8', '#0fb47a', '#f0b90b', '#f04060', '#9b59f8',
  '#e8762c', '#2ec5d3', '#d94f9e', '#5b8def', '#39b54a',
];
export function avatarColor(s) {
  s = String(s || '');
  let h = 0;
  for (let i = 0; i < s.length; i++) h = (h * 31 + s.charCodeAt(i)) >>> 0;
  return AVATAR_COLORS[h % AVATAR_COLORS.length];
}

export function initial(s) {
  s = String(s || '').trim();
  return s ? s[0].toUpperCase() : '?';
}

// Open an external URL — uses the pywebview bridge (real browser) when running
// as a desktop app, falling back to window.open in a normal browser.
export function openExternal(url) {
  if (!url) return;
  const api = window.pywebview && window.pywebview.api;
  if (api && api.open_url) { api.open_url(url); return; }
  window.open(url, '_blank', 'noopener');
}

// Bucket a duration (seconds) into short / mid / long
export function durBucket(sec) {
  sec = Number(sec) || 0;
  if (sec > 0 && sec < 240) return 'short';   // < 4 min
  if (sec <= 1200) return 'mid';              // 4–20 min
  return 'long';                              // > 20 min
}
