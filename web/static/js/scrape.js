import { createStore, useStore } from './store.js';
import { api } from './api.js';

// platforms: { youtube: {phase, raw, unique}, niconico: {...} }
const store = createStore({ running: false, platforms: {} });
let pollTimer = null;

export function useScrape() { return useStore(store); }

function pollStatus(onDone) {
  clearInterval(pollTimer);
  pollTimer = setInterval(async () => {
    try {
      const s = await api.get('/api/scrape/status');
      if (!s.running) {
        clearInterval(pollTimer);
        store.set({ running: false });
        onDone && onDone({ ok: true });
      }
    } catch {
      clearInterval(pollTimer);
      store.set({ running: false });
    }
  }, 3000);
}

function listen(jobId, onDone) {
  const es = new EventSource(`/api/scrape/progress/${jobId}`);
  es.onmessage = (e) => {
    let d;
    try { d = JSON.parse(e.data); } catch { return; }
    if (d.type === 'platform') {
      store.set((s) => ({ platforms: { ...s.platforms, [d.platform]: d } }));
    } else if (d.type === 'complete') {
      es.close();
      store.set({ running: false });
      onDone && onDone(d);
    }
  };
  es.onerror = () => { es.close(); pollStatus(onDone); };
}

export async function startScrape(region, onDone) {
  if (store.get().running) return;
  store.set({ running: true, platforms: {} });
  try {
    const { job_id } = await api.post(`/api/scrape/start?region=${region || 'jp'}`, {});
    listen(job_id, onDone);
  } catch (e) {
    // Already running (409) elsewhere — attach via coarse status polling
    pollStatus(onDone);
  }
}

// Switch to a region: attach to an in-flight scrape, else kick one off for it.
export async function autoScrape(region, onDone) {
  try {
    const s = await api.get('/api/scrape/status');
    if (s.running) { store.set({ running: true }); pollStatus(onDone); return; }
  } catch {}
  startScrape(region, onDone);
}
