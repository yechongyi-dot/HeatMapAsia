import { createStore, useStore } from './store.js';
import { api } from './api.js';
import { toast } from './toast.js';

const store = createStore({ items: [], open: false, format: 'best', running: false, cancelling: false });
let onCompleteCb = null;
let currentJobId = null;

export function useDownloads() { return useStore(store); }
export function setDrawerOpen(open) { store.set({ open }); }
export function toggleDrawer() { store.set((s) => ({ open: !s.open })); }
export function clearDownloads() { store.set({ items: [], open: false, running: false, cancelling: false }); }

function patch(index, fields) {
  store.set((s) => ({
    items: s.items.map((it) => (it.i === index ? { ...it, ...fields } : it)),
  }));
}

function run(items, format) {
  return api.post('/api/download/batch/start', { items, format }).then(({ job_id }) => {
    currentJobId = job_id;
    const es = new EventSource(`/api/download/progress/${job_id}`);
    es.onmessage = (e) => {
      let d; try { d = JSON.parse(e.data); } catch { return; }
      if (d.type === 'start') patch(d.index, { status: 'act' });
      else if (d.type === 'progress') patch(d.index, { pct: d.pct, speed: d.speed, eta: d.eta });
      else if (d.type === 'done') {
        const status = d.ok ? 'done' : d.cancelled ? 'cancel' : 'fail';
        patch(d.index, { status, pct: d.ok ? 100 : 0, error: d.error || '' });
      }
      else if (d.type === 'complete') {
        es.close();
        currentJobId = null;
        const list = store.get().items;
        const ok = list.filter((x) => x.status === 'done').length;
        const fail = list.filter((x) => x.status === 'fail').length;
        const cancelled = list.filter((x) => x.status === 'cancel').length;
        store.set({ running: false, cancelling: false });
        if (cancelled) {
          toast(`已取消：${ok} 个完成，${cancelled} 个取消${fail ? '，' + fail + ' 个失败' : ''}`, 'err');
        } else {
          toast(`下载完成：${ok} 个${fail ? '，' + fail + ' 个失败' : ''}`, fail ? 'err' : 'ok');
          // No failures → auto-dismiss the whole queue after a moment.
          if (!fail) setTimeout(() => { if (store.get().items === list) clearDownloads(); }, 5000);
        }
        if (onCompleteCb) onCompleteCb({ ok, fail, cancelled });
      }
    };
    es.onerror = () => { es.close(); currentJobId = null; store.set({ running: false }); toast('下载连接中断', 'err'); };
  }).catch(() => {
    toast('下载启动失败', 'err');
    store.set({ open: false, running: false });
  });
}

// items: [{video_id, platform, title, thumbnail_url}]
export function startDownload(items, format, onComplete) {
  onCompleteCb = onComplete || null;
  store.set({
    open: true,
    format,
    running: true,
    cancelling: false,
    items: items.map((it, i) => ({ i, title: it.title, status: 'wait', pct: 0, speed: '', eta: '', src: it })),
  });
  run(items, format);
}

// Ask the backend to stop the running batch; SSE drives the row updates.
export function cancelDownload() {
  if (!currentJobId || store.get().cancelling) return;
  store.set({ cancelling: true });
  api.post(`/api/download/cancel/${currentJobId}`).catch(() => {
    store.set({ cancelling: false });
    toast('取消失败', 'err');
  });
}

// Re-run only the failed rows as a fresh batch.
export function retryFailed() {
  const failed = store.get().items.filter((x) => x.status === 'fail');
  if (!failed.length) return;
  startDownload(failed.map((x) => x.src), store.get().format, onCompleteCb);
}
