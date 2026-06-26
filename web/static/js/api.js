// ─── Thin fetch wrapper ───────────────────────────────
// Each method resolves to parsed JSON; throws on non-2xx so callers can catch.

async function parse(r) {
  const text = await r.text();
  let data;
  try { data = text ? JSON.parse(text) : {}; } catch { data = { raw: text }; }
  if (!r.ok) {
    const msg = (data && (data.detail || data.error)) || `HTTP ${r.status}`;
    throw new Error(msg);
  }
  return data;
}

export const api = {
  get: (u) => fetch(u).then(parse),
  post: (u, b) => fetch(u, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(b || {}),
  }).then(parse),
  del: (u, b) => fetch(u, {
    method: 'DELETE',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(b || {}),
  }).then(parse),
};
