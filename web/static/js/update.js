import { createStore, useStore } from './store.js';
import { api } from './api.js';
import { toast } from './toast.js';
import { confirm } from './confirm.js';

// `available` is set when a newer release exists, so the version chip can show a
// persistent "update available" prompt even after the launch dialog is closed.
const store = createStore({ active: false, phase: '', pct: 0, available: null });

export function useUpdate() { return useStore(store); }

function fmtMB(b) { return (b / 1e6).toFixed(1) + ' MB'; }

function promptAndApply(info) {
  return confirm(
    `发现新版本 v${info.latest}（当前 v${info.current}，约 ${fmtMB(info.size)}）。立即下载并更新？应用会自动重启。`,
    '立即更新',
  ).then((ok) => { if (ok) applyUpdate(info.download_url); });
}

// Check GitHub for a newer release. *manual* shows feedback even when up to date.
// When a newer release is found (and we're the packaged app) it records the
// update and proactively opens the confirm dialog.
export async function checkForUpdate(manual = false) {
  let info;
  try { info = await api.get('/api/update/check'); }
  catch { if (manual) toast('检查更新失败', 'err'); return; }

  if (!info.ok) { if (manual) toast('检查更新失败：' + (info.error || ''), 'err'); return; }
  if (!info.update_available) {
    store.set({ available: null });
    if (manual) toast('已是最新版本 v' + info.current, 'ok');
    return;
  }
  if (!info.frozen) {
    if (manual) toast('开发模式不支持在线更新（请 git pull）', 'err');
    return;
  }
  // Newer release available — remember it (drives the chip) and prompt now.
  store.set({ available: { latest: info.latest, current: info.current, size: info.size, download_url: info.download_url } });
  await promptAndApply(info);
}

// Version-chip click: if we already know an update is available, go straight to
// the update prompt; otherwise run a manual check.
export function onVersionChipClick() {
  const a = store.get().available;
  if (a) promptAndApply(a);
  else checkForUpdate(true);
}

function applyUpdate(download_url) {
  store.set({ active: true, phase: 'download', pct: 0 });
  api.post('/api/update/apply', { download_url }).then(({ job_id }) => {
    const es = new EventSource(`/api/update/progress/${job_id}`);
    es.onmessage = (e) => {
      let d; try { d = JSON.parse(e.data); } catch { return; }
      if (d.type === 'progress') store.set({ phase: d.phase, pct: d.pct });
      else if (d.type === 'done') { es.close(); store.set({ phase: 'done', pct: 100 }); }
      else if (d.type === 'error') {
        es.close();
        store.set({ active: false });
        toast('更新失败：' + (d.error || ''), 'err');
      }
    };
    // On 'done' the app exits to apply the update, so a dropped connection here is expected.
    es.onerror = () => es.close();
  }).catch(() => { store.set({ active: false }); toast('更新启动失败', 'err'); });
}
