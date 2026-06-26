import { html } from '/static/vendor/preact-standalone.module.js';
import { REGIONS } from '../regions.js';

const PHASE = { scraping: '采集', dedup: '去重', saving: '入库', done: '✓', failed: '✕' };
const SHORT = { youtube: 'YouTube', official: '官方', niconico: 'ニコ' };

function ScrapeChip({ scrape }) {
  const parts = Object.keys(scrape.platforms).map((p) => {
    const ev = scrape.platforms[p];
    const n = ev.unique != null ? `(${ev.unique})` : ev.raw != null ? `(${ev.raw})` : '';
    return `${SHORT[p] || p} ${PHASE[ev.phase] || ev.phase}${n}`;
  });
  return html`
    <div class="scrape-chip">
      <span class="dot"></span>
      采集中${parts.length ? html` <b>${parts.join(' · ')}</b>` : ''}
    </div>`;
}

const LOGO = html`
  <svg width="18" height="18" viewBox="0 0 18 18" fill="none">
    <rect x="1" y="11" width="3" height="6" rx="1" fill="currentColor" opacity=".5"/>
    <rect x="6" y="7" width="3" height="10" rx="1" fill="currentColor" opacity=".7"/>
    <rect x="11" y="2" width="3" height="15" rx="1" fill="currentColor"/>
    <polyline points="2.5,9 7.5,5.5 12.5,1" stroke="currentColor" stroke-width="1.4" stroke-linecap="round" fill="none"/>
  </svg>`;

const TABS = [['rank', '热度榜'], ['channel', '频道分析'], ['lib', '素材库']];

export function TopBar({ view, onView, onRefresh, scrape, region, onRegion, saveDir, onOpenDir, onPickDir, appVersion, onCheckUpdate }) {
  const dirName = (saveDir || '').split(/[\\/]/).filter(Boolean).pop() || saveDir || '—';
  return html`
    <header class="topbar">
      <div class="logo">${LOGO} HeatMap<span class="logo-asia">Asia</span></div>
      <div class="region-seg" title="切换市场">
        ${REGIONS.map((r) => html`
          <button key=${r.id} class=${'region-btn' + (region === r.id ? ' on' : '')}
                  onClick=${() => onRegion(r.id)}><span class="rflag">${r.flag}</span>${r.name}</button>`)}
      </div>
      <div class="nav-pills">
        ${TABS.map(([id, label]) => html`
          <button key=${id} class=${'nav-pill' + (view === id ? ' on' : '')}
                  onClick=${() => onView(id)}>${label}</button>`)}
      </div>
      <div class="topbar-end">
        ${scrape.running ? html`<${ScrapeChip} scrape=${scrape} />` : null}
        ${appVersion ? html`<button class="ver-chip" title="点击检查更新" onClick=${onCheckUpdate}>v${appVersion}</button>` : null}
        <button class=${'tb-btn' + (scrape.running ? ' refreshing' : '')} title="刷新数据"
                onClick=${onRefresh}><span>⟳</span></button>
        <div class="path-chip">
          <div class="chip-main" title="打开文件夹" onClick=${onOpenDir}>
            <span>📂</span><span class="chip-name">${dirName}</span>
          </div>
          <button class="chip-edit" title="更改保存路径" onClick=${onPickDir}>✎</button>
        </div>
      </div>
    </header>`;
}
