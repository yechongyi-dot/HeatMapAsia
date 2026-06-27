import { createStore, useStore } from './store.js';
import { api } from './api.js';
import { toast } from './toast.js';

const store = createStore({ items: [], open: false, format: 'best', running: false, cancelling: false });
let onCompleteCb = null;
let nextId = 0;             // globally-unique row id so stacked batches don't collide
const jobs = new Map();     // job_id -> { es, idMap }   idMap: batchIndex -> rowId

export function useDownloads() { return useStore(store); }
export function setDrawerOpen(open) { store.set({ open }); }
export function toggleDrawer() { store.set((s) => ({ open: !s.open })); }

export function clearDownloads() {
  // Detach + cancel any still-running batches, then wipe the queue.
  for (const [jobId, j] of jobs) {
    try { j.es.close(); } catch { /* ignore */ }
    api.post(`/api/download/cancel/${jobId}`).catch(() => {});
  }
  jobs.clear();
  store.set({ items: [], open: false, running: false, cancelling: false });
}

function patchRow(rowId, fields) {
  store.set((s) => ({ items: s.items.map((it) => (it.i === rowId ? { ...it, ...fields } : it)) }));
}

// Summarise + clean up, but only once ALL batches have finished.
function finishIfIdle() {
  if (jobs.size > 0) return;
  const list = store.get().items;
  const ok = list.filter((x) => x.status === 'done').length;
  const fail = list.filter((x) => x.status === 'fail').length;
  const cancelled = list.filter((x) => x.status === 'cancel').length;
  store.set({ running: false, cancelling: false });
  if (cancelled) {
    toast(`已取消：${ok} 个完成，${cancelled} 个取消${fail ? '，' + fail + ' 个失败' : ''}`, 'err');
  } else {
    toast(`下载完成：${ok} 个${fail ? '，' + fail + ' 个失败' : ''}`, fail ? 'err' : 'ok');
    // No failures → auto-dismiss the queue after a moment (unless a new batch
    // was added in the meantime, which changes the items reference).
    if (!fail) setTimeout(() => { if (store.get().items === list && jobs.size === 0) clearDownloads(); }, 5000);
  }
  if (onCompleteCb) onCompleteCb({ ok, fail, cancelled });
}

function run(batchItems, format, idMap) {
  return api.post('/api/download/batch/start', { items: batchItems, format }).then(({ job_id }) => {
    const es = new EventSource(`/api/download/progress/${job_id}`);
    jobs.set(job_id, { es, idMap });
    es.onmessage = (e) => {
      let d; try { d = JSON.parse(e.data); } catch { return; }
      const rowId = idMap[d.index];
      if (d.type === 'start') patchRow(rowId, { status: 'act' });
      else if (d.type === 'progress') patchRow(rowId, { pct: d.pct, speed: d.speed, eta: d.eta });
      else if (d.type === 'done') {
        const status = d.ok ? 'done' : d.cancelled ? 'cancel' : 'fail';
        patchRow(rowId, { status, pct: d.ok ? 100 : 0, error: d.error || '' });
      } else if (d.type === 'complete') {
        es.close();
        jobs.delete(job_id);
        finishIfIdle();
      }
    };
    es.onerror = () => {
      es.close();
      jobs.delete(job_id);
      // Connection dropped — mark this batch's still-pending rows as failed.
      for (const rowId of Object.values(idMap)) {
        store.set((s) => ({ items: s.items.map((it) =>
          (it.i === rowId && (it.status === 'wait' || it.status === 'act'))
            ? { ...it, status: 'fail', error: '连接中断' } : it) }));
      }
      finishIfIdle();
    };
  }).catch(() => {
    for (const rowId of Object.values(idMap)) patchRow(rowId, { status: 'fail', error: '启动失败' });
    toast('下载启动失败', 'err');
    finishIfIdle();
  });
}

// items: [{video_id, platform, title, thumbnail_url}]
// APPENDED to the queue — selecting a new batch while one is still running no
// longer replaces the old one; the batches download concurrently.
export function startDownload(newItems, format, onComplete) {
  onCompleteCb = onComplete || null;
  const idMap = {};
  const rows = newItems.map((it, batchIdx) => {
    const id = nextId++;
    idMap[batchIdx] = id;
    return { i: id, title: it.title, status: 'wait', pct: 0, speed: '', eta: '', src: it };
  });
  store.set((s) => ({
    open: true,
    format,
    running: true,
    cancelling: false,
    items: [...s.items, ...rows],
  }));
  run(newItems, format, idMap);
}

// Cancel every running batch; SSE drives the row updates.
export function cancelDownload() {
  if (store.get().cancelling || jobs.size === 0) return;
  store.set({ cancelling: true });
  for (const jobId of jobs.keys()) {
    api.post(`/api/download/cancel/${jobId}`).catch(() => {});
  }
}

// Re-run the failed rows as a fresh batch (dropping the old failed rows first).
export function retryFailed() {
  const failed = store.get().items.filter((x) => x.status === 'fail');
  if (!failed.length) return;
  const failedIds = new Set(failed.map((x) => x.i));
  store.set((s) => ({ items: s.items.filter((it) => !failedIds.has(it.i)) }));
  startDownload(failed.map((x) => x.src), store.get().format, onCompleteCb);
}
