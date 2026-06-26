import { html } from '/static/vendor/preact-standalone.module.js';
import { useState } from '/static/vendor/preact-standalone.module.js';
import { fmtN, fmtDur, openExternal } from '../util.js';

export function VideoCard({ v, rank, picked, onPick, onDownload }) {
  const [imgErr, setImgErr] = useState(false);
  const rc = rank === 1 ? 'g' : rank === 2 ? 's' : rank === 3 ? 'b' : '';
  const dur = fmtDur(v.duration_seconds);
  const open = () => openExternal(v.url);

  return html`
    <div class=${'vc' + (picked ? ' picked' : '')}>
      <div class="vc-thumb" onClick=${open}>
        ${v.thumbnail_url && !imgErr
          ? html`<img src=${v.thumbnail_url} loading="lazy" onError=${() => setImgErr(true)} />`
          : html`<div class="noimg">▶</div>`}
        <div class=${'vc-rank ' + rc}>${rank}</div>
        ${dur ? html`<div class="vc-dur">${dur}</div>` : null}
        <div class=${'vc-pick' + (picked ? ' on' : '')}
             title="选择"
             onClick=${(e) => { e.stopPropagation(); onPick(v.video_id); }}>${picked ? '✓' : ''}</div>
        <div class="vc-overlay">
          <div class="ov-row"><span class="l">热度评分</span><span class="v hi">${Math.round(v.score || 0).toLocaleString()}</span></div>
          <div class="ov-row"><span class="l">播放量</span><span class="v">${(v.view_count || 0).toLocaleString()}</span></div>
          ${v.like_count ? html`<div class="ov-row"><span class="l">点赞</span><span class="v">${v.like_count.toLocaleString()}</span></div>` : null}
          ${v.comment_count ? html`<div class="ov-row"><span class="l">评论</span><span class="v">${v.comment_count.toLocaleString()}</span></div>` : null}
          ${dur ? html`<div class="ov-row"><span class="l">时长</span><span class="v">${dur}</span></div>` : null}
          <div class="ov-row"><span class="l">发布</span><span class="v">${v.published_text || ''}</span></div>
        </div>
      </div>
      <div class="vc-body" onClick=${open}>
        <div class="vc-title">${v.title || '(无标题)'}</div>
        <div class="vc-meta">
          <span>👁 ${fmtN(v.view_count)}</span>
          ${v.like_count ? html`<span>❤ ${fmtN(v.like_count)}</span>` : null}
          ${v.comment_count ? html`<span>💬 ${fmtN(v.comment_count)}</span>` : null}
        </div>
        <div class="vc-ch">${v.channel || ''}</div>
      </div>
      <button class="vc-dlbtn" title="下载" onClick=${(e) => { e.stopPropagation(); onDownload(v); }}>↓</button>
    </div>`;
}
