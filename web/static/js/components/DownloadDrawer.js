import { html } from '/static/vendor/preact-standalone.module.js';
import { useDownloads, toggleDrawer, retryFailed, clearDownloads, cancelDownload } from '../downloads.js';

const ICON = { wait: '⋯', act: '↓', done: '✓', fail: '✕', cancel: '⊘' };

function right(it) {
  if (it.status === 'act') return (it.speed ? it.speed + ' · ' : '') + it.pct + '%';
  if (it.status === 'done') return '完成';
  if (it.status === 'fail') return '失败';
  if (it.status === 'cancel') return '已取消';
  return '等待中';
}

export function DownloadDrawer() {
  const { items, open, running, cancelling } = useDownloads();
  if (!items.length) return null;
  const done = items.filter((x) => x.status === 'done').length;
  const fail = items.filter((x) => x.status === 'fail').length;

  return html`
    <div class=${'dl-drawer' + (open ? ' open' : '')}>
      <div class="dl-hdr" onClick=${toggleDrawer}>
        <span style="font-size:13px">↓</span>
        <span class="dl-hdr-title">下载队列</span>
        <span class="dl-hdr-sub">${done} / ${items.length} 完成</span>
        <div class="dl-hdr-end" onClick=${(e) => e.stopPropagation()}>
          ${running
            ? html`<button class="dl-close" disabled=${cancelling} onClick=${cancelDownload}>${cancelling ? '取消中…' : '取消'}</button>`
            : fail ? html`<button class="dl-close" onClick=${retryFailed}>重试失败 (${fail})</button>` : null}
          <button class="dl-close" onClick=${toggleDrawer}>${open ? '收起' : '展开'}</button>
          <button class="dl-close" title="清空队列" onClick=${clearDownloads}>✕</button>
        </div>
      </div>
      <div class="dl-body">
        ${items.map((it) => html`
          <div class="dl-item" key=${it.i}>
            <div class=${'dl-ic ' + it.status}>${ICON[it.status]}</div>
            <div class="dl-mid">
              <div class=${'dl-name ' + it.status}>${(it.title || '').substring(0, 60)}</div>
              ${it.status === 'fail' && it.error
                ? html`<div class="dl-err" title=${it.error}>${String(it.error).substring(0, 90)}</div>`
                : html`<div class="dl-bar-wrap">
                    <div class=${'dl-bar' + (it.status === 'done' ? ' done' : (it.status === 'fail' || it.status === 'cancel') ? ' fail' : '')}
                         style=${'width:' + it.pct + '%'}></div>
                  </div>`}
            </div>
            <div class="dl-right">${right(it)}</div>
          </div>`)}
      </div>
    </div>`;
}
