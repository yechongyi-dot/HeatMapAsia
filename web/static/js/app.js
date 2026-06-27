import { html, render } from '/static/vendor/preact-standalone.module.js';
import { useState, useEffect } from '/static/vendor/preact-standalone.module.js';
import { api } from './api.js';
import { usePersistedState } from './hooks.js';
import { toast, Toasts } from './toast.js';
import { ConfirmHost } from './confirm.js';
import { useScrape, startScrape, autoScrape } from './scrape.js';
import { setDrawerOpen } from './downloads.js';
import { checkForUpdate, onVersionChipClick } from './update.js';
import { TopBar } from './components/TopBar.js';
import { DownloadDrawer } from './components/DownloadDrawer.js';
import { UpdateModal } from './components/UpdateModal.js';
import { RankView } from './views/RankView.js';
import { ChannelView } from './views/ChannelView.js';
import { LibraryView } from './views/LibraryView.js';
import { regionHasPlat } from './regions.js';

function App() {
  const [view, setView] = usePersistedState('hm.view', 'rank');
  const [region, setRegionRaw] = usePersistedState('hm.region', 'jp');
  const [plat, setPlat] = usePersistedState('hm.plat', 'youtube');
  const [win, setWin] = usePersistedState('hm.win', '24h');
  const [channelFilter, setChannelFilter] = useState(null);
  const [saveDir, setSaveDir] = useState('');
  const [appVersion, setAppVersion] = useState('');
  const [dataVersion, setDataVersion] = useState(0);
  const scrape = useScrape();

  // Switch market. If the current platform tab doesn't exist in the new region
  // (e.g. niconico is Japan-only), fall back to YouTube. Scrape that region if
  // it has no data yet (handled by autoScrape attaching/kicking per region).
  const setRegion = (next) => {
    if (next === region) return;
    setRegionRaw(next);
    if (!regionHasPlat(next, plat)) setPlat('youtube');
    setChannelFilter(null);
    autoScrape(next, (res) => {
      setDataVersion((v) => v + 1);
      if (res && res.message) toast(res.message, res.ok === false ? 'err' : 'ok');
    });
  };

  // Initial load: save dir + attach/kick scrape for the current region
  useEffect(() => {
    api.get('/api/download/status').then((d) => setSaveDir(d.save_dir || '')).catch(() => {});
    api.get('/api/version').then((d) => setAppVersion(d.version || '')).catch(() => {});
    autoScrape(region, (res) => {
      setDataVersion((v) => v + 1);
      if (res && res.message) toast(res.message, res.ok === false ? 'err' : 'ok');
    });
    // Silent update check shortly after load (doesn't compete with the initial scrape).
    const t = setTimeout(() => checkForUpdate(false), 4000);
    return () => clearTimeout(t);
  }, []);

  // Global Escape closes the download drawer
  useEffect(() => {
    const h = (e) => { if (e.key === 'Escape') setDrawerOpen(false); };
    window.addEventListener('keydown', h);
    return () => window.removeEventListener('keydown', h);
  }, []);

  const onRefresh = () => startScrape(region, (res) => {
    setDataVersion((v) => v + 1);
    if (res && res.message) toast(res.message, res.ok === false ? 'err' : 'ok');
  });

  const pickChannel = (name) => { setChannelFilter(name); setView('rank'); };

  const openSaveDir = () => api.post('/api/download/open-dir').catch(() => {});
  const pickSaveDir = async () => {
    let next = null;
    if (window.pywebview && window.pywebview.api && window.pywebview.api.pick_folder) {
      try { next = await window.pywebview.api.pick_folder(); }
      catch { toast('无法打开文件夹选择器', 'err'); return; }
    } else {
      next = window.prompt('输入保存路径：', saveDir || '');
    }
    if (!next || !next.trim()) return;
    try {
      await api.post('/api/download/dir', { path: next.trim() });
      setSaveDir(next.trim());
      toast('保存路径已更新', 'ok');
    } catch { toast('路径设置失败', 'err'); }
  };

  let activeView;
  if (view === 'rank') {
    activeView = html`<${RankView} region=${region} plat=${plat} win=${win} onPlat=${setPlat} onWin=${setWin}
      dataVersion=${dataVersion} channelFilter=${channelFilter}
      onClearChannelFilter=${() => setChannelFilter(null)} />`;
  } else if (view === 'channel') {
    activeView = html`<${ChannelView} region=${region} plat=${plat} win=${win} onPlat=${setPlat} onWin=${setWin}
      dataVersion=${dataVersion} onPickChannel=${pickChannel} />`;
  } else {
    activeView = html`<${LibraryView} saveDir=${saveDir} />`;
  }

  return html`
    <div class="app">
      <${TopBar} view=${view} onView=${setView} onRefresh=${onRefresh} scrape=${scrape}
        region=${region} onRegion=${setRegion}
        saveDir=${saveDir} onOpenDir=${openSaveDir} onPickDir=${pickSaveDir}
        appVersion=${appVersion} onCheckUpdate=${() => onVersionChipClick()} />
      ${activeView}
      <${DownloadDrawer} />
      <${UpdateModal} />
      <${Toasts} />
      <${ConfirmHost} />
    </div>`;
}

render(html`<${App} />`, document.getElementById('root'));
